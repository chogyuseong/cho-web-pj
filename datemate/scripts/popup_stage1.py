"""팝업 1단계(1a) 규칙 v1 재측정. 0단계 표본(1페이지)이 아니라 같은 검색어의 2페이지(start=51)를 새로 받아 v0·v1 을 나란히 잰다.

명령(datemate 폴더에서):
  python scripts/popup_stage1.py fetch    블로그 5건(5지역 × 1, start=51, display=50, 최신순). 재시도 없음. 이미 받은 지역은 다시 부르지 않음.
  python scripts/popup_stage1.py coords   새 표본에서 v1 로 매칭된 거점 중 좌표 확인이 필요한 곳만 지역 검색 1건씩, 최대 20건.
  python scripts/popup_stage1.py analyze  저장된 원본만으로 v0·v1 집계(외부 호출 없음). 규칙 v0 은 커밋 f8ebdf4 의 app/popups.py 를
                                          runtime/popup_stage1/v0/popups_v0.py 로 꺼내 둔 파일을 읽는다(호출 전 저장소에서 git show 로 꺼냄).

원본·집계는 runtime/popup_stage1/ (Git 에 올라가지 않음)에만 쓴다. 키는 NAVER_SEARCH_CLIENT_ID / SECRET 에서만 읽고 어디에도 쓰지 않는다.
운영 DB 의 호출 기록·한도에 섞이지 않게 observed_http 를 거치지 않고 httpx 로 직접 부른다(0단계와 같음).
"""

import hashlib
import importlib.util
import json
import os
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import popups  # noqa: E402
from app.popup_hubs import HUBS, HUBS_V0, HUBS_VERSION  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.getenv("DATEMATE_POPUP_STAGE1_DIR") or ROOT / "runtime" / "popup_stage1")
RAW = OUT / "raw"
HOST = "https://naverapihub.apigw.ntruss.com"
REGIONS = ("서울", "부산", "대구", "강원", "전북")
DISPLAY = 50
START = 51
KST = timezone(timedelta(hours=9))
TODAY = date(2026, 11, 14)
MAX_SEARCH_CALLS = 5
MAX_LOCAL_CALLS = 20
REVIEW_PER_REGION = 10


def _env(name):
    value = os.getenv(name, "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1].strip()
    return value


def _headers():
    cid, secret = _env("NAVER_SEARCH_CLIENT_ID"), _env("NAVER_SEARCH_CLIENT_SECRET")
    if not cid or not secret:
        return None
    return {"X-NCP-APIGW-API-KEY-ID": cid, "X-NCP-APIGW-API-KEY": secret}


def call(client, path, params):
    """한 번만 부른다(재시도 없음). 키는 기록하지 않는다."""
    import httpx

    started = time.perf_counter()
    row = dict(http_status=None, latency_ms=None, error=None)
    body = None
    try:
        r = client.get(HOST + path, params=params, headers=_headers())
        row["http_status"] = r.status_code
        if r.status_code == 200:
            try:
                body = r.json()
            except ValueError:
                row["error"] = "invalid_json"
        else:
            row["error"] = r.text[:300]
    except httpx.HTTPError as exc:
        row["error"] = type(exc).__name__
    row["latency_ms"] = round((time.perf_counter() - started) * 1000)
    return dict(
        request=dict(path=path, params=params),
        attempts=[row],
        body=body,
        fetched_at=datetime.now(KST).isoformat(),
    )


def _save(name, data):
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / name).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _load(name):
    path = RAW / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _calls(prefix):
    return sum(
        len(json.loads(p.read_text(encoding="utf-8"))["attempts"])
        for p in RAW.glob(prefix + "*.json")
    )


def fetch():
    import httpx

    if not _headers():
        print("키 없음: 호출하지 않습니다.")
        return 2
    used = _calls("search-")
    with httpx.Client(timeout=10) as client:
        for region in REGIONS:
            name = f"search-blog-{region}.json"
            if _load(name):
                print(f"{name}: 이미 있음")
                continue
            if used >= MAX_SEARCH_CALLS:
                print("검색 호출 상한")
                break
            params = dict(
                query=f"{region} 팝업스토어",
                display=DISPLAY,
                start=START,
                sort="date",
                format="json",
            )
            result = call(client, "/search/v1/blog", params)
            used += 1
            _save(name, result)
            a = result["attempts"][0]
            print(f"{name}: HTTP {a['http_status']} {a['latency_ms']}ms")
    return 0


