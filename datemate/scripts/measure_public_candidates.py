"""실제 키로 추천 후보의 출처를 바꾸기 전후를 잰다(docs/naver-terms-stage2-design.ko.md 3.8(b)·3.5(b), 4절 3단계).

같은 조건 표본으로 추천을 만들고 다음을 기록한다.
  · 코스 3안: 받은 안 수, 조건을 그대로 지킨 안 수(완화·대안 아님, 미충족 조건 없음), 실패·빈 결과
  · 후보 수(추천이 쓴 후보 풀)와 출처별·종류별 수
  · 이동 시간(안마다 구간 합, 가장 긴 구간)
  · 코스 장소의 '확인 필요' 비율: 영업시간(일정 계산용 값), 영업 안내 글(한국관광공사), 가격, 사진(등록 사진·한국관광공사 사진)
  · 외부 호출 수(호스트별)와, 새 코드에서는 공공 API 별 호출·캐시 적중(app/public_places.STATS)

이 스크립트는 바꾸기 전 코드(main)와 바꾼 뒤 코드 양쪽에서 그대로 돌아가야 한다(양쪽에 있는 함수만 쓴다).
실제 외부 API 를 부른다(네이버 검색, 공공데이터포털). 키는 DATEMATE_ENV_FILE 이 가리키는 .env 에서 읽고 출력하지 않는다.
DB 는 임시 폴더의 SQLite 라 앱의 저장소·캐시를 건드리지 않는다. 네이버 Maps 키는 비워 이동 시간을 거리 추정으로 통일한다.

실행(datemate 폴더, 의존성이 깔린 환경):
  DATEMATE_ENV_FILE=.env python scripts/measure_public_candidates.py --set seoul --label before --json out.json
  --set seoul|outside|all   --repeat  (같은 조건을 다른 사용자로 한 번 더: 사용자 사이 캐시 적중 확인)
  --explore  (둘러보기 호출 수도 잰다)   --no-info  (장소별 사진·영업 안내 조회를 건너뜀: TourAPI 호출을 아낌)
"""

import json
import os
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["DATEMATE_RUNTIME"] = tempfile.mkdtemp(prefix="datemate-public-measure-")
os.environ["DATABASE_URL"] = ""
for _key in ("GMS_KEY", "NAVER_MAPS_KEY_ID", "NAVER_MAPS_KEY", "DATEMATE_OPERATING_EVIDENCE_FILE"):
    os.environ[_key] = ""
os.environ["EMBEDDING_MODE"] = "demo"
os.environ.setdefault("DATEMATE_PROVIDER_CALLS_PER_HOUR", "5000")
os.environ.setdefault("DATEMATE_RECOMMENDATIONS_PER_MINUTE", "1000")
os.environ.setdefault("DATEMATE_USER_RECOMMENDATIONS_PER_MINUTE", "1000")
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app import naver_cache, store  # noqa: E402
from app.models import Conditions  # noqa: E402

VISIT = "2026-11-21"  # 토요일
BASE = dict(mode="real", allow_estimates=True, include_meal=True, start="13:00", end="19:00", count=3, visit_date=VISIT)


def case(label, region, name, lat, lon, **patch):
    origin = dict(name=name, lat=lat, lon=lon)
    return label, dict(BASE, region=region, origin=origin, area_center=origin, **patch)


