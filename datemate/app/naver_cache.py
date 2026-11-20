"""네이버 검색 API 결과와 그 파생물의 보관(검색 API 특약 2.3·2.4, 2026-09 개정).

개정 특약은 검색 결과(가공물·파생물 포함)의 저장·캐싱을 금지하고, 서비스 연속성에 필요한 임시 보관만 허용한다.
서버 보관은 개인화 목적이면 '24시간 또는 새 질의 시까지 중 짧은 기간', 이력 조회 목적이면 최대 21일이며 목적별로 나눈다.
그래서 이 모듈은 사용자 공용 캐시(store.cache)를 쓰지 않고 다음 두 가지만 둔다.

1) 요청 안 메모(_memo): 한 HTTP 요청(또는 추천 작업 하나) 동안만 같은 검색을 한 번만 부르게 한다. 요청이 끝나면 사라진다.
2) 사용자별 개인화 보관: 같은 브라우저(소유자 = 세션 토큰의 sha256)만 읽는 cache 행. 키는 'nv:{목적}:{소유자}:{원래 키}',
   값은 {'owner': 소유자, 'v': 값}이라 cache_owners 트리거가 소유자를 기록하고(내 데이터 삭제·보존 기한 정리에 함께 지워짐),
   폐기된 세션은 쓰기가 거절된다. 수명은 최대 PERSONAL_MAX_SECONDS(24시간)이고, 같은 사용자가 새로 검색하면(new_query)
   그 목적과 장소 상세(place) 보관분을 지운다.

소유자가 없는 문맥(스크립트·유지보수·컨테이너 시작 색인)은 메모만 쓰고 DB 에 남기지 않는다.
이력 조회 목적의 코스 보관(최대 21일)은 app/naver_terms.py 와 maintenance 가 맡는다.
"""

import json
import time
from contextlib import contextmanager
from contextvars import ContextVar

from . import store

PERSONAL_MAX_SECONDS = 86400
# 목적: plan(코스 추천·변경), explore(장소 둘러보기), popups(팝업 둘러보기), place(장소 상세의 블로그·사진·메뉴·위치 확인 등).
PURPOSES = ("plan", "explore", "popups", "place")
# 원래 키의 앞부분으로 목적을 고른다. 여기에 없는 키는 place.
PURPOSE_BY_PREFIX = (
    ("query-fingerprint:plan", "plan"),
    ("query-fingerprint:explore", "explore"),
    ("query-fingerprint:popups", "popups"),
    ("course-blog-", "plan"),
    ("intent-local-", "plan"),
    ("leisure-local-", "plan"),
    ("discovered-place:", "plan"),
    ("local-restaurants-", "plan"),
    ("meal-rescue-", "plan"),
    ("restaurant:", "plan"),
    ("parking-", "plan"),
    ("explore-", "explore"),
    ("popup", "popups"),
)
# 예전(공용) 캐시 키의 앞부분. 마이그레이션 v0005 와 cleanup_shared() 가 지운다.
SHARED_PREFIXES = (
    "place-blogs-",
    "course-blog-five-",
    "discovered-place:",
    "explore-query-",
    "explore-result-",
    "explore-place:",
    "image-strict-",
    "image-search-",
    "intent-local-",
    "leisure-local-",
    "restaurant-menu-",
    "parking-local-",
    "place-identity-",
    "popups-raw:",
    "popup-hub-point:",
    "popup-photo:",
    "price-search-",
    "restaurant:",
    "local-restaurants-",
    "meal-rescue-",
    "review-facts-",
    "caption-blog-photos-",
    "public-place-photos-",
    "photo-subject-",
    "answer:",
)

_owner = ContextVar("naver_cache_owner", default=None)
_memo = ContextVar("naver_cache_memo", default=None)
# 요청 안 메모를 거치지 않고 실제로 나간 네이버 검색 API 호출 수(진단·테스트용, 요청 범위).
_calls = ContextVar("naver_cache_calls", default=None)


def purpose_of(key):
    for prefix, purpose in PURPOSE_BY_PREFIX:
        if key.startswith(prefix):
            return purpose
    return "place"


def personal_key(owner, key):
    return f"nv:{purpose_of(key)}:{owner}:{key}"


def current_owner():
    return _owner.get()


@contextmanager
def scope(owner, fresh=True):
    """owner 의 요청 범위를 연다. fresh 면 새 메모를 쓴다(이미 열린 메모를 이어 쓰려면 False)."""
    token = _owner.set(owner)
    memo_token = _memo.set({}) if fresh or _memo.get() is None else None
    calls_token = _calls.set({"calls": 0}) if fresh or _calls.get() is None else None
    try:
        yield
    finally:
        if calls_token is not None:
            _calls.reset(calls_token)
        if memo_token is not None:
            _memo.reset(memo_token)
        _owner.reset(token)


def bind(owner, memo=True):
    """미들웨어용: 요청 하나의 소유자와 새 메모를 건다. unbind 에 넘길 토큰을 돌려준다.

    memo=False 는 요청 안 메모 없이 사용자별 보관만 쓴다(함수를 여러 번 직접 부르는 테스트가 '요청 여러 개'처럼 동작하게).
    """
    return (_owner.set(owner), _memo.set({} if memo else None), _calls.set({"calls": 0}))


