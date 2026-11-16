"""팝업 둘러보기 API (1단계 1a): GET /api/popups?region=&visit_date=&q=

범위는 "출처 중심 팝업 탐색"이다(docs/popup-stores-spec.md 0-5).
- 네이버 블로그 검색 결과 글 하나가 항목 하나다. 제목·요약·URL 은 내용을 바꾸지 않는다(태그·엔티티만 텍스트로 정규화).
  행사명 추출·묶기는 쓰지 않는다.
- 데이트메이트가 읽은 정보(기간·거점·위치 등급)는 항목의 별도 필드로 둔다. 화면은 이것을 원문 인용과 나눠 "검색 요약에서 읽은 …"으로 보여 준다.
- 방문일 상태는 캐시하지 않고 요청마다 계산한다(visit_date 가 없으면 한국시간 오늘).

캐시와 외부 호출
- 원본 검색 결과: 성공 1시간, 팝업 글 0건 10분, 실패는 캐시하지 않음. 키에 지역·정규화 검색어·조회 조건·규칙/사전 버전.
- 거점 좌표 판정: 7일(기존 서비스의 최장 지역 검색 보관 기간과 같게). 판정에 필요한 최소값(상태·등급·좌표)만 남긴다.
- 요청당 외부 호출: 블로그 1 + 좌표가 캐시에 없는 거점 최대 3. 재시도 없음. 시간 제한 10초. 모두 observed_http 를 거친다.
- 같은 캐시 키의 동시 호출은 키별 잠금으로 한 번만 부르고, 잠금은 짧게만 기다린다(image_search 와 같은 2.5초).
- 외부 호출이 필요한 요청만 IP 대역별 전용 한도(분당 3회·시간당 30회)를 쓴다. 캐시로 답하는 요청은 한도를 쓰지 않는다.

뉴스 검색은 이 Application 에 권한이 없어(0단계 401) 부르지 않는다. 응답의 sources 는 검색원 목록이라 나중에 더할 수 있다.
"""

import hashlib
import json
import os
import threading
import time
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, HTTPException, Query

from . import popups, store, web_security
from .image_search import LOCK_WAIT_SECONDS, safe_web_url, search_enabled
from .popup_hubs import HUBS, HUBS_VERSION
from .regions import REGIONS, normalize_region
from .request_usage import client_range
from .service_time import today
from .telemetry import observed_http

router = APIRouter()

BLOG_URL = "https://naverapihub.apigw.ntruss.com/search/v1/blog"
LOCAL_URL = "https://naverapihub.apigw.ntruss.com/search/v1/local"
DISPLAY = 50
SORT = "date"
RAW_TTL = 3600
EMPTY_TTL = 600
POINT_TTL = 7 * 86400
TIMEOUT = 10
MAX_POINT_LOOKUPS = 3
QUERY_MAX = 30
PAST_DAYS = 31
FUTURE_DAYS = 366
NOT_FOUND = "Not Found"
LIMIT_MESSAGE = "새 팝업 검색이 많아요. 잠시 후 다시 시도해 주세요."
ATTRIBUTION = "네이버 블로그 검색 결과"
HUB_BY_ID = {h["id"]: h for h in HUBS}

MESSAGES = {
    "key_missing": "네이버 검색 키가 설정되지 않아 팝업 글을 찾을 수 없어요.",
    "unavailable": "네이버 블로그 검색에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.",
    "busy": "같은 검색을 처리하고 있어요. 잠시 후 다시 시도해 주세요.",
    "empty": "검색된 글 중에 보여 드릴 팝업 글이 없어요.",
    "partial": "일부 장소의 위치를 확인하지 못해 위치 미확인으로 표시했어요.",
}


def enabled():
    value = os.getenv("DATEMATE_POPUPS_ENABLED", "1").strip().lower()
    return value not in ("0", "false", "off", "no")


# ---------------------------------------------------------------- 입력


def normalize_query(value):
    """NFKC, 제어·서식 문자 제거, 공백 하나로. 길이 검사는 부르는 쪽에서."""
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) not in ("Cc", "Cf", "Cs"))
    return " ".join(text.split())


