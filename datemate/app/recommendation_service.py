"""Recommendation use case shared by HTTP endpoints and background workers.

Stage order is intentional: normalize, research, verify, price, enforce required
conditions, diversify, explain, then check cancellation before persistence.
"""

import json
import logging
import time
import uuid
from . import naver_cache, store
from .execution import recommendation_slot
from .models import Conditions
from .planner import recommend
from .plan_jobs import report
from .request_intent import normalize
from .feedback_preferences import personalizing, explanation
from .request_usage import measure
from .perf_trace import current as current_trace, recording, span
from .telemetry import naver_session


def generate(data: Conditions, owner: str):
    with (
        recording() as trace,
        recommendation_slot(owner),
        personalizing(owner, data.use_feedback, data.mode) as profile,
        measure() as usage,
        naver_session(),
        naver_cache.scope(owner),
    ):
        # 새 추천 = 같은 사용자의 새 질의: 이전 추천의 네이버 검색 보관분(발견 장소·검색 글·가격 근거 등)을 지운다(특약 2.4).
        # 같은 조건으로 다시 추천하면 같은 질의로 보고 지우지 않는다(fingerprint).
        naver_cache.new_query(
            "plan",
            owner,
            fingerprint=data.model_dump_json(exclude={"leg_modes", "planning_session_id"}),
        )
        started = time.perf_counter()
        try:
            # 구간별 수단은 만든 코스를 바꿀 때만 생긴다. 새 추천은 기본 수단 하나로 찾는다.
            data = normalize(data.model_copy(update={"leg_modes": []}))
            # 축제 참석 시간 고정(app/festival_time.py): 운영 시간은 받아 둔 축제 상세 캐시에서만 읽는다(외부 호출 없음).
            from .festivals import with_cached_hours

            data = with_cached_hours(data)
            # 한 곳만 새로운 곳으로(app/fresh_place.py): 익숙한 종류는 이 브라우저의 최근 코스로 서버가 정한다.
            from .fresh_place import with_familiar

            data = with_familiar(data, owner)
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
    """후보 장소를 찾고 코스를 짠다.

    후보는 우리 카탈로그와 공공 자료(한국관광공사·소상공인 상가정보, app/intent_discovery.py)에서만 나온다.
    네이버 지역 검색 결과는 후보·점수·필터·이유 문장에 쓰지 않는다(tests/test_public_candidates.py).
    네이버 블로그 검색 결과(evidence)는 화면의 독립 블록에 그대로 보여 주려고 싣기만 한다(특약 2.2).
    추천이 쓰는 것은 조건에서 만든 검색어 문자열(requested_query)뿐이고, 글의 내용·순위·건수·검색 성공 여부는 쓰지 않는다
    (tests/test_blog_independent_block.py).
    """
    report("장소 검색", "선택 지역의 실제 장소를 찾고 있어요")
    from .course_search import course_query, search_courses

    with span("research.course_search"):
        evidence = search_courses(data) if data.mode == "real" else None
    intent_discovery = None
    if data.mode == "real":
        from .quality import configure

        data = configure(data, evidence["requested_query"])
        from .intent_discovery import discover_requested_places

        with span("research.intent_discovery"):
            intent_discovery = discover_requested_places(data)
    report("코스 구성", "취향·필수 조건·이동 동선을 비교하고 있어요")
    with span("compose.recommend"):
        result = recommend(data)
    if data.mode == "real" and (
        not result["plans"] or any(p.get("search_adjustments") for p in result["plans"])
    ):
        # 더 넓은 범위의 대안을 받아들이기 전에, 취향 낱말 없이 같은 지역의 후보(요청 활동·부족한 종류)를 한 번 더 찾아 다시 짠다.
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
        from . import public_places

        # 다시 찾을지는 조건에서 만든 검색어가 달라지는지(취향 낱말이 있었는지)와 공공 자료 키 유무로만 정한다. 블로그 검색 결과는 보지 않는다.
        if public_places.enabled() and (
            course_query(local) != course_query(data) or not result["plans"]
        ):
            with span("compose.retry_search"):
                discover_requested_places(local)
            with span("compose.retry_recommend"):
                retried = recommend(data)
            if retried["plans"]:
                result = retried
                for p in result["plans"] + result.get("reserve", []):
                    p.setdefault(
                        "search_adjustments",
                        dict(
                            stage="same_location",
                            origin_unchanged=True,
                            original_radius_km=data.neighborhood_radius_km,
                            effective_radius_km=data.neighborhood_radius_km,
                            messages=[
                                "위치는 그대로 두고, 취향 낱말 없이 같은 지역의 장소를 한 번 더 찾아 코스를 다시 짰어요."
                            ],
                            differences=[
                                dict(label=r["label"], message=r["message"])
                                for r in p.get("condition_checks", [])
                                if r["state"] == "unmet"
                            ],
                        ),
                    )
    if not result["plans"] and data.area_center:
        result.setdefault("suggestions", []).insert(
            0,
            f"{data.area_center.name} 반경 {data.neighborhood_radius_km:g}km 안에서 찾고 있어요. 동네 이동 범위나 방문 수를 조정해 주세요.",
        )
    if evidence:
        result["course_search"] = evidence
        if intent_discovery is not None:
            result.setdefault("diagnostics", {})["intent_discovery"] = intent_discovery
        for plan in result["plans"] + result.get("reserve", []):
            plan["course_search"] = evidence
    return data, result


