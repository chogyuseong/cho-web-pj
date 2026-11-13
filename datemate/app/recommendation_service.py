"""Recommendation use case shared by HTTP endpoints and background workers.

Stage order is intentional: normalize, research, verify, price, enforce required
conditions, diversify, explain, then check cancellation before persistence.
"""

import json
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
from .perf_trace import current as current_trace, recording, span


def generate(data: Conditions, owner: str):
    with (
        recording() as trace,
        recommendation_slot(owner),
        personalizing(owner, data.use_feedback, data.mode) as profile,
        measure() as usage,
    ):
        started = time.perf_counter()
        try:
            # 구간별 수단은 만든 코스를 바꿀 때만 생긴다. 새 추천은 기본 수단 하나로 찾는다.
            data = normalize(data.model_copy(update={"leg_modes": []}))
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
                for plan in result["plans"] + result.get("reserve", []):
                    plan["personalization"] = result["personalization"]
            result = _finish(data, result, owner)
        except Exception:
            _record(
                owner,
                started,
                trace=trace,
                status="failed",
                external_usage=usage.snapshot(),
            )
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
            trace=trace,
        )
        return result


def _public(summary):
    """응답(diagnostics.timing)에 싣는 것: 외부 호출의 호스트 이름이 드러나는 종류별 표와 예산 거절 수는 뺀다.

    그 둘은 서버 로그(recommendation_timing)와 추천 이벤트에만 남는다.
    """
    external = {k: v for k, v in summary["external"].items() if k not in ("by_kind", "rejected")}
    return dict(summary, external=external)


def _compact(summary):
    """이벤트·로그용 요약: 단계별 시간, 외부 호출 합계, DB 합계만(종류별 표는 로그에만 덧붙임)."""
    return dict(
        total_ms=summary["total_ms"],
        stages={row["name"]: row["ms"] for row in summary["stages"]},
        external={
            k: summary["external"][k]
            for k in ("calls", "failed", "rejected", "wait_ms_sum", "wall_ms", "peak_parallel")
        },
        cache_hits=summary["cache_hits"],
        counts=summary.get("counts", {}),
        db=summary["db"],
    )


