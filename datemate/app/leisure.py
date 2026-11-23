"""Sports alternatives around an existing itinerary stop, without moving other stops.

종목 목록·판별 규칙은 app/sports.py 에 있다. 실제 장소 모드의 후보는 공공 자료에서 찾는다(app/public_places.py):
한국관광공사 TourAPI 의 레포츠 항목(실외 반경에 걸친 시·군·구 목록에서)과 소상공인 상가정보의 예술·스포츠 업종(코스 장소 주변).
네이버 지역 검색 결과는 후보로 쓰지 않는다(2026-11-20 2단계, docs/naver-terms-stage2-design.ko.md 3.8(b)).
"""

import hashlib
import re

from . import sports as sport_table
from .models import Conditions
from .request_intent import matches, intent
from .routes import distance

SPORTS = sport_table.KEYS

# 실내 레저 반경 1.5km: 코스 장소에서 걸어서 20분 안팎(도보 4km/h, 직선→실제 경로 보정 1.35). 기존 레저 반경과 같다.
INDOOR_RADIUS_KM = 1.5
# 실외 레저 반경 5km: 테니스장·승마장·수상레저 같은 실외 시설은 도심에 드물어 1.5km 안에서는 거의 없다.
# 대중교통(18km/h)·자전거(12km/h)로 20~30분 거리다.
OUTDOOR_RADIUS_KM = 5.0
# 자동차(평균 25km/h, 보정 1.35)는 같은 30분 안팎으로 약 10km까지 닿는다.
OUTDOOR_RADIUS_CAR_KM = 10.0
# 한 종목에서 가까운 순으로 이만큼만 후보로 둔다(상가정보에는 당구장만 수십 곳인 동네가 있다).
MAX_PER_SPORT = 4
# 화면에 비교할 후보 수(구분별). 시간·비용 재계산은 외부 호출 없이 로컬에서 한다.
MAX_INDOOR_OPTIONS = 16
MAX_OUTDOOR_OPTIONS = 12


def outdoor_radius(c):
    return OUTDOOR_RADIUS_CAR_KM if c.transport == "car" else OUTDOOR_RADIUS_KM


def leisure_info(place, c):
    """장소의 종목·실내외·검색 반경. 종목을 확인할 수 없으면 None."""
    sport = sport_table.place_sport(place)
    if not sport:
        return None
    setting, basis = sport_table.setting_of(
        sport, " ".join(str(place.get(k) or "") for k in ("name", "description"))
    )
    return dict(
        key=sport.key,
        label=sport.label,
        setting=setting,
        setting_basis=basis,
        varies=sport.varies and basis == "default",
        radius_km=INDOOR_RADIUS_KM if setting == "indoor" else outdoor_radius(c),
    )


def nearby_sports(plan, index):
    from .catalog import places

    anchor = plan["places"][index]
    used = {p["id"] for p in plan["places"]}
    c = Conditions.model_validate(plan["conditions"])
    rows = []
    seen = set()
    excluded = intent(c)["excluded"]
    for place in places(c.mode, c.visit_date):
        if place["id"] in used or place["id"] in seen:
            continue
        info = leisure_info(place, c)
        if not info or info["key"] in excluded:
            continue
        if any(matches(place, k) for k in excluded):
            continue
        seen.add(place["id"])
        if any(w.casefold() in str(place).casefold() for w in c.avoid if w):
            continue
        meters = round(distance(anchor, place) * 1000)
        if meters <= info["radius_km"] * 1000:
            rows.append((meters, place))
    unique = []
    # 서로 다른 검색어로 찾은 같은 장소('그루트  클라이밍'·'그루트 클라이밍')는 ID가 달라도 하나만 남긴다(가까운 것 우선).
    for meters, place in sorted(rows, key=lambda x: (x[0], x[1]["id"])):
        if not any(
            same_leisure_place(place, p) for p in [*plan["places"], *(p for _, p in unique)]
        ):
            unique.append((meters, place))
    return unique


