"""동네 기준 반경(기본 2.5km) 밖에 있는 종류를 잰다(배포-이어가기.txt 7절 '강릉 안목해변처럼 전시·공방이 반경 밖인 동네').

예전 판단(6-1)은 네이버 지역 검색 후보 때의 것이다. 지금 후보는 한국관광공사 시·군·구 목록을 거리로 거른 것이라(app/public_places.tour_near),
같은 목록을 반경 10km 로 받아 종류(category)별로 가장 가까운 곳과 2.5·5·10km 안의 수를 센다. 그리고 실제 추천(app.recommendation_service.generate)을
요청 활동별로 돌려, 요청한 종류가 코스에 들어갔는지·조건이 완화됐는지를 본다.

실제 공공데이터포털 API 를 부른다(관광공사 목록은 시·군·구마다 타입 5건, 상가정보 몇 건). 키는 DATEMATE_ENV_FILE 이 가리키는 .env 에서 읽고 출력하지 않는다.
DB 는 임시 폴더의 SQLite 라 앱의 저장소·캐시를 건드리지 않는다. 네이버 Maps 키는 비워 이동 시간을 거리 추정으로 통일한다.

실행(datemate 폴더): DATEMATE_ENV_FILE=.env python scripts/measure_neighborhood_reach.py --json out.json  [--no-plans]
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import measure_public_candidates as base  # 환경 설정(임시 DB·키 비우기)과 run_case 를 함께 쓴다.

from app import store  # noqa: E402

RINGS = (2.5, 5.0, 10.0)
POINTS = [
    ("강릉 안목해변", "강원", 37.7716, 128.9477),
    ("경주 황리단길", "경북", 35.8375, 129.2095),
    ("전주 한옥마을", "전북", 35.8150, 127.1530),
    ("제주 애월", "제주", 33.4630, 126.3100),
    ("부산 해운대", "부산", 35.1631, 129.1635),
]
GANGNEUNG = [
    base.case("강릉 기본", "강원", "강원 강릉 안목해변 지역 중심", 37.7716, 128.9477),
    base.case("강릉 전시+카페", "강원", "강원 강릉 안목해변 지역 중심", 37.7716, 128.9477, request="전시 보고 카페 가기"),
    base.case("강릉 공방 체험", "강원", "강원 강릉 안목해변 지역 중심", 37.7716, 128.9477, request="공방 체험 하고 싶어"),
    base.case("강릉 문화·예술", "강원", "강원 강릉 안목해변 지역 중심", 37.7716, 128.9477, themes=["문화·예술"]),
]


def reach(name, region, lat, lon):
    from app.public_places import tour_near, tour_place
    from app.routes import distance

    data = tour_near(lat, lon, max(RINGS))
    center, by_kind = dict(lat=lat, lon=lon), defaultdict(list)
    for row in data["rows"]:
        place = tour_place(row, region)
        if place:
            by_kind[place["category"]].append((round(distance(center, place), 2), place["name"]))
    kinds = {}
    for kind, items in sorted(by_kind.items()):
        items.sort()
        kinds[kind] = dict(
            nearest_km=items[0][0],
            nearest=items[0][1],
            **{f"within_{ring:g}km": sum(km <= ring for km, _ in items) for ring in RINGS},
        )
    return dict(point=name, region=region, status=data["status"], districts=data.get("districts"), kinds=kinds)


def plan_row(label, fields, owner):
    row = base.run_case(label, fields, owner, False)
    picked = Counter(p["kind"] for p in row.get("places", []))
    return dict(
        label=label,
        status=row.get("status"),
        plans=row["plans"],
        strict=row["strict"],
        unmet=row.get("unmet"),
        reasons=row.get("reasons"),
        pool=row.get("pool"),
        pool_by_kind=row.get("pool_by_kind"),
        course_kinds=dict(picked),
        courses=row.get("courses"),
        calls=row.get("calls"),
    )


def main():
    args = sys.argv[1:]
    store.init()
    out = dict(points=[], plans=[])
    for point in POINTS:
        row = reach(*point)
        out["points"].append(row)
        print(f"{row['point']}: {row['status']} · 시·군·구 {row['districts']}", flush=True)
        for kind, v in row["kinds"].items():
            rings = " ".join(f"{ring:g}km {v[f'within_{ring:g}km']}" for ring in RINGS)
            print(f"   {kind}: 가장 가까운 곳 {v['nearest_km']}km({v['nearest']}) · {rings}", flush=True)
    if "--no-plans" not in args:
        owner = store.owner_of("measure-reach")
        for label, fields in GANGNEUNG:
            row = plan_row(label, fields, owner)
            out["plans"].append(row)
            print(f"[추천] {label}: {row['status']} · {row['plans']}안(조건 그대로 {row['strict']}) · 미충족 {row['unmet']} · "
                  f"후보 {row['pool']} {row['pool_by_kind']} · 코스 종류 {row['course_kinds']}", flush=True)
            for course in row["courses"] or []:
                print("     ", course, flush=True)
    out["public_api_calls"] = base.public_stats()
    print("공공 API 호출·캐시:", out["public_api_calls"], flush=True)
    if "--json" in args:
        Path(args[args.index("--json") + 1]).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
