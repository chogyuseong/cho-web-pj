"""Recommendation use case shared by HTTP endpoints and background workers.

Stage order is intentional: normalize, research, verify, price, enforce required
conditions, diversify, explain, then check cancellation before persistence.
"""

import logging
import time
import uuid
from . import store
from .execution import recommendation_slot
from .models import Conditions
from .planner import recommend
from .plan_jobs import report
from .request_intent import normalize
from .feedback_preferences import personalizing, explanation
from .request_usage import measure


def generate(data: Conditions, owner: str):
    with (
        recommendation_slot(owner),
        personalizing(owner, data.use_feedback, data.mode) as profile,
        measure() as usage,
    ):
        started = time.perf_counter()
        try:
            data = normalize(data)
            if data.planning_session_id:
                from .planning_outcomes import session_for

                session_for(data.planning_session_id, owner)
            if data.use_feedback:
                from .experience import feedback_exclusions

                data = data.model_copy(
                    update={
                        "excluded_place_ids": list(
                            set(data.excluded_place_ids) | set(feedback_exclusions(owner))
                        )[:100]
                    }
                )
            from .routes import candidate_routes

            with candidate_routes():
                data, result = _research(data)
            if profile:
                result["personalization"] = explanation(profile)
                for plan in result["plans"]:
                    plan["personalization"] = result["personalization"]
            result = _finish(data, result, owner)
        except Exception:
            _record(owner, started, status="failed", external_usage=usage.snapshot())
            raise
        _record(
            owner,
            started,
            status="complete",
            plans=len(result["plans"]),
            best_effort_plans=sum(bool(p.get("best_effort")) for p in result["plans"]),
            evidence_fields=sum(
                p.get("verification", {}).get("coverage", {}).get("confirmed_fields", 0)
                for p in result["plans"]
            ),
            total_evidence_fields=sum(
                p.get("verification", {}).get("coverage", {}).get("total_fields", 0)
                for p in result["plans"]
            ),
            external_usage=usage.snapshot(),
        )
        return result


def _record(owner, started, **values):
    # Observability must never turn a successfully saved recommendation into an error.
    from .experience import event

    try:
        event(
            owner,
            "",
            "recommendation",
            dict(
                values,
                elapsed_ms=round((time.perf_counter() - started) * 1000),
                api_cost_status="not_measured",
            ),
        )
    except Exception:
        logging.getLogger(__name__).warning("recommendation_metric_write_failed")


def _research(data):
    report("장소 검색", "선택 지역의 후기와 실제 장소를 찾고 있어요")
    from .course_search import search_courses, priority

    evidence = search_courses(data) if data.mode == "real" else None
    if data.mode == "real":
        from .quality import configure

        data = configure(data, evidence["query"])
        from .intent_discovery import discover_requested_places

        evidence["intent_discovery"] = discover_requested_places(data)
    report("코스 구성", "취향·필수 조건·이동 동선을 비교하고 있어요")
    result = recommend(data, evidence)
    if data.mode == "real" and (
        not result["plans"] or any(p.get("search_adjustments") for p in result["plans"])
    ):
        # Retry live research without taste keywords before accepting a wider-area fallback.
        local = data.model_copy(
            update={
                "course_query": "",
                "request": "",
                "themes": [],
                "date_category": "",
                "date_subcategory": "",
                "setting": "any",
                "trust_mode": "balanced",
            }
        )
        broad = search_courses(local)
        discover_requested_places(local)
        if broad["status"] == "available" and (
            broad["query"] != evidence["query"] or not result["plans"]
        ):
            original_query = evidence["query"]
            broad["search_history"] = [
                *evidence.get("search_history", []),
                *broad.get("search_history", []),
            ]
            broad["requested_query"] = original_query
            broad["search_relaxed"] = broad["query"] != original_query
            broad["relaxation_note"] = (
                "위치는 유지하고 취향 검색어를 줄여 같은 지역의 일반 데이트 후기를 다시 검색했어요."
            )
            retried = recommend(data, broad)
            if retried["plans"]:
                result = retried
                evidence = broad
                for p in result["plans"]:
                    adjustments = p.setdefault(
                        "search_adjustments",
                        dict(
                            stage="same_location",
                            origin_unchanged=True,
                            original_radius_km=data.neighborhood_radius_km,
                            effective_radius_km=data.neighborhood_radius_km,
                            messages=[],
                            differences=[
                                dict(label=r["label"], message=r["message"])
                                for r in p.get("condition_checks", [])
                                if r["state"] == "unmet"
                            ],
                        ),
                    )
                    if original_query != broad["query"]:
                        adjustments["messages"].insert(
                            0, f"후기 검색어를 ‘{original_query}’ → ‘{broad['query']}’로 넓혔어요."
                        )
    if not result["plans"] and data.area_center:
        result.setdefault("suggestions", []).insert(
            0,
            f"{data.area_center.name} 반경 {data.neighborhood_radius_km:g}km 안에서 찾고 있어요. 동네 이동 범위나 방문 수를 조정해 주세요.",
        )
    if evidence:
        result["course_search"] = evidence
        for plan in result["plans"]:
            plan["course_search"] = evidence
            plan["blog_score"] = priority(plan, evidence)
            plan["recommendation_method"] = (
                "naver_blog_selected5" if plan["blog_score"] else "conditions_fallback"
            )
            for i, place in enumerate(plan["places"]):
                matched = evidence["matches"].get(place["id"])
                if matched:
                    plan["reasons"][i] = (
                        "네이버 코스 검색 "
                        + ", ".join(str(n) + "위 글" for n in matched["ranks"])
                        + "에 등장 · "
                        + plan["reasons"][i]
                    )
    return data, result


