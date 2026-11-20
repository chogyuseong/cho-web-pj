"""한국관광공사 TourAPI(KorService2)에서 '같은 장소'의 사진과 영업 안내를 찾는다(2026-11-19, 2026-11-20 규칙 보강).

왜: 네이버 화면 자동 조회를 그만두며(app/naver_pages.py) 사진과 영업 정보가 줄어드는 것을, 공식·공개 자료로 메운다.
  TourAPI 는 공공데이터(공공데이터포털 이용 허락)이고 이미 축제(app/festivals.py)에 같은 TOUR_API_KEY 로 쓰고 있다.

어느 관광공사 항목과 연결하나
  · 공공 자료 후보(app/public_places.py, tour_content_id 가 있음): 그 항목 그대로. 이름으로 다시 찾지 않는다.
  · 상가정보 후보(id 'public:store-'): 찾지 않는다(후보를 고를 때 같은 동네의 관광공사 항목과 이미 견줬다).
  · 그 밖(카탈로그 장소): searchKeyword2 로 이름을 찾아(search_keyword, 시·도를 알면 lDongRegnCd 로 좁힘) 아래 규칙으로 하나를 고른다.

이름 맞추기(same_place) — 두 단계, 단계마다 '반경 안에 하나뿐일 때만 연결'
  1) 같은 이름: 띄어쓰기·기호를 뺀 이름이 같거나, 지점 낱말을 뗀 이름이 같다(app/course_search.without_branch).
     관광공사 제목 앞 꼬리표('[K드라마 촬영지] …')와 뒤 괄호('경복궁(景福宮)')는 떼고 본다. 여행코스·축제 항목은 쓰지 않는다.
  2) 같은 이름이 하나도 없을 때만, 느슨한 이름(loose_key): 지역 앞말(주소의 시·도·시·군·구·읍·면 이름, 예 '제주'·'애월')을 앞에서 떼고,
     업종을 바꾸지 않는 머리·꼬리말('카페', '본점')을 떼고, 같은 뜻의 꼬리말을 한 묶음으로 본다(해수욕장=해변=비치, 전통시장=재래시장=시장).
     예: '애월한담공원' ↔ '한담공원', '제주카약올레' ↔ '카약올레', '협재해수욕장' ↔ '협재해변'.
     다른 가게 사진이 붙지 않게: 꼬리말 묶음이 다르면 다른 이름이다('한담해변' ≠ '한담해안산책로'·'애월한담공원'),
     부분 일치는 쓰지 않는다('한담해변' ≠ '한담민물장어'·'CU 제주애월한담점'), 남는 이름이 흔한 낱말(GENERIC)이거나 2자 미만이면 쓰지 않고,
     음식점·카페(우리 분류)는 관광공사 음식점(39)과만, 그 밖은 음식점이 아닌 항목과만, 숙박(32)은 연결하지 않는다.
  같은 단계에서 맞는 곳이 둘 이상이면 어느 쪽인지 모르므로 연결하지 않는다.
거리(link_radius_m): 해변·공원·산·숲·호수처럼 넓은 곳은 1km(WIDE_RADIUS_M), 그 밖은 400m(RADIUS_M).
  넓은 곳 = 관광공사 새 분류가 자연관광(NA)·도시공원(VE03)·골목길·마을·둘레길(VE04)이거나, 우리 분류가 '산책·풍경'이거나,
  이름이 해변·공원·숲·산·오름·호수 등으로 끝난다(음식점·카페는 넓은 곳으로 보지 않음).

쓰는 것
  · 대표 사진 firstimage — 저작권 유형 cpyrhtDivCd 가 공공누리 제1유형(출처 표시)·제3유형(출처 표시+변경 금지)일 때만.
    축제 사진(app/festivals.py IMAGE_LICENSES)과 같은 기준. 관광공사 사진 호스트는 썸네일 서버 허용 목록
    (app/photo_thumb.py ALLOWED_HOST_SUFFIXES)에 없어 줄이지 않고 원본 그대로 보여 주므로 '변경'이 생기지 않는다.
    썸네일 허용 목록에 관광공사 호스트를 넣으려면 제3유형은 빼야 한다.
  · 추가 사진 detailImage2 — 대표 사진이 없을 때(2026-11-20 한담해변: firstimage 는 비었는데 detailImage2 에 제3유형 8장) 부른다.
    사진마다 cpyrhtDivCd 를 보고 제1·제3유형만, 관광공사 사진 호스트만(http 는 https 로) 쓴다.
    대표 사진이 있을 때 넘겨 보기용으로도 부를지는 DATEMATE_TOUR_EXTRA_PHOTOS(기본 끔): 개발계정 하루 1,000건 한도에서 장소마다 1건이 더 들어
    운영계정 승인 전에는 끈다. 이 호출은 app/public_places 의 관광공사 하루 상한(_reserve) 안에서만 한다.
  · 영업 안내 detailIntro2 — 관광공사에 제공된 글 그대로(예: '10:00~18:00 (입장 마감 17:30)'). 일정 계산에 넣지 않고
    글로만 보여 준다. 언제 확인한 정보인지 알 수 없어 '방문 전 확인'을 늘 붙인다(app/festivals.py 의 축제 안내와 같은 원칙).

캐시(사용자 공용 store 캐시): 찾은 결과·추가 사진은 7일(공공 자료 공용 캐시 규칙), 못 찾음은 6시간, 실패는 1분(FAIL_SECONDS).
실패를 '없음'으로 두지 않는다: 키 오류·권한 오류(공공데이터포털 SERVICE_KEY_IS_NOT_REGISTERED_ERROR 등)는 HTTP 403 이나
200 + {"OpenAPI_ServiceResponse": …} 본문으로 온다(2026-11-20 확인). tour_body 가 둘 다 오류로 본다.
'사진 다시 불러오기'(force)는 실패 표시만 건너뛴다(찾은 결과·없음은 그대로 쓴다 — 하루 호출 한도 보호).
"""