def _source_date(item):
    v = str(item.get("postdate") or "")
    try:
        return date(int(v[:4]), int(v[4:6]), int(v[6:8])) if len(v) == 8 and v.isdigit() else None
    except ValueError:
        return None


def _v0():
    path = OUT / "v0" / "popups_v0.py"
    spec = importlib.util.spec_from_file_location("popups_v0", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_posts():
    rows = []
    for region in REGIONS:
        raw = _load(f"search-blog-{region}.json")
        if not raw or not raw["body"]:
            continue
        posts = []
        for rank, item in enumerate(raw["body"].get("items") or [], START):
            if not isinstance(item, dict):
                continue
            posts.append(
                dict(
                    region=region,
                    rank=rank,
                    url=item.get("link"),
                    title=popups.normalize_text(item.get("title")),
                    description=popups.normalize_text(item.get("description")),
                    source_date=_source_date(item),
                )
            )
        rows.extend(popups.dedupe_by_url(posts))
    return rows


def coords():
    import httpx

    if not _headers():
        print("키 없음")
        return 2
    counts = Counter()
    v0 = _v0()
    for r in load_posts():
        if not popups.has_popup(r["title"] + " " + r["description"]):
            continue
        text = r["title"] + " \n " + r["description"]
        # v0·v1 어느 쪽이든 매칭한 거점(같은 원본으로 두 규칙의 위치 확인 수를 비교하려고)
        ids = set(popups.hub_match(text, HUBS, r["region"])["ids"])
        ids |= set(v0.hub_match(text, HUBS_V0, r["region"])["ids"])
        for hid in ids:
            counts[hid] += 1
    order = sorted(counts, key=lambda h: (-counts[h], h))
    print(f"v1 로 매칭된 거점 {len(order)}곳: {dict(counts)}")
    by_id = {h["id"]: h for h in HUBS}
    used = _calls("local-")
    with httpx.Client(timeout=10) as client:
        for hid in order:
            name = f"local-{hid}.json"
            if _load(name):
                continue
            if used >= MAX_LOCAL_CALLS:
                print("지역 검색 상한")
                break
            params = dict(
                query=by_id[hid]["local_query"], display=5, start=1, sort="random", format="json"
            )
            result = call(client, "/search/v1/local", params)
            used += 1
            _save(name, result)
            a = result["attempts"][0]
            print(f"{name}: HTTP {a['http_status']} {a['latency_ms']}ms")
    return 0


def _ratio(n, d):
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else f"{n}/0 (-)"


def _jsonable(value):
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _points(module, hubs):
    """같은 지역 검색 원본을 규칙별 검증 함수로 판정(v0 은 첫 통과 항목, v1 은 쇼핑 업종 우선)."""
    by_id = {h["id"]: h for h in hubs}
    out = {}
    for path in sorted(RAW.glob("local-*.json")):
        hid = path.stem[len("local-") :]
        if hid not in by_id:
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw["attempts"][0]["http_status"] != 200:
            out[hid] = dict(status="failed")
            continue
        items = (raw["body"] or {}).get("items") or []
        try:
            out[hid] = module.verify_local_result(by_id[hid], items)
        except Exception as exc:  # v0 은 대전·서울·부산·대구 밖 시·도 이름을 모른다
            out[hid] = dict(status="error", reason=type(exc).__name__)
    return out


def _judge(module, hubs, r, points):
    text = r["title"] + " \n " + r["description"]
    ext = module.extract_period(r["title"], r["description"])
    status = module.post_status(ext, TODAY)
    hub = module.hub_match(text, hubs, r["region"])
    roundup = module.classify_roundup(r["title"], r["description"], hubs)
    located = (
        hub["status"] == "single" and points.get(hub["hub_id"], {}).get("status") == "verified"
    )
    period = ext["period"]
    if ext["status"] == "period":
        if period["year_known"]:
            desc = f"{period['start'] or '?'}~{period['end'] or '?'}"
        else:
            sm, em = period["start_md"], period["end_md"]
            desc = f"{'.'.join(map(str, sm)) if sm else '?'}~{'.'.join(map(str, em)) if em else '?'}(연도 미상)"
    else:
        desc = {"none": "없음", "conflict": "충돌"}[ext["status"]]
    return dict(
        period_status=ext["status"],
        year_known=bool(period and period["year_known"]),
        today=status["status"],
        hub=hub["status"],
        hub_id=hub["hub_id"],
        ids=hub["ids"],
        past_ids=hub.get("past_ids", []),
        roundup=roundup["kind"],
        located=located,
        summary=f"기간 {desc} · 거점 {hub['hub_id'] or hub['status']} · {roundup['kind']}"
        + (f" · 지난/비교 {','.join(hub['past_ids'])}" if hub.get("past_ids") else ""),
    )


def analyze():
    v0 = _v0()
    rows = load_posts()
    pts = {"v0": _points(v0, HUBS_V0), "v1": _points(popups, HUBS)}
    for r in rows:
        r["popup"] = popups.has_popup(r["title"] + " " + r["description"])
        r["v0"] = _judge(v0, HUBS_V0, r, pts["v0"])
        r["v1"] = _judge(popups, HUBS, r, pts["v1"])
    table = []
    for region in REGIONS:
        raw = _load(f"search-blog-{region}.json")
        group = [r for r in rows if r["region"] == region]
        pop = [r for r in group if r["popup"]]
        d = len(pop)
        row = dict(
            region=region,
            http=raw["attempts"][0]["http_status"] if raw else None,
            latency_ms=raw["attempts"][0]["latency_ms"] if raw else None,
            returned=len((raw or {}).get("body", {}).get("items") or [])
            if raw and raw["body"]
            else 0,
            deduped=len(group),
            popup=_ratio(d, len(group)),
            dates=sorted({str(r["source_date"]) for r in group}),
        )
        for v in ("v0", "v1"):
            j = [r[v] for r in pop]
            row[v] = dict(
                period=_ratio(sum(x["period_status"] == "period" for x in j), d),
                conflict=sum(x["period_status"] == "conflict" for x in j),
                year_known=_ratio(sum(x["year_known"] for x in j), d),
                decidable_today=_ratio(sum(x["today"] != "unknown" for x in j), d),
                ended_today=sum(x["today"] == "ended" for x in j),
                hub_single=_ratio(sum(x["hub"] == "single" for x in j), d),
                hub_multiple=sum(x["hub"] == "multiple" for x in j),
                other_region=sum(x["hub"] == "other_region" for x in j),
                located=_ratio(sum(x["located"] for x in j), d),
                roundup=sum(x["roundup"] == "roundup" for x in j),
                past_mentions=sum(bool(x["past_ids"]) for x in j),
            )
        table.append(row)
    review = []
    for region in REGIONS:
        cand = [
            r
            for r in rows
            if r["region"] == region
            and r["popup"]
            and (r["v1"]["period_status"] != "none" or r["v1"]["hub"] in ("single", "multiple"))
        ]
        cand.sort(key=lambda r: hashlib.sha1(popups.canonical_url(r["url"]).encode()).hexdigest())
        review.extend(cand[:REVIEW_PER_REGION])
    changed = [r for r in rows if r["popup"] and r["v0"]["summary"] != r["v1"]["summary"]]
    OUT.mkdir(parents=True, exist_ok=True)
    summary = dict(
        rules=[getattr(v0, "RULES_VERSION", "?"), popups.RULES_VERSION],
        hubs_version=HUBS_VERSION,
        today=TODAY.isoformat(),
        table=table,
        points={k: v for k, v in pts.items()},
    )
    (OUT / "analysis.json").write_text(
        json.dumps(_jsonable(summary), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (OUT / "review.json").write_text(
        json.dumps(_jsonable(review), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (OUT / "changed.json").write_text(
        json.dumps(_jsonable(changed), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    for row in table:
        print(json.dumps(_jsonable(row), ensure_ascii=False))
    print(json.dumps(_jsonable(pts), ensure_ascii=False))
    print(f"검토 {len(review)}건, v0≠v1 {len(changed)}건 → {OUT}")
    return 0


def main(argv):
    commands = dict(fetch=fetch, coords=coords, analyze=analyze)
    if len(argv) < 2 or argv[1] not in commands:
        print(__doc__)
        return 1
    return commands[argv[1]]()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