SEOUL = [
    case("성수 기본+식사", "서울", "서울 성수역 지역 중심", 37.5446, 127.0559),
    case("홍대 카페+문화", "서울", "서울 홍대입구역 지역 중심", 37.5572, 126.9254, themes=["카페·미식", "문화·예술"]),
    case("강남 볼링+맛집", "서울", "서울 강남역 지역 중심", 37.4979, 127.0276, request="볼링 치고 맛집 가고 싶어", transport="transit"),
    case("익선동 전시+카페", "서울", "서울 종로3가역 지역 중심", 37.5716, 126.9916, request="전시 보고 카페 가기"),
    case("잠실 오락+식사", "서울", "서울 잠실역 지역 중심", 37.5133, 127.1001, themes=["오락·놀이"]),
    case("이태원 저녁", "서울", "서울 이태원역 지역 중심", 37.5345, 126.9946, start="17:00", end="22:00"),
    case("망원 카페 집중", "서울", "서울 망원역 지역 중심", 37.556, 126.901, themes=["카페·미식"], theme_mode="focus", include_meal=False),
    case("건대 방탈출+맛집", "서울", "서울 건대입구역 지역 중심", 37.5404, 127.0692, request="방탈출 하고 맛집 가기"),
    case("노원 기본+식사", "서울", "서울 노원역 지역 중심", 37.6555, 127.0616),
    case("신림 공방", "서울", "서울 신림역 지역 중심", 37.4842, 126.9297, request="공방 체험 하고 싶어"),
    case("혜화 공연+저녁", "서울", "서울 혜화역 지역 중심", 37.5823, 127.0019, request="연극 보고 저녁 먹기", start="15:00", end="21:00"),
    case("여의도 산책+식사", "서울", "서울 여의도역 지역 중심", 37.5216, 126.9243, themes=["산책·풍경"]),
]
OUTSIDE = [
    case("부산 해운대 기본", "부산", "부산 해운대역 지역 중심", 35.1631, 129.1635),
    case("전주 한옥마을 기본", "전북", "전북 전주 한옥마을 지역 중심", 35.8150, 127.1530),
    case("강릉 안목해변 기본", "강원", "강원 강릉 안목해변 지역 중심", 37.7716, 128.9477),
    case("대구 동성로 카페+오락", "대구", "대구 동성로 지역 중심", 35.8690, 128.5940, themes=["카페·미식", "오락·놀이"]),
    case("경주 황리단길 기본", "경북", "경북 경주 황리단길 지역 중심", 35.8375, 129.2095),
    case("제주 애월 카페(자동차)", "제주", "제주 애월읍 지역 중심", 33.4630, 126.3100, transport="car", themes=["카페·미식", "산책·풍경"]),
]
EXPLORE = [("서울", "", ""), ("서울", "카페", ""), ("서울", "", "성수"), ("부산", "", ""), ("전북", "맛집", "전주 한옥마을")]


def provider_calls():
    with store.connect() as db:
        rows = db.execute("SELECT provider,SUM(calls),SUM(errors) FROM provider_metrics GROUP BY provider").fetchall()
    return {row[0]: (int(row[1] or 0), int(row[2] or 0)) for row in rows}


def delta(before, after):
    out = {}
    for provider, (calls, errors) in after.items():
        old = before.get(provider, (0, 0))
        if calls - old[0] or errors - old[1]:
            out[provider] = dict(calls=calls - old[0], errors=errors - old[1])
    return out


def public_stats():
    """새 코드의 공공 API 별 호출·캐시 적중. 바꾸기 전 코드에는 없다."""
    try:
        from app import public_places
    except ImportError:
        return None
    return dict(public_places.STATS)


def source_of(place):
    pid = str(place.get("id") or "")
    kind = str(place.get("source_type") or "")
    if pid.startswith(("discovered:", "food:naver-")) or "네이버" in kind:
        return "네이버 지역 검색"
    if pid.startswith("public:tour-"):
        return "한국관광공사"
    if pid.startswith("public:store-"):
        return "상가정보"
    if pid.startswith("food:"):
        return "식당 시드"
    return "카탈로그"


def kind_of(place):
    if place.get("meal") or str(place.get("id", "")).startswith("food:"):
        return "식사"
    return place.get("category") or "기타"


def unmet(plan):
    return [r["condition"] for r in plan.get("condition_checks") or [] if r.get("state") == "unmet" and r.get("condition") != "stay_minutes"]


def place_info(place, lookups):
    """한 장소의 정보 유무. lookups=False 면 외부 조회 없이 장소에 실린 값만 본다."""
    from app.media import photos_for

    hours = place.get("hours") is not None
    photo = bool(photos_for(place)) or bool(place.get("photos")) or bool(place.get("tour_photo"))
    notice = bool(place.get("tour_hours"))
    if lookups and not (photo and notice):
        from app.tour_places import tour_info

        info = tour_info(place)
        photo = photo or bool(info.get("photo"))
        notice = notice or bool(info.get("hours") or info.get("rest"))
    return dict(hours=hours, hours_notice=notice, photo=photo)


