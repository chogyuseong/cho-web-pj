"""서울시 착한가격업소 메뉴·가격(서울 열린데이터광장 OA-1174, ListPriceModelStoreProductService) (2026-11-26).

왜: 식당 메뉴 칸에 가격이 없다. 네이버 메뉴는 읽지 않고(약관, app/menus.py), 관광공사 안내에는 메뉴 이름만 있다.
서울시가 지정한 착한가격업소는 가게별 품목·가격을 공공 자료로 낸다. 같은 가게가 확실할 때만 그 메뉴·가격을 글 그대로 싣는다.

자료 (2026-11-26 실제 키로 확인)
  한 줄 = 가게 하나의 품목 하나. 전체 4,255줄(가게 1,867곳). 한 번에 최대 1,000줄씩 페이지로 받는다(서울 API 규칙).
  열: SH_ID·SH_NAME·INDUTY_CODE_SE(업종 코드)·INDUTY_CODE_SE_NAME·SH_ADDR·SH_PHONE·SH_RCMN·IM_NAME(품목)·IM_PRICE(원, 실수).
  업종 코드: 001 한식 · 002 중식 · 003 경양식/일식 · 004 기타외식업(카페 포함) · 005 이미용 · 006 목욕업 · 007 세탁 ·
  008 숙박업 · 013 기타서비스업. 음식 업종(FOOD_CODES) 3,149줄·가게 1,331곳만 쓴다.
  주소는 '서울특별시 서울 송파구 오금로 485. 1층'처럼 섞여 있고, 지번만 있는 가게(‘중계동 154-41’)·시험 행(‘서울특별시 테스트’)이 있다.
  응답에 자료 기준일 열이 없다. 그래서 화면에는 우리가 받은 날(fetched_on)을 '확인' 날짜로 보여 준다.

같은 가게 판정 (보수적으로 — 틀린 가격을 보여 주는 것이 가장 나쁘다)
  1) 서울 장소만(주소의 시·도가 서울). 가상 장소·네이버 검색 장소(naver_terms.is_naver_place)는 보지 않는다.
  2) 도로명과 건물번호가 같다(place_identity.road_key: '명동10길 29' — '29'와 '29-1'은 다르다). 지번 주소는 맞추지 않는다.
  3) 자치구가 같다(양쪽 주소에서 '…구'가 모두 읽혀야 한다 — 같은 도로명이 다른 구에 있을 수 있어서).
  4) 이름이 띄어쓰기·기호·법인 표기만 빼고 똑같다(place_identity._compact; 우리 이름에서 지점 낱말을 뗀 이름도 본다).
     한쪽이 다른 쪽을 품는 것(예: '홍두깨' ⊂ '홍두깨손칼국수')은 같은 가게로 보지 않는다.
  5) 맞는 가게가 정확히 한 곳이어야 한다. 같은 주소·이름으로 두 곳 이상이면 어느 가격인지 몰라 붙이지 않는다.

보관
  하루에 한 번 전체를 받아 store 캐시에 둔다. 주소(도로명|건물번호)마다 한 행(키에 세대 표시를 넣어 지난 자료가 섞이지 않게)과
  요약 한 행(META_KEY: 세대, 받은 날, 가게 수)이다. 사용자 요청은 서울 API 를 부르지 않는다 — 보관분을 읽기만 하고,
  보관분이 없거나 하루가 지났으면 배경 스레드에 새로 받기를 맡긴다(그 요청은 지금 있는 보관분으로, 없으면 착한가격 없이 답한다).
  받기가 실패하거나 모양이 이상하면 지난 보관분(최대 KEEP_SECONDS)을 그대로 쓰고 RETRY_SECONDS 동안 다시 받지 않는다.
  키(SEOUL_OPEN_API_KEY)가 없으면 아무것도 하지 않는다. 키는 주소 경로에 들어가므로 예외 글·로그에 주소를 남기지 않는다.
"""

import logging
import os
import re
import threading
import unicodedata
from datetime import datetime, timedelta, timezone

import httpx

from . import store
from .telemetry import observed_http