def _record(owner, started, trace=None, **values):
    # Observability must never turn a successfully saved recommendation into an error.
    from .experience import event

    if trace is not None:
        # 시간 기록 계산이 실패해도 추천 결과나 실패 경로의 원래 예외를 가리지 않는다(timing 만 빠짐).
        try:
            summary = trace.summary()
            values["timing"] = _compact(summary)
            logging.getLogger(__name__).info(
                "recommendation_timing status=%s %s",
                values.get("status"),
                json.dumps(
                    dict(values["timing"], by_kind=summary["external"]["by_kind"]),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
        except Exception:
            values.pop("timing", None)
            logging.getLogger(__name__).warning("recommendation_timing_failed")
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

    with span("research.course_search"):
        evidence = search_courses(data) if data.mode == "real" else None
    if data.mode == "real":
        from .quality import configure

        data = configure(data, evidence["query"])
        from .intent_discovery import discover_requested_places

        with span("research.intent_discovery"):
            evidence["intent_discovery"] = discover_requested_places(data)
    report("코스 구성", "취향·필수 조건·이동 동선을 비교하고 있어요")
    with span("compose.recommend"):
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
        with span("compose.retry_search"):
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
            with span("compose.retry_recommend"):
                retried = recommend(data, broad)
            if retried["plans"]:
                result = retried
                evidence = broad
                for p in result["plans"] + result.get("reserve", []):
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
        for plan in result["plans"] + result.get("reserve", []):
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


def _verify_car_routes(data, plans):
    from .planner import evaluate
    from .condition_audit import audit_plan

    for i, plan in enumerate(plans):
        verified, error = evaluate(
            plan["places"], data, soft=bool(plan.get("best_effort")), verify_routes=True
        )
        if verified:
            plan.update(verified)
            plans[i] = audit_plan(plan, data)
            plan["route_verification"] = "네이버 자동차 길찾기 조회 반영 (조회 시점 기준)"
        else:
            plan["route_verification"] = (
                "실제 경로 확인 실패: " + str(error) + " · 추정 동선을 유지했어요."
            )


def _shape(plans):
    """가격 확인 전후 비교용: 안마다 (장소 id 순서, 이름, 설명). 진단에만 쓰고 응답에는 개수만 싣는다."""
    return [
        (tuple(p["id"] for p in plan["places"]), plan.get("option_purpose"), plan.get("option_description"))
        for plan in plans
    ]


def _count_pricing(before, plans, price_stats, refill_stats):
    """가격 확인이 3안을 얼마나 바꿨는지와 조회한 가격이 최종 안에 쓰였는지를 개수로만 남긴다(timing.counts)."""
    from .perf_trace import count

    try:
        after = _shape(plans)
        final_places = {pid for ids, _, _ in after for pid in ids}
        count("price.plans_before", len(before))
        count("price.plans_after", len(after))
        for i, (ids, purpose, description) in enumerate(before):
            match = next((j for j, row in enumerate(after) if set(row[0]) == set(ids)), None)
            if match is None:
                count("price.plans_dropped")
                continue
            row = after[match]
            changed = False
            for name, flag in (
                ("price.plans_moved", match != i),
                ("price.order_changed", row[0] != ids),
                ("price.renamed", row[1] != purpose),
                ("price.redescribed", row[2] != description),
            ):
                count(name, flag)
                changed |= flag
            count("price.plans_unchanged", not changed)
        count("price.plans_added", sum(not any(set(r[0]) == set(b[0]) for b in before) for r in after))
        for prefix, stats in (("price", price_stats), ("price.refill", refill_stats)):
            looked = stats.get("looked_up") or set()
            count(prefix + ".places", stats.get("places", 0))
            count(prefix + ".cached", stats.get("cached", 0))
            count(prefix + ".lookups", len(looked))
            count(prefix + ".lookups_used", len(looked & final_places))
            for status, n in (stats.get("statuses") or {}).items():
                if status in ("available", "not_found", "unavailable", "key_missing"):
                    count(prefix + ".status_" + status, n)
    except Exception:
        logging.getLogger(__name__).warning("pricing_counts_failed")


# 가격 확인 뒤 빠진 코스를 예비 후보로 채울 때의 추가 외부 호출 상한.
REFILL_PLANS = 2
REFILL_PRICE_LOOKUPS = 6


def _refill(data, kept, reserve, stats=None):
    """experience 모드: 필수 조건으로 빠진 자리를 예비 후보 최대 2개로 다시 검증해 채운다.

    stats(dict)를 주면 가격 조회 구성을 채운다(price_plans 의 stats, 진단용)."""
    from .option_diversity import refill_candidates
    from .pricing import price_plans
    from .preferences import filter_required
    from .request_usage import current

    candidates = refill_candidates(kept, reserve, data, limit=REFILL_PLANS)
    looked_up = {p["id"] for plan in kept for p in plan["places"]}
    chosen, lookups = [], set()
    for plan in candidates:
        needed = {
            p["id"]
            for p in plan["places"]
            if data.mode == "real" and p.get("price") is None and p["id"] not in looked_up
        }
        if len(lookups | needed) > REFILL_PRICE_LOOKUPS:
            continue
        chosen.append(plan)
        lookups |= needed
    if not chosen:
        return []
    route_calls = (
        len(chosen) * (data.count + 1) if data.mode == "real" and data.transport == "car" else 0
    )
    usage = current()
    if usage:
        snapshot = usage.snapshot()
        if (
            snapshot["budget_exhausted"]
            or snapshot["limit"] - snapshot["total_calls"] < len(lookups) + route_calls
        ):
            return []
    if route_calls:
        _verify_car_routes(data, chosen)
    return filter_required(price_plans(chosen, stats=stats))


def _finish(data, result, owner):
    from .pricing import price_plans
    from .config import option_selector

    experience = option_selector() == "experience"
    reserve = result.pop("reserve", None) or []
    if data.mode == "real" and data.transport == "car":
        with span("compose.verify_car_routes"):
            _verify_car_routes(data, result["plans"])
    report(
        "가격 확인",
        "코스 후보를 찾았어요. 가격과 필수 조건을 마지막으로 확인해요",
        preview=[[p["name"] for p in plan["places"]] for plan in result["plans"]],
    )
    before_pricing = _shape(result["plans"])
    price_stats = {}
    with span("price.price_plans"):
        result["plans"] = price_plans(result["plans"], stats=price_stats)
    from .preferences import filter_required, hard_blocks

    blocked = [p for p in result["plans"] if hard_blocks(p)]
    priced = len(result["plans"])
    result["plans"] = filter_required(result["plans"])
    dropped = priced - len(result["plans"])
    refilled = []
    refill_stats = {}
    if experience and dropped and reserve:
        with span("price.refill"):
            refilled = _refill(data, result["plans"], reserve, refill_stats)
        result["plans"] += refilled
    if blocked and not result["plans"]:
        result.update(
            status="required_unmet",
            reasons=["선택한 필수 조건을 충족하는 코스를 확인하지 못했어요."],
            suggestions=[
                "필수 조건 또는 입력 범위를 직접 조정해 주세요. 미확인 조건을 충족으로 처리하지 않습니다."
            ],
        )
    if data.mode == "real" or refilled:
        from .option_diversity import select_options

        # 탐색 단계의 option_selection(후보 풀 비교)은 그대로 두고, 가격 확인 뒤 재선택은 따로 남긴다.
        final_selection = {}
        with span("price.select_options"):
            result["plans"] = select_options(
                result["plans"], data, final_selection, stage="after_pricing"
            )
        result.setdefault("diagnostics", {})["option_selection_after_pricing"] = final_selection[
            "option_selection"
        ]
    if experience and dropped:
        for p in result["plans"]:
            note = f"가격 확인 후 필수 조건을 넘은 코스 {dropped}개를 제외했어요."
            p["diversity_note"] = " ".join(filter(None, [p.get("diversity_note"), note]))
    from .experience import verification_summary
    from .request_usage import current

    if current() and current().snapshot()["budget_exhausted"]:
        result["resource_notice"] = (
            "일부 자료 조회가 요청 한도에 도달해 확인 자료와 추정을 함께 표시했어요. 누락된 영업·가격·이동 정보는 방문 전 확인해 주세요."
        )

    with span("price.verification_summary"):
        for p in result["plans"]:
            if result.get("resource_notice"):
                p["resource_notice"] = result["resource_notice"]
            p["verification"] = verification_summary(p)
    from .recommendation_summary import enrich

    with span("price.enrich"):
        for p in result["plans"]:
            enrich(p)
    _count_pricing(before_pricing, result["plans"], price_stats, refill_stats)
    from .plan_jobs import check_current

    check_current()
    group_id = uuid.uuid4().hex
    for plan in result["plans"]:
        plan["recommendation_group_id"] = group_id
    with span("save.plans"):
        result["plans"] = [store.save_plan(p, owner) for p in result["plans"]]
    trace = current_trace()
    if trace:
        # 결과에만 싣는다(저장된 코스에는 넣지 않음). 시간 값이라 같은 입력이어도 매번 다르다.
        # 계산이 실패하면 timing 만 빼고 이미 저장한 추천은 그대로 돌려준다.
        try:
            timing = _public(trace.summary())
        except Exception:
            timing = None
            logging.getLogger(__name__).warning("recommendation_timing_failed")
        if timing is not None:
            result.setdefault("diagnostics", {})["timing"] = timing
    return result