import hashlib
import os
import re
from datetime import date

import httpx

from . import store
from .routes import distance
from .telemetry import observed_http

LIST_ENDPOINT = "https://apis.data.go.kr/B551011/KorService2/searchKeyword2"
DETAIL_ENDPOINT = "https://apis.data.go.kr/B551011/KorService2/detailIntro2"
IMAGE_ENDPOINT = "https://apis.data.go.kr/B551011/KorService2/detailImage2"
RADIUS_M = 400
WIDE_RADIUS_M = 1000
LIST_ROWS = 100
CACHE_SECONDS = 7 * 86400
# 못 찾은 결과는 짧게 둔다. v1 키는 위치 기반 목록이 놓친 없음을 하루 붙들어 두어 고친 뒤에도 안 보였다(2026-11-19).
# 찾는 방법을 바꾸면 cache_key 의 버전도 올린다(v3: 2026-11-20 느슨한 이름·1km·추가 사진).
MISS_SECONDS = 6 * 3600
FAIL_SECONDS = 60
IMAGE_SECONDS = 7 * 86400
# 장소 카드가 보여 주는 사진 수(app/media.py 도 5장까지)
MAX_PHOTOS = 5
# 관광 타입(contentTypeId)별 detailIntro2 의 영업시간·쉬는 날 필드(TourAPI 4.0 매뉴얼).
HOURS_FIELDS = {
    "12": ("usetime", "restdate"),  # 관광지
    "14": ("usetimeculture", "restdateculture"),  # 문화시설
    "28": ("usetimeleports", "restdateleports"),  # 레포츠
    "38": ("opentime", "restdateshopping"),  # 쇼핑
    "39": ("opentimefood", "restdatefood"),  # 음식점
}
# 장소로 연결하지 않는 관광 타입: 여행코스(25)·축제(15). 느슨한 이름에서는 숙박(32)도 뺀다.
NOT_PLACE_TYPES = ("25", "15")
FOOD_TYPE = "39"
LODGING_TYPE = "32"
# 넓은 곳의 관광공사 새 분류 앞부분: 자연관광 전체, 도시공원, 골목길·마을·둘레길.
WIDE_LCLS = ("NA", "VE03", "VE04")
WIDE_NAME = re.compile(r"(해변|해수욕장|해안|비치|공원|숲|산|오름|봉|호수|저수지|계곡|폭포|섬|수목원|정원|습지|둘레길|올레길|산책로|생태원)$")
# 느슨한 이름: 업종을 바꾸지 않는 머리·꼬리말, 같은 뜻으로 보는 꼬리말 묶음(긴 것 먼저), 그것만 남으면 쓰지 않는 흔한 낱말.
NEUTRAL_HEADS = ("카페",)
NEUTRAL_TAILS = ("본점", "카페")
SUFFIX_CLASSES = (
    ("해수욕장", "beach"),
    ("해변", "beach"),
    ("비치", "beach"),
    ("전통시장", "market"),
    ("재래시장", "market"),
    ("상설시장", "market"),
    ("시장", "market"),
)
GENERIC = {
    "카페", "식당", "공원", "해변", "해안", "바다", "시장", "박물관", "미술관", "전시관", "전망대", "거리", "마을", "광장",
    "산책로", "정원", "호수", "숲", "산", "섬", "본점", "맛집", "편의점", "주차장", "관광지", "센터",
}  # fmt: skip
# 지역 앞말을 알아보는 주소 낱말: 시·도, 시·군·구, 읍·면(동·리는 보지 않음 — 가게 이름에 흔히 들어 있다).
_ADMIN = re.compile(r"^([가-힣]{1,6}?)(특별자치도|특별자치시|특별시|광역시|자치도|도|시|군|구|읍|면)$")
_TAG = re.compile(r"^\s*\[[^\]]*\]\s*")
_PAREN = re.compile(r"\s*\([^)]*\)\s*$")


