"""한국관광공사 TourAPI(KorService2)에서 '같은 장소'의 사진과 영업 안내를 찾는다(2026-11-19).

왜: 네이버 화면 자동 조회를 그만두며(app/naver_pages.py) 사진과 영업 정보가 줄어드는 것을, 공식·공개 자료로 메운다.
  TourAPI 는 공공데이터(공공데이터포털 이용 허락)이고 이미 축제(app/festivals.py)에 같은 TOUR_API_KEY 로 쓰고 있다.

같은 장소의 기준(모두 만족해야 연결):
  · searchKeyword2 로 장소 이름(지점 낱말을 뗀 이름)을 찾고, 좌표가 우리 장소 반경 RADIUS_M(400m) 안인 것만 남긴다.
  · 이름이 같다: 띄어쓰기·기호를 뺀 이름이 같거나, 지점 낱말을 뗀 이름이 같다(app/course_search.without_branch).
  · 그런 항목이 정확히 하나다(같은 이름이 둘이면 어느 쪽인지 모르므로 연결하지 않는다).

쓰는 것:
  · 사진 firstimage — 저작권 유형 cpyrhtDivCd 가 공공누리 제1유형(출처 표시)·제3유형(출처 표시+변경 금지)일 때만.
    축제 사진(app/festivals.py IMAGE_LICENSES)과 같은 기준. 관광공사 사진 호스트는 썸네일 서버 허용 목록
    (app/photo_thumb.py ALLOWED_HOST_SUFFIXES)에 없어 줄이지 않고 원본 그대로 보여 주므로 '변경'이 생기지 않는다.
    썸네일 허용 목록에 관광공사 호스트를 넣으려면 제3유형은 빼야 한다.
  · 영업 안내 detailIntro2 — 관광공사에 제공된 글 그대로(예: '10:00~18:00 (입장 마감 17:30)'). 일정 계산에 넣지 않고
    글로만 보여 준다. 언제 확인한 정보인지 알 수 없어 '방문 전 확인'을 늘 붙인다(app/festivals.py 의 축제 안내와 같은 원칙).
캐시: 공공데이터라 하루(CACHE_SECONDS) 둔다. 키가 없거나 실패하면 빈 결과(화면은 예전처럼 '확인 필요').
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
RADIUS_M = 400
CACHE_SECONDS = 86400
# 못 찾은 결과는 짧게 둔다. v1 키는 위치 기반 목록이 놓친 없음을 하루 붙들어 두어 고친 뒤에도 안 보였다(2026-11-19).
# 찾는 방법을 바꾸면 cache_key 의 버전(v2)도 올린다.
MISS_SECONDS = 6 * 3600
# 관광 타입(contentTypeId)별 detailIntro2 의 영업시간·쉬는 날 필드(TourAPI 4.0 매뉴얼).
HOURS_FIELDS = {
    "12": ("usetime", "restdate"),  # 관광지
    "14": ("usetimeculture", "restdateculture"),  # 문화시설
    "28": ("usetimeleports", "restdateleports"),  # 레포츠
    "38": ("opentime", "restdateshopping"),  # 쇼핑
    "39": ("opentimefood", "restdatefood"),  # 음식점
}


def _key():
    return os.getenv("TOUR_API_KEY", "").strip()


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


def _items(response):
    body = response.json().get("response", {})
    if str(body.get("header", {}).get("resultCode", "0000")) not in ("0000", "00"):
        raise ValueError("provider_error")
    group = ((body.get("body") or {}).get("items") or {}) or {}
    group = group.get("item") if isinstance(group, dict) else []
    rows = group if isinstance(group, list) else [group] if group else []
    return [row for row in rows if isinstance(row, dict)]


def same_place(place, rows):
    """rows(searchKeyword2 항목) 중 우리 장소와 같은 것 하나. 없거나 둘 이상이면 None."""
    from .course_search import without_branch

    names = {_compact(place.get("name")), _compact(without_branch(place.get("name") or ""))}
    names = {n for n in names if len(n) >= 2}
    found = []
    for row in rows:
        # 관광공사 제목에는 '[K드라마 촬영지] 공근혜갤러리', '경복궁(景福宮)'처럼 앞 꼬리표·뒤 괄호가 붙기도 한다(2026-11-19 실제 응답).
        title = re.sub(r"^\s*\[[^\]]*\]\s*", "", str(row.get("title") or ""))
        title = re.sub(r"\s*\([^)]*\)\s*$", "", title)
        if not ({_compact(title), _compact(without_branch(title))} & names):
            continue
        try:
            point = dict(lat=float(row["mapy"]), lon=float(row["mapx"]))
        except (KeyError, TypeError, ValueError):
            continue
        if distance(place, point) * 1000 <= RADIUS_M:
            found.append(row)
    return found[0] if len(found) == 1 else None


def tour_info(place):
    """dict(status, content_id, photo, hours, rest, source_url). status: available·not_found·key_missing·unavailable·not_applicable."""
    if place.get("demo") or place.get("lat") is None or place.get("lon") is None or not place.get("name"):
        return dict(status="not_applicable")
    key = _key()
    if not key:
        return dict(status="key_missing")
    if place.get("tour_content_id"):
        # 관광공사 목록에서 온 후보(app/public_places.py): 이름으로 다시 찾지 않고 그 항목의 안내만 받는다(호출 1건).
        return _listed_info(place, key)
    if str(place.get("id") or "").startswith("public:store-"):
        # 상가정보에서 온 후보는 후보를 고를 때 같은 동네의 관광공사 항목과 이미 견줬다(같은 가게면 관광공사 항목이 뽑힘).
        # 여기서 이름으로 또 찾지 않는다(하루 호출 한도를 아낌).
        return dict(status="not_found")
    cache_key = "tour-place-v2:" + hashlib.sha256(
        repr([place.get("id"), place.get("name"), place.get("lat"), place.get("lon")]).encode()
    ).hexdigest()
    cached = store.cached(cache_key)
    if cached:
        return cached
    base = dict(serviceKey=key, MobileOS="ETC", MobileApp="DateMate", _type="json")
    try:
        with httpx.Client(timeout=8) as client:
            # 이름으로 찾고(searchKeyword2) 좌표로 거른다. 위치 기반 목록(locationBasedList2)은 타입을 주지 않으면
            # 56m 옆 박물관도 빠뜨렸다(2026-11-19 실제 응답: 대한민국역사박물관·금호미술관). 같은 이름·400m·하나뿐 규칙은 그대로.
            from .course_search import without_branch

            listing = observed_http(
                client.get,
                LIST_ENDPOINT,
                params=dict(base, keyword=without_branch(place["name"]), arrange="A", numOfRows=30, pageNo=1),
            )
            listing.raise_for_status()
            if len(listing.content) > 1_000_000:
                raise ValueError("oversized_response")
            row = same_place(place, _items(listing))
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
        # 축제 사진과 같은 함수: 공공누리 유형·관광공사 사진 호스트(https)·주소 길이를 함께 본다.
        # 위치 기반 목록은 사진 주소를 http:// 로 주기도 한다(2026-11-19 실제 응답). 관광공사 사진 호스트 하나만 https 로 바꾼다.
        from .festivals import IMAGE_HOST, festival_image

        upgraded = {
            field: "https://" + str(row[field])[len("http://"):]
            for field in ("firstimage", "firstimage2")
            if str(row.get(field) or "").startswith("http://" + IMAGE_HOST + "/")
        }
        photo, license_type = festival_image(dict(row, **upgraded))
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
        )
        store.cache(cache_key, result, CACHE_SECONDS)
        return result
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
        return dict(status="unavailable")


# 관광공사 목록에서 온 장소의 영업 안내 보관(초). 안내 글은 자주 바뀌지 않고, 장소마다 하루 한 번씩 다시 부르면 하루 호출 한도
# (개발계정 1,000건)가 금방 찬다(둘러보기 한 쪽이 24곳). 그래서 7일 둔다.
LISTED_SECONDS = 7 * 86400


def _listed_info(place, key):
    """관광공사 목록에서 온 장소(tour_content_id 가 있음)의 사진·영업 안내. 사진은 목록에 실려 온 것을 쓴다(호출 없음).

    영업 안내(detailIntro2, 장소당 1건)는 app/public_places 의 하루 호출 상한 안에서만 부른다. 상한을 넘었거나 실패하면 안내 없이
    사진만 돌려주고 보관하지 않는다(다음에 다시 시도)."""
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
    )
    if type_id in HOURS_FIELDS and content_id.isdigit():
        if not public_places._reserve("tour"):
            return result
        try:
            detail = observed_http(
                httpx.get,
                DETAIL_ENDPOINT,
                params=dict(
                    serviceKey=key.strip("'\""), MobileOS="ETC", MobileApp="DateMate", _type="json",
                    contentId=content_id, contentTypeId=type_id,
                ),
                timeout=8,
            )  # fmt: skip
            detail.raise_for_status()
            intro = (_items(detail) or [{}])[0]
            hours_field, rest_field = HOURS_FIELDS[type_id]
            result.update(hours=_text(intro.get(hours_field)), rest=_text(intro.get(rest_field)))
        except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
            return result
    store.cache(cache_key, result, LISTED_SECONDS)
    return result


def _license_type(place):
    if not place.get("tour_photo"):
        return None
    return "Type1" if "제1유형" in str(place.get("tour_photo_license") or "") else "Type3"


def tour_photos(place):
    """media.py 사진 목록에 넣을 모양(공공누리 제1유형 사진이 있을 때만 한 장)."""
    info = tour_info(place)
    if info.get("status") != "available" or not info.get("photo"):
        return []
    kind = "제1유형" if info.get("license_type") == "Type1" else "제3유형(변경 금지)"
    label = "한국관광공사 제공 사진 · 공공누리 " + kind
    return [
        dict(
            id="tourapi-" + info["content_id"],
            kind="tourapi",
            provider="한국관광공사 TourAPI",
            title=place["name"] + " 장소 사진",
            source_label=label,
            source_type="public_data",
            image_url=info["photo"],
            url=info["photo"],
            source=info.get("source_url"),
            search_url=info.get("source_url"),
            caption=label + " · 좌표 400m 안·같은 이름으로 연결한 사진이에요.",
            author="한국관광공사",
            license="공공누리 " + kind,
            license_url="https://www.kogl.or.kr/info/licenseType" + ("1" if kind == "제1유형" else "3") + ".do",
            taken_at=None,
            checked_at=info.get("checked_at"),
            association="한국관광공사 관광정보의 좌표·이름 대조",
            image_role="장소 연결 사진",
        )
    ]


def tour_hours(place):
    """화면 '영업 정보' 줄에 붙일 관광공사 안내(글 그대로). 없으면 None."""
    info = tour_info(place)
    if info.get("status") != "available" or not (info.get("hours") or info.get("rest")):
        return None
    return dict(hours=info.get("hours"), rest=info.get("rest"), source_url=info.get("source_url"), checked_at=info.get("checked_at"))
