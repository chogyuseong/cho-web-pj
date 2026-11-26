"""자동차로 도착하는 장소 근처의 주차장.

결과 화면에서 주차장 패널이 보일 때만 부른다(추천 과정에서는 부르지 않는다). 계획(plan)에는 아무것도
저장하지 않고, 일정·비용·시간도 바꾸지 않는다. 만차 여부는 확인하지 않으므로 만들지 않는다.

찾는 장소는 자동차 구간이 도착하는 장소다(leg_modes.car_position_notes 의 규칙대로 차는 그곳에 선다).
귀가 구간의 도착(집)은 찾지 않는다.
주차장은 공공데이터 전국주차장정보표준데이터(app/public_parking.py, 저장소에 든 파일이라 외부 호출 없음)에서만 찾아
가까운 순으로 장소당 3곳을 보이고, 요금·방문일 운영시간·기준일을 붙인다.
2026-11-20 2단계: 예전에는 네이버 지역 검색 결과('장소명 주차장', '동네 공영주차장')를 거르고 공공데이터와 맞춰 함께 보였다.
검색 결과를 우리 목록의 입력으로 쓰지 않기로 해 뺐다(검색 API 특약 1.1·1.2, docs/naver-terms-stage2-design.ko.md 3.8(b)).
민영 주차장처럼 공공데이터에 없는 곳은 화면의 '네이버 지도에서 주차장 찾기' 링크로 안내한다.
"""

import hashlib
import math
from datetime import date

from . import public_parking
from .leg_modes import leg_mode, uses_car
from .models import Conditions
from .regions import region_from_address

SOURCE_TYPE = "공공데이터포털 전국주차장정보표준데이터"
RADIUS_M = 800
PER_STOP = 3
NOTE = "주차 시간·요금은 일정과 비용에 포함하지 않았어요."
MESSAGES = {
    "not_car": "자동차로 도착하는 장소가 없어요.",
    "demo": "가상 장소에서는 실제 주차장을 검색하지 않습니다.",
    "not_found": f"이 장소 {RADIUS_M}m 안에는 공공데이터에 실린 주차장이 없어요. 민영 주차장은 네이버 지도에서 찾아 주세요.",
}


def car_stops(plan):
    """자동차 구간이 도착하는 장소의 번호. 구간 i 는 장소 i 에 도착한다(귀가 구간은 장소 수 뒤에 있어 빠진다)."""
    legs = plan.get("legs") or []
    return [i for i in range(min(len(legs), len(plan["places"]))) if leg_mode(plan, i) == "car"]


def walk_minutes(km):
    """routes.leg 의 추정 규칙과 같다: 직선거리 × 1.35 ÷ 시속 4km."""
    return max(1, math.ceil(km * 1.35 / 4 * 60))


def visit_date(conditions):
    try:
        return date.fromisoformat(str(conditions.get("visit_date") or ""))
    except ValueError:
        return None


def public_lot(lot, distance_m, visit):
    """공공데이터 주차장 한 곳."""
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


def parking_near(plan):
    """GET /api/plans/{id}/parking 의 응답. 계획은 읽기만 한다."""
    diagnostics = dict(public_candidates=0, public_bus_only=0)

    def result(status, stops=(), message=None):
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
    course_region = conditions.get("region")
    visit = visit_date(conditions)
    # 여러 장소에서 같은 주차장이 나오면 가장 가까운 장소 아래에만 둔다.
    near, owner, bus_lots = {}, {}, set()
    for i in indices:
        place = plan["places"][i]
        # 코스 지역과, 장소 주소의 시·도(코스 경계 근처 장소) 안의 주차장만 쓴다.
        regions = {r for r in (course_region, region_from_address(place.get("address"))) if r}
        rows = []
        for d, lot in public_parking.nearby(place["lat"], place["lon"], RADIUS_M):
            region = region_from_address(lot["address"])
            if region and region not in regions:
                continue
            if public_parking.bus_only(lot["name"]):
                bus_lots.add(lot["id"])
                continue
            rows.append((d, lot))
            if lot["id"] not in owner or d < owner[lot["id"]][0]:
                owner[lot["id"]] = (d, i)
        near[i] = rows
    diagnostics.update(public_candidates=len(owner), public_bus_only=len(bus_lots))
    stops = []
    for i in indices:
        place = plan["places"][i]
        lots = [public_lot(lot, d, visit) for d, lot in near[i] if owner[lot["id"]][1] == i]
        lots = sorted(lots, key=lambda lot: lot["distance_m"])[:PER_STOP]
        status = "available" if lots else "not_found"
        stops.append(
            dict(
                index=i,
                place_id=place["id"],
                place_name=place["name"],
                lots=lots,
                status=status,
                message="" if lots else MESSAGES["not_found"],
            )
        )
    attach_live(stops, diagnostics)
    overall = "available" if any(stop["lots"] for stop in stops) else "not_found"
    return result(overall, stops, "" if overall == "available" else None)
