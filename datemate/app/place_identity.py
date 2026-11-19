"""같은 업체인지 공식 네이버 지역 검색 API 로 확인(2026-11-19).

카드의 '위치' 줄(static/plan-evidence.js identityEvidence)이 이 결과로 '확인됨'이 된다. 예전에는 네이버 검색 결과 화면을
자동으로 읽어 업체 번호를 찾았는데, 네이버 약관상 그 방식을 쓰지 않기로 했다(app/naver_pages.py).

규칙(모두 만족해야 확인됨):
  · 지역 검색 API 결과 중 이름이 같은 업체 — 띄어쓰기·기호를 뺀 이름이 같거나, 지점 낱말을 뗀 이름이 같을 때
    (app/course_search.without_branch, 업종 낱말 '서점' 등은 떼지 않음)
  · 그 업체의 좌표가 우리 장소에서 MAX_KM(0.4km) 안
  · 위 두 조건을 만족하는 업체가 정확히 하나(같은 이름 지점이 근처에 둘이면 어느 쪽인지 모르므로 확인하지 않음)
API 결과에는 네이버 지도 업체 번호가 없어 지도 링크는 검색 주소 그대로다(업체 화면으로 바로 열지 않는다).

캐시: 우리가 계산한 참·거짓과 확인 시각만 CACHE_SECONDS(1시간) 둔다. API 결과(이름·주소·좌표)는 저장하지 않는다
(네이버 API 약관 7.3 ③ 별도 데이터베이스 관리 금지, docs/popup-stage0-2026-11-14.md).
함께 바꿀 값: MAX_KM 을 바꾸면 static/plan-evidence.js 의 IDENTITY_VERIFIED 문구('400m 안')도 고친다.
"""

import hashlib
import re

from . import store
from .routes import distance

MAX_KM = 0.4
CACHE_SECONDS = 3600


def _compact(text):
    return re.sub(r"[\W_]+", "", re.sub(r"<[^>]+>", "", str(text or ""))).casefold()


def _point(item):
    """지역 검색 API 의 mapx·mapy 를 위도·경도로(app/explore.py local_coordinates 와 같은 해석). 읽을 수 없으면 None."""
    from .explore import local_coordinates

    found = local_coordinates(item)
    return dict(lat=found[0], lon=found[1]) if found else None


def matches(place, items):
    """지역 검색 결과 items 중 같은 업체로 볼 수 있는 것의 수(이름 같음 + MAX_KM 안)."""
    from .course_search import without_branch

    names = {_compact(place.get("name")), _compact(without_branch(place.get("name") or ""))}
    names = {n for n in names if len(n) >= 2}
    count = 0
    for item in items:
        title = re.sub(r"<[^>]+>", "", str(item.get("title") or ""))
        if not ({_compact(title), _compact(without_branch(title))} & names):
            continue
        point = _point(item)
        if point and distance(place, point) <= MAX_KM:
            count += 1
    return count


def verify_identity(place):
    """dict(verified=bool, method=str). 키가 없거나 API 를 못 쓰면 verified=False(모른다)로 둔다."""
    if place.get("demo") or not place.get("name") or place.get("lat") is None or place.get("lon") is None:
        return dict(verified=False, method="not_applicable")
    from .image_search import search_enabled

    if not search_enabled():
        return dict(verified=False, method="key_missing")
    key = "place-identity-v1:" + hashlib.sha256(
        repr([place.get("id"), place.get("name"), place.get("lat"), place.get("lon")]).encode()
    ).hexdigest()
    cached = store.cached(key)
    if cached:
        return cached
    from .discovery import local_lookup
    from .regions import normalize_region, region_from_address

    address = place.get("address") or ""
    district = re.search(r"([가-힣]+(?:구|군|시))(?=\s|$)", address)
    area = " ".join(filter(None, [normalize_region(place.get("region")) or region_from_address(address), district[1] if district else ""]))
    items, status = local_lookup(place["name"], area)
    if status != "available":
        return dict(verified=False, method=status)
    result = dict(verified=matches(place, items) == 1, method="naver_local_search_api")
    store.cache(key, result, CACHE_SECONDS)
    return result