def _finish(data, result, owner):
    from .pricing import price_plans

    from .route_providers import configured

    if data.mode == "real" and (data.transport == "car" or configured(data.transport)):
        from .planner import evaluate
        from .condition_audit import audit_plan

        for i, plan in enumerate(result["plans"]):
            verified, error = evaluate(
                plan["places"], data, soft=bool(plan.get("best_effort")), verify_routes=True
            )
            if verified:
                plan.update(verified)
                result["plans"][i] = audit_plan(plan, data)
                plan["route_verification"] = {
                    "car": "네이버 자동차 길찾기 조회 반영 (조회 시점 기준)",
                    "walk": "TMAP 도보 경로 조회 반영 · 방문일 현장 상황 별도 확인",
                    "transit": "TMAP 대중교통 경로 조회 반영 · 방문일 시간표 별도 확인",
                }[data.transport]
            else:
                plan["route_verification"] = (
                    "실제 경로 확인 실패: " + str(error) + " · 추정 동선을 유지했어요."
                )
    report(
        "가격 확인",
        "코스 후보를 찾았어요. 가격과 필수 조건을 마지막으로 확인해요",
        preview=[[p["name"] for p in plan["places"]] for plan in result["plans"]],
    )
    result["plans"] = price_plans(result["plans"])
    from .preferences import filter_required, hard_blocks

    blocked = [p for p in result["plans"] if hard_blocks(p)]
    result["plans"] = filter_required(result["plans"])
    if blocked and not result["plans"]:
        result.update(
            status="required_unmet",
            reasons=["선택한 필수 조건을 충족하는 코스를 확인하지 못했어요."],
            suggestions=[
                "필수 조건 또는 입력 범위를 직접 조정해 주세요. 미확인 조건을 충족으로 처리하지 않습니다."
            ],
        )
    if data.mode == "real":
        from .option_diversity import select_options

        result["plans"] = select_options(result["plans"], data)
    if result["plans"] and all(p.get("best_effort") for p in result["plans"]):
        result["status"] = "best_effort"
    from .experience import verification_summary
    from .request_usage import current

    if current() and current().snapshot()["budget_exhausted"]:
        result["resource_notice"] = (
            "일부 자료 조회가 요청 한도에 도달해 확인 자료와 추정을 함께 표시했어요. 누락된 영업·가격·이동 정보는 방문 전 확인해 주세요."
        )

    for p in result["plans"]:
        if result.get("resource_notice"):
            p["resource_notice"] = result["resource_notice"]
        p["verification"] = verification_summary(p)
    from .recommendation_summary import enrich

    for p in result["plans"]:
        enrich(p)
    from .plan_jobs import check_current

    check_current()
    group_id = uuid.uuid4().hex
    for plan in result["plans"]:
        plan["recommendation_group_id"] = group_id
    result["plans"] = [store.save_plan(p, owner) for p in result["plans"]]
    return result