def _key():
    return os.getenv("TOUR_API_KEY", "").strip()


def extra_photos_enabled():
    """대표 사진이 있어도 detailImage2 로 넘겨 보기용 사진을 더 받을지(DATEMATE_TOUR_EXTRA_PHOTOS=1). 기본 끔(하루 한도)."""
    return os.getenv("DATEMATE_TOUR_EXTRA_PHOTOS", "").strip().lower() in ("1", "true", "yes", "on")


def _compact(text):
    return re.sub(r"[\W_]+", "", str(text or "")).casefold()


def _text(value):
    """TourAPI 안내 글의 <br> 과 태그를 줄바꿈·공백으로. 비면 None. 너무 길면 자른다."""
    if not isinstance(value, str):
        return None
    text = re.sub(r"<br\s*/?>", " / ", value, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" /")
    return text[:200] or None


def tour_body(response):
    """KorService2 응답의 body(dict). 오류 응답이면 ValueError.

    정상 응답은 {"response": {"header": {"resultCode": "0000"}, "body": …}} 이다. 오류는 다른 모양으로 온다(2026-11-20 실제 응답):
      · 키 미등록: HTTP 403 + {"OpenAPI_ServiceResponse": {"cmmMsgHeader": {"errMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR", …}}}
      · 매개변수 오류 등 서비스 오류: HTTP 200 + {"responseTime": …, "resultCode": "11", "resultMsg": "NO_MANDATORY_REQUEST_PARAMETERS_ERROR1(…)"}
    XML 이면 json() 이 ValueError 를 낸다. 'response' 와 그 머리(resultCode 0000)가 없는 응답은 모두 오류로 본다 — 예전에는 머리가 없으면
    기본값 '0000' 으로 읽어, 200 으로 온 오류를 '항목 0개'(없음)로 저장했다(관광공사 목록 7일, 장소 사진 6시간, 축제 1시간)."""
    data = response.json()
    if not isinstance(data, dict) or not isinstance(data.get("response"), dict):
        raise ValueError("provider_error")
    header = data["response"].get("header")
    if not isinstance(header, dict) or str(header.get("resultCode")) not in ("0000", "00"):
        raise ValueError("provider_error")
    body = data["response"].get("body")
    return body if isinstance(body, dict) else {}


def _items(response):
    group = tour_body(response).get("items") or {}
    group = group.get("item") if isinstance(group, dict) else []
    rows = group if isinstance(group, list) else [group] if group else []
    return [row for row in rows if isinstance(row, dict)]


# ---------------------------------------------------------------- 이름·거리 규칙