def _verify_car_routes(data, plans):
    from .planner import evaluate
    from .leg_modes import middle_after
    from .condition_audit import audit_plan

    for i, plan in enumerate(plans):
        # 추정 구간으로 정한 중간 축제 자리를 먼저 둔다(planner.evaluate festival_hint) — 쓰지 않을 구간의 길찾기 조회를 줄인다.
        verified, error = evaluate(
            plan["places"],
            data,
            soft=bool(plan.get("best_effort")),
            verify_routes=True,
            festival_hint=middle_after(plan),
        )
        if verified:
            # 축제 방문 기록은 다시 계산한 코스를 따른다(실제 길찾기로 축제 자리가 빠지면 옛 기록이 남지 않게).
            plan.pop("festival_visit", None)
            plan.update(verified)
            plans[i] = audit_plan(plan, data)
            plan["route_verification"] = "네이버 자동차 길찾기 조회 반영 (조회 시점 기준)"
        else:
            plan["route_verification"] = (
                "실제 경로 확인 실패: " + str(error) + " · 추정 동선을 유지했어요."
            )


def _nearest_outside(data, plans):
    """요청한 활동이 동네 반경 안에 없어 미충족인 안에, 반경 밖에서 가장 가까운 곳(이름·직선거리)을 붙인다.

    받아 둔 관광공사 목록만 읽어 외부 호출이 없다(public_places.nearest_outside). 코스는 바꾸지 않고 조건 확인 문장에만 쓴다
    (condition_audit). 걸어서는 반경 밖에 닿지 않는다는 판단(배포-이어가기.txt 6-1)은 그대로다."""
    if data.mode != "real" or not data.area_center:
        return
    from . import public_places
    from .condition_audit import audit_plan
    from .request_intent import INTENTS, intent, matches

    keys = intent(data)["intents"]
    if not keys or not public_places.enabled():
        return
    found = {}
    for i, plan in enumerate(plans):
        missing = [key for key in keys if not any(matches(p, key) for p in plan["places"])]
        hints = []
        for key in missing:
            if key not in found:
                found[key] = public_places.nearest_outside(
                    data.area_center.lat,
                    data.area_center.lon,
                    data.neighborhood_radius_km,
                    data.region,
                    # 요청 활동의 종류(INTENTS 의 첫 값)인 곳만. '솔향식빵공방' 같은 빵집이 '공방' 낱말로 걸리지 않게(실제 키 강릉 확인).
                    lambda place, key=key: matches(place, key)
                    and place.get("category") == INTENTS[key][0],
                )
            if found[key]:
                hints.append(dict(intent=INTENTS[key][1][0], **found[key]))
        if hints:
            plan["nearest_outside"] = hints
            plans[i] = audit_plan(plan, data)


