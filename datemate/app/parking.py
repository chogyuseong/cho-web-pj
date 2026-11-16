"""자동차로 도착하는 장소 근처의 주차장.

결과 화면에서 주차장 패널이 보일 때만 부른다(추천 과정에서는 부르지 않는다). 계획(plan)에는 아무것도
저장하지 않고, 일정·비용·시간도 바꾸지 않는다. 요금·운영시간·만차 여부는 확인하지 않으므로 만들지 않는다.

찾는 장소는 자동차 구간이 도착하는 장소다(leg_modes.car_position_notes 의 규칙대로 차는 그곳에 선다).
귀가 구간의 도착(집)은 찾지 않는다. 장소마다 네이버 지역 검색 2건('장소명 주차장', '동네 공영주차장').
공공데이터 전국주차장정보표준데이터(app/public_parking.py, 외부 호출 없음)의 같은 주차장에는 요금·방문일 운영시간·기준일을 붙이고,
네이버 결과에 없던 공공데이터 주차장도 함께 넣어 가까운 순으로 장소당 3곳을 보인다. 네이버 키가 없으면 공공데이터만 쓴다.
"""

import hashlib
import json
import math
from collections import Counter
from datetime import date

from . import public_parking, store
from .image_search import plain, search_enabled
from .leg_modes import leg_mode, uses_car
from .models import Conditions
from .regions import korean_coordinates, region_from_address
from .routes import distance

SOURCE_TYPE = "네이버 지역 검색 · 공공데이터포털 전국주차장정보표준데이터"
RADIUS_M = 800
PER_STOP = 3
MAX_LOOKUPS = 10
CACHE_FOUND_SECONDS = 3600
CACHE_EMPTY_SECONDS = 30
EXCLUDED_WORDS = ("발렛", "주차대행", "세차")
REJECTED = ("not_parking", "other_region", "bad_coordinates", "out_of_radius", "duplicate")
NOTE = "주차 시간·요금은 일정과 비용에 포함하지 않았어요."
MESSAGES = {
    "not_car": "자동차로 도착하는 장소가 없어요.",
    "demo": "가상 장소에서는 실제 주차장을 검색하지 않습니다.",
    # 문구는 주변 식당 검색(restaurants.search_nearby)과 같다.
    "key_missing": "네이버 검색 키를 설정해 주세요.",
    "permission_required": "네이버 클라우드 NAVER API HUB의 기존 Application에서 NAVER 검색 > 지역 API를 활성화해 주세요. "
    "이미지·블로그 키는 그대로 사용할 수 있습니다.",
    "unavailable": "주차장 검색에 연결하지 못했어요.",
    "not_found": f"이 장소 {RADIUS_M}m 안에서 주차장을 찾지 못했어요.",
}


def car_stops(plan):
    """자동차 구간이 도착하는 장소의 번호. 구간 i 는 장소 i 에 도착한다(귀가 구간은 장소 수 뒤에 있어 빠진다)."""
    legs = plan.get("legs") or []
    return [i for i in range(min(len(legs), len(plan["places"]))) if leg_mode(plan, i) == "car"]


def neighbourhood(place, region):
    """'공영주차장' 검색에 쓸 구·동. 주소에서 고르고, 고르지 못하면 None."""
    from .intent_discovery import area_terms

    address = str(place.get("address") or "").strip()
    if not address:
        return None
    area, _ = area_terms(address, region)
    return area or None


def walk_minutes(km):
    """routes.leg 의 추정 규칙과 같다: 직선거리 × 1.35 ÷ 시속 4km."""
    return max(1, math.ceil(km * 1.35 / 4 * 60))


def squeeze(text):
    return "".join(str(text or "").split()).casefold()


def cache_key(place, region):
    raw = json.dumps(
        [round(place["lat"], 4), round(place["lon"], 4), place["name"], region], ensure_ascii=False
    )
    return "parking-local-v1:" + hashlib.sha256(raw.encode()).hexdigest()


def filter_lots(place, items, regions):
    """한 장소의 검색 결과를 거른다. (주차장 목록, 받은 수, 제외 이유별 수)."""
    rejected = Counter()
    lots = {}
    for item in items:
        name = " ".join(plain(item.get("title", "")).split())
        category = plain(item.get("category", ""))
        address = " ".join(plain(item.get("roadAddress") or item.get("address") or "").split())
        text = name + " " + category
        if "주차" not in text or any(word in text for word in EXCLUDED_WORDS):
            rejected["not_parking"] += 1
            continue
        if region_from_address(address) not in regions:
            rejected["other_region"] += 1
            continue
        try:
            lon, lat = float(item["mapx"]), float(item["mapy"])
            if abs(lon) > 180:
                lon /= 10000000
            if abs(lat) > 90:
                lat /= 10000000
            if not korean_coordinates(lat, lon):
                rejected["bad_coordinates"] += 1
                continue
        except (KeyError, ValueError, TypeError):
            rejected["bad_coordinates"] += 1
            continue
        km = distance(place, dict(lat=lat, lon=lon))
        if km * 1000 > RADIUS_M:
            rejected["out_of_radius"] += 1
            continue
        key = squeeze(name) + "|" + squeeze(address)
        if key in lots:
            rejected["duplicate"] += 1
            continue
        lots[key] = dict(
            id="parking:naver-" + hashlib.sha256(key.encode()).hexdigest()[:16],
            name=name,
            category=category,
            address=address,
            lat=lat,
            lon=lon,
            distance_m=round(km * 1000),
            walk_minutes=walk_minutes(km),
            public_by_name="공영" in name,
        )
    return sorted(lots.values(), key=lambda lot: lot["distance_m"]), len(items), rejected