def run_case(label, fields, owner, lookups):
    from app.quality import pool
    from app.recommendation_service import generate

    c = Conditions(**fields)
    before_calls, before_public, started = provider_calls(), public_stats(), time.perf_counter()
    row = dict(label=label, region=c.region)
    try:
        result = generate(c, owner)
    except Exception as exc:  # 실패도 결과다(실패 비율).
        row.update(status="error", error=type(exc).__name__, plans=0, strict=0, seconds=round(time.perf_counter() - started, 1))
        return row
    row["seconds"] = round(time.perf_counter() - started, 1)
    row["calls"] = delta(before_calls, provider_calls())
    after_public = public_stats()
    if after_public is not None:
        row["public_api"] = {k: v - (before_public or {}).get(k, 0) for k, v in after_public.items() if v - (before_public or {}).get(k, 0)}
    plans = result.get("plans") or []
    strict = [p for p in plans if not p.get("best_effort") and not p.get("search_adjustments") and not unmet(p)]
    row.update(status=result.get("status"), plans=len(plans), strict=len(strict),
               unmet=sorted({x for p in plans for x in unmet(p)}), reasons=(result.get("reasons") or [])[:3])
    # 후보 풀: 추천이 마지막에 쓴 조건(동네 기준점 포함)으로 다시 센다. 같은 사용자 범위라 그 추천이 찾은 후보가 보인다.
    conditions = Conditions.model_validate(plans[0]["conditions"]) if plans else c
    with naver_cache.scope(owner):
        candidates = pool(conditions)
    row["pool"] = len(candidates)
    row["pool_by_source"] = dict(Counter(source_of(p) for p in candidates))
    row["pool_by_kind"] = dict(Counter(kind_of(p) for p in candidates))
    legs = [sum(leg["minutes"] or 0 for leg in p["legs"]) for p in plans]
    row["travel_minutes"] = legs
    row["longest_leg"] = [max((leg["minutes"] or 0 for leg in p["legs"]), default=0) for p in plans]
    places, seen = [], set()
    for plan in plans:
        for place, cost in zip(plan["places"], plan["costs"]):
            if place["id"] in seen:
                continue
            seen.add(place["id"])
            with naver_cache.scope(owner):
                info = place_info(place, lookups)
            # 가격: 등록·확인된 단가(confirmed)만 '있음'. 계획용 가정 금액(planning_assumption)과 미확인은 '확인 필요'.
            info.update(price=cost.get("status") == "confirmed", price_assumed=cost.get("price_kind") == "planning_assumption",
                        price_status=cost.get("status"), source=source_of(place), kind=kind_of(place), name=place["name"])
            places.append(info)
    row["places"] = places
    row["courses"] = [" → ".join(p["name"] for p in plan["places"]) for plan in plans]
    return row


def run_explore(region, activity, q, owner):
    from app import explore

    before_calls, before_public, started = provider_calls(), public_stats(), time.perf_counter()
    with naver_cache.scope(owner):
        data = explore.results(region, activity, q)
    row = dict(region=region, activity=activity, q=q, status=data.get("status"), places=len(data.get("places") or []),
               naver_blocks=len(data.get("naver_blocks") or []), seconds=round(time.perf_counter() - started, 1),
               calls=delta(before_calls, provider_calls()))
    after_public = public_stats()
    if after_public is not None:
        row["public_api"] = {k: v - (before_public or {}).get(k, 0) for k, v in after_public.items() if v - (before_public or {}).get(k, 0)}
    return row


def share(rows, key, value=False):
    return round(100 * sum(r[key] is value for r in rows) / len(rows)) if rows else None


