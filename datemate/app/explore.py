"""Search date venues in one province on request from Naver local search."""
import hashlib
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
from datetime import datetime,timezone
import httpx
from .telemetry import observed_http
from fastapi import APIRouter,HTTPException,Query
from . import store
from .image_search import plain,search_enabled
from .regions import REGIONS,korean_coordinates,normalize_region,region_from_address
from .request_usage import context_map
from .routes import distance
from .search_address_text import place_query
from .web_security import require_ip

router=APIRouter()
ACTIVITIES=['카페','맛집','전시','공방','산책','실내','이색체험','소품샵','미술관','박물관','서점','방탈출','볼링','정원']
MAX_QUERIES=16
RESULT_TTL=6*3600
RANKING='선택한 지역의 네이버 지역 검색 결과를 중복 제거해 보여드려요. 전체 순위나 별점 순위는 아닙니다.'

def queries(region,activity='',q=''):
    q=' '.join(str(q or '').split())
    if activity:
        # 검색어가 있으면 모든 질의에 검색어를 넣어 결과가 검색어와 무관해지지 않게 한다.
        rows=([f'{region} {q} {activity}',f'{region} {q} 데이트 {activity}',f'{region} {q} {activity} 추천'] if q else
              [f'{region} 데이트 {activity}',f'{region} {activity} 추천',f'{region} {activity}',f'{region} 분위기 좋은 {activity}'])
    elif q:
        rows=[f'{region} {q}',f'{region} {q} 데이트',f'{region} {q} 추천',f'{region} {q} 가볼만한곳',f'{region} {q} 카페',f'{region} {q} 맛집']
    else:
        rows=[f'{region} 데이트 장소',*[f'{region} 데이트 {term}' for term in ACTIVITIES]]
    return list(dict.fromkeys(rows))[:MAX_QUERIES]

def normalize(value):return re.sub(r'[\W_]+','',str(value or '')).casefold()

def address_key(address):
    first,_,rest=str(address or '').strip().partition(' ')
    return normalize((normalize_region(first) or first)+rest)

BLOCKED_CATEGORY=('자동차','주차장','부동산','병원','의원','결혼','소개팅','결혼정보','여행사','호텔','숙박','유흥주점')
CAFE_WORDS=('카페','디저트','베이커리')
FOOD_WORDS=('음식점','한식','양식','일식','중식','분식','레스토랑')
# 업종 대분류('>' 앞)가 이 단어를 모두 포함하면 장소가 아니라 대행·광고 업체다(예: '지원,대행>전시,행사대행').
SERVICE_HEADS=(('지원','대행'),('광고','마케팅'))

def classify_local(category,name=''):
    """네이버 지역 검색 업종(category)과 상호로 (활동 분류, 식사 여부)를 고른다. 후보가 아니면 None."""
    category=str(category or '');name=str(name or '')
    if any(w in category for w in BLOCKED_CATEGORY):return None
    head=category.split('>')[0]
    if any(all(w in head for w in words) for words in SERVICE_HEADS):return None
    if any(w in category for w in CAFE_WORDS):return '카페·미식',False
    if any(w in category for w in FOOD_WORDS):return '카페·미식',True
    for words,label in [(['미술','박물관','전시','갤러리','공연','문화재','유적'],'문화·예술'),(['공방','공예','체험'],'체험·제작'),(['공원','정원','산책','숲','관광','전망','식물원','해변','해수욕장','해안','호수','둘레길'],'산책·풍경'),(['서점','도서관','책방'],'휴식·힐링'),(['방탈출','보드','오락','게임','쇼핑','소품','편집','백화점','복합문화'],'오락·놀이'),(['스포츠','레저','볼링','클라이밍','수족관','동물원'],'레저·활동')]:
        if any(w in category for w in words):
            # '갤러리카페'처럼 상호에 카페가 있으면 전시가 아니라 카페다.
            if label=='문화·예술' and '카페' in name:return '카페·미식',False
            return label,False
    return None

def classify(category):
    found=classify_local(category)
    return found[0] if found else None

def local_coordinates(item):
    """지역 검색 결과의 mapx·mapy(경위도 × 10^7)를 (lat, lon)으로. 국내 좌표가 아니면 None."""
    try:
        lon,lat=float(item['mapx']),float(item['mapy'])
        if abs(lon)>180:lon/=10000000
        if abs(lat)>90:lat/=10000000
        return (lat,lon) if korean_coordinates(lat,lon) else None
    except (KeyError,ValueError,TypeError):return None

def venue(item,query,rank,region='서울'):
    if not isinstance(item,dict):return None
    name=plain(item.get('title',''));address=plain(item.get('roadAddress') or item.get('address') or '')
    category=plain(item.get('category',''));found=classify_local(category,name)
    if not name or region_from_address(address)!=region or not found:return None
    kind,meal=found
    point=local_coordinates(item)
    if not point:return None
    lat,lon=point
    pid='discovered:'+hashlib.sha256((name+address).encode()).hexdigest()[:20]
    return dict(id=pid,name=name,address=address,lat=lat,lon=lon,region=region,demo=False,category=kind,themes=[kind],tags=[category],
        meal=meal,
        description=category,source='https://map.naver.com/p/search/'+quote(place_query({'name':name,'address':address})),source_type='네이버 지역 검색 · 장소 둘러보기',
        checked_at=datetime.now(timezone.utc).isoformat(),discovery_verification='업체명·시·도 주소·좌표 확인 · 현재 영업 여부 별도 확인',
        price=None,price_unit='person',hours=None,closed_days=None,breaks=None,last_entry=None,reservation=None,stay=None,stay_basis=None,rating=None,setting=None,
        photos=[],videos=[],license='검색 결과',search_score=1/(60+rank),found_in=[dict(query=query,rank=rank)])

