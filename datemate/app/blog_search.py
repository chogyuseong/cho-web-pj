"""자체 후기와 구분하는 네이버 블로그 검색 요약. 본문 수집/실제 방문 인증 아님."""
import hashlib
import os
from urllib.parse import urlsplit,urlencode
import httpx
from . import store
from .telemetry import observed_http
from .image_search import search_enabled,plain,safe_https,_lock,LOCK_WAIT_SECONDS

RESULT_TTL=3600
NOT_FOUND_TTL=600

def place_blogs(place):
    empty={'posts':[],'provider':'네이버 블로그 검색','verification':'검색 결과 · 실제 방문·후기 진위 확인 안 됨'}
    if place.get('demo'):return dict(empty,status='demo',message='가상 장소의 실제 블로그 후기는 검색하지 않습니다.')
    if not search_enabled():return dict(empty,status='key_missing',message='블로그 검색 API 키가 설정되지 않았습니다.')
    from .regions import normalize_region, region_from_address
    region=normalize_region(place.get('region')) or region_from_address(place.get('address')) or '서울'
    query=f'{place["name"]} {region} 방문 후기'
    keywords=place.get('image_keywords') or [place['name']]
    # Same place and query: reuse the answer for an hour instead of spending provider budget.
    key='place-blogs-v1:'+hashlib.sha256(repr([place.get('id'),query,keywords]).encode()).hexdigest()
    cached=store.cached(key)
    if cached:return cached
    unavailable=dict(empty,status='unavailable',message='블로그 검색에 연결하지 못했습니다. 잠시 후 다시 확인해 주세요.')
    # Wait briefly for the shared search slot; never queue request threads behind it.
    if not _lock.acquire(timeout=LOCK_WAIT_SECONDS):return unavailable
    try:
        with httpx.Client(timeout=10) as client:
            response=observed_http(client.get,'https://naverapihub.apigw.ntruss.com/search/v1/blog',params={'query':query,'display':10,'start':1,'sort':'sim','format':'json'},
                headers={'X-NCP-APIGW-API-KEY-ID':os.environ['NAVER_SEARCH_CLIENT_ID'],'X-NCP-APIGW-API-KEY':os.environ['NAVER_SEARCH_CLIENT_SECRET']})
            response.raise_for_status();data=response.json()
    except (httpx.HTTPError,ValueError,TypeError,KeyError):return unavailable
    finally:_lock.release()
    try:
        if not isinstance(data,dict) or not isinstance(data.get('items',[]),list):raise ValueError('invalid_response')
        posts=[];seen=set()
        for item in data.get('items',[]):
            if not isinstance(item,dict):continue
            title=plain(item.get('title',''));description=plain(item.get('description',''));url=item.get('link','')
            if not safe_https(url) or urlsplit(url).hostname not in ('blog.naver.com','m.blog.naver.com') or url in seen:continue
            compact=''.join((title+' '+description).split()).casefold()
            if not all(''.join(word.split()).casefold() in compact for word in keywords):continue
            seen.add(url);date=str(item.get('postdate',''))
            posts.append(dict(title=title,description=description,url=url,blogger=plain(item.get('bloggername','')),
                posted_at=f'{date[:4]}-{date[4:6]}-{date[6:]}' if len(date)==8 and date.isdigit() else None))
            if len(posts)==3:break
        result=dict(empty,posts=posts,status='available' if posts else 'not_found',
            message='' if posts else '이 장소와 관련된 네이버 블로그 검색 결과가 없습니다.',
            search_url='https://search.naver.com/search.naver?'+urlencode({'where':'blog','query':query}))
    except (ValueError,TypeError,KeyError):return unavailable
    # Failures are not cached so the next visit can retry.
    store.cache(key,result,RESULT_TTL if posts else NOT_FOUND_TTL)
    return result
