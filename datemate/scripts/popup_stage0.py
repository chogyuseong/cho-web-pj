"""팝업스토어 0단계 실측(docs/popup-stores-spec.md 0-2·5절). 운영 코드와 연결되지 않은 진단 스크립트.

명령(datemate 폴더에서):
  python scripts/popup_stage0.py fetch    실제 검색 호출. 블로그·뉴스 × 5지역 = 최대 10건(뉴스는 서울 1건으로 권한부터 확인).
                                          이미 받은 원본이 있으면 다시 부르지 않는다(--force 로만 다시 부름).
  python scripts/popup_stage0.py coords   표본에서 실제로 매칭된 거점만 지역 검색 1건씩(최대 30건). 이미 받은 거점은 건너뜀.
  python scripts/popup_stage0.py analyze  저장된 원본만으로 다시 집계(외부 호출 없음).

원본과 집계는 runtime/popup_stage0/ (Git 에 올라가지 않음, DATEMATE_POPUP_STAGE0_DIR 로 바꿀 수 있음)에만 쓴다.
키는 환경변수 NAVER_SEARCH_CLIENT_ID / NAVER_SEARCH_CLIENT_SECRET 에서만 읽고 어디에도 쓰지 않는다.
재시도는 실패한 호출당 1회(네트워크 오류·429·5xx 만). 결과 링크를 따라가 원문을 가져오지 않는다. LLM 을 쓰지 않는다.
"""

import hashlib
import json
import os
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import popups  # noqa: E402
from app.popup_hubs import HUBS_V0, HUBS_VERSION  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.getenv("DATEMATE_POPUP_STAGE0_DIR") or ROOT / "runtime" / "popup_stage0")
RAW = OUT / "raw"
HOST = "https://naverapihub.apigw.ntruss.com"
REGIONS = ("서울", "부산", "대구", "강원", "전북")
SOURCES = ("blog", "news")
DISPLAY = 50
KST = timezone(timedelta(hours=9))
TODAY = date(2026, 11, 14)  # 실측일(한국시간). 상태 분포의 기준일
HOME = {
    "서울": dict(name="서울 성수", lat=37.5446, lon=127.0559),
    "부산": dict(name="부산 해운대", lat=35.1631, lon=129.1636),
}
MAX_SEARCH_CALLS = 10
MAX_LOCAL_CALLS = 30
REVIEW_PER_REGION = 20


# ---------------------------------------------------------------- 호출


def _headers():
    cid = os.getenv("NAVER_SEARCH_CLIENT_ID", "").strip()
    secret = os.getenv("NAVER_SEARCH_CLIENT_SECRET", "").strip()
    if not cid or not secret:
        return None
    return {"X-NCP-APIGW-API-KEY-ID": cid, "X-NCP-APIGW-API-KEY": secret}


def _error_code(body_text):
    try:
        data = json.loads(body_text)
    except ValueError:
        return None
    if isinstance(data, dict):
        err = data.get("error") if isinstance(data.get("error"), dict) else data
        for k in ("errorCode", "code", "error_code"):
            if err.get(k):
                return str(err.get(k))
    return None


def call(client, path, params):
    """한 번 부르고, 네트워크 오류·429·5xx 면 한 번만 다시 부른다. 키는 기록하지 않는다."""
    import httpx

    attempts = []
    body = None
    for attempt in (1, 2):
        started = time.perf_counter()
        try:
            r = client.get(HOST + path, params=params, headers=_headers())
            ms = round((time.perf_counter() - started) * 1000)
            row = dict(
                attempt=attempt,
                http_status=r.status_code,
                latency_ms=ms,
                error_code=None,
                error=None,
            )
            if r.status_code == 200:
                try:
                    body = r.json()
                except ValueError:
                    row["error"] = "invalid_json"
            else:
                row["error_code"] = _error_code(r.text)
                row["error_body"] = r.text[:500]
            attempts.append(row)
            if r.status_code == 200 or not (r.status_code == 429 or r.status_code >= 500):
                break
        except httpx.HTTPError as exc:
            ms = round((time.perf_counter() - started) * 1000)
            attempts.append(
                dict(
                    attempt=attempt,
                    http_status=None,
                    latency_ms=ms,
                    error_code=None,
                    error=type(exc).__name__,
                )
            )
    return dict(
        request=dict(path=path, params=params),
        attempts=attempts,
        body=body,
        fetched_at=datetime.now(KST).isoformat(),
    )