def clean_title(title):
    """관광공사 제목의 앞 꼬리표('[K드라마 촬영지] ')와 뒤 괄호('(景福宮)')를 뗀다(2026-11-19 실제 응답)."""
    return _PAREN.sub("", _TAG.sub("", str(title or ""))).strip()


def region_words(address, region=None):
    """주소에서 지역 앞말로 볼 낱말(띄어쓰기·기호 없는 소문자). '제주특별자치도 제주시 애월읍 …' → {제주특별자치도, 제주, 제주시, 애월읍, 애월}."""
    words = set()
    for token in str(address or "").split()[:4]:
        token = _compact(token)
        match = _ADMIN.match(token)
        if match:
            words.add(token)
            if len(match[1]) >= 2:
                words.add(match[1])
    from .public_places import REGION_CODES

    for name in (region, *(t for t in str(address or "").split()[:1])):
        if _compact(name) in REGION_CODES:
            words.add(_compact(name))
    return {word for word in words if len(word) >= 2}


def _strip_region(text, words):
    """앞에서 지역 앞말을 떼어 낸다(여러 번). 남는 이름이 2자 이상일 때만."""
    changed = True
    while changed:
        changed = False
        for word in sorted(words, key=len, reverse=True):
            if text.startswith(word) and len(text) - len(word) >= 2:
                text, changed = text[len(word) :], True
                break
    return text


def loose_key(name, words):
    """느슨한 이름 (남는 이름, 꼬리말 묶음). 모듈 설명의 2) 규칙."""
    from .course_search import without_branch

    text, kind = _compact(without_branch(clean_title(name))), ""
    for tail in NEUTRAL_TAILS:
        if text.endswith(tail) and len(text) - len(tail) >= 2:
            text = text[: -len(tail)]
    for suffix, found in SUFFIX_CLASSES:
        if text.endswith(suffix) and len(text) - len(suffix) >= 2:
            text, kind = text[: -len(suffix)], found
            break
    # 꼬리말을 먼저 떼고 지역 앞말을 뗀다: '애월시장'은 ('애월', 시장)으로 남아 '애월전통시장'과 같고, '애월한담해변'은 ('한담', 해변)이 된다.
    text = _strip_region(text, words)
    for head in NEUTRAL_HEADS:
        if text.startswith(head) and len(text) - len(head) >= 2:
            text = text[len(head) :]
    return text, kind


def _exact_names(name):
    from .course_search import without_branch

    name = clean_title(name)
    return {n for n in (_compact(name), _compact(without_branch(name))) if len(n) >= 2}


def _is_food(place):
    return bool(place.get("meal")) or place.get("category") == "카페·미식"


def is_wide(place, row=None):
    """넓은 곳(해변·공원·산·숲·호수 등)인지. 관광공사 분류 또는 우리 분류·이름으로 본다."""
    if _is_food(place):
        return False
    lcls = str((row or {}).get("lclsSystm3") or (row or {}).get("lclsSystm1") or "")
    if lcls.startswith(WIDE_LCLS):
        return True
    return place.get("category") == "산책·풍경" or bool(WIDE_NAME.search(_compact(clean_title(place.get("name")))))


def link_radius_m(place, row=None):
    return WIDE_RADIUS_M if is_wide(place, row) else RADIUS_M


def _point(row):
    try:
        return dict(lat=float(row["mapy"]), lon=float(row["mapx"]))
    except (KeyError, TypeError, ValueError):
        return None


def match_rows(place, rows):
    """(같은 이름 항목들, 느슨한 이름 항목들) — 둘 다 반경(link_radius_m) 안. 같은 이름이 있으면 느슨한 쪽은 비운다."""
    names = _exact_names(place.get("name"))
    ours_words = region_words(place.get("address"), place.get("region"))
    ours = loose_key(place.get("name"), ours_words)
    loose_ok = len(ours[0]) >= 2 and ours[0] not in GENERIC
    exact, loose = [], []
    for row in rows:
        type_id = str(row.get("contenttypeid") or "")
        point = _point(row)
        if type_id in NOT_PLACE_TYPES or point is None:
            continue
        if distance(place, point) * 1000 > link_radius_m(place, row):
            continue
        title = clean_title(row.get("title"))
        if _exact_names(title) & names:
            exact.append(row)
            continue
        if not loose_ok or type_id == LODGING_TYPE or _is_food(place) != (type_id == FOOD_TYPE):
            continue
        if loose_key(title, ours_words | region_words(row.get("addr1"))) == ours:
            loose.append(row)
    return exact, ([] if exact else loose)


