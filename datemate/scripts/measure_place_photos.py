"""실제 키로 '사진 없는 장소 비율'과 한국관광공사 호출 수를 사진 규칙을 바꾸기 전후로 잰다(2026-11-20 사진 보강, app/tour_places.py).

표본(동네마다): ① 공공 자료 후보 = 중심에서 가까운 관광공사 항목 N 곳(app/public_places.tour_near → tour_place, 추천 후보가 되는 분류만),
               ② 그 동네의 카탈로그 장소(app/catalog, 중심 반경 안, 가까운 순).
전(바꾸기 전 규칙): ① 목록의 대표 사진(firstimage)만 ② 같은 이름·400m·하나뿐인 항목의 대표 사진만.
후(지금 규칙):      ① 대표 사진이 없으면 detailImage2 ② 느슨한 이름·넓은 곳 1km 로 연결하고, 대표 사진이 없으면 detailImage2.
등록 사진(data/place_photos.json)이 있는 장소는 전후 모두 '사진 있음'이다.
'전'은 따로 부르지 않는다: 같은 응답에 예전 규칙(old_same_place)을 적용한다. 지금의 이름 검색은 예전보다 넓게 받으므로(시·도 안 100건)
예전 규칙이 찾을 항목은 이 응답에도 있다 — '전'을 실제보다 좋게 볼 수는 있어도 나쁘게 보지는 않는다.
영업 안내(detailIntro2)는 부르지 않는다(전후가 같은 호출이라 재지 않음).

호출을 아낀다: 관광공사 호출이 --max-calls(기본 90)에 닿으면 더 부르지 않고 그때까지의 결과만 낸다(개발계정 하루 1,000건).
실행(datemate 폴더):  DATEMATE_ENV_FILE=.env python scripts/measure_place_photos.py --json out.json [--per-area 20] [--catalog 8] [--max-calls 90]
키는 출력하지 않는다. DB 는 임시 폴더의 SQLite 라 앱의 저장소·캐시를 건드리지 않는다.
"""

import json
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["DATEMATE_RUNTIME"] = tempfile.mkdtemp(prefix="datemate-photo-measure-")
os.environ["DATABASE_URL"] = ""
for _name in ("GMS_KEY", "NAVER_MAPS_KEY_ID", "NAVER_MAPS_KEY", "NAVER_SEARCH_CLIENT_ID", "NAVER_SEARCH_CLIENT_SECRET"):
    os.environ[_name] = ""
os.environ["EMBEDDING_MODE"] = "demo"
os.environ.setdefault("DATEMATE_PROVIDER_CALLS_PER_HOUR", "5000")
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import httpx  # noqa: E402

from app import public_places, store, tour_places  # noqa: E402
from app.routes import distance  # noqa: E402

AREAS = [
    ("제주 애월", "제주", 33.4630, 126.3100),
    ("서울 성수", "서울", 37.5446, 127.0559),
    ("전주 한옥마을", "전북", 35.8150, 127.1530),
]
RADIUS_KM = 1.5
TOUR_HOST_PATH = "/B551011/"
CALLS = Counter()


class Budget(RuntimeError):
    pass


def install_counter(limit):
    """관광공사 호출을 종류별로 세고, limit 에 닿으면 Budget 을 낸다(앱 코드는 이 예외를 삼키지 않는다)."""
    real = httpx.Client.send

    def send(self, request, *args, **kwargs):
        if TOUR_HOST_PATH in request.url.path:
            if sum(CALLS.values()) >= limit:
                raise Budget()
            CALLS[request.url.path.rsplit("/", 1)[-1]] += 1
        return real(self, request, *args, **kwargs)

    httpx.Client.send = send


def old_same_place(place, rows):
    """바꾸기 전 규칙(main 0410365 app/tour_places.same_place): 같은 이름(띄어쓰기·기호·지점 낱말 무시)·400m·하나뿐."""
    from app.course_search import without_branch

    compact = tour_places._compact
    names = {compact(place.get("name")), compact(without_branch(place.get("name") or ""))}
    names = {n for n in names if len(n) >= 2}
    found = []
    for row in rows:
        title = tour_places.clean_title(row.get("title"))
        if not ({compact(title), compact(without_branch(title))} & names):
            continue
        point = tour_places._point(row)
        if point and distance(place, point) * 1000 <= 400:
            found.append(row)
    return found[0] if len(found) == 1 else None


def registered(place):
    from app.media import photos_for

    return bool(photos_for(place)) or bool(place.get("photos"))


def images(content_id):
    """detailImage2 사진 수(공공누리 제1·제3유형). (수, 상태). 캐시 적중이면 호출이 늘지 않는다."""
    result = tour_places.tour_images(content_id)
    return len(result["photos"]), result["status"]


def measure_listed(area, region, lat, lon, per_area):
    near = public_places.tour_near(lat, lon, RADIUS_KM)
    places = [p for p in (public_places.tour_place(row, region) for row in near["rows"]) if p][:per_area]
    rows = []
    for place in places:
        before = bool(place.get("tour_photo"))
        after, status, extra = before, "listed", 0
        if not before:
            extra, status = images(place["tour_content_id"])
            after = extra > 0
        rows.append(dict(area=area, kind="public", name=place["name"], category=place["category"], before=before, after=after,
                         how=status, extra_photos=extra))
    return near.get("status"), rows


