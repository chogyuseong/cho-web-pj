"""Sports alternatives around an existing itinerary stop, without moving other stops."""

from .models import Conditions
from .request_intent import matches, intent
from .routes import distance
from concurrent.futures import ThreadPoolExecutor
from .request_usage import context_map

SPORTS = ("climbing", "bowling", "table_tennis", "badminton", "skating", "screen_golf")


def nearby_sports(plan, index):
    from .catalog import places

    anchor = plan["places"][index]
    used = {p["id"] for p in plan["places"]}
    c = Conditions.model_validate(plan["conditions"])
    rows = []
    seen = set()
    excluded = intent(c)["excluded"]
    for place in places(c.mode, c.visit_date):
        if place["id"] in used or place["id"] in seen or not any(matches(place, k) for k in SPORTS):
            continue
        if any(matches(place, k) for k in excluded):
            continue
        seen.add(place["id"])
        if any(w.casefold() in str(place).casefold() for w in c.avoid if w):
            continue
        meters = round(distance(anchor, place) * 1000)
        if meters <= 1500:
            rows.append((meters, place))
    return sorted(rows, key=lambda x: (x[0], x[1]["id"]))


def options(plan, index, locked, discover=False, diagnostics=None):
    if index < 0 or index >= len(plan["places"]):
        raise ValueError("올바른 코스 순서를 선택해 주세요.")
    c = Conditions.model_validate(plan["conditions"])
    if index in set(locked) | set(c.locked):
        raise ValueError("고정한 장소는 먼저 고정을 해제해 주세요.")
    if discover and c.mode == "real":
        from .intent_discovery import discover_requested_places

        anchor = plan["places"][index]
        import re

        district = re.search(r"[가-힣]+구(?:\s|$)", anchor.get("address") or "")
        # A museum's name is a poor search area when its address is missing.
        area = district[0].strip() if district else (c.area_center or c.origin).name

        def search_sport(key):
            from .request_intent import INTENTS

            # Revalidate nested Point and scope each search to this course stop.
            search = Conditions.model_validate(
                c.model_dump()
                | {
                    "origin": {"name": area, "lat": anchor["lat"], "lon": anchor["lon"]},
                    "area_center": None,
                    "neighborhood_radius_km": 1.5,
                    "request": INTENTS[key][1][0],
                    "course_query": "",
                }
            )
            return discover_requested_places(search)

        with ThreadPoolExecutor(max_workers=3) as executor:
            searched = context_map(executor, search_sport, SPORTS)
        if diagnostics is not None:
            diagnostics.update(
                search_status="permission_required"
                if any(r.get("permission_required") for r in searched)
                else "unavailable"
                if all(
                    r.get("status") == "not_available" or r.get("search_unavailable")
                    for r in searched
                )
                else "complete"
            )
    from .planner import evaluate
    from .condition_audit import audit_plan
    from .best_effort import annotate
    from .preferences import hard_blocks

    result = []
    nearby = nearby_sports(plan, index)
    if diagnostics is not None:
        diagnostics.update(nearby_count=len(nearby), rejected={})
    for meters, place in nearby[:24]:
        chosen = list(plan["places"])
        chosen[index] = place
        updated, error = evaluate(chosen, c, soft=bool(plan.get("best_effort")))
        if error:
            if diagnostics is not None:
                diagnostics["rejected"][error] = diagnostics["rejected"].get(error, 0) + 1
            continue
        from .pricing import apply_prices

        updated = apply_prices(updated, {})
        if plan.get("best_effort"):
            updated = annotate(updated, c)
        updated = audit_plan(updated, c)
        blocked = hard_blocks(updated)
        if blocked:
            if diagnostics is not None:
                for item in blocked:
                    reason = item["label"]
                    diagnostics["rejected"][reason] = diagnostics["rejected"].get(reason, 0) + 1
            continue
        from .plan_changes import cost_delta

        updated["delta"] = {
            "minutes": updated["minutes"] - plan["minutes"],
            "cost": cost_delta(plan["total"], updated["total"]),
        }
        updated["change_reason"] = (
            "선택한 레저로 이 장소만 교체하고 이동·시간·비용을 다시 계산했어요."
        )
        if plan.get("course_search"):
            updated["course_search"] = plan["course_search"]
        result.append({"distance_m": meters, "plan": updated})
    return result