def same_place(place, rows):
    """rows(searchKeyword2 항목) 중 우리 장소와 같은 것 하나. 없거나 같은 단계에서 둘 이상이면 None."""
    exact, loose = match_rows(place, rows)
    found = exact or loose
    return found[0] if len(found) == 1 else None


def search_keyword(place):
    """searchKeyword2 에 넣을 낱말. 이름 그대로(지점 낱말·꼬리표 뗌)가 기본이고, 지역 앞말이 있으면 떼고('제주 카약올레' → '카약올레',
    '애월한담공원' → '한담공원'), 여러 낱말이 남으면 가장 긴 낱말 하나로 찾는다(띄어쓰기가 다른 제목도 걸리게). 관광공사 검색은 제목의 부분 일치다."""
    from .course_search import without_branch

    name = " ".join(without_branch(clean_title(place.get("name"))).split())
    words = region_words(place.get("address"), place.get("region"))
    tokens = [t for t in name.split() if _compact(t) not in words and _compact(t) not in (*NEUTRAL_HEADS, *NEUTRAL_TAILS)]
    if len(tokens) > 1:
        tokens = [max(tokens, key=lambda t: len(_compact(t)))]
    keyword = tokens[0] if tokens else name
    stripped = _strip_region(_compact(keyword), words)
    if stripped != _compact(keyword) and stripped not in GENERIC:
        keyword = stripped
    return keyword if len(_compact(keyword)) >= 2 else name


def _region_code(place):
    from .public_places import REGION_CODES
    from .regions import region_from_address

    # 둘러보기의 이름 검색(public_places.tour_keyword)과 같은 값. 세종은 36110 이다.
    return REGION_CODES.get(place.get("region") or region_from_address(place.get("address")))


def _search_rows(place, client, base):
    """searchKeyword2 로 받은 항목들(호출 1건). 찾는 낱말(search_keyword)의 결과가 LIST_ROWS 를 넘어 잘렸으면 '하나뿐'인지 알 수 없으므로
    이름 전체로 한 번 더 좁혀 찾는다(드묾: '더 현대 서울'처럼 흔한 낱말 하나로 찾게 되는 이름).
    그래도 잘렸으면 빈 목록을 돌려준다: 받지 못한 항목 중에 같은 이름이 또 있을 수 있어 '반경 안에 하나뿐'을 지킬 수 없다(연결하지 않음)."""
    from .course_search import without_branch

    name = " ".join(without_branch(clean_title(place.get("name"))).split()) or str(place.get("name"))
    for keyword in dict.fromkeys((search_keyword(place), name)):
        params = dict(base, keyword=keyword, arrange="A", numOfRows=LIST_ROWS, pageNo=1)
        if _region_code(place):
            params["lDongRegnCd"] = _region_code(place)
        listing = observed_http(client.get, LIST_ENDPOINT, params=params)
        listing.raise_for_status()
        if len(listing.content) > 2_000_000:
            raise ValueError("oversized_response")
        rows = _items(listing)
        if int(tour_body(listing).get("totalCount") or 0) <= len(rows):
            return rows
    return []


# ---------------------------------------------------------------- 조회


def _base(key):
    return dict(serviceKey=key.strip("'\""), MobileOS="ETC", MobileApp="DateMate", _type="json")


def _failed(cache_key):
    result = dict(status="unavailable")
    store.cache(cache_key, result, FAIL_SECONDS)
    return result