def _save(name, data):
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / name).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _load(name):
    path = RAW / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _calls_made(prefix):
    n = 0
    for path in RAW.glob(prefix + "*.json"):
        n += len(json.loads(path.read_text(encoding="utf-8"))["attempts"])
    return n


def fetch(force=False):
    import httpx

    if not _headers():
        print(
            "키 없음: NAVER_SEARCH_CLIENT_ID / NAVER_SEARCH_CLIENT_SECRET 가 비어 있어 호출하지 않습니다."
        )
        return 2
    plan = (
        [("news", "서울")]
        + [("blog", r) for r in REGIONS]
        + [("news", r) for r in REGIONS if r != "서울"]
    )
    used = 0 if force else _calls_made("search-")
    with httpx.Client(timeout=10) as client:
        for source, region in plan:
            name = f"search-{source}-{region}.json"
            if not force and _load(name):
                print(f"{name}: 이미 있음, 건너뜀")
                continue
            if source == "news" and region != "서울":
                probe = _load("search-news-서울.json")
                if not probe or not probe["body"]:
                    print(f"{name}: 뉴스 권한 확인 실패로 건너뜀")
                    continue
            if used >= MAX_SEARCH_CALLS:
                print("검색 호출 상한에 닿아 멈춥니다.")
                break
            params = dict(
                query=f"{region} 팝업스토어",
                display=DISPLAY,
                start=1,
                sort="date",
                format="json",
            )
            result = call(client, f"/search/v1/{source}", params)
            used += len(result["attempts"])
            _save(name, result)
            last = result["attempts"][-1]
            print(
                f"{name}: HTTP {last['http_status']} {last.get('error_code') or ''} {last['latency_ms']}ms"
            )
    return 0


def coords(force=False):
    import httpx

    if not _headers():
        print("키 없음: 호출하지 않습니다.")
        return 2
    matched = sorted({hid for row in load_posts() if row["popup"] for hid in row["hub"]["ids"]})
    print(f"표본에서 매칭된 거점 {len(matched)}곳")
    by_id = {h["id"]: h for h in HUBS_V0}
    used = 0 if force else _calls_made("local-")
    with httpx.Client(timeout=10) as client:
        for hid in matched:
            name = f"local-{hid}.json"
            if not force and _load(name):
                continue
            if used >= MAX_LOCAL_CALLS:
                print("지역 검색 상한에 닿아 멈춥니다.")
                break
            params = dict(
                query=by_id[hid]["local_query"],
                display=5,
                start=1,
                sort="random",
                format="json",
            )
            result = call(client, "/search/v1/local", params)
            used += len(result["attempts"])
            _save(name, result)
            print(
                f"{name}: HTTP {result['attempts'][-1]['http_status']} {result['attempts'][-1]['latency_ms']}ms"
            )
    return 0


# ---------------------------------------------------------------- 집계


def _source_date(source, item):
    if source == "blog":
        v = str(item.get("postdate") or "")
        try:
            return (
                date(int(v[:4]), int(v[4:6]), int(v[6:8])) if len(v) == 8 and v.isdigit() else None
            )
        except ValueError:
            return None
    try:
        return parsedate_to_datetime(str(item.get("pubDate"))).astimezone(KST).date()
    except (TypeError, ValueError, IndexError):
        return None


