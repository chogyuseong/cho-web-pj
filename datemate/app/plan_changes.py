"""Complete a change consistently, then save only if its parent is still current."""

import copy
import json
import uuid
from . import store
from .models import Conditions


def cost_delta(before, after):
    return [after[0] - before[1], after[1] - before[0]]


def save_change(plan, original, owner):
    from .condition_audit import audit_plan
    from .preferences import hard_blocks
    from .experience import verification_summary
    from .recommendation_summary import enrich
    from .pricing import price_plans
    from .planner import evaluate
    from .route_providers import configured

    updated = copy.deepcopy(plan)
    conditions = Conditions.model_validate(updated["conditions"])
    moved = [p["id"] for p in updated["places"]] != [p["id"] for p in original["places"]]
    if (
        moved
        and conditions.mode == "real"
        and (conditions.transport == "car" or configured(conditions.transport))
    ):
        checked, error = evaluate(
            updated["places"], conditions, soft=bool(updated.get("best_effort")), verify_routes=True
        )
        if checked:
            updated.update(checked)
            updated["route_verification"] = (
                "변경한 동선의 실제 경로를 다시 확인했어요. 조회 시점 기준입니다."
            )
        else:
            updated["route_verification"] = (
                "변경한 동선의 실제 경로 확인 실패 · 추정 동선입니다: " + str(error)
            )
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
        updated["delta"] = dict(
            minutes=updated["minutes"] - original["minutes"],
            cost=cost_delta(original["total"], updated["total"]),
        )
    updated.update(id=uuid.uuid4().hex, parent=original["id"])
    updated["aggregate_key"] = store.aggregate_key([p["id"] for p in updated["places"]])
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
            "INSERT INTO plans VALUES(?,?,?,?,?)",
            (
                updated["id"],
                owner,
                original["id"],
                updated["aggregate_key"],
                json.dumps(updated, ensure_ascii=False),
            ),
        )
    return updated