def without_region(region, q):
    """검색어 앞의 같은 시·도 이름은 뺀다("서울 성수" → "성수"). 검색어와 캐시 키가 같아진다."""
    words = q.split()
    if words and normalize_region(words[0]) == region:
        return " ".join(words[1:])
    return q


def search_query(region, q):
    """블로그 검색어. 0단계·1단계 실측과 같은 '{지역} 팝업스토어' 꼴을 기본으로 한다."""
    if not q:
        return f"{region} 팝업스토어"
    return f"{region} {q}" + ("" if "팝업" in q else " 팝업스토어")


def _hash(parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()


def raw_key(region, q):
    return "popups-raw:" + _hash(
        [popups.RULES_VERSION, HUBS_VERSION, region, q.casefold(), SORT, DISPLAY, 1]
    )


def point_key(hub_id):
    return f"popup-hub-point:{popups.RULES_VERSION}:{HUBS_VERSION}:{hub_id}"


# ---------------------------------------------------------------- 잠금·한도

_locks = {}
_locks_guard = threading.Lock()


def _key_lock(key):
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            if len(_locks) > 512:
                for k in [k for k, v in _locks.items() if not v.locked()]:
                    del _locks[k]
            lock = _locks[key] = threading.Lock()
        return lock


def allow_new_search(raise_error):
    """외부 호출이 필요한 요청만 센다. 분당(ip:… 범위, 기존 require_ip 와 같은 저장소)과 시간당 한도.

    시간당 한도는 'ip:' 가 아니라 'popups:' 범위에 둔다. 유지보수 작업이 'ip:' 범위를 분 단위 버킷으로 보고 2분 뒤 지우기 때문이다
    (app/maintenance.py). raise_error 가 False 면 예외 대신 False 를 돌려준다(이미 캐시로 답할 수 있는 요청의 좌표 확인).
    """
    if not web_security.ip_allow("popup-search", "DATEMATE_IP_POPUP_SEARCHES_PER_MINUTE", 3):
        if raise_error:
            raise HTTPException(429, LIMIT_MESSAGE, headers={"Retry-After": "60"})
        return False
    key = client_range()
    if key and not store.reserve_budget(
        [(f"popups:hour:{key}", web_security.limit("DATEMATE_IP_POPUP_SEARCHES_PER_HOUR", 30))],
        int(time.time() // 3600),
    ):
        if raise_error:
            raise HTTPException(429, LIMIT_MESSAGE, headers={"Retry-After": "3600"})
        return False
    return True


# ---------------------------------------------------------------- 외부 호출


def _headers():
    return {
        "X-NCP-APIGW-API-KEY-ID": os.environ["NAVER_SEARCH_CLIENT_ID"],
        "X-NCP-APIGW-API-KEY": os.environ["NAVER_SEARCH_CLIENT_SECRET"],
    }


def _get(client, url, params):
    """(응답 JSON, 실패 사유). 실패는 캐시하지 않는다."""
    try:
        response = observed_http(client.get, url, params=params, headers=_headers())
    except httpx.PoolTimeout:
        return None, "capacity"
    except httpx.TimeoutException:
        return None, "timeout"
    except httpx.HTTPError:
        return None, "network"
    if response.status_code in (401, 403):
        return None, "permission"
    if response.status_code == 429:
        return None, "rate_limited"
    if response.status_code >= 400:
        return None, f"http_{response.status_code}"
    try:
        data = response.json()
    except ValueError:
        return None, "invalid_response"
    if not isinstance(data, dict) or not isinstance(data.get("items", []), list):
        return None, "invalid_response"
    return data, None


def _posted_at(value):
    v = str(value or "")
    try:
        return date(int(v[:4]), int(v[4:6]), int(v[6:8])).isoformat() if len(v) == 8 else None
    except ValueError:
        return None


def raw_posts(items):
    """검색 결과를 글 목록으로. 제목·요약은 태그·엔티티만 텍스트로 바꾸고 자르지 않는다. URL 은 받은 그대로(http/https 만)."""
    posts = []
    for item in items:
        if not isinstance(item, dict):
            continue
        url = str(item.get("link") or "").strip()
        if not safe_web_url(url) or not popups.canonical_url(url):
            continue
        posts.append(
            dict(
                title=popups.normalize_text(item.get("title")),
                description=popups.normalize_text(item.get("description")),
                url=url,
                blogger=popups.normalize_text(item.get("bloggername")) or None,
                posted_at=_posted_at(item.get("postdate")),
            )
        )
    return popups.dedupe_by_url(posts)


def fetch_blog(client, query):
    data, reason = _get(
        client,
        BLOG_URL,
        dict(query=query, display=DISPLAY, start=1, sort=SORT, format="json"),
    )
    if reason:
        return dict(status="failed", reason=reason)
    return dict(
        status="ok",
        posts=raw_posts(data.get("items") or []),
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )


def lookup_point(client, hub):
    """거점 좌표 판정 하나. 성공한 호출의 판정(확인·모호·결과 없음)은 7일 캐시, 실패는 None(캐시 안 함)."""
    data, reason = _get(
        client,
        LOCAL_URL,
        dict(query=hub["local_query"], display=5, start=1, sort="random", format="json"),
    )
    if reason:
        return None
    verdict = popups.verify_local_result(hub, data.get("items") or [])
    point = verdict.get("point") or {}
    stored = dict(
        status=verdict["status"],
        level=verdict.get("level"),
        lat=point.get("lat"),
        lon=point.get("lon"),
    )
    store.cache(point_key(hub["id"]), stored, POINT_TTL)
    return stored


# ---------------------------------------------------------------- 글 판정(요청마다)


def post_id(url):
    return "popup-post:" + hashlib.sha1(popups.canonical_url(url).encode()).hexdigest()[:16]


def period_view(extraction, status):
    """확인 수준: confirmed(연도까지) / month_day(연도 미상, 근거만) / conflict / none."""
    if extraction["status"] == "conflict":
        return dict(
            level="conflict",
            start=None,
            end=None,
            evidence=[p["evidence"] for p in extraction["periods"]][:3],
            status="unknown",
            end_only=False,
        )
    p = extraction["period"]
    if not p:
        return dict(
            level="none", start=None, end=None, evidence=[], status="unknown", end_only=False
        )
    if not p["year_known"]:
        return dict(
            level="month_day",
            start=None,
            end=None,
            evidence=[p["evidence"]],
            status="unknown",
            end_only=False,
        )
    return dict(
        level="confirmed",
        start=p["start"].isoformat() if p["start"] else None,
        end=p["end"].isoformat() if p["end"] else None,
        evidence=[p["evidence"]],
        status=status["status"],
        end_only=bool(status.get("end_only")),
    )


def place_view(hub, verdicts):
    """위치 등급: building / area_anchor / unverified. 좌표는 확인된 경우에만."""
    if hub["status"] == "multiple":
        return dict(hub_id=None, level="unverified", reason="multiple")
    if hub["status"] != "single":
        return dict(hub_id=None, level="unverified", reason="not_found")
    h = HUB_BY_ID[hub["hub_id"]]
    base = dict(
        hub_id=h["id"],
        name=h["name"],
        kind=h["kind"],
        anchor=h["anchor"],
        region=h["region"],
        # 1b 주변 코스 버튼이 출발지 이름 앞부분(시·도 시·군·구)을 만들 때 쓴다. 기존 지역 검색은 이 부분에서 동네를 읽는다.
        district=h["district"],
    )
    v = verdicts.get(h["id"])
    if v is None:
        return base | dict(level="unverified", reason="not_checked")
    if v == "failed":
        return base | dict(level="unverified", reason="lookup_failed")
    if v["status"] != "verified":
        return base | dict(level="unverified", reason=v["status"])
    return base | dict(level=v["level"], reason="verified", lat=v["lat"], lon=v["lon"])


def judge(raw, region, visit):
    """원본 글 → 보여 줄 글과 뺀 글 수. 거점 좌표는 아직 붙이지 않는다.

    '팝업'이 없는 글과 팝업 행사 증거가 모자란 글(popups.popup_evidence, 규칙 v2·v3)은 함께 not_popup 으로 센다.
    다른 지역 거점만 있는 글과 제목이 다른 시·도 팝업을 말하는 글(규칙 v3)은 other_region 으로 센다.
    """
    shown, counts = [], Counter()
    for p in raw:
        text = p["title"] + " \n " + p["description"]
        if not popups.has_popup(text):
            counts["not_popup"] += 1
            continue
        hub = popups.hub_match(text, HUBS, region)
        if hub["status"] == "other_region" or popups.title_other_region(p["title"], region):
            counts["other_region"] += 1
            continue
        extraction = popups.extract_period(p["title"], p["description"])
        evidence = popups.popup_evidence(
            p["title"],
            p["description"],
            has_period=extraction["status"] != "none",
            has_hub=hub["status"] in ("single", "multiple"),
        )
        if not evidence["show"]:
            counts["not_popup"] += 1
            continue
        status = popups.post_status(extraction, visit)
        if status["status"] == "ended":
            counts["ended"] += 1
            continue
        roundup = popups.classify_roundup(p["title"], p["description"], HUBS)["kind"] == "roundup"
        shown.append(
            dict(
                id=post_id(p["url"]),
                title=p["title"],
                description=p["description"],
                url=p["url"],
                blogger=p["blogger"],
                posted_at=p["posted_at"],
                roundup=roundup,
                period=period_view(extraction, status),
                _hub=hub,
            )
        )
    return shown, counts


def order_key(post):
    """결정적 정렬: 일반 글 먼저, 거점을 읽은 글 먼저, 최근 글 먼저, 글 ID."""
    posted = date.fromisoformat(post["posted_at"]).toordinal() if post["posted_at"] else 0
    return (post["roundup"], post["place"]["hub_id"] is None, -posted, post["id"])


# ---------------------------------------------------------------- 조회


def unavailable(region, q, visit, basis, reason):
    """검색원을 쓰지 못한 응답. reason: key_missing / busy / 외부 호출 실패 사유(timeout, permission, …)."""
    status = "key_missing" if reason == "key_missing" else "unavailable"
    source = dict(
        id="blog",
        name="네이버 블로그 검색",
        status="key_missing" if reason == "key_missing" else "failed",
        reason=reason,
    )
    return response(
        status,
        MESSAGES.get(reason, MESSAGES["unavailable"]),
        region,
        q,
        visit,
        basis,
        [source],
        [],
        Counter(),
        dict(requested=0, failed=0, skipped=0),
    )


def response(status, message, region, q, visit, basis, sources, posts, counts, checks):
    return dict(
        status=status,
        message=message,
        region=region,
        q=q,
        visit_date=visit.isoformat(),
        basis=basis,
        sources=sources,
        attribution=ATTRIBUTION,
        posts=posts,
        counts=dict(
            shown=len(posts),
            general=sum(not p["roundup"] for p in posts),
            roundup=sum(p["roundup"] for p in posts),
            location_unknown=sum(p["place"]["level"] == "unverified" for p in posts),
            hidden_ended=counts["ended"],
            excluded_other_region=counts["other_region"],
            not_popup=counts["not_popup"],
        ),
        hub_checks=checks,
        rules_version=popups.RULES_VERSION,
        hubs_version=HUBS_VERSION,
    )


def find_popups(region, q, visit, basis):
    key = raw_key(region, q)
    query = search_query(region, q)
    raw = store.cached(key)
    called = False
    with httpx.Client(timeout=TIMEOUT) as client:
        if raw is None:
            if not search_enabled():
                return unavailable(region, q, visit, basis, "key_missing")
            lock = _key_lock(key)
            if not lock.acquire(timeout=LOCK_WAIT_SECONDS):
                return unavailable(region, q, visit, basis, "busy")
            try:
                raw = store.cached(key)
                if raw is None:
                    allow_new_search(raise_error=True)
                    called = True
                    result = fetch_blog(client, query)
                    if result["status"] != "ok":
                        return unavailable(region, q, visit, basis, result["reason"])
                    raw = dict(posts=result["posts"], fetched_at=result["fetched_at"])
                    # 캐시 수명은 '팝업' 글자만 본다(증거 판정은 요청마다 judge 에서).
                    has_popup = any(
                        popups.has_popup(p["title"] + " " + p["description"]) for p in raw["posts"]
                    )
                    store.cache(key, raw, RAW_TTL if has_popup else EMPTY_TTL)
            finally:
                lock.release()
        shown, counts = judge(raw["posts"], region, visit)
        verdicts, checks = hub_points(client, shown, may_call=called)
    for post in shown:
        post["place"] = place_view(post.pop("_hub"), verdicts)
    shown.sort(key=order_key)
    source = dict(
        id="blog",
        name="네이버 블로그 검색",
        status="ok",
        reason=None,
        query=query,
        sort=SORT,
        display=DISPLAY,
        returned=len(raw["posts"]),
        fetched_at=raw.get("fetched_at"),
        cached=not called,
    )
    if not shown:
        status = "empty"
    elif checks["failed"]:
        status = "partial"
    else:
        status = "ready"
    return response(
        status,
        MESSAGES.get(status),
        region,
        q,
        visit,
        basis,
        [source],
        shown,
        counts,
        checks,
    )


def hub_points(client, shown, may_call):
    """보여 줄 글의 단일 거점 좌표 판정. 캐시에 없는 거점은 많이 나온 순서로 최대 3곳만 이번 요청에서 확인한다."""
    wanted = Counter(p["_hub"]["hub_id"] for p in shown if p["_hub"]["status"] == "single")
    order = sorted(wanted, key=lambda h: (-wanted[h], h))
    found = store.cached_many([point_key(h) for h in order])
    verdicts = {h: found[point_key(h)] for h in order if point_key(h) in found}
    missing = [h for h in order if h not in verdicts]
    checks = dict(requested=0, failed=0, skipped=0)
    if missing and not search_enabled():
        checks["skipped"] = len(missing)
        return verdicts, checks
    if missing and not may_call and not allow_new_search(raise_error=False):
        checks["skipped"] = len(missing)
        return verdicts, checks
    for hub_id in missing[:MAX_POINT_LOOKUPS]:
        lock = _key_lock(point_key(hub_id))
        if not lock.acquire(blocking=False):
            checks["skipped"] += 1
            continue
        try:
            checks["requested"] += 1
            verdict = lookup_point(client, HUB_BY_ID[hub_id])
        finally:
            lock.release()
        if verdict is None:
            checks["failed"] += 1
            verdicts[hub_id] = "failed"
        else:
            verdicts[hub_id] = verdict
    checks["skipped"] += max(0, len(missing) - MAX_POINT_LOOKUPS)
    return verdicts, checks


@router.get("/api/popups")
def popup_list(
    region: str = Query(default="서울", max_length=20),
    visit_date: date | None = None,
    q: str = Query(default="", max_length=60),
):
    if not enabled():
        raise HTTPException(404, NOT_FOUND)
    canonical = normalize_region(region)
    if canonical not in REGIONS:
        raise HTTPException(422, "지원하지 않는 시·도예요.")
    query = normalize_query(q)
    if len(query) > QUERY_MAX:
        raise HTTPException(422, f"검색어는 {QUERY_MAX}자까지 입력할 수 있어요.")
    query = without_region(canonical, query)
    now = today()
    if visit_date is None:
        visit, basis = now, "today"
    else:
        if not now - timedelta(days=PAST_DAYS) <= visit_date <= now + timedelta(days=FUTURE_DAYS):
            raise HTTPException(422, "방문일은 오늘 기준 31일 전부터 1년 뒤까지 고를 수 있어요.")
        visit, basis = visit_date, "visit_date"
    return find_popups(canonical, query, visit, basis)