def _shape(plans):
    """가격 확인 전후 비교용: 안마다 (장소 id 순서, 이름, 설명). 진단에만 쓰고 응답에는 개수만 싣는다."""
    return [
        (
            tuple(p["id"] for p in plan["places"]),
            plan.get("option_purpose"),
            plan.get("option_description"),
        )
        for plan in plans
    ]


def _count_pricing(before, plans):
    """비용 계산(등록 단가·계획용 가정)과 필수 조건 확인이 3안을 얼마나 바꿨는지를 개수로만 남긴다(timing.counts).
    가격을 찾는 외부 조회는 없다(블로그 요약에서 금액을 읽지 않음, app/pricing.py)."""
    from .perf_trace import count

    try:
        after = _shape(plans)
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
        count(
            "price.plans_added", sum(not any(set(r[0]) == set(b[0]) for b in before) for r in after)
        )
    except Exception:
        logging.getLogger(__name__).warning("pricing_counts_failed")


# 비용 계산 뒤 빠진 코스를 채울 때 다시 검증하는 예비 후보 수(자동차면 후보마다 길찾기 호출이 든다).
REFILL_PLANS = 2


def _refill(data, kept, reserve):
    """experience 모드: 필수 조건으로 빠진 자리를 예비 후보 최대 2개로 다시 검증해 채운다."""
    from .option_diversity import refill_candidates
    from .pricing import price_plans
    from .preferences import filter_required
    from .request_usage import current

    chosen = refill_candidates(kept, reserve, data, limit=REFILL_PLANS)
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
            or snapshot["limit"] - snapshot["total_calls"] < route_calls
        ):
            return []
    if route_calls:
        _verify_car_routes(data, chosen)
    return filter_required(price_plans(chosen))


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
        # 확정 전 후보 카드: 가격·비용·조건 확인 결과는 싣지 않는다(확정 전 값을 확정값처럼 보이지 않게).
        preview_options=[
            dict(
                purpose=plan.get("option_purpose"),
                places=[dict(id=p["id"], name=p["name"]) for p in plan["places"]],
            )
            for plan in result["plans"]
        ],
    )
    # 결과에 들어간 식당·카페의 폐업 여부(행안부 인허가)를 미리 조회해 둔다 — 다음 추천부터 quality.pool 이 폐업한 곳을 뺀다
    # (2026-11-24, app/place_identity.prefetch). 배경 일꾼이 하므로 이 요청을 늦추지 않는다.
    if data.mode == "real":
        from .place_identity import prefetch

        prefetch([p for plan in result["plans"] for p in plan["places"]])
    before_pricing = _shape(result["plans"])
    with span("price.price_plans"):
        result["plans"] = price_plans(result["plans"])
    from .preferences import filter_required, hard_blocks

    blocked = [p for p in result["plans"] if hard_blocks(p)]
    priced = len(result["plans"])
    result["plans"] = filter_required(result["plans"])
    dropped = priced - len(result["plans"])
    refilled = []
    if experience and dropped and reserve:
        with span("price.refill"):
            refilled = _refill(data, result["plans"], reserve)
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

    with span("price.nearest_outside"):
        _nearest_outside(data, result["plans"])
    with span("price.verification_summary"):
        for p in result["plans"]:
            if result.get("resource_notice"):
                p["resource_notice"] = result["resource_notice"]
            p["verification"] = verification_summary(p)
    from .recommendation_summary import enrich

    with span("price.enrich"):
        for p in result["plans"]:
            enrich(p)
    _count_pricing(before_pricing, result["plans"])
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