# 상호를 바꿔 쓴 같은 장소로 볼 최대 거리. 이름이 같으면 quality.same_place 와 같은 0.8km,
# 한 이름이 다른 이름을 포함하면('○○클라이밍'·'○○클라이밍 성수점') 30m 안일 때만 같은 장소로 본다.
SAME_NAME_KM = 0.8
CONTAINED_NAME_KM = 0.03


def name_key(name):
    return re.sub(r"[^0-9A-Za-z가-힣]", "", str(name or "")).casefold()


def same_leisure_place(a, b):
    from .quality import same_place

    if same_place(a, b):
        return True
    x, y = name_key(a.get("name")), name_key(b.get("name"))
    if not x or not y:
        return False
    km = distance(a, b)
    return (x == y and km <= SAME_NAME_KM) or (
        (x in y or y in x) and min(len(x), len(y)) >= 3 and km <= CONTAINED_NAME_KM
    )


def message(c):
    return (
        f"현재 코스 장소에서 실내 레저는 반경 {INDOOR_RADIUS_KM:g}km, 실외 레저는 반경 {outdoor_radius(c):g}km 안의 후보예요. "
        "선택하면 해당 순서의 장소만 교체해요. 직선거리 기준이며 영업·예약·계절 운영은 방문 전에 확인해 주세요."
    )


def discover_leisure(c, anchor):
    """코스 장소 주변 레저를 공공 자료에서 찾아 종목별로 이 사용자의 후보에 두고 진단을 돌려준다."""
    from . import naver_cache, public_places
    from collections import Counter

    if c.mode != "real" or not public_places.enabled():
        return dict(search_status="unavailable", lookups=0)
    point = (round(anchor["lat"], 4), round(anchor["lon"], 4))
    excluded = sorted(intent(c)["excluded"])
    cachekey = (
        "public-leisure-v1:"
        + hashlib.sha256(str([point, c.region, c.transport, excluded]).encode()).hexdigest()
    )
    cached = naver_cache.cached(cachekey)
    if cached:
        return dict(cached, lookups=0, cache_hit=True)
    stats = Counter()
    sources = []
    found = []
    # 관광공사 레포츠(관광 타입 28): 실외 반경까지. 상가정보 예술·스포츠 업종: 코스 장소 주변(업소가 드물면 3km).
    tour = public_places.tour_near(anchor["lat"], anchor["lon"], outdoor_radius(c), types=("28",))
    sources.append(dict(source="tour", status=tour.get("status"), rows=len(tour.get("rows") or [])))
    for row in tour.get("rows") or []:
        place = public_places.tour_place(row, c.region)
        if place and place["category"] == "레저·활동":
            found.append(place)
        else:
            stats["unclassified"] += 1
    stores, radius_m = public_places.stores_near("play", anchor["lat"], anchor["lon"])
    sources.append(
        dict(
            source="store:play",
            status=stores.get("status"),
            rows=len(stores.get("rows") or []),
            radius_m=radius_m,
        )
    )
    for row in stores.get("rows") or []:
        pair = public_places.store_place(row, c.region, stores.get("data_month"))
        if pair and pair[0] == "sport":
            found.append(pair[1])
        else:
            stats["unclassified"] += 1
    adopted = Counter()
    kept = []
    for place in sorted(found, key=lambda p: (distance(anchor, p), p["id"])):
        stats["received"] += 1
        key = place["tags"][0]
        if key in excluded:
            stats["excluded"] += 1
            continue
        radius = INDOOR_RADIUS_KM if place.get("setting") == "indoor" else outdoor_radius(c)
        if distance(anchor, place) > radius:
            stats["out_of_radius"] += 1
            continue
        if adopted[key] >= MAX_PER_SPORT:
            stats["over_cap"] += 1
            continue
        if any(same_leisure_place(place, other) for other in kept):
            stats["duplicate"] += 1
            continue
        adopted[key] += 1
        # 레저 패널이 찾은 운동 시설 표시: 운동을 원하지 않은 기본 추천의 후보에는 섞지 않는다(quality.from_leisure_search).
        kept.append(dict(place, leisure_search=True))
    stats["adopted"] = len(kept)
    # 이미 추천 후보로 찾아 둔 같은 장소(표시 없음)는 덮어쓰지 않는다.
    known = naver_cache.cached_many(public_places.CANDIDATE_PREFIX + p["id"] for p in kept)
    public_places.remember(
        [p for p in kept if public_places.CANDIDATE_PREFIX + p["id"] not in known]
    )
    statuses = [s["status"] for s in sources]
    ok = any(s == "available" for s in statuses)
    result = dict(
        search_status="complete" if ok else "unavailable",
        lookups=len(sources),
        sources=sources,
        stats=dict(stats),
        adopted_by_sport=dict(adopted),
    )
    naver_cache.cache(cachekey, result, 900 if ok else 30)
    return result