def tour_info(place, force=False):
    """dict(status, content_id, photo, hours, rest, source_url, link). status: available·not_found·key_missing·unavailable·not_applicable.

    link: listed(공공 자료 후보의 항목 그대로)·exact(같은 이름)·loose(느슨한 이름). radius_m: 연결에 쓴 거리."""
    if place.get("demo") or place.get("lat") is None or place.get("lon") is None or not place.get("name"):
        return dict(status="not_applicable")
    key = _key()
    if not key:
        return dict(status="key_missing")
    if place.get("tour_content_id"):
        # 관광공사 목록에서 온 후보(app/public_places.py): 이름으로 다시 찾지 않고 그 항목의 안내만 받는다(호출 1건).
        return _listed_info(place, key, force)
    if str(place.get("id") or "").startswith("public:store-"):
        # 상가정보에서 온 후보는 후보를 고를 때 같은 동네의 관광공사 항목과 이미 견줬다(같은 가게면 관광공사 항목이 뽑힘).
        # 여기서 이름으로 또 찾지 않는다(하루 호출 한도를 아낌).
        return dict(status="not_found")
    cache_key = "tour-place-v3:" + hashlib.sha256(
        repr([place.get("id"), place.get("name"), place.get("address"), place.get("lat"), place.get("lon")]).encode()
    ).hexdigest()
    cached = store.cached(cache_key)
    if cached and not (force and cached.get("status") == "unavailable"):
        return cached
    base = _base(key)
    try:
        with httpx.Client(timeout=8) as client:
            # 이름으로 찾고(searchKeyword2) 좌표로 거른다. 위치 기반 목록(locationBasedList2)은 타입을 주지 않으면
            # 56m 옆 박물관도 빠뜨렸다(2026-11-19 실제 응답: 대한민국역사박물관·금호미술관).
            row = same_place(place, _search_rows(place, client, base))
            if row is None:
                result = dict(status="not_found")
                store.cache(cache_key, result, MISS_SECONDS)
                return result
            content_id, type_id = str(row.get("contentid") or ""), str(row.get("contenttypeid") or "")
            hours = rest = None
            if type_id in HOURS_FIELDS and content_id.isdigit():
                detail = observed_http(
                    client.get, DETAIL_ENDPOINT, params=dict(base, contentId=content_id, contentTypeId=type_id)
                )
                detail.raise_for_status()
                intro = (_items(detail) or [{}])[0]
                hours_field, rest_field = HOURS_FIELDS[type_id]
                hours, rest = _text(intro.get(hours_field)), _text(intro.get(rest_field))
        photo, license_type = row_photo(row)
        exact, _ = match_rows(place, [row])
        result = dict(
            status="available",
            content_id=content_id,
            title=_text(row.get("title")),
            photo=photo,
            license_type=license_type if photo else None,
            hours=hours,
            rest=rest,
            source_url=f"https://korean.visitkorea.or.kr/detail/ms_detail.do?cotid={content_id}" if content_id else None,
            checked_at=date.today().isoformat(),
            link="exact" if exact else "loose",
            radius_m=link_radius_m(place, row),
        )
        store.cache(cache_key, result, CACHE_SECONDS)
        return result
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
        return _failed(cache_key)


# 관광공사 목록에서 온 장소의 영업 안내 보관(초). 안내 글은 자주 바뀌지 않고, 장소마다 하루 한 번씩 다시 부르면 하루 호출 한도
# (개발계정 1,000건)가 금방 찬다(둘러보기 한 쪽이 24곳). 그래서 7일 둔다.
LISTED_SECONDS = 7 * 86400


