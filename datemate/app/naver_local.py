"""네이버 지역 검색 API 호출과, 그 결과를 화면에 '받은 그대로' 싣는 모양.

2026-11-20 2단계(docs/naver-terms-stage2-design.ko.md 3.5·3.7·3.8): 지역 검색 결과는 추천 후보·점수·필터·이유 문장의 입력으로 쓰지 않는다.
쓰는 곳은 둘뿐이다.
  · 둘러보기의 '네이버에서 더 찾기'(app/explore.py naver_blocks): 검색어 하나당 결과를 받은 순서 그대로 한 블록.
  · 출발지 검색(app/geocoding.py search_places): 주소 검색에 결과가 없을 때 사용자가 고를 장소 목록. 사용자가 고른 한 곳의 좌표가 출발지가 된다.
거르기·합치기·중복 제거·재정렬을 하지 않고, 업종 분류로 우리 활동 분류를 만들지 않는다. 보관은 사용자별 최대 24시간(app/naver_cache.py).
"""
import hashlib
import os
from urllib.parse import quote
import httpx
from . import naver_cache
from .blog_search import original_text
from .image_search import safe_web_url
from .telemetry import observed_http

LOCAL_SEARCH_URL='https://naverapihub.apigw.ntruss.com/search/v1/local'
DISPLAY=5
QUERY_TTL=3600


def lookup(client,query):
    """(검색어, 받은 항목 목록, 상태). 같은 사용자의 같은 검색어는 1시간 안에 다시 부르지 않는다. 실패는 보관하지 않는다."""
    key='explore-query-v1:'+hashlib.sha256(query.encode()).hexdigest()
    cached=naver_cache.cached(key)
    if cached is not None:return query,cached['items'],'available'
    try:
        response=observed_http(client.get,LOCAL_SEARCH_URL,params=dict(query=query,display=DISPLAY,start=1,sort='random',format='json'),
            headers={'X-NCP-APIGW-API-KEY-ID':os.environ['NAVER_SEARCH_CLIENT_ID'],'X-NCP-APIGW-API-KEY':os.environ['NAVER_SEARCH_CLIENT_SECRET']})
        if response.status_code in (401,403):return query,[],'permission_required'
        response.raise_for_status();items=response.json().get('items',[])
        if not isinstance(items,list):raise ValueError('items')
        naver_cache.cache(key,dict(items=items[:DISPLAY]),QUERY_TTL)
        return query,items[:DISPLAY],'available'
    except (httpx.HTTPError,KeyError,ValueError,TypeError):return query,[],'unavailable'


def local_coordinates(item):
    """지역 검색 결과의 mapx·mapy(경위도 × 10^7)를 (lat, lon)으로. 국내 좌표가 아니면 None. 출발지 검색만 쓴다."""
    from .regions import korean_coordinates
    try:
        lon,lat=float(item['mapx']),float(item['mapy'])
        if abs(lon)>180:lon/=10000000
        if abs(lat)>90:lat/=10000000
        return (lat,lon) if korean_coordinates(lat,lon) else None
    except (KeyError,ValueError,TypeError):return None


def original_items(items):
    """지역 검색 항목 → 화면 블록에 넣을 모양. 순서·건수를 바꾸지 않고 고르지 않는다.
    글자는 API 가 준 그대로(검색어 강조 태그 <b> 를 빼고 HTML 엔티티를 글자로 바꾸는 것만). 좌표는 싣지 않는다(지도에 그리지 않음).
    map_url 은 그 항목의 원본으로 가는 링크(네이버 지도의 같은 이름·주소 검색)다."""
    rows=[]
    for item in items:
        if not isinstance(item,dict):continue
        title=original_text(item.get('title'));road=original_text(item.get('roadAddress'));address=original_text(item.get('address'))
        link=str(item.get('link') or '').strip()
        rows.append(dict(title=title,category=original_text(item.get('category')),road_address=road,address=address,
            description=original_text(item.get('description')),telephone=original_text(item.get('telephone')),
            link=link if safe_web_url(link) else None,
            map_url='https://map.naver.com/p/search/'+quote(' '.join(' '.join(part for part in (title,road or address) if part).split()))))
    return rows
