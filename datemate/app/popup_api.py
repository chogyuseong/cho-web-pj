"""팝업 글 API: GET /api/popups?region=&visit_date=&q=

2026-11-20(네이버 검색 API 특약 1.2, docs/naver-terms-stage2-design.ko.md 3.3·결정 Q3)부터 '글 목록만' 돌려준다.
- posts: 네이버 블로그 검색 한 번의 결과를 네이버가 준 순서 그대로, 받은 건수 그대로. 제목·요약은 태그·엔티티만 글자로 바꾸고
  자르지 않는다. 원본 링크·블로거 이름·작성일을 함께 싣는다. 고르기·빼기·재정렬·합치기·중복 제거를 하지 않는다.
  예외 하나: 링크가 http/https 주소가 아닌 항목은 원본 링크를 안전하게 만들 수 없어 뺀다(보안, counts.returned 와 shown 의 차이로 드러남).
- 글에서 읽어 내던 것(팝업 여부 판정, 기간·방문일 상태, 거점 연결, 모아 보기 분류, 행사명, 대표 사진)은 없다.
  이미지 검색·지역 검색 API 는 부르지 않는다.
- hubs: 검색 결과와 무관한 우리 거점 사전(app/popup_hubs.py, 좌표는 한국관광공사 자료의 고정값). 글이 0건이거나 검색을 못 써도 그대로 싣는다.

검색어는 '{연}년 {월}월 {시·도} [검색어] 팝업스토어'(방문일의 연·월, 없으면 한국시간 오늘), 정렬은 네이버의 정확도순(sort=sim), 50건.
  정렬을 바꾼 까닭(2026-11-24 사용자 신고 '팝업 글에 부동산 글이 섞인다'): 같은 검색어 50건을 실제로 받아 보니 최신순(date)은 부동산 단어
  (임대·분양·매매 등)가 든 글 1건·'팝업'이 없는 글 9건, 정확도순(sim)은 0건·0건이었다. 받은 결과는 예전처럼 거르거나 다시 줄 세우지 않는다
  (특약 1.2 — 우리가 바꾸는 것은 네이버에 보내는 요청뿐). 검색어 앞의 '-임대'처럼 빼는 말은 이 API 가 지원하지 않아 오히려 부동산 글이 늘었다.

캐시와 외부 호출
- 검색 결과: 사용자별 보관(app/naver_cache.py, 최대 24시간·새 팝업 검색 시 삭제) 안에서 성공 1시간, 0건 10분. 실패는 보관하지 않는다.
  키에 시·도·정규화 검색어·정렬·건수·방문 연월.
- 요청당 외부 호출: 블로그 검색 1. 재시도 없음. 시간 제한 10초. observed_http(제공자 시간당 한도)를 거친다.
- 같은 키의 동시 호출은 키별 잠금으로 한 번만 부르고, 잠금은 짧게만 기다린다(image_search 와 같은 2.5초).
- 외부 호출이 필요한 요청만 IP 대역별 전용 한도(분당 3회·시간당 30회)를 쓴다. 보관분으로 답하는 요청은 한도를 쓰지 않는다.
"""

import hashlib
import html
import json
import os
import re
import threading
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, HTTPException, Query

from . import naver_cache, store, web_security
from .image_search import LOCK_WAIT_SECONDS, safe_web_url, search_enabled
from .popup_hubs import CHECKED, COORDINATE_PROVIDER, HUBS_VERSION, hubs_in
from .regions import REGIONS, normalize_region
from .request_usage import client_range
from .service_time import today
from .telemetry import observed_http

router = APIRouter()

BLOG_URL = "https://naverapihub.apigw.ntruss.com/search/v1/blog"
DISPLAY = 50
# 정렬: 정확도순(sim). 위 모듈 설명의 실험 참고. 바꾸면 RAW_VERSION 도 올리고 static/popups.js scopeText 의 이름표를 확인한다.
SORT = "sim"
RAW_TTL = 3600
EMPTY_TTL = 600
TIMEOUT = 10
QUERY_MAX = 30
PAST_DAYS = 31
FUTURE_DAYS = 366
NOT_FOUND = "Not Found"
LIMIT_MESSAGE = "새 팝업 검색이 많아요. 잠시 후 다시 시도해 주세요."
ATTRIBUTION = "네이버 블로그 검색 결과"
# 보관 키 버전. v2: 검색 한 번의 결과를 받은 그대로(예전 보관분은 두 검색어 결과를 합친 것이라 다시 쓰지 않는다).
# v3(2026-11-24): 정렬을 최신순 → 정확도순으로 바꿨다(키에 SORT 가 들어 있어 섞이지는 않지만, 버전으로도 끊는다).
RAW_VERSION = "popups-raw-v3"