def _jsonable(value):
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def load_posts():
    rows = []
    for source in SOURCES:
        for region in REGIONS:
            raw = _load(f"search-{source}-{region}.json")
            if not raw or not raw["body"]:
                continue
            items = raw["body"].get("items") or []
            posts = []
            for rank, item in enumerate(items, 1):
                if not isinstance(item, dict):
                    continue
                posts.append(
                    dict(
                        region=region,
                        source=source,
                        rank=rank,
                        url=item.get("link"),
                        original_url=item.get("originallink"),
                        title=popups.normalize_text(item.get("title")),
                        description=popups.normalize_text(item.get("description")),
                        source_date=_source_date(source, item),
                    )
                )
            for p in popups.dedupe_by_url(posts):
                text = p["title"] + " \n " + p["description"]
                p["popup"] = popups.has_popup(text)
                ext = popups.extract_period(p["title"], p["description"])
                p["extraction"] = ext
                p["status_today"] = popups.post_status(ext, TODAY)
                cf = (
                    popups.counterfactual_period(ext["period"], p["source_date"])
                    if ext["status"] == "period"
                    else None
                )
                p["cf_period"] = cf
                p["cf_status_today"] = popups.visit_status(cf, TODAY) if cf else p["status_today"]
                p["hub"] = popups.hub_match(text, HUBS_V0, region)
                p["roundup"] = popups.classify_roundup(p["title"], p["description"], HUBS_V0)
                p["name"] = popups.event_name(p["title"], HUBS_V0)
                rows.append(p)
    return rows


def _ratio(n, d):
    return f"{n}/{d} ({(100 * n / d):.0f}%)" if d else f"{n}/0 (-)"


def _local_points():
    by_id = {h["id"]: h for h in HUBS_V0}
    out = {}
    for path in sorted(RAW.glob("local-*.json")):
        hid = path.stem[len("local-") :]
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = (raw["body"] or {}).get("items") or []
        out[hid] = dict(
            verdict=popups.verify_local_result(by_id[hid], items),
            attempts=raw["attempts"],
            items=[
                dict(
                    title=popups.normalize_text(i.get("title")),
                    address=i.get("roadAddress") or i.get("address"),
                    mapx=i.get("mapx"),
                    mapy=i.get("mapy"),
                    category=i.get("category"),
                )
                for i in items
                if isinstance(i, dict)
            ],
        )
    return out


