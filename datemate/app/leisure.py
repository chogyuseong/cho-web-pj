"""Sports alternatives around an existing itinerary stop, without moving other stops.

종목 목록·판별 규칙은 app/sports.py 에 있다. 실제 장소 모드에서는 종목마다 검색하지 않고 묶음 검색어
(LEISURE_SEARCHES, 최대 12건)로 찾은 결과를 업종·상호로 종목별로 나눈다.
"""

import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import quote

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
# 레저 후보 1회 조회의 지역 검색 상한(묶음 검색 + 직접 요청한 종목 검색).
MAX_LEISURE_LOOKUPS = 12
# 화면에 비교할 후보 수(구분별). 시간·비용 재계산은 외부 호출 없이 로컬에서 한다.
MAX_INDOOR_OPTIONS = 16
MAX_OUTDOOR_OPTIONS = 12

INDOOR_ACTIVE = (
    "trampoline", "archery", "shooting", "darts", "roller", "vr_sports",
    "indoor_surfing", "indoor_ski", "skating", "swimming", "basketball",
)  # fmt: skip
# (검색어, 구분, 검색 지역 단위, 이 검색으로 주로 찾는 종목). 결과의 종목은 검색어가 아니라 업종·상호로 정한다.
# 실내는 코스 장소의 구 단위, 드문 실외 시설은 시·군(서울은 서울) 단위로 찾는다.
LEISURE_SEARCHES = (
    ("볼링장", "indoor", "district", ("bowling",)),
    ("당구장", "indoor", "district", ("billiards",)),
    ("클라이밍", "indoor", "district", ("climbing",)),
    ("탁구장", "indoor", "district", ("table_tennis",)),
    ("배드민턴장", "indoor", "district", ("badminton", "squash")),
    ("스크린골프", "indoor", "district", ("screen_golf",)),
    ("스크린야구", "indoor", "district", ("screen_baseball", "indoor_tennis")),
    ("실내스포츠", "indoor", "district", INDOOR_ACTIVE),
    ("레저", "outdoor", "district", tuple(sport_table.OUTDOOR_KEYS)),
    ("테니스장", "outdoor", "district", ("tennis", "futsal")),
    (
        "레포츠",
        "outdoor",
        "city",
        ("kart_luge", "zipline", "paragliding", "horse_riding", "cycling", "golf", "ski", "hiking"),
    ),
    ("수상레저", "outdoor", "city", ("paddle", "surfing", "boating", "water_leisure", "fishing")),
)


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


def search_plan(c, anchor):
    """(검색어, 구분, 검색 지역) 목록. 직접 요청한 종목을 먼저 찾고, 제외한 종목만 찾는 묶음은 뺀다. 최대 12건."""
    from .intent_discovery import search_area

    address = anchor.get("address") or ""
    district = re.search(r"[가-힣]+구(?:\s|$)", address)
    # 주소가 없으면 박물관 이름 같은 장소 이름이 아니라 출발지·동네 이름에서 구를 고른다.
    district = (
        district[0].strip() if district else search_area((c.area_center or c.origin).name, c.region)
    )
    city = re.search(r"(?:^|\s)([가-힣]{1,8}(?:시|군))(?:\s|$)", address)
    city = city[1] if city and not re.search(r"(?:특별|광역|자치)시$", city[1]) else ""
    areas = {"district": f"{c.region} {district}".strip(), "city": f"{c.region} {city}".strip()}
    parsed = intent(c)
    excluded = set(parsed["excluded"])
    rows = []
    for key in parsed["intents"]:
        sport = sport_table.BY_KEY.get(key)
        if sport:
            rows.append(
                (
                    sport.terms[0],
                    sport.setting,
                    areas["district" if sport.setting == "indoor" else "city"],
                )
            )
    for term, setting, scope, covers in LEISURE_SEARCHES:
        if set(covers) <= excluded:
            continue
        rows.append((term, setting, areas[scope]))
    unique = []
    for row in rows:
        if row[0] not in {r[0] for r in unique}:
            unique.append(row)
    return unique[:MAX_LEISURE_LOOKUPS]