MESSAGES = {
    "key_missing": "지금은 팝업 글을 불러올 수 없어요. 잠시 후 다시 확인해 주세요.",
    "unavailable": "네이버 블로그 검색에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.",
    "busy": "같은 검색을 처리하고 있어요. 잠시 후 다시 시도해 주세요.",
    "empty": "이 검색어로 검색된 글이 없어요.",
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
    """검색어 앞의 같은 시·도 이름은 뺀다("서울 성수" → "성수"). 검색어와 보관 키가 같아진다."""
    words = q.split()
    if words and normalize_region(words[0]) == region:
        return " ".join(words[1:])
    return q


def month_words(visit):
    """방문일의 '2026년 11월'. 그 달의 팝업 글이 더 잘 나오도록 검색어 앞에 붙인다."""
    return f"{visit.year}년 {visit.month}월"


def search_query(region, q, visit):
    """블로그 검색어: '{연}년 {월}월 {지역} [검색어] 팝업스토어'(예: '2026년 11월 서울 성수 팝업스토어')."""
    if not q:
        return f"{month_words(visit)} {region} 팝업스토어"
    return f"{month_words(visit)} {region} {q}" + ("" if "팝업" in q else " 팝업스토어")


def raw_key(region, q, visit):
    # 검색어에 방문 연·월이 들어가므로 키에도 넣는다(같은 달 안의 다른 방문일은 같은 검색 결과를 쓴다).
    parts = [RAW_VERSION, region, q.casefold(), SORT, DISPLAY, 1, month_words(visit)]
    return "popups-raw:" + hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()


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


def allow_new_search():
    """외부 호출이 필요한 요청만 센다. 분당(ip:… 범위, 기존 require_ip 와 같은 저장소)과 시간당 한도. 넘으면 429.

    시간당 한도는 'ip:' 가 아니라 'popups:' 범위에 둔다. 유지보수 작업이 'ip:' 범위를 분 단위 버킷으로 보고 2분 뒤 지우기 때문이다
    (app/maintenance.py).
    """
    if not web_security.ip_allow("popup-search", "DATEMATE_IP_POPUP_SEARCHES_PER_MINUTE", 3):
        raise HTTPException(429, LIMIT_MESSAGE, headers={"Retry-After": "60"})
    key = client_range()
    if key and not store.reserve_budget(
        [(f"popups:hour:{key}", web_security.limit("DATEMATE_IP_POPUP_SEARCHES_PER_HOUR", 30))],
        int(time.time() // 3600),
    ):
        raise HTTPException(429, LIMIT_MESSAGE, headers={"Retry-After": "3600"})


# ---------------------------------------------------------------- 외부 호출


def _headers():
    return {
        "X-NCP-APIGW-API-KEY-ID": os.environ["NAVER_SEARCH_CLIENT_ID"],
        "X-NCP-APIGW-API-KEY": os.environ["NAVER_SEARCH_CLIENT_SECRET"],
    }


def _get(client, url, params):
    """(응답 JSON, 실패 사유). 실패는 보관하지 않는다."""
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


def normalize_text(value):
    """검색 결과의 <b> 같은 태그를 지우고 HTML 엔티티를 글자로 바꾼 뒤 공백을 하나로. 글자를 자르거나 고치지 않는다."""
    text = re.sub(r"<[^>]*>", " ", str(value or ""))
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _posted_at(value):
    v = str(value or "")
    try:
        return date(int(v[:4]), int(v[4:6]), int(v[6:8])).isoformat() if len(v) == 8 else None
    except ValueError:
        return None


def post_id(url):
    return "popup-post:" + hashlib.sha1(url.encode()).hexdigest()[:16]


def raw_posts(items):
    """검색 결과 항목을 받은 순서 그대로 글 목록으로. 고르거나 합치지 않는다.

    링크가 http/https 주소가 아닌 항목(javascript: 등)만 뺀다: 화면에 원본 링크를 안전하게 걸 수 없기 때문이다(보안).
    """
    posts = []
    for item in items:
        if not isinstance(item, dict):
            continue
        url = str(item.get("link") or "").strip()
        if not safe_web_url(url):
            continue
        posts.append(
            dict(
                id=post_id(url),
                title=normalize_text(item.get("title")),
                description=normalize_text(item.get("description")),
                url=url,
                blogger=normalize_text(item.get("bloggername")) or None,
                posted_at=_posted_at(item.get("postdate")),
            )
        )
    return posts


def fetch_blog(client, query):
    data, reason = _get(
        client,
        BLOG_URL,
        dict(query=query, display=DISPLAY, start=1, sort=SORT, format="json"),
    )
    if reason:
        return dict(status="failed", reason=reason)
    items = data.get("items") or []
    return dict(
        status="ok",
        posts=raw_posts(items),
        returned=len(items),
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------- 조회


def response(status, message, region, q, visit, source, posts, returned):
    return dict(
        status=status,
        message=message,
        region=region,
        q=q,
        visit_date=visit.isoformat(),
        sources=[source],
        attribution=ATTRIBUTION,
        posts=posts,
        # returned: 네이버가 준 건수, shown: 화면에 싣는 건수(링크를 걸 수 없는 항목만 빠짐).
        counts=dict(shown=len(posts), returned=returned),
        # 우리 거점 사전. 검색 결과와 무관하다.
        hubs=hubs_in(region),
        hubs_version=HUBS_VERSION,
        hub_coordinates=dict(provider=COORDINATE_PROVIDER, checked=CHECKED),
    )


def unavailable(region, q, visit, reason):
    """검색원을 쓰지 못한 응답. reason: key_missing / busy / 외부 호출 실패 사유(timeout, permission, …)."""
    status = "key_missing" if reason == "key_missing" else "unavailable"
    source = dict(
        id="blog",
        name="네이버 블로그 검색",
        status="key_missing" if reason == "key_missing" else "failed",
        reason=reason,
    )
    message = MESSAGES.get(reason, MESSAGES["unavailable"])
    return response(status, message, region, q, visit, source, [], 0)


def find_popups(region, q, visit):
    key = raw_key(region, q, visit)
    query = search_query(region, q, visit)
    raw = naver_cache.cached(key)
    called = False
    if raw is None:
        if not search_enabled():
            return unavailable(region, q, visit, "key_missing")
        lock = _key_lock(key)
        if not lock.acquire(timeout=LOCK_WAIT_SECONDS):
            return unavailable(region, q, visit, "busy")
        try:
            raw = naver_cache.cached(key)
            if raw is None:
                allow_new_search()
                # 같은 사용자의 새 팝업 검색: 이전 팝업 검색 보관분을 지운다(특약 1.4 '새 질의 시까지').
                naver_cache.new_query("popups")
                called = True
                with httpx.Client(timeout=TIMEOUT) as client:
                    result = fetch_blog(client, query)
                if result["status"] != "ok":
                    return unavailable(region, q, visit, result["reason"])
                raw = dict(
                    posts=result["posts"],
                    returned=result["returned"],
                    fetched_at=result["fetched_at"],
                )
                naver_cache.cache(key, raw, RAW_TTL if raw["posts"] else EMPTY_TTL)
        finally:
            lock.release()
    source = dict(
        id="blog",
        name="네이버 블로그 검색",
        status="ok",
        reason=None,
        query=query,
        sort=SORT,
        display=DISPLAY,
        returned=raw["returned"],
        fetched_at=raw.get("fetched_at"),
        cached=not called,
    )
    status = "ready" if raw["posts"] else "empty"
    return response(
        status, MESSAGES.get(status), region, q, visit, source, raw["posts"], raw["returned"]
    )


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
        visit = now
    elif not now - timedelta(days=PAST_DAYS) <= visit_date <= now + timedelta(days=FUTURE_DAYS):
        raise HTTPException(422, "방문일은 오늘 기준 31일 전부터 1년 뒤까지 고를 수 있어요.")
    else:
        visit = visit_date
    return find_popups(canonical, query, visit)