def analyze():
    rows = load_posts()
    points = _local_points()
    calls = []
    for path in sorted(RAW.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        for a in raw["attempts"]:
            calls.append(
                dict(
                    file=path.name,
                    **{
                        k: a.get(k)
                        for k in (
                            "attempt",
                            "http_status",
                            "error_code",
                            "latency_ms",
                            "error",
                        )
                    },
                )
            )
    table = []
    for source in SOURCES:
        for region in REGIONS:
            raw = _load(f"search-{source}-{region}.json")
            group = [r for r in rows if r["source"] == source and r["region"] == region]
            pop = [r for r in group if r["popup"]]
            d = len(pop)
            ext = Counter(r["extraction"]["status"] for r in pop)
            full_year = [
                r
                for r in pop
                if r["extraction"]["status"] == "period" and r["extraction"]["period"]["year_known"]
            ]
            decidable = [r for r in pop if r["status_today"]["status"] != "unknown"]
            cf_decidable = [r for r in pop if r["cf_status_today"]["status"] != "unknown"]
            hub = Counter(r["hub"]["status"] for r in pop)
            named = [r for r in pop if r["name"]["name"]]
            roundup = Counter(r["roundup"]["kind"] for r in pop)
            eligible = [
                r
                for r in pop
                if r["roundup"]["kind"] == "single"
                and r["hub"]["status"] == "single"
                and r["name"]["name"]
            ]
            cards = popups.group_posts(
                [
                    dict(
                        url=r["url"],
                        hub_id=r["hub"]["hub_id"],
                        name_key=r["name"]["key"],
                        period=r["extraction"]["period"],
                        conflict=r["extraction"]["status"] == "conflict",
                    )
                    for r in eligible
                ]
            )
            located = [
                r
                for r in pop
                if r["hub"]["status"] == "single"
                and points.get(r["hub"]["hub_id"], {}).get("verdict", {}).get("status")
                == "verified"
            ]
            attempts = raw["attempts"] if raw else []
            table.append(
                dict(
                    region=region,
                    source=source,
                    requests=len(attempts),
                    http=[a["http_status"] for a in attempts],
                    error_codes=[a.get("error_code") for a in attempts if a.get("error_code")],
                    latency_ms=[a["latency_ms"] for a in attempts],
                    api_total=(raw["body"] or {}).get("total") if raw else None,
                    returned=len((raw["body"] or {}).get("items") or [])
                    if raw and raw["body"]
                    else 0,
                    deduped=len(group),
                    popup=_ratio(d, len(group)),
                    popup_n=d,
                    period_any=_ratio(ext["period"], d),
                    period_conflict=ext["conflict"],
                    period_full_year=_ratio(len(full_year), d),
                    decidable_today=_ratio(len(decidable), d),
                    cf_decidable_today=_ratio(len(cf_decidable), d),
                    hub_single=_ratio(hub["single"], d),
                    hub_multiple=hub["multiple"],
                    hub_other_region=hub["other_region"],
                    named=_ratio(len(named), d),
                    roundup=roundup["roundup"],
                    roundup_ambiguous=roundup["ambiguous"],
                    eligible_posts=len(eligible),
                    cards=len(cards),
                    cards_conflict=sum(1 for c in cards if c["conflict"]),
                    held_no_period=d - ext["period"],
                    held_no_hub=d - hub["single"],
                    held_no_name=d - len(named),
                    located_posts=len(located),
                )
            )
    # 수동 검토 표본: 지역별로 기간 후보가 있거나 거점이 매칭된 글을 URL 해시 순으로 최대 20건(블로그·뉴스 합쳐서).
    review = []
    for region in REGIONS:
        cand = [
            r
            for r in rows
            if r["region"] == region
            and r["popup"]
            and (
                r["extraction"]["status"] != "none" or r["hub"]["status"] in ("single", "multiple")
            )
        ]
        cand.sort(key=lambda r: hashlib.sha1(popups.canonical_url(r["url"]).encode()).hexdigest())
        review.extend(cand[:REVIEW_PER_REGION])
    # 근접성: 거점 위치가 확인된 글(단일 거점)과 카드의 홈 동네 기준 직선거리
    proximity = {}
    for region, home in HOME.items():
        dists = []
        for r in rows:
            if r["region"] != region or not r["popup"] or r["hub"]["status"] != "single":
                continue
            v = points.get(r["hub"]["hub_id"], {}).get("verdict", {})
            if v.get("status") != "verified":
                continue
            dists.append(
                dict(
                    url=r["url"],
                    hub=r["hub"]["hub_id"],
                    level=v["level"],
                    km=round(popups.distance_km(home, v["point"]), 2),
                )
            )
        hubs_seen = {}
        for x in dists:
            hubs_seen[x["hub"]] = x["km"]
        proximity[region] = dict(
            home=home,
            posts=len(dists),
            within_2km=sum(1 for x in dists if x["km"] <= 2),
            within_5km=sum(1 for x in dists if x["km"] <= 5),
            within_10km=sum(1 for x in dists if x["km"] <= 10),
            over_10km=sum(1 for x in dists if x["km"] > 10),
            hubs=hubs_seen,
        )
    # 사전 후보: 매칭되지 않은 글의 제목에서 자주 나온 낱말(공식 수치에 쓰지 않음)
    words = Counter()
    for r in rows:
        if r["popup"] and r["hub"]["status"] == "none":
            for w in set(popups.re.findall(r"[가-힣A-Za-z0-9&]{2,}", r["title"])):
                words[(r["region"], w)] += 1
    summary = dict(
        hubs_version=HUBS_VERSION,
        rules_version=popups.RULES_VERSION,
        today=TODAY.isoformat(),
        calls=calls,
        table=table,
        proximity=proximity,
        local=points,
        frequent_unmatched_words=[
            dict(region=k[0], word=k[1], posts=v) for k, v in words.most_common(200)
        ],
    )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "analysis.json").write_text(
        json.dumps(_jsonable(summary), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (OUT / "posts.json").write_text(
        json.dumps(_jsonable(rows), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (OUT / "review.json").write_text(
        json.dumps(_jsonable(review), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    for row in table:
        print(json.dumps(row, ensure_ascii=False))
    print(json.dumps(_jsonable(proximity), ensure_ascii=False))
    print(f"검토 표본 {len(review)}건, 글 {len(rows)}건, 호출 기록 {len(calls)}건 → {OUT}")
    return 0


def main(argv):
    if len(argv) < 2 or argv[1] not in ("fetch", "coords", "analyze"):
        print(__doc__)
        return 1
    force = "--force" in argv
    return dict(fetch=fetch, coords=coords, analyze=lambda force=False: analyze())[argv[1]](
        force=force
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
