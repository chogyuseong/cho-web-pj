from .search_address_text import place_query
"""Collect up to 500 distinct Seoul venues from ranked local-search queries."""
import hashlib
import json
import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from urllib.parse import quote
from datetime import datetime,timezone
import httpx
from .telemetry import observed_http
from fastapi import APIRouter,HTTPException,Query
from . import store
from .image_search import plain,search_enabled
from .routes import distance

router=APIRouter()
KEY='explore-seoul-500-v1'
LIMIT=500
DISTRICTS=['종로구','중구','용산구','성동구','광진구','동대문구','중랑구','성북구','강북구','도봉구','노원구','은평구','서대문구','마포구','양천구','강서구','구로구','금천구','영등포구','동작구','관악구','서초구','강남구','송파구','강동구']
TERMS=['데이트 카페','데이트 맛집','데이트 전시','데이트 공방','데이트 산책','데이트 실내','데이트 이색체험','데이트 소품샵','데이트 미술관','데이트 박물관','데이트 서점','데이트 방탈출','데이트 볼링','데이트 정원']
_lock=Lock();_executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='explore-index');_future=None
_collector=uuid.uuid4().hex

def queries():
    base=['서울 데이트 장소',*[f'서울 {term}' for term in TERMS],*[f'서울 {district} {term}' for district in DISTRICTS for term in TERMS]]
    focused=['감성 카페','분위기 좋은 레스토랑','독립서점','전시관','도자기 공방','방탈출','디저트 카페','정원 공원']
    return base+list(dict.fromkeys(f'서울 {district} {term}' for district in DISTRICTS for term in focused))

def normalize(value):return re.sub(r'[\W_]+','',str(value or '')).casefold()

def classify(category):
    if any(w in category for w in ('자동차','주차장','부동산','병원','의원','결혼','소개팅','결혼정보','여행사','호텔','숙박','유흥주점')):return None
    for words,label in [(['카페','디저트','베이커리'],'카페·미식'),(['음식점','한식','양식','일식','중식','분식','레스토랑'],'카페·미식'),(['미술','박물관','전시','갤러리','공연','문화재','유적'],'문화·예술'),(['공방','공예','체험'],'체험·제작'),(['공원','정원','산책','숲','관광','전망','식물원'],'산책·풍경'),(['서점','도서관','책방'],'휴식·힐링'),(['방탈출','보드','오락','게임','쇼핑','소품','편집','백화점','복합문화'],'오락·놀이'),(['스포츠','레저','볼링','클라이밍','수족관','동물원'],'레저·활동')]:
        if any(w in category for w in words):return label
    return None

def venue(item,query,rank):
    if not isinstance(item,dict):return None
    name=plain(item.get('title',''));address=plain(item.get('roadAddress') or item.get('address') or '')
    category=plain(item.get('category',''));kind=classify(category)
    if not name or not re.match(r'^서울(?:특별시)?\s',address) or not kind:return None
    try:
        lon,lat=float(item['mapx']),float(item['mapy'])
        if abs(lon)>180:lon/=10000000
        if abs(lat)>90:lat/=10000000
        if not (37.4<lat<37.75 and 126.7<lon<127.3):return None
    except (KeyError,ValueError,TypeError):return None
    pid='discovered:'+hashlib.sha256((name+address).encode()).hexdigest()[:20]
    return dict(id=pid,name=name,address=address,lat=lat,lon=lon,region='서울',demo=False,category=kind,themes=[kind],tags=[category],
        meal=any(w in category for w in ('음식점','한식','양식','일식','중식','분식','레스토랑')) and not any(w in category for w in ('카페','디저트')),
        description=category,source='https://map.naver.com/p/search/'+quote(place_query({'name':name,'address':address})),source_type='네이버 지역 검색 · 서울 장소 모음',
        checked_at=datetime.now(timezone.utc).isoformat(),discovery_verification='업체명·서울 주소·좌표 확인 · 현재 영업 여부 별도 확인',
        price=None,price_unit='person',hours=None,closed_days=None,breaks=None,last_entry=None,reservation=None,stay=None,stay_basis=None,rating=None,setting=None,
        photos=[],videos=[],license='검색 결과',search_score=1/(60+rank),found_in=[dict(query=query,rank=rank)])

def add_unique(bank,row):
    for existing in bank.values():
        if normalize(existing['name'])!=normalize(row['name']):continue
        same_address=normalize(existing['address'].replace('서울특별시','서울'))==normalize(row['address'].replace('서울특별시','서울'))
        if same_address or distance(existing,row)<.025:
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