def _listed_info(place, key, force=False):
    """관광공사 목록에서 온 장소(tour_content_id 가 있음)의 사진·영업 안내. 사진은 목록에 실려 온 것을 쓴다(호출 없음).

    영업 안내(detailIntro2, 장소당 1건)는 app/public_places 의 하루 호출 상한 안에서만 부른다. 상한을 넘었거나 실패하면 안내 없이
    사진만 돌려주고 보관하지 않는다(다음에 다시 시도). 실패는 1분 동안 다시 부르지 않는다(force 면 다시)."""
    from . import public_places

    content_id, type_id = str(place["tour_content_id"]), str(place.get("tour_content_type") or "")
    cache_key = "tour-listed-v1:" + content_id
    cached = store.cached(cache_key)
    if cached:
        return cached
    result = dict(
        status="available",
        content_id=content_id,
        title=place.get("name"),
        photo=place.get("tour_photo"),
        license_type=_license_type(place),
        hours=None,
        rest=None,
        source_url=place.get("source"),
        checked_at=date.today().isoformat(),
        link="listed",
        radius_m=None,
    )
    if type_id in HOURS_FIELDS and content_id.isdigit():
        retry_key = "tour-listed-retry-v1:" + content_id
        if (store.cached(retry_key) and not force) or not public_places._reserve("tour"):
            return result
        try:
            detail = observed_http(
                httpx.get,
                DETAIL_ENDPOINT,
                params=dict(_base(key), contentId=content_id, contentTypeId=type_id),
                timeout=8,
            )
            detail.raise_for_status()
            intro = (_items(detail) or [{}])[0]
            hours_field, rest_field = HOURS_FIELDS[type_id]
            result.update(hours=_text(intro.get(hours_field)), rest=_text(intro.get(rest_field)))
        except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
            store.cache(retry_key, True, FAIL_SECONDS)
            return result
    store.cache(cache_key, result, LISTED_SECONDS)
    return result


def _license_type(place):
    if not place.get("tour_photo"):
        return None
    return "Type1" if "제1유형" in str(place.get("tour_photo_license") or "") else "Type3"


# ---------------------------------------------------------------- 사진


def safe_image(url):
    """관광공사 사진 호스트의 https 주소만(http 는 https 로 바꿈). 아니면 None."""
    from .festivals import IMAGE_HOST, festival_image

    url = str(url or "").strip()
    if url.startswith("http://" + IMAGE_HOST + "/"):
        url = "https://" + url[len("http://") :]
    return festival_image(dict(firstimage=url, cpyrhtDivCd="Type1"))[0]


def row_photo(row):
    """(대표 사진 주소, 공공누리 유형). 공공누리 제1·제3유형이고 관광공사 사진 호스트일 때만. 위치 기반 목록은 http:// 로 주기도 한다(2026-11-19)."""
    from .festivals import festival_image

    upgraded = {field: safe_image(row.get(field)) for field in ("firstimage", "firstimage2")}
    return festival_image(dict(row, **{field: url or "" for field, url in upgraded.items()}))


def tour_images(content_id, force=False):
    """detailImage2 의 사진들(공공누리 제1·제3유형, 관광공사 사진 호스트만). dict(status, photos=[dict(url, license_type, name, serial)]).

    status: available(사진 있음)·not_found(자료에 사진 없음 — 확정)·unavailable(실패, 1분 뒤 다시)·limited(하루 상한)·key_missing.
    공용 캐시 7일(IMAGE_SECONDS). 실패는 1분(FAIL_SECONDS), force 면 실패 표시를 건너뛴다."""
    from . import public_places

    content_id = str(content_id or "")
    if not content_id.isdigit():
        return dict(status="not_found", photos=[])
    key = _key()
    if not key:
        return dict(status="key_missing", photos=[])
    cache_key = "tour-images-v1:" + content_id
    hit = store.cached(cache_key)
    if hit and not (force and hit.get("status") == "unavailable"):
        public_places._hit("tour_image")
        return hit
    if not public_places._reserve("tour"):
        public_places.STATS["tour_image_limited"] += 1
        return dict(status="limited", photos=[])
    public_places.STATS["tour_image_call"] += 1
    try:
        response = observed_http(
            httpx.get,
            IMAGE_ENDPOINT,
            params=dict(_base(key), contentId=content_id, imageYN="Y", numOfRows=20, pageNo=1),
            timeout=8,
        )
        response.raise_for_status()
        if len(response.content) > 1_000_000:
            raise ValueError("oversized_response")
        photos, seen = [], set()
        for item in _items(response):
            license_type = str(item.get("cpyrhtDivCd") or "").strip()
            url = safe_image(item.get("originimgurl")) or safe_image(item.get("smallimageurl"))
            if license_type not in ("Type1", "Type3") or not url or url in seen:
                continue
            seen.add(url)
            photos.append(
                dict(url=url, license_type=license_type, name=_text(item.get("imgname")), serial=str(item.get("serialnum") or "")[:40])
            )
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
        public_places.STATS["tour_image_failed"] += 1
        failed = dict(status="unavailable", photos=[])
        store.cache(cache_key, failed, FAIL_SECONDS)
        return failed
    result = dict(status="available" if photos else "not_found", photos=photos[:8])
    store.cache(cache_key, result, IMAGE_SECONDS)
    return result


