"""사진이 없는 장소의 네이버 이미지 검색 결과(2026-11-26).

왜: 공공 자료(관광공사)에 사진이 없는 가게가 많아 카드가 비어 보였다. 네이버 지도(플레이스) 사진은 API·제휴가 없고(네이버 답 2026-11-24 세 번째 문의 1·3번),
대신 '이미지 검색 API 결과를 선별하거나 가공하지 않고, 검색 결과의 순서 및 내용을 유지하여 표시하는 방식은 이용 가능'(같은 답 2번).
그래서 우리가 물어본 그대로 「{가게 이름} {도로명 주소}」로 검색해, 받은 순서·건수·제목 그대로 돌려준다.

지키는 것(특약 1.1~1.4, docs/naver-terms-inquiry-draft-2026-11-20.ko.md):
- 고르지 않는다: 제목에 가게 이름이 없어도, 링크가 이상해도 빼지 않는다(그 항목의 링크만 None). 순서도 그대로.
- 가공하지 않는다: 제목은 검색어 강조 태그만 빼고 글자 그대로(blog_search.original_text). 그림은 네이버가 준 썸네일 주소를 그대로 쓴다(우리가 받아 저장하지 않음).
- 화면(static/place-photos.js naverImageBlock)은 장소 사진 칸 안의 따로 접힌 칸에 '네이버 검색결과' 블록 하나로만 보이고, 블록 앞뒤에 우리 글을 붙이지 않는다.
- 우리 계산(추천·사진 판정·AI)에 넣지 않는다. 보관은 블로그와 같이 사용자별 naver_cache(최대 24시간, 새 검색 때 지움).
테스트 tests/test_naver_images.py."""
import hashlib
import os
from urllib.parse import urlencode

import httpx

from . import naver_cache as store
from .blog_search import original_text
from .image_search import LOCK_WAIT_SECONDS, _lock, safe_https, search_enabled
from .telemetry import observed_http

IMAGE_SEARCH_URL = 'https://naverapihub.apigw.ntruss.com/search/v1/image'
RESULT_TTL = 3600
NOT_FOUND_TTL = 600
# 받는 건수. 사진 칸에 한 줄 3장 × 2줄. 받은 것은 모두 보여 준다(건수를 정해서 받는 것이지 받은 뒤 고르지 않는다).
DISPLAY = 6


def image_query(place):
    """네이버에 물어본 그대로 「{가게 이름} {도로명 주소}」. 주소가 없으면 이름과 시·도."""
    from .regions import normalize_region, region_from_address

    address = str(place.get('road_address') or place.get('address') or '').strip()
    if address:
        return f"{place['name']} {address}"
    region = normalize_region(place.get('region')) or region_from_address(place.get('address')) or ''
    return f"{place['name']} {region}".strip()


def original_images(items):
    """이미지 검색 결과 → 그림 목록. 순서·건수 그대로. https 가 아닌 주소는 그 칸만 None(항목은 남긴다)."""
    def https(value):
        url = str(value or '').strip()
        return url if safe_https(url) else None

    images = []
    for item in items:
        if not isinstance(item, dict):
            continue
        images.append(dict(title=original_text(item.get('title')), thumbnail=https(item.get('thumbnail')), link=https(item.get('link'))))
    return images


def place_images(place):
    empty = {'images': [], 'provider': '네이버 이미지 검색', 'verification': '검색 결과 · 이 장소의 사진인지 확인하지 않음'}
    if place.get('demo'):
        return dict(empty, status='demo', message='가상 장소는 사진을 검색하지 않아요.')
    if not search_enabled():
        return dict(empty, status='key_missing', message='지금은 이미지 검색 결과를 불러올 수 없어요.')
    query = image_query(place)
    key = 'place-images-v1:' + hashlib.sha256(repr([place.get('id'), query]).encode()).hexdigest()
    cached = store.cached(key)
    if cached:
        return cached
    unavailable = dict(empty, status='unavailable', message='이미지 검색에 연결하지 못했어요. 잠시 후 다시 확인해 주세요.')
    if not _lock.acquire(timeout=LOCK_WAIT_SECONDS):
        return unavailable
    try:
        with httpx.Client(timeout=10) as client:
            response = observed_http(
                client.get,
                IMAGE_SEARCH_URL,
                params={'query': query, 'display': DISPLAY, 'start': 1, 'sort': 'sim', 'filter': 'all', 'format': 'json'},
                headers={'X-NCP-APIGW-API-KEY-ID': os.environ['NAVER_SEARCH_CLIENT_ID'], 'X-NCP-APIGW-API-KEY': os.environ['NAVER_SEARCH_CLIENT_SECRET']},
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        return unavailable
    finally:
        _lock.release()
    if not isinstance(data, dict) or not isinstance(data.get('items', []), list):
        return unavailable
    images = original_images(data.get('items', []))
    result = dict(
        empty,
        images=images,
        query=query,
        status='available' if images else 'not_found',
        message='' if images else '이 검색어로 찾은 이미지가 없어요.',
        search_url='https://search.naver.com/search.naver?' + urlencode({'where': 'image', 'query': query}),
    )
    store.cache(key, result, RESULT_TTL if images else NOT_FOUND_TTL)
    return result
