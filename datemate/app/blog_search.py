"""자체 후기와 구분하는 네이버 블로그 검색 결과. 본문 수집/실제 방문 인증 아님.

네이버 검색 API 특약 1.2(2026-09 개정): 검색 결과를 받은 순서·건수·제목·요약 그대로 보여 준다(original_posts).
이름 낱말로 거르거나 몇 건만 고르거나 제목·요약을 다듬지 않는다. 화면은 static/place-blogs.js, 코스 조사 패널은 app/course_search.py.
"""
import hashlib
import html
import os
import re
from urllib.parse import urlencode
import httpx
from . import naver_cache as store
from .telemetry import observed_http
from .image_search import search_enabled,safe_web_url,_lock,LOCK_WAIT_SECONDS

BLOG_SEARCH_URL='https://naverapihub.apigw.ntruss.com/search/v1/blog'
RESULT_TTL=3600
NOT_FOUND_TTL=600
DISPLAY=10


def original_text(value):
    """API 가 준 글자 그대로. 검색어 강조 태그(<b>)를 빼고 HTML 엔티티를 글자로 바꾸는 것만 한다(자르지 않고 공백도 그대로)."""
    return html.unescape(re.sub(r'<[^>]*>','',str(value or '')))


def original_posts(items):
    """블로그 검색 결과 → 글 목록. 순서·건수를 바꾸지 않고, 고르거나 합치지 않는다.
    링크가 웹 주소(http·https)가 아니면 그 글의 url 만 None 으로 둔다(화면은 제목을 글자로만 보여 줌)."""
    posts=[]
    for item in items:
        if not isinstance(item,dict):continue
        url=str(item.get('link') or '').strip();date=str(item.get('postdate') or '')
        posts.append(dict(title=original_text(item.get('title')),description=original_text(item.get('description')),
            url=url if safe_web_url(url) else None,blogger=original_text(item.get('bloggername')),
            posted_at=f'{date[:4]}-{date[4:6]}-{date[6:]}' if len(date)==8 and date.isdigit() else None))
    return posts


def place_blogs(place):
    empty={'posts':[],'provider':'네이버 블로그 검색','verification':'검색 결과 · 실제 방문·후기 진위 확인 안 됨'}
    if place.get('demo'):return dict(empty,status='demo',message='가상 장소의 실제 블로그 후기는 검색하지 않습니다.')
    if not search_enabled():return dict(empty,status='key_missing',message='블로그 검색 API 키가 설정되지 않았습니다.')
    from .regions import normalize_region, region_from_address
    region=normalize_region(place.get('region')) or region_from_address(place.get('address')) or '서울'
    query=f'{place["name"]} {region} 방문 후기'
    # Same place and query: reuse the answer for an hour instead of spending provider budget.
    key='place-blogs-v2:'+hashlib.sha256(repr([place.get('id'),query]).encode()).hexdigest()
    cached=store.cached(key)
    if cached:return cached
    unavailable=dict(empty,status='unavailable',message='블로그 검색에 연결하지 못했습니다. 잠시 후 다시 확인해 주세요.')
    # Wait briefly for the shared search slot; never queue request threads behind it.
    if not _lock.acquire(timeout=LOCK_WAIT_SECONDS):return unavailable
    try:
        with httpx.Client(timeout=10) as client:
            response=observed_http(client.get,BLOG_SEARCH_URL,params={'query':query,'display':DISPLAY,'start':1,'sort':'sim','format':'json'},
                headers={'X-NCP-APIGW-API-KEY-ID':os.environ['NAVER_SEARCH_CLIENT_ID'],'X-NCP-APIGW-API-KEY':os.environ['NAVER_SEARCH_CLIENT_SECRET']})
            response.raise_for_status();data=response.json()
    except (httpx.HTTPError,ValueError,TypeError,KeyError):return unavailable
    finally:_lock.release()
    if not isinstance(data,dict) or not isinstance(data.get('items',[]),list):return unavailable
    posts=original_posts(data.get('items',[]))
    result=dict(empty,posts=posts,query=query,status='available' if posts else 'not_found',
        message='' if posts else '이 검색어로 찾은 네이버 블로그 글이 없습니다.',
        search_url='https://search.naver.com/search.naver?'+urlencode({'where':'blog','query':query}))
    # Failures are not cached so the next visit can retry.
    store.cache(key,result,RESULT_TTL if posts else NOT_FOUND_TTL)
    return result