def _photo_entry(place, info, url, license_type, suffix="", index=0):
    kind = "제1유형" if license_type == "Type1" else "제3유형(변경 금지)"
    label = "한국관광공사 제공 사진 · 공공누리 " + kind
    # 7일 보관된 예전 결과(tour-listed-v1)에는 link 가 없다. 공공 자료 후보는 늘 항목 그대로다.
    link = "listed" if place.get("tour_content_id") else info.get("link")
    if link == "listed":
        how, association = "한국관광공사 관광정보 항목의 사진이에요.", "한국관광공사 관광정보 항목"
    elif link == "loose":
        how = f"좌표 {info.get('radius_m') or RADIUS_M}m 안에서 이름이 맞는 한 곳(띄어쓰기·지역 이름 차이는 무시)으로 연결한 사진이에요."
        association = "한국관광공사 관광정보의 좌표·이름 대조"
    else:
        how = f"좌표 {info.get('radius_m') or RADIUS_M}m 안·같은 이름으로 연결한 사진이에요."
        association = "한국관광공사 관광정보의 좌표·이름 대조"
    return dict(
        id="tourapi-" + info["content_id"] + suffix,
        kind="tourapi",
        provider="한국관광공사 TourAPI",
        title=place["name"] + " 장소 사진" + (f" {index + 1}" if index else ""),
        source_label=label,
        source_type="public_data",
        image_url=url,
        url=url,
        source=info.get("source_url"),
        search_url=info.get("source_url"),
        caption=label + " · " + how,
        author="한국관광공사",
        license="공공누리 " + kind,
        license_url="https://www.kogl.or.kr/info/licenseType" + ("1" if kind == "제1유형" else "3") + ".do",
        taken_at=None,
        checked_at=info.get("checked_at"),
        association=association,
        image_role="장소 연결 사진",
    )


def tour_photo_result(place, force=False):
    """media.py 사진 목록에 넣을 관광공사 사진들과 상태. dict(status, photos).

    대표 사진(firstimage)이 있으면 그것 하나(DATEMATE_TOUR_EXTRA_PHOTOS 면 detailImage2 사진도 뒤에), 없으면 detailImage2 사진들.
    status: available · not_found(연결된 항목이 없거나 사진이 없음 — 확정) · unavailable(실패 — 다시 시도할 만함) ·
            limited(하루 상한) · key_missing · not_applicable."""
    info = tour_info(place, force)
    if info.get("status") != "available":
        return dict(status=info.get("status") or "not_found", photos=[])
    found = []
    if info.get("photo"):
        found.append((info["photo"], info.get("license_type") or "Type3", ""))
    status = "available" if found else "not_found"
    if not found or extra_photos_enabled():
        images = tour_images(info.get("content_id"), force)
        if not found and images["status"] != "available":
            status = images["status"]
        for photo in images["photos"]:
            if all(photo["url"] != url for url, _, _ in found):
                found.append((photo["url"], photo["license_type"], "-" + (photo["serial"] or str(len(found)))))
        if found:
            status = "available"
    photos = [_photo_entry(place, info, url, license_type, suffix, index) for index, (url, license_type, suffix) in enumerate(found[:MAX_PHOTOS])]
    return dict(status=status, photos=photos)


def tour_photos(place, force=False):
    """media.py 사진 목록에 넣을 모양(공공누리 제1·제3유형 관광공사 사진, 최대 MAX_PHOTOS 장)."""
    return tour_photo_result(place, force)["photos"]


def tour_hours(place):
    """화면 '영업 정보' 줄에 붙일 관광공사 안내(글 그대로). 없으면 None."""
    info = tour_info(place)
    if info.get("status") != "available" or not (info.get("hours") or info.get("rest")):
        return None
    return dict(hours=info.get("hours"), rest=info.get("rest"), source_url=info.get("source_url"), checked_at=info.get("checked_at"))