def discover_leisure(c, anchor):
    """묶음 검색으로 코스 장소 주변 레저를 찾아 종목별로 분류해 저장하고 진단을 돌려준다."""
    from . import intent_discovery, store
    from .image_search import plain
    from .regions import region_from_address, korean_coordinates
    from .request_usage import current, measure
    from .search_address_text import place_query
    from collections import Counter
    from contextlib import nullcontext

    if c.mode != "real" or not intent_discovery.search_enabled():
        return dict(search_status="unavailable", lookups=0)
    queries = search_plan(c, anchor)
    point = (round(anchor["lat"], 4), round(anchor["lon"], 4))
    cachekey = (
        "leisure-local-v1:"
        + hashlib.sha256(str([point, c.region, c.transport, queries]).encode()).hexdigest()
    )
    cached = store.cached(cachekey)
    if cached:
        return dict(cached, lookups=0, cache_hit=True)
    stats = {term: Counter() for term, _, _ in queries}
    adopted = Counter()
    kept_rows = []
    # 레저 조회는 추천 요청 밖에서 불리므로 여기서 요청별 외부 호출 예산(request_usage)을 연다.
    with nullcontext(current()) if current() else measure() as usage:
        found = intent_discovery.lookup_all(
            [(setting, term, area) for term, setting, area in queries]
        )
        snapshot = usage.snapshot()
    statuses = [status for _, status in found]
    for (term, _, _), (items, _) in zip(queries, found):
        st = stats[term]
        for item in items:
            st["received"] += 1
            category = plain(item.get("category", ""))
            name = plain(item.get("title", ""))
            address = plain(item.get("roadAddress") or item.get("address", ""))
            if not name or region_from_address(address) != c.region:
                st["other_region"] += 1
                continue
            if sport_table.noise(category, name):
                st["noise"] += 1
                continue
            sport = sport_table.classify(category, name)
            if not sport:
                st["unclassified"] += 1
                continue
            try:
                lon, lat = float(item["mapx"]), float(item["mapy"])
                if abs(lon) > 180:
                    lon /= 10000000
                if abs(lat) > 90:
                    lat /= 10000000
                if not korean_coordinates(lat, lon):
                    raise ValueError
            except (KeyError, ValueError, TypeError):
                st["bad_coordinates"] += 1
                continue
            setting, _ = sport_table.setting_of(sport, name + " " + category)
            radius = INDOOR_RADIUS_KM if setting == "indoor" else outdoor_radius(c)
            if distance(anchor, dict(lat=lat, lon=lon)) > radius:
                st["out_of_radius"] += 1
                continue
            # 검색어마다 강조 태그(<b>)가 달라 상호의 공백이 달라진다. 공백을 하나로 맞추고, 이번 검색에서 이미 채택한 같은 장소는 건너뛴다.
            name = re.sub(r"\s+", " ", name).strip()
            pid = "discovered:" + hashlib.sha256((name + address).encode()).hexdigest()[:20]
            here = dict(name=name, lat=lat, lon=lon, id=pid)
            if any(same_leisure_place(here, kept) for kept in kept_rows):
                st["duplicate"] += 1
                continue
            kept_rows.append(here)
            st["adopted"] += 1
            adopted[sport.key] += 1
            # 이미 저장된 장소(블로그 근거 등)는 덮어쓰지 않는다.
            if store.cached("discovered-place:" + pid):
                continue
            row = dict(
                id=pid, name=name, address=address, lat=lat, lon=lon, region=c.region, demo=False,
                category="레저·활동", themes=["레저·활동"], tags=[sport.key, category], meal=False,
                description=category,
                source="https://map.naver.com/p/search/" + quote(place_query({"name": name, "address": address})),
                source_type="네이버 지역 검색 · 레저 종목 분류",
                checked_at=datetime.now(timezone.utc).isoformat(),
                discovery_verification="네이버 업체 분류·상호·주소·좌표 연결 · 영업 여부·계절 운영 별도 확인",
                price=None, price_unit="person", hours=None, closed_days=None, breaks=None, last_entry=None,
                reservation=None, stay=None, stay_basis=None, rating=None, setting=None, photos=[], videos=[],
                license="검색 결과",
            )  # fmt: skip
            store.cache("discovered-place:" + pid, row, 604800)
    result = dict(
        search_status="permission_required"
        if "permission_required" in statuses
        else "unavailable"
        if statuses and all(s == "unavailable" for s in statuses)
        else "complete",
        lookups=len(queries),
        queries=[dict(term=t, setting=s, area=a) for t, s, a in queries],
        term_stats={k: dict(v) for k, v in stats.items()},
        adopted_by_sport=dict(adopted),
        external_calls=snapshot["total_calls"],
        budget_exhausted=snapshot["budget_exhausted"],
    )
    ok = any(s == "available" for s in statuses)
    store.cache(cachekey, result, 900 if ok else 30)
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
    from .planner import evaluate
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
        updated, error = evaluate(chosen, c, soft=bool(plan.get("best_effort")))
        if error:
            reject(info, [error])
            continue
        from .pricing import apply_prices

        updated = apply_prices(updated, {})
        if plan.get("best_effort"):
            updated = annotate(updated, c)
        updated = audit_plan(updated, c)
        blocked = hard_blocks(updated)
        if blocked:
            reject(info, [item["label"] for item in blocked])
            continue
        from .plan_changes import change_delta

        updated["delta"] = change_delta(plan, updated)
        updated["change_reason"] = (
            "선택한 레저로 이 장소만 교체하고 이동·시간·비용을 다시 계산했어요."
        )
        if plan.get("course_search"):
            updated["course_search"] = plan["course_search"]
        result.append({"distance_m": meters, "plan": updated, "sport": info})
    return result
