"""지역·취향 검색어로 찾은 네이버 블로그 글을 받은 그대로 보여 주기 위한 조회.

네이버 검색 API 특약 1.2(2026-09 개정, docs/naver-terms-stage2-design.ko.md 3.1(a)):
  · 검색 결과는 네이버가 준 순서 그대로, 받은 건수 그대로, 제목·요약 원문 그대로 독립 블록으로만 보여 준다(static/course-search.js).
  · 추천 계산(후보·순위·이유 문장)에는 쓰지 않는다. 글을 골라내거나 점수를 매기지 않고, 글에 나온 장소를 찾지도 않는다.
여기서 추천이 쓰는 것은 검색어 문자열(course_query, 우리 조건에서 만든 값)뿐이다.
"""
import os
import re
from datetime import datetime, timezone
import httpx
from .telemetry import observed_http
from . import naver_cache as store
from .blog_search import BLOG_SEARCH_URL, original_posts
from .image_search import search_enabled
from .routes import distance
from .request_usage import cache_hit

# 화면이 새 형식(받은 그대로)인지 가리는 값. 이 값이 없는 예전 저장 코스의 course_search 는 그리지 않는다(마이그레이션 v0006 이 지움).
FORMAT = 2
DISPLAY = 20


def base_course_query(c):
    if c.course_query.strip():
        query=c.course_query.strip()
        from .seoul_districts import DISTRICT_ADDRESSES
        if query.removeprefix('서울특별시').removeprefix('서울').strip() in DISTRICT_ADDRESSES:
            return query+' 데이트 코스'
        from .quality import AREAS
        if any(area.rstrip('동') in query for area in AREAS) or re.search(r'[가-힣]{2,8}(?:동|구|역)',query):return query
        area=base_course_query(c.model_copy(update={'course_query':''})).replace(' 데이트 코스','')
        return area+' '+query
    name=c.origin.name
    if name.startswith('지도에서 선택'):
        from .geocoding import district_at
        name=district_at(c.origin.lat,c.origin.lon)
        if not name:return '지도 위치의 지역명 확인 필요'
    district=re.search(r'([가-힣]{1,8}구)(?:\s|$)',name)
    if district:return (c.region+' ' if c.region!='서울' else '')+district[1]+' 데이트 코스'
    area=re.search(r'[가-힣]{2,8}동',c.request+' '+name)
    if area:return (c.region+' ' if c.region!='서울' else '')+area[0]+' 데이트 코스'
    if c.region!='서울':return c.region+' '+re.sub(r'\s*(지역 중심|지도에서 선택.*)$','',name).strip()+' 데이트 코스'
    anchors=[('연남동',37.5572,126.9254),('성수동',37.5446,127.0559),('종로',37.5765,126.9855),('강남',37.4979,127.0276)]
    closest=min(anchors,key=lambda a:distance(c.origin.model_dump(),dict(lat=a[1],lon=a[2])))
    if distance(c.origin.model_dump(),dict(lat=closest[1],lon=closest[2]))<2:return closest[0]+' 데이트 코스'
    return re.sub(r'\s*(지역 중심|지도에서 선택.*)$','',name)+' 데이트 코스'


def course_query(c):
    from .taxonomy import CONCEPT_PROFILES
    base=base_course_query(c)
    profile=CONCEPT_PROFILES.get(c.date_subcategory)
    from .request_intent import search_terms
    additions=search_terms(c)
    if profile:additions+=[c.date_subcategory,*profile['search'].split()]
    if not additions:return base
    return base+' '+ ' '.join(word for word in additions if word not in base)


# 지점 낱말이 아니라 업종을 뜻하는 '…점'. 이 낱말로 끝나면 떼지 않는다('책방 서점'을 '책방'으로 줄이지 않게).
NOT_BRANCH=('서점','백화점','편의점','상점','매점','주점','문구점','할인점','전문점','음식점','제과점','정육점','과일점')


def without_branch(name):
    '''OO카페 성수점 -> OO카페. 띄어 쓴 마지막 낱말이 …점(지점·본점 포함)이고 업종 낱말이 아닐 때만 뗀다.'''
    head,sep,last=name.rstrip().rpartition(' ')
    if not sep or not head.strip() or not last.endswith('점') or len(last)<2 or last in NOT_BRANCH:return name
    return head.strip()


def _fetch(query):
    response=observed_http(httpx.get,BLOG_SEARCH_URL,params=dict(query=query,display=DISPLAY,start=1,sort='sim',format='json'),
        headers={'X-NCP-APIGW-API-KEY-ID':os.environ['NAVER_SEARCH_CLIENT_ID'],'X-NCP-APIGW-API-KEY':os.environ['NAVER_SEARCH_CLIENT_SECRET']},timeout=8)
    response.raise_for_status()
    data=response.json()
    if not isinstance(data,dict) or not isinstance(data.get('items',[]),list):raise ValueError('invalid_response')
    return data.get('items',[])


def search_courses(c):
    """코스 조사 패널에 보여 줄 블로그 검색 결과. requested_query 는 조건에서 만든 검색어(검색 결과와 무관)라 추천의 동네 기준에 쓴다.
    posts 는 네이버가 준 순서·건수·제목·요약 그대로다(blog_search.original_posts). 결과가 0건이면 취향 낱말을 뺀 지역 검색어로 한 번 더 찾고
    그 사실(search_relaxed)과 실제 검색어(query)를 함께 돌려준다."""
    query=course_query(c)
    result=dict(format=FORMAT,query=query,provider='네이버 블로그 검색 · 관련도순 최대 '+str(DISPLAY)+'건',posts=[],
                requested_query=query,search_history=[],concept=c.date_subcategory,search_relaxed=False,
                checked_at=datetime.now(timezone.utc).isoformat(),status='key_missing')
    if not search_enabled():return result
    if '지도 위치의 지역명 확인 필요' in query:
        result.update(status='location_unresolved',message='선택 좌표의 지역명을 확인하지 못해 블로그 글을 찾지 않았어요. 지역명을 검색해 선택하면 그 지역의 글을 볼 수 있어요.')
        return result
    key='course-blog-v4:'+query+':'+str(c.visit_date)
    cached=store.cached(key)
    if cached:cache_hit('course_blog');return cached
    try:
        items=_fetch(query)
        result['search_history'].append(dict(query=query,result_count=len(items)))
        base=base_course_query(c)
        if not items and query!=base:
            query=base
            items=_fetch(query)
            result.update(query=query,search_relaxed=True)
            result['search_history'].append(dict(query=query,result_count=len(items)))
        result['posts']=original_posts(items)
        result['status']='available' if result['posts'] else 'not_found'
        result['message']='' if result['posts'] else '이 검색어로 찾은 블로그 글이 없어요.'
        store.cache(key,result,900)
    except (httpx.HTTPError,ValueError,TypeError,KeyError):result.update(status='unavailable',message='네이버 블로그 검색에 연결하지 못했어요. 코스 추천에는 영향이 없어요.')
    return result