def save(snapshot):
    snapshot=dict(snapshot,collector=_collector,collection_heartbeat=time.time())
    now=time.time()
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        current=db.execute('SELECT payload FROM cache WHERE key=? AND expires>?',(KEY,now)).fetchone()
        if current and json.loads(current['payload']).get('collector') not in (None,_collector):return
        db.execute('INSERT INTO cache VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,expires=excluded.expires',
                   (KEY,json.dumps(snapshot,ensure_ascii=False),now+86400))
        db.executemany('INSERT INTO cache VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,expires=excluded.expires',[("explore-place:"+p['id'],json.dumps(p,ensure_ascii=False),now+7*86400) for p in snapshot['places']])

def collect():
    bank={};duplicate=0;rejected=0;attempts=0;errors=0;permission=False;all_queries=queries()
    previous=store.cached(KEY) or {}
    try:
        with httpx.Client(timeout=8) as client,ThreadPoolExecutor(max_workers=3) as pool:
            for start in range(0,len(all_queries),12):
                for query,items,status in pool.map(lambda q:lookup(client,q),all_queries[start:start+12]):
                    attempts+=1
                    if status!='available':errors+=1
                    if status=='permission_required':permission=True
                    for rank,item in enumerate(items,1):
                        row=venue(item,query,rank)
                        if not row:rejected+=1;continue
                        if not add_unique(bank,row):duplicate+=1
                rows=sorted(bank.values(),key=lambda p:-p['search_score'])[:LIMIT]
                snapshot=dict(status='collecting',places=rows,target=LIMIT,queries_done=attempts,queries_max=len(all_queries),duplicates_removed=duplicate,rejected=rejected,failed_queries=errors,
                    checked_at=datetime.now(timezone.utc).isoformat(),ranking_method='지역·활동별 정확도순 결과 합산 · 네이버 전체 순위/별점 순위 아님')
                save(snapshot)
                if permission:break
        snapshot['unique_found']=len(bank)
        snapshot['status']='ready' if len(bank)>=LIMIT else 'partial' if bank else 'permission_required' if permission else 'unavailable'
        snapshot['message']='중복 제거한 서울 장소 최대 500곳이에요.' if len(bank)>=LIMIT else f'현재 조건으로 확인한 서울 장소 {len(bank)}곳을 표시해요. 확인되지 않은 장소로 수를 채우지 않아요.'
        if permission:snapshot['message']='네이버 지역 검색 권한을 확인해 주세요.'
        if not bank and previous.get('places'):snapshot.update(places=previous['places'],status='partial',message='조회에 실패해 이전 수집 결과를 유지했어요.')
        save(snapshot)
    except Exception as error:
        import logging
        logging.getLogger(__name__).exception('explore_collection_failed')
        save(dict(previous,status='collecting' if isinstance(error,RuntimeError) and 'shutdown' in str(error) else 'partial' if previous.get('places') else 'unavailable',places=previous.get('places',[]),message='장소 수집이 중단됐어요. 재연결 시 다시 수집합니다.'))

def ensure(refresh=False):
    global _future
    with _lock:
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT payload FROM cache WHERE key=? AND expires>?',(KEY,time.time())).fetchone()
            cached=json.loads(row['payload']) if row else None
            if _future and not _future.done():return cached or dict(status='collecting',places=[])
            if cached and cached.get('status')=='collecting' and cached.get('collection_heartbeat',0)>time.time()-120:return cached
            if not refresh and cached and cached.get('status')!='collecting':return cached
            if not search_enabled():return dict(status='key_missing',places=[],message='네이버 검색 키가 필요해요.')
            initial=dict(cached or {},status='collecting',places=(cached or {}).get('places',[]),target=LIMIT,queries_done=0,queries_max=len(queries()),message='서울 지역·활동별 검색 결과를 모으고 있어요.',collector=_collector,collection_heartbeat=time.time())
            db.execute('INSERT INTO cache VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,expires=excluded.expires',
                       (KEY,json.dumps(initial,ensure_ascii=False),time.time()+86400))
        _future=_executor.submit(collect)
        return initial

@router.get('/api/explore')
def explore(q:str=Query(default='',max_length=200),offset:int=Query(default=0,ge=0),limit:int=Query(default=24,ge=1,le=60)):
    snapshot=ensure();rows=snapshot.get('places',[])
    if q.strip() and normalize(q) not in ('서울데이트장소','서울데이트','서울'):
        terms=q.casefold().split();rows=[p for p in rows if all(term in (' '.join([p['name'],p['address'],p['category'],*p['tags']])).casefold() for term in terms)]
    return {k:v for k,v in snapshot.items() if k not in ('places','collector','collection_heartbeat')}|dict(places=rows[offset:offset+limit],total=len(rows),collected=len(snapshot.get('places',[])),offset=offset,has_more=offset+limit<len(rows),search='네이버 지역 검색 · 중복 제거')

@router.post('/api/explore/refresh')
def refresh():
    key='explore-refresh-rate'
    if store.cached(key):raise HTTPException(429,'전체 목록 갱신은 잠시 후 다시 시도해 주세요.')
    store.cache(key,True,600);state=ensure(refresh=True)
    return dict(status=state['status'])
