"""Complete a change consistently, then save only if its parent is still current."""

import copy
import json
import time
import uuid
from . import store
from .models import Conditions


def cost_delta(before, after):
    return [after[0] - before[1], after[1] - before[0]]


def change_delta(before, after):
    """바꾸기 전과 후의 차이. 화면은 total_before 와 바뀐 코스의 total 을 나란히 보여 준다
    (cost 는 범위끼리의 차이라 화면에 내지 않는다)."""
    return dict(
        minutes=after["minutes"] - before["minutes"],
        cost=cost_delta(before["total"], after["total"]),
        total_before=list(before["total"]),
    )


def save_change(plan, original, owner, recovery=None):
    """recovery: 지각 복구 기록(app/delay_recovery.py). 주면 그 기록을 붙이고, 지연을 반영해 짠 시간표를
    자동차 길찾기 재조회로 덮지 않는다(새 외부 호출 없음). 수단 바꾸기·장소 바꾸기·레저 교체(app/main.py)는 지연을 넣어 다시 계산한 뒤
    kept 표시를 붙인 같은 기록을 넘긴다(delay_check.kept_record). recovery 없이 부르는 변경(순서 바꾸기 — 지각을 반영한 코스는 견주지 않음)은
    바꾸기 전 코스의 지각 기록을 이어받지 않는다. 식사 추가·합의 코스는 이 함수를 거치지 않고 초안(experience.make_draft/apply_draft)에
    번호를 옮긴 기록(delay_check.moved_record)을 실어 저장한다."""
    from .condition_audit import audit_plan
    from .preferences import hard_blocks
    from .experience import verification_summary
    from .recommendation_summary import enrich
    from .pricing import price_plans
    from .planner import evaluate
    from .leg_modes import endpoints, festival_pair, uses_car

    updated = copy.deepcopy(plan)
    updated.pop("delay_recovery", None)
    if recovery:
        updated["delay_recovery"] = copy.deepcopy(recovery)
    conditions = Conditions.model_validate(updated["conditions"])
    moved = [p["id"] for p in updated["places"]] != [p["id"] for p in original["places"]]
    if moved and conditions.leg_modes:
        # 장소를 바꿔 끊긴 구간의 수단 예외는 남기지 않는다(그 구간은 이미 기본 수단으로 계산됐다).
        current = set(endpoints(updated)) | ({festival_pair(updated)} - {None})
        kept = [m for m in conditions.leg_modes if (m.from_, m.to) in current]
        conditions = conditions.model_copy(update={"leg_modes": kept})
        updated["conditions"]["leg_modes"] = [m.model_dump() for m in kept]
    # 자동차 실제 길찾기 재확인: 지각 복구 자체(recovery 에 kept 없음)는 새 외부 호출을 하지 않으므로 건너뛴다.
    # 지연을 이어 가는 장소 변경(kept='place')은 재확인하되, 같은 지연과 같은 종료 허용(delayed_conditions)을 넣어 다시 계산한다
    # — 넣지 않으면 재확인이 지연을 지운 시간표로 덮는다.
    kept = bool(recovery and recovery.get("kept"))
    if moved and conditions.mode == "real" and uses_car(conditions) and (not recovery or kept):
        # 후보를 만들 때 정한 중간 축제 자리를 먼저 둔다(planner.evaluate festival_hint): 자리가 옮겨지지 않고,
        # 쓰지 않을 구간(장소 i → i+1, 마지막 장소 → 행사장)의 실제 길찾기 조회가 생기지 않는다.
        from .delay_check import carried_delays, delayed_conditions
        from .leg_modes import middle_after

        check_conditions = delayed_conditions(original, conditions) if kept else conditions
        checked, error = evaluate(
            updated["places"],
            check_conditions,
            soft=bool(updated.get("best_effort")),
            verify_routes=True,
            festival_hint=middle_after(updated),
            delays=(carried_delays(original) or None) if kept else None,
        )
        if checked and check_conditions is not conditions:
            checked["conditions"]["end"] = conditions.end  # 계산에만 늦춘 종료 시각을 원래 값으로
        if checked:
            # 축제 방문 기록은 다시 계산한 코스를 따른다(실제 길찾기로 축제 자리가 빠지거나 바뀌면 옛 기록이 남지 않게).
            updated.pop("festival_visit", None)
            updated.update(checked)
            updated["route_verification"] = (
                "변경한 동선의 실제 경로를 다시 확인했어요. 조회 시점 기준입니다."
            )
        else:
            updated["route_verification"] = (
                "변경한 동선의 실제 경로 확인 실패 · 추정 동선입니다: " + str(error)
            )
    # 바꾸기 전 코스와 견줘 축제 방문이 달라졌으면 안내를 싣는다(실제 길찾기 재확인 뒤의 최종 모양 기준).
    from .festival_time import set_change_note

    set_change_note(updated, original)
    updated = price_plans([updated])[0]
    updated = audit_plan(updated)
    if hard_blocks(updated):
        raise ValueError("필수 조건을 충족하지 않아 변경하지 않았어요.")
    if original.get("recommendation_group_id"):
        updated["recommendation_group_id"] = original["recommendation_group_id"]
    updated["undo_locks"] = dict(original["conditions"].get("locked", {}))
    updated["verification"] = verification_summary(updated)
    enrich(updated)
    if moved or updated.get("delta"):
        updated["delta"] = change_delta(original, updated)
    updated.update(id=uuid.uuid4().hex, parent=original["id"])
    updated["aggregate_key"] = store.aggregate_key([p["id"] for p in updated["places"]])
    payload = store.plan_payload(updated)
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT payload FROM plans WHERE id=? AND owner=?", (original["id"], owner)
        ).fetchone()
        if not row:
            raise ValueError("원래 일정을 찾을 수 없어요. 현재 코스에서 다시 시도해 주세요.")
        current = json.loads(row["payload"])
        if current.get("lock_version", 0) != original.get("lock_version", 0):
            raise ValueError("처리 중 고정 장소가 바뀌었어요. 현재 코스에서 다시 시도해 주세요.")
        db.execute(
            "INSERT INTO plans(id,owner,parent,aggregate_key,payload,created) VALUES(?,?,?,?,?,?)",
            (
                updated["id"],
                owner,
                original["id"],
                updated["aggregate_key"],
                payload,
                time.time(),
            ),
        )
    return updated