def unbind(tokens):
    owner, memo, calls = tokens
    _calls.reset(calls)
    _memo.reset(memo)
    _owner.reset(owner)


def count_call(n=1):
    box = _calls.get()
    if box is not None:
        box["calls"] += n


def calls():
    box = _calls.get()
    return box["calls"] if box else 0


def _ttl(ttl):
    return max(1, min(int(ttl), PERSONAL_MAX_SECONDS))


def cached(key):
    memo = _memo.get()
    if memo is not None and key in memo:
        return memo[key]
    owner = _owner.get()
    if not owner:
        return None
    hit = store.cached(personal_key(owner, key))
    value = hit.get("v") if isinstance(hit, dict) else None
    if value is not None and memo is not None:
        memo[key] = value
    return value


def cached_many(keys):
    keys = list(dict.fromkeys(keys))
    memo = _memo.get()
    found = {k: memo[k] for k in keys if memo is not None and k in memo}
    owner = _owner.get()
    missing = [k for k in keys if k not in found]
    if owner and missing:
        rows = store.cached_many(personal_key(owner, k) for k in missing)
        for k in missing:
            hit = rows.get(personal_key(owner, k))
            if isinstance(hit, dict) and hit.get("v") is not None:
                found[k] = hit["v"]
                if memo is not None:
                    memo[k] = hit["v"]
    return found


def cache(key, value, ttl=PERSONAL_MAX_SECONDS):
    cache_many([(key, value, ttl)])


def cache_many(entries):
    entries = list(entries)
    memo = _memo.get()
    if memo is not None:
        for key, value, _ in entries:
            memo[key] = value
    owner = _owner.get()
    if not owner or not entries:
        return
    try:
        store.cache_many(
            [(personal_key(owner, key), {"owner": owner, "v": value}, _ttl(ttl)) for key, value, ttl in entries]
        )
    except Exception:
        # 폐기된 세션(내 데이터 삭제 직후)의 늦은 쓰기는 트리거가 거절한다. 요청 안 메모는 그대로 쓴다.
        import logging

        logging.getLogger(__name__).info("naver_personal_cache_write_skipped")


def owned_values(prefix):
    """현재 소유자의 보관분과 요청 안 메모에서 키가 prefix 로 시작하는 값들({키: 값})."""
    found = {}
    owner = _owner.get()
    if owner:
        # 소유자는 16진수, 키 앞부분은 영문·기호뿐이라 LIKE 의 '_'·'%' 가 섞이지 않는다(검사로 확인).
        like = personal_key(owner, prefix) + "%"
        if "%" in like[:-1] or "_" in like:
            raise ValueError("unsupported prefix")
        with store.connect() as db:
            rows = db.execute(
                "SELECT key,payload FROM cache WHERE key LIKE ? AND expires>?",
                (like, time.time()),
            ).fetchall()
        head = f"nv:{purpose_of(prefix)}:{owner}:"
        for row in rows:
            try:
                value = json.loads(row[1]).get("v")
            except (ValueError, AttributeError):
                continue
            if value is not None:
                found[row[0].removeprefix(head)] = value
    memo = _memo.get() or {}
    found.update({k: v for k, v in memo.items() if k.startswith(prefix) and v is not None})
    return found


def new_query(purpose, owner=None, fingerprint=None):
    """같은 사용자의 새 검색: 그 목적과 장소 상세(place) 보관분을 지운다(특약 2.4 '새 질의 시까지').

    fingerprint 를 주면 직전 질의와 같을 때(같은 조건으로 다시 추천) 새 질의로 보지 않고 지우지 않는다. 지운 행 수를 돌려준다.
    """
    owner = owner or _owner.get()
    if fingerprint is not None and owner:
        marker = f"query-fingerprint:{purpose}"
        if cached(marker) == fingerprint:
            return 0
    memo = _memo.get()
    if memo is not None:
        for key in [k for k in memo if purpose_of(k) in (purpose, "place")]:
            del memo[key]
    if not owner:
        return 0
    removed = 0
    with store.connect() as db:
        for name in dict.fromkeys((purpose, "place")):
            like = f"nv:{name}:{owner}:%"
            cursor = db.execute("DELETE FROM cache WHERE key LIKE ?", (like,))
            removed += max(0, getattr(cursor, "rowcount", 0) or 0)
    if fingerprint is not None:
        cache(f"query-fingerprint:{purpose}", fingerprint, PERSONAL_MAX_SECONDS)
    return removed


def cleanup_shared(db=None):
    """예전 사용자 공용 캐시에 남은 네이버 검색 결과·파생물 행을 지운다(마이그레이션 v0005, 유지보수)."""
    def run(connection):
        # answer:* 는 이제 네이버 필드를 뺀 근거로 만든 사용자별 답변이라 매번 지우지 않는다(예전 행은 마이그레이션 v0005 가 지움).
        # 한 문장으로 지운다(cache 표를 한 번만 훑음).
        prefixes = [p + "%" for p in SHARED_PREFIXES if p != "answer:"]
        cursor = connection.execute(
            "DELETE FROM cache WHERE " + " OR ".join("key LIKE ?" for _ in prefixes), tuple(prefixes)
        )
        return max(0, getattr(cursor, "rowcount", 0) or 0)

    if db is not None:
        return run(db)
    with store.connect() as connection:
        return run(connection)