def summarize(rows):
    done = [r for r in rows if r.get("status") != "error"]
    places = [p for r in done for p in r.get("places", [])]
    travel = [m for r in done for m in r.get("travel_minutes", [])]
    longest = [m for r in done for m in r.get("longest_leg", [])]
    hosts = Counter()
    for r in done:
        for host, v in (r.get("calls") or {}).items():
            hosts[host] += v["calls"]
    public = Counter()
    for r in done:
        public.update(r.get("public_api") or {})
    return dict(
        cases=len(rows),
        errors=len(rows) - len(done),
        empty=sum(r["plans"] == 0 for r in done),
        three_plans=sum(r["plans"] >= 3 for r in done),
        plans_avg=round(sum(r["plans"] for r in done) / len(done), 2) if done else None,
        strict_cases=sum(r["strict"] > 0 for r in done),
        strict_plan_share=round(100 * sum(r["strict"] for r in done) / max(1, sum(r["plans"] for r in done))),
        pool_avg=round(sum(r.get("pool", 0) for r in done) / len(done), 1) if done else None,
        pool_min=min((r.get("pool", 0) for r in done), default=None),
        travel_avg=round(sum(travel) / len(travel), 1) if travel else None,
        longest_leg_avg=round(sum(longest) / len(longest), 1) if longest else None,
        places=len(places),
        hours_unknown_pct=share(places, "hours"),
        hours_notice_missing_pct=share(places, "hours_notice"),
        price_unknown_pct=share(places, "price"),
        price_assumed_pct=share(places, "price_assumed", True),
        photo_missing_pct=share(places, "photo"),
        place_sources=dict(Counter(p["source"] for p in places)),
        seconds_avg=round(sum(r["seconds"] for r in rows) / len(rows), 1) if rows else None,
        calls_by_host=dict(hosts),
        calls_per_case={host: round(n / len(done), 1) for host, n in hosts.items()} if done else {},
        public_api=dict(public),
    )


def main():
    args = sys.argv[1:]
    which = args[args.index("--set") + 1] if "--set" in args else "seoul"
    label = args[args.index("--label") + 1] if "--label" in args else "run"
    cases = dict(seoul=SEOUL, outside=OUTSIDE, all=SEOUL + OUTSIDE)[which]
    store.init()
    owner = store.owner_of("measure-" + label)
    rows = []
    for name, fields in cases:
        with naver_cache.scope(owner):
            pass
        row = run_case(name, fields, owner, "--no-info" not in args)
        rows.append(row)
        print(f"[{label}] {name}: 상태 {row.get('status')} · {row['plans']}안(조건 그대로 {row['strict']}) · 후보 {row.get('pool')} "
              f"{row.get('pool_by_source')} · {row['seconds']}초 · 호출 {row.get('calls')} {row.get('public_api') or ''}", flush=True)
        for course in row.get("courses", []):
            print("     ", course, flush=True)
    out = dict(label=label, set=which, visit=VISIT, summary=summarize(rows), rows=rows)
    if "--repeat" in args:
        other = store.owner_of("measure-repeat-" + label)
        again = [run_case(name, fields, other, False) for name, fields in cases]
        out["repeat_summary"] = summarize(again)
        out["repeat_rows"] = again
    if "--explore" in args:
        explorer = store.owner_of("measure-explore-" + label)
        first = [run_explore(*row, explorer) for row in EXPLORE]
        second = [run_explore(*row, store.owner_of("measure-explore2-" + label)) for row in EXPLORE]
        out["explore"] = dict(first=first, other_user=second)
        for row in first + second:
            print(f"[{label}] 둘러보기 {row['region']} {row['activity']} {row['q']}: {row['status']} · 장소 {row['places']} · "
                  f"네이버 블록 {row['naver_blocks']} · 호출 {row['calls']} {row.get('public_api') or ''}", flush=True)
    print(json.dumps(out["summary"], ensure_ascii=False, indent=1))
    if "repeat_summary" in out:
        print("다른 사용자로 다시:", json.dumps(out["repeat_summary"], ensure_ascii=False, indent=1))
    if "--json" in args:
        Path(args[args.index("--json") + 1]).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
