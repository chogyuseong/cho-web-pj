"""Complete a change consistently, then save only if its parent is still current."""

import copy
import json
import time
import uuid
from . import store


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


def save_change(plan, original, owner, recovery=None, kind=None):
    """kind: 이 코스를 만든 변경의 종류를 저장해 둘 때('transport' — 수단 바꾸기). 화면의 되돌리기 단추 문구가 새로고침·고정 토글 뒤에도
    같게 읽는다(static/plan-detail.js, 2026-11-24 점검 F6 — 예전에는 응답에만 있는 transport_change 를 봤다). 주지 않으면 표시를 지운다
    (다음 변경이 앞 변경의 표시를 물려받지 않게). 식사·합의·축제 넣기 초안은 experience.apply_draft 에서 지운다.
    recovery: 지각 복구 기록(app/delay_recovery.py). 주면 그 기록을 붙이고, 지연을 반영해 짠 시간표를
    자동차 길찾기 재조회로 덮지 않는다(새 외부 호출 없음). 수단 바꾸기·장소 바꾸기·레저 교체(app/main.py)는 지연을 넣어 다시 계산한 뒤
    kept 표시를 붙인 같은 기록을 넘긴다(delay_check.kept_record). recovery 없이 부르는 변경(순서 바꾸기 — 지각을 반영한 코스는 견주지 않음)은
    바꾸기 전 코스의 지각 기록을 이어받지 않는다. 식사 추가·합의 코스는 이 함수를 거치지 않고 초안(experience.make_draft/apply_draft)에
    번호를 옮긴 기록(delay_check.moved_record)을 실어 저장한다."""
    from .condition_audit import audit_plan
    from .preferences import hard_blocks
    from .experience import verification_summary
    from .recommendation_summary import enrich
    from .pricing import price_plans
    from .leg_modes import uses_car
    from .plan_rules import reevaluate, settle_leg_modes

    updated = copy.deepcopy(plan)
    updated.pop("delay_recovery", None)
    updated.pop("change_kind", None)
    if kind:
        updated["change_kind"] = kind
    if recovery:
        updated["delay_recovery"] = copy.deepcopy(recovery)
    moved = [p["id"] for p in updated["places"]] != [p["id"] for p in original["places"]]
    # 장소를 바꿔 끊긴 구간의 수단 예외는 남기지 않는다(그 구간은 이미 기본 수단으로 계산됐다).
    # 식사·합의 초안(experience.make_draft)도 같은 함수를 쓴다(2026-11-24 — 예전에는 이 경로만 정리했다).
    conditions = settle_leg_modes(updated)
    # 자동차 실제 길찾기 재확인: 지각 복구 자체(recovery 에 kept 없음)는 새 외부 호출을 하지 않으므로 건너뛴다.
    # 지연을 이어 가는 장소 변경(kept='place')은 재확인하되, 같은 지연과 같은 종료 허용(delayed_conditions)을 넣어 다시 계산한다
    # — 넣지 않으면 재확인이 지연을 지운 시간표로 덮는다.
    kept = bool(recovery and recovery.get("kept"))
    if moved and conditions.mode == "real" and uses_car(conditions) and (not recovery or kept):
        # 후보를 만들 때 정한 중간 축제 자리를 먼저 둔다(planner.evaluate festival_hint): 자리가 옮겨지지 않고,
        # 쓰지 않을 구간(장소 i → i+1, 마지막 장소 → 행사장)의 실제 길찾기 조회가 생기지 않는다.
        # 지연·종료 허용·되돌리기는 plan_rules.reevaluate 가 한다. 지연을 이어 가지 않는 변경(순서 바꾸기)은 넣지 않는다(delays={}).
        from .delay_check import carried_delays
        from .leg_modes import middle_after

        checked, error = reevaluate(
            original,
            updated["places"],
            conditions,
            delays=carried_delays(original) if kept else {},
            late_end=kept,
            soft=bool(updated.get("best_effort")),
            verify_routes=True,
            festival_hint=middle_after(updated),
        )
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