URL = "http://openapi.seoul.go.kr:8088/{key}/json/ListPriceModelStoreProductService/{start}/{end}/"
SERVICE = "ListPriceModelStoreProductService"
SOURCE_URL = "https://data.seoul.go.kr/dataList/OA-1174/S/1/datasetView.do"
SOURCE_LABEL = "착한가격업소 · 서울시 제공"
FOOD_CODES = frozenset({"001", "002", "003", "004"})
PAGE_ROWS = 1000
MAX_PAGES = 20
TIMEOUT = 10
REFRESH_SECONDS = 86400
KEEP_SECONDS = 3 * 86400
RETRY_SECONDS = 1800
MAX_PRICE = 5_000_000
PREFIX = "good-price-v1:"
META_KEY = PREFIX + "meta"
RETRY_KEY = PREFIX + "retry"
_DISTRICT = re.compile(r"^[가-힣]{1,6}구$")

log = logging.getLogger(__name__)
_lock = threading.Lock()
_worker = None


def enabled():
    return bool(os.environ.get("SEOUL_OPEN_API_KEY", "").strip())


def _text(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or ""))).strip()


def district(address):
    """주소에서 자치구('송파구'). '서울특별시 서울 송파구 …'·'서울 송파구 …' 모두. 읽지 못하면 None."""
    for word in _text(address).replace(",", " ").split()[:4]:
        if _DISTRICT.fullmatch(word):
            return word
    return None