def visit_date(conditions):
    try:
        return date.fromisoformat(str(conditions.get("visit_date") or ""))
    except ValueError:
        return None


def public_lot(lot, distance_m, visit):
    """네이버 결과에 없던 공공데이터 주차장 한 곳."""
    name = lot["name"] if "주차" in lot["name"] else lot["name"] + " 주차장"
    return dict(
        id="parking:public-" + hashlib.sha256(lot["id"].encode()).hexdigest()[:16],
        name=name,
        category="공공데이터 주차장",
        address=lot["address"],
        lat=lot["lat"],
        lon=lot["lon"],
        distance_m=round(distance_m),
        walk_minutes=walk_minutes(distance_m / 1000),
        public_by_name=False,
        public=public_parking.details(lot, visit),
    )


def attach_live(stops, diagnostics):
    """서울시 '(시)' 공영주차장이면 실시간 주차 대수를 붙인다(서울 열린데이터광장, 3분 캐시). 맞춘 코드는 응답에서 뺀다."""
    pairs = []
    for stop in stops:
        for lot in stop["lots"]:
            info = lot.get("public")
            if info and "_seoul_code" in info:
                pairs.append((info, info.pop("_seoul_code")))
    diagnostics["live_candidates"] = len(pairs)
    diagnostics["live_attached"] = 0
    if not pairs:
        return
    from .seoul_parking_live import live_counts

    live = live_counts()
    for info, code in pairs:
        if code in live:
            info["live"] = live[code]
            diagnostics["live_attached"] += 1


def lookup_status(statuses):
    if "permission_required" in statuses:
        return "permission_required"
    if "available" in statuses:
        return "available"
    return "unavailable"


