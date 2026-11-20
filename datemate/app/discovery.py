"""공식 네이버 지역 검색 API 호출(요청 활동 후보 app/intent_discovery.py, 같은 업체 확인 app/place_identity.py 가 쓴다).

블로그 글에서 장소를 뽑아 후보로 연결하던 경로(extract·resolve·discover)는 없앴다.
  · 2026-11-20 1단계: 검색 결과를 AI 입력에 쓸 수 없어(특약 2.3) LLM 추출을 껐다.
  · 2단계: 블로그 검색 결과를 추천 계산에 쓰지 않는다(특약 2.2, docs/naver-terms-stage2-design.ko.md 3.1(a)).
"""
import os
from contextvars import ContextVar
import httpx
from .telemetry import observed_http
from . import store


LOCAL_SEARCH_URL='https://naverapihub.apigw.ntruss.com/search/v1/local'
# 여러 건을 한꺼번에 찾는 쪽(intent_discovery.lookup_all)이 권한 없음 표시를 이미 한 번 확인했으면 True.
permission_checked=ContextVar('local_permission_checked',default=False)

def local_lookup(name,area,sort='random'):
    """sort: 'random'(정확도순, 기본) 또는 'comment'(카페·블로그 리뷰 수순)."""
    if not permission_checked.get() and store.cached('discovery-local-permission'):return [],'permission_required'
    try:
        r=observed_http(httpx.get,LOCAL_SEARCH_URL,params=dict(query=area+' '+name,display=5,sort=sort if sort in ('random','comment') else 'random',format='json'),headers={'X-NCP-APIGW-API-KEY-ID':os.getenv('NAVER_SEARCH_CLIENT_ID',''),'X-NCP-APIGW-API-KEY':os.getenv('NAVER_SEARCH_CLIENT_SECRET','')},timeout=6)
        if r.status_code in (401,403):
            store.cache('discovery-local-permission',True,60)
            return [],'permission_required'
        r.raise_for_status();return r.json().get('items',[]),'available'
    except (httpx.HTTPError,ValueError):return [],'unavailable'