def _price(value):
    """IM_PRICE(원, 실수) → 정수 원. 0·음수·소수·너무 큰 값은 None(고치거나 추정하지 않고 버린다)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not number.is_integer() or not 0 < number <= MAX_PRICE:
        return None
    return int(number)


def parse_page(data):
    """응답 한 페이지 → (행 목록, 전체 줄 수). 오류 코드·모양이 이상하면 ValueError."""
    body = (data or {}).get(SERVICE) if isinstance(data, dict) else None
    if not isinstance(body, dict):
        raise ValueError("invalid_response")
    code = str((body.get("RESULT") or {}).get("CODE") or "")
    if code != "INFO-000":
        raise ValueError("provider_error")
    rows = body.get("row")
    total = body.get("list_total_count")
    if not isinstance(rows, list) or not isinstance(total, int) or total < 0:
        raise ValueError("invalid_response")
    return [row for row in rows if isinstance(row, dict)], total


def build(rows):
    """전체 행 → {'도로명|건물번호': [가게, …]}. 가게 = dict(id, name, address, district, items=[dict(name, amount)]).
    음식 업종만, 도로명 주소·이름·가격 있는 품목이 있는 가게만. 품목 이름·가격은 글 그대로(같은 이름·가격이 두 번이면 한 번)."""
    from .place_identity import road_key

    shops = {}
    for row in rows:
        if str(row.get("INDUTY_CODE_SE") or "") not in FOOD_CODES:
            continue
        shop_id, name, address = (
            _text(row.get("SH_ID")),
            _text(row.get("SH_NAME")),
            _text(row.get("SH_ADDR")),
        )
        if not shop_id or not name or not road_key(address) or not district(address):
            continue
        shop = shops.setdefault(
            shop_id,
            dict(
                id=shop_id,
                name=name[:80],
                address=address[:200],
                district=district(address),
                items=[],
            ),
        )
        if (shop["name"], shop["address"]) != (name[:80], address[:200]):
            shop["conflict"] = (
                True  # 같은 가게 번호에 다른 이름·주소 — 어느 쪽인지 몰라 쓰지 않는다.
            )
        item, amount = _text(row.get("IM_NAME"))[:80], _price(row.get("IM_PRICE"))
        if item and amount is not None and dict(name=item, amount=amount) not in shop["items"]:
            shop["items"].append(dict(name=item, amount=amount))
    index = {}
    for shop in shops.values():
        if shop.pop("conflict", False) or not shop["items"]:
            continue
        road, number = road_key(shop["address"])
        index.setdefault(f"{road}|{number}", []).append(shop)
    return index


def fetch(client, key):
    """전체 자료를 페이지로 받는다. 다 받지 못하면 예외(일부만 보관하지 않는다)."""
    rows, total, start = [], None, 1
    for _ in range(MAX_PAGES):
        end = start + PAGE_ROWS - 1
        response = observed_http(client.get, URL.format(key=key, start=start, end=end))
        response.raise_for_status()
        page, total = parse_page(response.json())
        rows.extend(page)
        if end >= total or not page:
            break
        start = end + 1
    else:
        raise ValueError("too_many_rows")
    if total and len(rows) < total:
        raise ValueError("incomplete")
    return rows


def refresh():
    """서울 API 에서 전체를 새로 받아 보관한다. 배경 일꾼이 부른다(사용자 요청 안에서 부르지 않는다). 성공하면 True."""
    key = os.environ.get("SEOUL_OPEN_API_KEY", "").strip()
    if not key:
        return False
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=False) as client:
            index = build(fetch(client, key))
        if not index:
            raise ValueError("empty")
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError) as error:
        # 예외 글에는 키가 든 주소가 있을 수 있어 종류만 남긴다.
        log.warning("good_price_refresh_failed kind=%s", type(error).__name__)
        store.cache(RETRY_KEY, True, RETRY_SECONDS)
        return False
    now = datetime.now(timezone.utc)
    generation = now.strftime("%Y%m%d%H%M%S")
    store.cache_many(
        [(f"{PREFIX}{generation}:{road}", shops, KEEP_SECONDS) for road, shops in index.items()]
    )
    korea_day = (now + timedelta(hours=9)).date().isoformat()
    store.cache(
        META_KEY,
        dict(
            generation=generation,
            fetched_at=now.isoformat(),
            fetched_on=korea_day,
            shops=sum(len(v) for v in index.values()),
        ),
        KEEP_SECONDS,
    )
    return True


def _work():
    global _worker
    try:
        refresh()
    except Exception:  # 배경 받기 실패가 앱을 멈추지 않게 한다(지난 보관분 그대로).
        log.warning("good_price_worker_failed")
    finally:
        with _lock:
            _worker = None


def _start_refresh():
    """새로 받기를 배경 스레드에 맡긴다(이미 돌고 있으면 그대로). 테스트는 이 함수를 막는다(tests/conftest.py)."""
    global _worker
    with _lock:
        if _worker is None:
            _worker = threading.Thread(target=_work, name="good-price", daemon=True)
            _worker.start()


def _stale(meta):
    try:
        fetched = datetime.fromisoformat(str(meta.get("fetched_at")))
    except ValueError:
        return True
    return (datetime.now(timezone.utc) - fetched).total_seconds() >= REFRESH_SECONDS


def applies(place):
    """착한가격업소와 맞춰 볼 장소인지: 실제 서울 장소이고 이름·도로명 주소가 있으며 네이버 검색 장소가 아니다."""
    from .naver_terms import is_naver_place
    from .regions import region_from_address

    return bool(
        isinstance(place, dict)
        and not place.get("demo")
        and place.get("name")
        and region_from_address(place.get("address")) == "서울"
        and not is_naver_place(place)
    )


def match(place, shops):
    """보관한 가게 목록(같은 도로명|건물번호) 중 우리 장소와 같은 가게 하나. 없거나 둘 이상이면 None. 규칙은 모듈 설명 '같은 가게 판정'."""
    from .place_identity import _compact, _names, road_key

    ours, our_district = road_key(place.get("address")), district(place.get("address"))
    names = _names(place)
    if not ours or not our_district or not names:
        return None
    found = [
        shop
        for shop in shops or []
        if isinstance(shop, dict)
        and road_key(shop.get("address")) == ours
        and shop.get("district") == our_district
        and _compact(shop.get("name")) in names
    ]
    return found[0] if len(found) == 1 else None


def good_price_menu(place):
    """식당 메뉴 칸에 붙일 착한가격업소 메뉴. 같은 가게가 확실하지 않거나 자료가 없으면 None.
    dict(items=[dict(name, amount)], shop_name, shop_address, fetched_on, source_url, source_label). 서울 API 를 부르지 않는다."""
    if not enabled() or not applies(place):
        return None
    from .place_identity import road_key

    ours = road_key(place.get("address"))
    if not ours:
        return None
    found = store.cached_many([META_KEY, RETRY_KEY])
    meta = found.get(META_KEY)
    if (meta is None or _stale(meta)) and RETRY_KEY not in found:
        _start_refresh()
    if not isinstance(meta, dict) or not meta.get("generation"):
        return None
    shop = match(place, store.cached(f"{PREFIX}{meta['generation']}:{ours[0]}|{ours[1]}"))
    if not shop:
        return None
    return dict(
        items=[dict(item) for item in shop["items"]],
        shop_name=shop["name"],
        shop_address=shop["address"],
        fetched_on=meta.get("fetched_on"),
        source_url=SOURCE_URL,
        source_label=SOURCE_LABEL,
    )
