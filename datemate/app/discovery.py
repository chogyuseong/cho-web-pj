"""블로그의 장소·주소 인용을 검증한 후 공개 지도 정보에 연결한다."""
import hashlib
import os
import re
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from .request_usage import context_map
from datetime import datetime,timezone
import httpx
from .telemetry import observed_http
from . import naver_cache, store
from .image_search import plain
from .geocoding import search_address
from .regions import region_from_address, korean_coordinates


def norm(s):return ''.join(s.casefold().split())

def extract(posts):
    # 네이버 검색 API 특약 2.3(2026-09 개정): 검색 결과(제목·요약)와 그 파생물을 AI 입력에 쓸 수 없다.
    # 블로그 글에서 장소를 뽑는 LLM 추출은 키가 있어도 끈다. 규칙 기반 대체는 2단계에서 검토한다(docs/naver-terms-review-2026-11-19.ko.md).
    return [],'ai_blocked_by_naver_terms'


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

def resolve(mention,posts,query):
    name=mention['name'];items,status=local_lookup(name,query.replace('데이트 코스',''))
    point=None;address='';verification='';local_source=''
    for item in items:
        title=plain(item.get('title',''))
        if not title or (norm(name) not in norm(title) and norm(title) not in norm(name)):continue
        address=plain(item.get('roadAddress') or item.get('address',''))
        region=region_from_address(address)
        if not region:continue
        # 같은 이름의 다른 지점은 원문 주소와 일치해야 한다.
        if mention['address']:
            numbers=re.findall(r'[가-힣]+(?:로|길)\d*|\d+(?:-\d+)?',mention['address'])
            if numbers and not all(n in address for n in numbers):continue
        try:
            lon,lat=float(item['mapx']),float(item['mapy'])
            if abs(lon)>180:lon/=10000000
            if abs(lat)>90:lat/=10000000
            if not korean_coordinates(lat,lon):continue
            point=dict(lat=lat,lon=lon);name=title;verification='네이버 업체 검색으로 상호·주소·좌표 연결';local_source='https://map.naver.com/p/search/'+quote(title)
            break
        except (ValueError,KeyError,TypeError):continue
    if point is None and mention['address']:
        found=search_address(mention['address'])
        candidates=[p for p in found.get('results',[]) if region_from_address(p['name'])]
        # 주소가 유일할 때만 사용. 상호 존재/현재 영업 여부까지 확인된 것은 아니다.
        if len(candidates)==1:
            point=candidates[0];address=point['name'];verification='블로그 원문 상호·주소 인용 + 네이버 주소 좌표 확인 (업체 영업 여부 미검증)'
    if point is None:return None,status
    source=next(p['url'] for p in posts if p['rank']==mention['rank'])
    category={'restaurant':'카페·미식','cafe':'카페·미식','culture':'문화·예술','workshop':'체험·제작','park':'산책·풍경'}.get(mention['kind'])
    if not category:return None,'unsupported'
    pid='discovered:'+hashlib.sha256((name+address).encode()).hexdigest()[:20]
    row=dict(id=pid,name=name,address=address,lat=point['lat'],lon=point['lon'],region=region_from_address(address),demo=False,
        category=category,themes=[category],search_aliases=[mention['name']],tags=[mention['kind']],meal=mention['kind']=='restaurant',setting=None,
        source=source,source_type='블로그 발견 · 주소 연결',naver_result=True,checked_at=datetime.now(timezone.utc).isoformat(),
        discovery_verification=verification,place_source=local_source,description='블로그에서 발견한 장소. 현재 영업·예약·가격은 별도 확인이 필요해요.',
        price=None,price_unit='person',hours=None,closed_days=None,breaks=None,last_entry=None,reservation=None,stay=None,stay_basis=None,rating=None,photos=[],videos=[],license='검색 결과와 원문 인용',
        discovery_evidence=dict(source=source,quote=mention['quote'],rank=mention['rank']))
    naver_cache.cache('discovered-place:'+pid,row,naver_cache.PERSONAL_MAX_SECONDS)
    return row,'available'

def discover(posts,query):
    mentions,status=extract(posts)
    with ThreadPoolExecutor(max_workers=3) as pool:resolved=context_map(pool,lambda m:resolve(m,posts,query),mentions)
    rows={p['id']:p for p,_ in resolved if p}
    return list(rows.values()),dict(status=status,extracted=len(mentions),resolved=len(rows),local_permission_required=any(s=='permission_required' for _,s in resolved))