def measure_catalog(area, region, lat, lon, limit):
    from app.catalog import places as catalog_places

    center = dict(lat=lat, lon=lon)
    found = [p for p in catalog_places("real") if not p.get("demo") and p.get("lat") is not None and distance(center, p) <= RADIUS_KM * 2]
    found.sort(key=lambda p: distance(center, p))
    rows = []
    for place in found[:limit]:
        if registered(place):
            rows.append(dict(area=area, kind="catalog", name=place["name"], category=place.get("category"), before=True, after=True, how="registered"))
            continue
        with httpx.Client(timeout=8) as client:
            listing = tour_places._search_rows(place, client, tour_places._base(tour_places._key()))
        old, new = old_same_place(place, listing), tour_places.same_place(place, listing)
        before = bool(old and tour_places.row_photo(old)[0])
        after, how = bool(new and tour_places.row_photo(new)[0]), "none"
        if new:
            how = "exact" if tour_places.match_rows(place, [new])[0] else "loose"
            if not after and str(new.get("contentid") or "").isdigit():
                extra, status = images(new["contentid"])
                after, how = extra > 0, how + "+" + status
        rows.append(dict(area=area, kind="catalog", name=place["name"], category=place.get("category"), before=before, after=after, how=how,
                         keyword=tour_places.search_keyword(place), listed=len(listing), linked=new and new.get("title"),
                         linked_before=old and old.get("title")))
    return rows


def share(rows):
    return dict(places=len(rows), no_photo_before=sum(not r["before"] for r in rows), no_photo_after=sum(not r["after"] for r in rows),
                before_pct=round(100 * sum(not r["before"] for r in rows) / len(rows)) if rows else None,
                after_pct=round(100 * sum(not r["after"] for r in rows) / len(rows)) if rows else None)


def main():
    args = sys.argv[1:]
    option = lambda name, default: int(args[args.index(name) + 1]) if name in args else default
    per_area, catalog_limit, limit = option("--per-area", 20), option("--catalog", 8), option("--max-calls", 90)
    if not tour_places._key():
        sys.exit("TOUR_API_KEY 가 없습니다(DATEMATE_ENV_FILE).")
    store.init()
    install_counter(limit)
    rows, notes, stopped = [], [], False
    for area, region, lat, lon in AREAS:
        try:
            status, listed = measure_listed(area, region, lat, lon, per_area)
            rows += listed
            notes.append(f"{area}: 관광공사 목록 {status}, 공공 후보 {len(listed)}곳")
            rows += measure_catalog(area, region, lat, lon, catalog_limit)
        except Budget:
            stopped = True
            notes.append(f"{area}: 호출 상한({limit})에 닿아 여기서 멈춤")
            break
    first_calls = dict(CALLS)
    # 같은 장소를 한 번 더(다른 사용자가 같은 카드를 여는 경우): 추가 사진은 공용 캐시라 호출이 늘지 않아야 한다.
    repeat_before = sum(CALLS.values())
    try:
        for area, region, lat, lon in AREAS:
            measure_listed(area, region, lat, lon, per_area)
    except Budget:
        stopped = True
    repeat_calls = sum(CALLS.values()) - repeat_before
    public = [r for r in rows if r["kind"] == "public"]
    catalog = [r for r in rows if r["kind"] == "catalog"]
    lookups = [r for r in catalog if r["how"] != "registered"]
    summary = dict(
        all=share(rows), public=share(public), catalog=share(catalog),
        by_area={area: dict(all=share([r for r in rows if r["area"] == area]), public=share([r for r in public if r["area"] == area]),
                            catalog=share([r for r in catalog if r["area"] == area])) for area, *_ in AREAS},
        tour_calls=first_calls, tour_calls_total=sum(first_calls.values()),
        # 장소 카드가 열릴 때 늘어나는 호출 = detailImage2(대표 사진이 없는 연결 항목마다 1건, 7일 공용 캐시).
        extra_calls=first_calls.get("detailImage2", 0), extra_calls_per_place=round(first_calls.get("detailImage2", 0) / len(rows), 2) if rows else None,
        name_searches=first_calls.get("searchKeyword2", 0), name_search_places=len(lookups),
        repeat_calls=repeat_calls, image_cache_hits=public_places.STATS.get("tour_image_cache", 0),
        stats={k: v for k, v in public_places.STATS.items() if k.startswith("tour")}, stopped_at_limit=stopped, notes=notes,
    )
    for row in rows:
        mark = "→ 사진 생김" if row["after"] and not row["before"] else ("사진 있음" if row["after"] else "사진 없음")
        print(f"[{row['area']}] {row['kind']:7} {row['name']} · {mark} · {row['how']}" + (f" · 연결 {row.get('linked')}" if row.get("linked") else ""), flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if "--json" in args:
        Path(args[args.index("--json") + 1]).write_text(json.dumps(dict(summary=summary, rows=rows), ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