def add_unique(bank,row):
    for existing in bank.values():
        if normalize(existing['name'])!=normalize(row['name']):continue
        if address_key(existing['address'])==address_key(row['address']) or distance(existing,row)<.025:
            existing['search_score']+=row['search_score']
            existing['found_in'].extend(row['found_in'])
            return False
    bank[row['id']]=row;return True

def lookup(client,query):
    key='explore-query-v1:'+hashlib.sha256(query.encode()).hexdigest()
    cached=store.cached(key)
    if cached is not None:return query,cached['items'],'available'
    try:
        response=observed_http(client.get,'https://naverapihub.apigw.ntruss.com/search/v1/local',params=dict(query=query,display=5,start=1,sort='random',format='json'),headers={'X-NCP-APIGW-API-KEY-ID':os.environ['NAVER_SEARCH_CLIENT_ID'],'X-NCP-APIGW-API-KEY':os.environ['NAVER_SEARCH_CLIENT_SECRET']})
        if response.status_code in (401,403):return query,[],'permission_required'
        response.raise_for_status();items=response.json().get('items',[])
        if not isinstance(items,list):raise ValueError('items')
        store.cache(key,dict(items=items[:5]),3600)
        return query,items[:5],'available'
    except (httpx.HTTPError,KeyError,ValueError,TypeError):return query,[],'unavailable'

def persist(places):
    """Keep found venues readable by /api/places/{id}?mode=real for the detail dialog."""
    if not places:return
    expires=time.time()+7*86400
    with store.connect() as db:
        db.executemany('INSERT INTO cache VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,expires=excluded.expires',
                       [('explore-place:'+p['id'],json.dumps(p,ensure_ascii=False),expires) for p in places])

def results(region,activity='',q=''):
    q=' '.join(q.split())
    key='explore-result-v2:'+hashlib.sha256(json.dumps([region,activity,q.casefold()],ensure_ascii=False).encode()).hexdigest()
    cached=store.cached(key)
    if cached is not None:return cached
    if not search_enabled():return dict(status='key_missing',places=[],message='네이버 검색 키가 필요해요.',queries_used=0)
    # A new (uncached) search costs up to 16 provider calls; bound them per IP range.
    require_ip('explore-search','DATEMATE_IP_EXPLORE_SEARCHES_PER_MINUTE',10,'새 조건 검색이 많아요. 잠시 후 다시 시도해 주세요.')
    bank={};errors=0;permission=False;planned=queries(region,activity,q)
    with httpx.Client(timeout=8) as client,ThreadPoolExecutor(max_workers=4) as pool:
        found=context_map(pool,lambda query:lookup(client,query),planned)
    for query,items,status in found:
        if status!='available':errors+=1
        if status=='permission_required':permission=True
        for rank,item in enumerate(items,1):
            row=venue(item,query,rank,region)
            if row:add_unique(bank,row)
    rows=sorted(bank.values(),key=lambda p:-p['search_score'])
    if permission and not rows:status,message='permission_required','네이버 지역 검색 권한을 확인해 주세요.'
    elif errors==len(planned):status,message='unavailable','장소 검색에 실패했어요. 잠시 후 다시 시도해 주세요.'
    elif rows:status,message='ready',None if not errors else '일부 검색이 실패해 찾은 장소만 보여드려요.'
    else:status,message='empty','조건에 맞는 장소를 찾지 못했어요. 다른 활동이나 검색어로 찾아보세요.'
    result=dict(status=status,places=rows,message=message,queries_used=len(planned),failed_queries=errors,
                checked_at=datetime.now(timezone.utc).isoformat())
    persist(rows)
    if status in ('ready','empty'):store.cache(key,result,RESULT_TTL if not errors else 600)
    return result

@router.get('/api/explore')
def explore(region:str=Query(default='서울',max_length=20),activity:str=Query(default='',max_length=20),q:str=Query(default='',max_length=60),
            offset:int=Query(default=0,ge=0),limit:int=Query(default=24,ge=1,le=60)):
    canonical=normalize_region(region)
    if canonical not in REGIONS:raise HTTPException(422,'지원하지 않는 시·도예요.')
    activity=activity.strip()
    if activity=='전체':activity=''
    if activity and activity not in ACTIVITIES:raise HTTPException(422,'지원하지 않는 활동이에요.')
    data=results(canonical,activity,q);rows=data.get('places',[])
    return {k:v for k,v in data.items() if k!='places'}|dict(places=rows[offset:offset+limit],total=len(rows),offset=offset,has_more=offset+limit<len(rows),
        region=canonical,activity=activity or '전체',ranking_method=RANKING,search='네이버 지역 검색 · 중복 제거')