def options(plan, index, locked, discover=False, diagnostics=None):
    if index < 0 or index >= len(plan["places"]):
        raise ValueError("올바른 코스 순서를 선택해 주세요.")
    c = Conditions.model_validate(plan["conditions"])
    if index in set(locked) | set(c.locked):
        raise ValueError("고정한 장소는 먼저 고정을 해제해 주세요.")
    if discover and c.mode == "real":
        searched = discover_leisure(c, plan["places"][index])
        if diagnostics is not None:
            diagnostics.update(searched)
    from .condition_audit import audit_plan
    from .best_effort import annotate
    from .preferences import hard_blocks

    result = []
    nearby = [
        (meters, place, leisure_info(place, c)) for meters, place in nearby_sports(plan, index)
    ]
    indoor = [row for row in nearby if row[2]["setting"] == "indoor"][:MAX_INDOOR_OPTIONS]
    outdoor = [row for row in nearby if row[2]["setting"] == "outdoor"][:MAX_OUTDOOR_OPTIONS]
    if diagnostics is not None:
        diagnostics.update(
            nearby_count=len(nearby),
            nearby_indoor=sum(r[2]["setting"] == "indoor" for r in nearby),
            nearby_outdoor=sum(r[2]["setting"] == "outdoor" for r in nearby),
            rejected={},
            # 구분별로 일정 조건 때문에 뺀 후보 수와 사유(화면의 "○곳은 제외했어요" 안내에 쓴다).
            rejected_by_setting={
                "indoor": {"count": 0, "reasons": {}},
                "outdoor": {"count": 0, "reasons": {}},
            },
        )

    def reject(info, reasons):
        if diagnostics is None:
            return
        group = diagnostics["rejected_by_setting"][info["setting"]]
        group["count"] += 1
        for reason in reasons:
            diagnostics["rejected"][reason] = diagnostics["rejected"].get(reason, 0) + 1
            group["reasons"][reason] = group["reasons"].get(reason, 0) + 1

    for meters, place, info in sorted(indoor + outdoor, key=lambda r: (r[0], r[1]["id"])):
        chosen = list(plan["places"])
        chosen[index] = place
        # 중간 축제는 되도록 원래 자리에(planner.evaluate festival_hint). 달라지면 후보에 알림(festival_change).
        from .festival_time import set_change_note
        from .leg_modes import middle_after

        # 지각을 반영한 코스는 그 지연을 다시 넣는다(planner.replacements 와 같은 규칙 — app/plan_rules.reevaluate).
        from .delay_check import kept_note
        from .plan_rules import reevaluate

        updated, error = reevaluate(
            plan,
            chosen,
            c,
            late_end=True,
            soft=bool(plan.get("best_effort")),
            festival_hint=middle_after(plan),
        )
        if error:
            reject(info, [error])
            continue
        from .pricing import apply_prices

        updated = apply_prices(updated)
        if plan.get("best_effort"):
            updated = annotate(updated, c)
        updated = audit_plan(updated, c)
        blocked = hard_blocks(updated)
        if blocked:
            reject(info, [item["label"] for item in blocked])
            continue
        from .plan_changes import change_delta

        updated["delta"] = change_delta(plan, updated)
        set_change_note(updated, plan)
        updated["change_reason"] = (
            "선택한 레저로 이 장소만 교체하고 이동·시간·비용을 다시 계산했어요." + kept_note(plan)
        )
        if plan.get("course_search"):
            updated["course_search"] = plan["course_search"]
        result.append({"distance_m": meters, "plan": updated, "sport": info})
    return result