def parking_near(plan):
    """GET /api/plans/{id}/parking 의 응답. 계획은 읽기만 한다."""
    from .intent_discovery import lookup_all
    from .request_usage import cache_hit as count_cache_hit, measure

    rejected = Counter({reason: 0 for reason in REJECTED})
    diagnostics = dict(queries=0, lookups=0, cache_hit=False, received=0, rejected=rejected)

    def result(status, stops=(), message=None):
        diagnostics["rejected"] = dict(rejected)
        return dict(
            status=status,
            stops=list(stops),
            note=NOTE,
            source_type=SOURCE_TYPE,
            message=MESSAGES.get(status, "") if message is None else message,
            diagnostics=diagnostics,
        )

    conditions = plan.get("conditions") or {}
    if conditions.get("mode") == "demo":
        return result("demo")
    if conditions.get("mode") != "real" or not uses_car(Conditions.model_validate(conditions)):
        return result("not_car")
    indices = car_stops(plan)
    if not indices:
        return result("not_car")
    # 네이버 키가 없어도 공공데이터 주차장(외부 호출 없음)은 보여 준다.
    naver = search_enabled()
    course_region = conditions.get("region")
    targets = []
    for i in indices:
        place = plan["places"][i]
        # 코스 지역과, 장소 주소의 시·도(코스 경계 근처 장소) 안의 주차장만 쓴다.
        regions = {r for r in (course_region, region_from_address(place.get("address"))) if r}
        region = course_region or region_from_address(place.get("address")) or ""
        targets.append(
            dict(index=i, place=place, regions=regions, region=region, key=cache_key(place, region))
        )
    cached = store.cached_many(t["key"] for t in targets)
    queries, owners = [], []
    for target in targets:
        if target["key"] in cached or not naver:
            continue
        place = target["place"]
        terms = [("주차장", place["name"])]
        area = neighbourhood(place, target["region"])
        if area:
            terms.append(("공영주차장", area))
        for term, where in terms:
            if len(queries) < MAX_LOOKUPS:
                queries.append((target["index"], term, where))
                owners.append(target["key"])
    diagnostics["queries"] = len(queries)
    found = {}
    if queries:
        # 외부 호출은 이 요청만의 상한(최대 10건) 안에서, 시간당 제공자 예산(lookup_all 의 prepaid)을 거친다.
        with measure(limit=len(queries)):
            answers = lookup_all(queries)
        diagnostics["lookups"] = len(queries)
        for key, (items, status) in zip(owners, answers):
            entry = found.setdefault(key, dict(items=[], statuses=[]))
            entry["items"] += items
            entry["statuses"].append(status)
    per_place, writes = {}, []
    for target in targets:
        key = target["key"]
        if key in cached:
            per_place[key] = cached[key]
            continue
        if not naver:
            per_place[key] = dict(status="key_missing", lots=[], received=0, rejected={})
            continue
        entry = found.get(key, dict(items=[], statuses=["unavailable"]))
        status = lookup_status(entry["statuses"])
        lots, received, reasons = filter_lots(target["place"], entry["items"], target["regions"])
        if status == "available" and not lots:
            status = "not_found"
        row = dict(
            status=status if not lots else "available",
            lots=lots,
            received=received,
            rejected=dict(reasons),
        )
        per_place[key] = row
        writes.append((key, row, CACHE_FOUND_SECONDS if lots else CACHE_EMPTY_SECONDS))
    if writes:
        store.cache_many(writes)
    if naver and targets and not queries:
        diagnostics["cache_hit"] = True
        count_cache_hit("parking_local")
    # 여러 장소에서 같은 주차장이 나오면 가장 가까운 장소 아래에만 둔다.
    nearest = {}
    for target in targets:
        row = per_place[target["key"]]
        diagnostics["received"] += row.get("received", 0)
        rejected.update(row.get("rejected") or {})
        for lot in row["lots"]:
            current = nearest.get(lot["id"])
            if current is None:
                nearest[lot["id"]] = (lot["distance_m"], target["index"])
            else:
                rejected["duplicate"] += 1
                if lot["distance_m"] < current[0]:
                    nearest[lot["id"]] = (lot["distance_m"], target["index"])
    # 공공데이터 주차장: 네이버 결과와 같은 곳이면 요금·운영시간을 붙이고, 아니면 따로 넣는다(가장 가까운 장소 아래에만).
    visit = visit_date(conditions)
    public_near, public_owner = {}, {}
    for target in targets:
        place = target["place"]
        rows = []
        for d, lot in public_parking.nearby(place["lat"], place["lon"], RADIUS_M):
            region = region_from_address(lot["address"])
            if region and region not in target["regions"]:
                continue
            rows.append((d, lot))
            owner = public_owner.get(lot["id"])
            if owner is None or d < owner[0]:
                public_owner[lot["id"]] = (d, target["index"])
        public_near[target["index"]] = rows
    diagnostics["public_candidates"] = len(public_owner)
    diagnostics["public_matched"] = 0
    diagnostics["public_matched_by_name"] = 0
    # 1) 네이버 결과마다 같은 공공데이터 주차장을 찾아 붙인다(쓴 행은 모든 장소에서 다시 쓰지 않음).
    owned, used = {}, set()
    for target in targets:
        row = per_place[target["key"]]
        own = [
            dict(lot, public=None)
            for lot in row["lots"]
            if nearest[lot["id"]][1] == target["index"]
        ]
        for lot in own:
            for _, pub in public_near[target["index"]]:
                if pub["id"] in used:
                    continue
                gap = public_parking.metres(lot["lat"], lot["lon"], pub["lat"], pub["lon"])
                if public_parking.same_lot(lot["name"], pub, gap):
                    lot["public"] = public_parking.details(pub, visit)
                    used.add(pub["id"])
                    diagnostics["public_matched"] += 1
                    break
            if lot["public"] is None:
                # 좌표가 없는 자료(서울 노외 주차장 등)는 같은 시·도·구 + 이름 핵심으로 맞춘다.
                pub = public_parking.by_name(lot["name"], lot["address"])
                if pub and pub["id"] not in used:
                    lot["public"] = public_parking.details(pub, visit)
                    used.add(pub["id"])
                    diagnostics["public_matched"] += 1
                    diagnostics["public_matched_by_name"] += 1
        owned[target["index"]] = own
    stops, statuses = [], []
    for target in targets:
        row = per_place[target["key"]]
        own = owned[target["index"]]
        # 2) 네이버 결과에 없던 공공데이터 주차장은 가장 가까운 장소 아래에만 넣는다.
        for d, pub in public_near[target["index"]]:
            if pub["id"] in used or public_owner[pub["id"]][1] != target["index"]:
                continue
            own.append(public_lot(pub, d, visit))
        own.sort(key=lambda lot: lot["distance_m"])
        lots = own[:PER_STOP]
        status = (
            "available"
            if lots
            else ("not_found" if row["status"] == "available" else row["status"])
        )
        statuses.append(status)
        place = target["place"]
        stops.append(
            dict(
                index=target["index"],
                place_id=place["id"],
                place_name=place["name"],
                lots=lots,
                status=status,
                message="" if lots else MESSAGES.get(status, ""),
            )
        )
    attach_live(stops, diagnostics)
    if "available" in statuses:
        overall = "available"
    elif "permission_required" in statuses:
        overall = "permission_required"
    elif "unavailable" in statuses:
        overall = "unavailable"
    elif "key_missing" in statuses:
        overall = "key_missing"
    else:
        overall = "not_found"
    return result(overall, stops, "" if overall == "available" else None)
