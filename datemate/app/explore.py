"""장소 둘러보기: 공공 자료로 만든 기본 목록과, 그 아래 따로 두는 '네이버에서 더 찾기' 블록.

2026-11-20 2단계(docs/naver-terms-stage2-design.ko.md 3.5(b)): 예전에는 네이버 지역 검색 여러 건의 결과를 합쳐 중복을 지우고 점수로 다시 줄 세웠다.
검색 결과를 합치거나 재정렬하지 않기로 해(검색 API 특약 2.2) 둘로 나눴다.
  1) 기본 목록(GET /api/explore): 한국관광공사 TourAPI 의 시·도 목록(법정동 시·도 코드와 새 분류로 좁힘. 검색어가 있으면 이름 검색)과, 동네를 알 수 있을 때 그 주변의
     소상공인 상가정보(app/public_places.py). 공공 자료라 우리 기준으로 정렬한다: 사진이 있는 관광공사 항목 → 나머지 관광공사 항목 →
     상가정보 업소(지점 표기가 없는 곳 먼저, 가까운 순). 인기·별점 순위가 아니다.
  2) 네이버에서 더 찾기(GET /api/explore/naver): 검색어 하나당 네이버 지역 검색 결과를 받은 순서 그대로 한 블록씩. 합치기·중복 제거·점수·
     업종 분류를 하지 않고, 우리 목록·후보·장소 상세에 넣지 않는다. 사용자가 펼쳤을 때만 부른다.

동네 중심(center_for): 상가정보는 반경 조회뿐이라 중심 좌표가 필요하다. 검색어에 우리가 정해 둔 동네·거점 이름이 있으면 그 좌표,
없으면 관광공사 이름 검색 결과 중 이름에 검색어가 든 항목들의 가운데 좌표를 쓴다. 중심을 모르면(검색어 없음 등) 관광공사 목록만 보여 준다.
"""
import hashlib
import json
import re
from datetime import datetime,timezone
from urllib.parse import quote
import httpx
from fastapi import APIRouter,HTTPException,Query
from . import naver_cache,public_places,store
from .image_search import search_enabled
from .naver_local import lookup,original_items
from .regions import REGIONS,normalize_region
from .routes import distance
from .web_security import require_ip

router=APIRouter()
ACTIVITIES=['카페','맛집','전시','공방','산책','실내','이색체험','소품샵','미술관','박물관','서점','방탈출','볼링','정원']
RESULT_TTL=6*3600
MAX_NAVER_QUERIES=4
# 둘러보기에서 상가정보 업소를 종류마다 고르는 수(추천 후보보다 넉넉히).
STORE_CAPS={kind:12 for kind in public_places.STORE_CAPS}
RANKING='공공 자료(한국관광공사 관광정보·소상공인 상가정보)를 사진이 있는 곳 먼저 정리했어요. 인기·별점 순위가 아니에요.'
DATA_NOTE='공공 자료에는 사진·영업시간·후기가 없는 곳이 많아요. 장소를 열면 네이버 지도에서 확인하는 링크가 있어요.'
CENTER_HINT='동네 이름(예: 성수, 해운대)으로 검색하면 그 주변 가게(소상공인 상가정보)도 함께 보여 드려요.'

# 활동 → (관광공사 목록 조건들 (관광 타입 또는 None, 새 분류 lclsSystm 앞부분 또는 None), 상가정보 묶음들, 장소 판별).
def _tag(*tags):return lambda p:any(t in p['tags'] for t in tags)
def _label(pattern):return lambda p:bool(re.search(pattern,p['description']+' '+p['name']))
SPECS={
    '':((('12',None),('14',None)),('food',),lambda p:True),
    '카페':(((None,'FD05'),),('food',),_tag('cafe')),
    '맛집':((('39',None),),('food',),lambda p:bool(p['meal'])),
    '전시':(((None,'VE070300'),(None,'VE070600')),(),_tag('culture')),
    '미술관':(((None,'VE070600'),),(),_label('미술관')),
    '박물관':(((None,'VE070100'),),(),_label('박물관')),
    '공방':(((None,'EX02'),(None,'SH050100')),('craft',),_tag('workshop')),
    '산책':(((None,'VE03'),(None,'NA04')),(),lambda p:p['category']=='산책·풍경'),
    '정원':(((None,'NA040700'),(None,'VE03')),(),_label('수목원|공원|정원|식물원')),
    '실내':((('14',None),),('food',),lambda p:p.get('setting')=='indoor'),
    '이색체험':(((None,'EX07'),(None,'EX01')),('play','comic'),_tag('game','workshop','boating')),
    '소품샵':(((None,'SH050300'),(None,'SH050100')),('gift',),_tag('shopping','workshop')),
    '서점':(((None,'VE120100'),(None,'VE090300')),('book',),_tag('book')),
    '방탈출':((),('play',),lambda p:_tag('game')(p) and _label('방탈출|이스케이프|escape|Escape')(p)),
    '볼링':((),('play',),_tag('bowling')),
}
# 홈 화면의 동네 카드(static/index.html)와 같은 좌표. 서울 동네는 quality.AREAS, 팝업 거점은 popup_hubs.HUBS 를 함께 본다.
PRESET_AREAS={'부산':{'해운대':(35.1631,129.1636)},'제주':{'애월':(33.4621,126.3104)},'경북':{'황리단길':(35.8375,129.2095)},
    '전북':{'한옥마을':(35.8150,127.1530)},'강원':{'안목':(37.7716,128.9477)}}


def squeeze(text):return re.sub(r'\s+','',str(text or '')).casefold()


def center_for(region,q,keyword_rows=()):
    """검색어가 가리키는 동네의 중심 dict(name, lat, lon, basis) 또는 None. 네이버 검색 결과는 쓰지 않는다."""
    text=squeeze(q)
    if len(text)<2:return None
    from .popup_hubs import HUBS
    from .quality import AREAS
    known=dict(PRESET_AREAS.get(region,{}))
    if region=='서울':known.update({name.rstrip('동'):point for name,point in AREAS.items()})
    for hub in HUBS:
        if hub['region']==region and hub['lat'] is not None:
            known.setdefault(hub['name'],(hub['lat'],hub['lon']))
    for name,(lat,lon) in sorted(known.items(),key=lambda pair:-len(pair[0])):
        if squeeze(name) in text:return dict(name=name,lat=lat,lon=lon,basis='dictionary')
    hits=[row for row in keyword_rows if text in squeeze(row.get('title'))][:7]
    if not hits:return None
    lats=sorted(row['lat'] for row in hits);lons=sorted(row['lon'] for row in hits)
    return dict(name=' '.join(q.split()),lat=lats[len(lats)//2],lon=lons[len(lons)//2],basis='tour_keyword')


def public_list(region,activity='',q=''):
    """공공 자료 기본 목록. dict(status, places, sources, center, …)."""
    sources,tour_rows,center=[],[],None
    tour_specs,sheets,keep=SPECS[activity]
    if q:
        found=public_places.tour_keyword(region,q)
        sources.append(dict(source='tour_keyword',status=found.get('status'),rows=len(found.get('rows') or [])))
        tour_rows=list(found.get('rows') or [])
        center=center_for(region,q,tour_rows)
    else:
        for content_type,lcls in tour_specs:
            found=public_places.tour_area(region,content_type,lcls)
            sources.append(dict(source=f'tour_area:{content_type or "all"}:{lcls or "all"}',status=found.get('status'),rows=len(found.get('rows') or [])))
            tour_rows+=found.get('rows') or []
    places,seen=[],set()
    for row in tour_rows:
        place=public_places.tour_place(row,region)
        if not place or place['id'] in seen or not keep(place):continue
        seen.add(place['id']);places.append(place)
    # 사진 있는 곳 먼저. 동네 중심을 알면 가까운 순, 모르면 받은 순서(수정일 최신순)를 지킨다.
    order={p['id']:i for i,p in enumerate(places)}
    places.sort(key=lambda p:(not p.get('tour_photo'),distance(center,p) if center else order[p['id']]))
    if center:
        pairs=[]
        for sheet in sheets:
            data,radius_m=public_places.stores_near(sheet,center['lat'],center['lon'])
            sources.append(dict(source='store:'+sheet,status=data.get('status'),rows=len(data.get('rows') or []),radius_m=radius_m))
            for row in data.get('rows') or []:
                pair=public_places.store_place(row,region,data.get('data_month'))
                if pair and keep(pair[1]):pairs.append(pair)
        places+=[place for _,place in public_places.pick_stores(pairs,center,STORE_CAPS,taken=places)]
    statuses=[s['status'] for s in sources]
    if places:status,message='ready',None if all(s=='available' for s in statuses) else '일부 자료를 받지 못해 받은 곳만 보여 드려요.'
    elif 'key_missing' in statuses:status,message='key_missing','공공데이터포털 키가 필요해요.'
    elif statuses and all(s in ('unavailable','limited') for s in statuses):status,message='unavailable','공공 자료를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.'
    else:status,message='empty','공공 자료에서 조건에 맞는 장소를 찾지 못했어요. 다른 활동이나 동네 이름으로 찾아보세요.'
    return dict(status=status,places=places,message=message,sources=sources,center=center,
                center_hint=None if center or activity in ('미술관','박물관','전시','산책','정원') else CENTER_HINT,
                checked_at=datetime.now(timezone.utc).isoformat())


def results(region,activity='',q=''):
    q=' '.join(q.split())
    key='explore-public-v1:'+hashlib.sha256(json.dumps([region,activity,q.casefold()],ensure_ascii=False).encode()).hexdigest()
    # 공공 자료로 만든 목록이라 사용자 사이에 나눠 쓴다(네이버 결과가 들어 있지 않다).
    cached=store.cached(key)
    if cached is not None:return cached
    if not public_places.enabled():return dict(status='key_missing',places=[],message='공공데이터포털 키가 필요해요.',sources=[])
    # 새 조건은 공공 API 를 몇 건 부른다. IP 범위마다 분당 횟수를 묶는다.
    require_ip('explore-search','DATEMATE_IP_EXPLORE_SEARCHES_PER_MINUTE',10,'새 조건 검색이 많아요. 잠시 후 다시 시도해 주세요.')
    result=public_list(region,activity,q)
    # 장소 상세(/api/places/{id})가 읽을 수 있게 장소마다 따로 둔다(공공 자료, 사용자 공용).
    store.cache_many([('public-place:'+p['id'],p,RESULT_TTL+3600) for p in result['places']])
    if result['status'] in ('ready','empty'):store.cache(key,result,RESULT_TTL if result['status']=='ready' and not result['message'] else 600)
    return result


def naver_queries(region,activity='',q=''):
    """'네이버에서 더 찾기'의 검색어(최대 MAX_NAVER_QUERIES 개). 검색어 하나가 블록 하나다."""
    q=' '.join(str(q or '').split())
    if activity and q:rows=[f'{region} {q} {activity}',f'{region} {q} 데이트 {activity}']
    elif activity:rows=[f'{region} 데이트 {activity}',f'{region} {activity} 추천']
    elif q:rows=[f'{region} {q}',f'{region} {q} 데이트',f'{region} {q} 카페',f'{region} {q} 맛집']
    else:rows=[f'{region} 데이트 장소',f'{region} 데이트 카페',f'{region} 데이트 맛집',f'{region} 데이트 전시']
    return list(dict.fromkeys(rows))[:MAX_NAVER_QUERIES]


def naver_blocks(region,activity='',q=''):
    """검색어마다 네이버 지역 검색 결과를 받은 그대로 한 블록씩. 합치지 않고, 거르지 않고, 다시 줄 세우지 않는다."""
    from concurrent.futures import ThreadPoolExecutor
    from .request_usage import context_map
    planned=naver_queries(region,activity,q)
    if not search_enabled():return dict(status='key_missing',blocks=[],message='네이버 검색 키가 필요해요.')
    fingerprint=json.dumps([region,activity,' '.join(q.split()).casefold()],ensure_ascii=False)
    key='explore-naver-v1:'+hashlib.sha256(fingerprint.encode()).hexdigest()
    cached=naver_cache.cached(key)
    if cached is not None:return cached
    require_ip('explore-search','DATEMATE_IP_EXPLORE_SEARCHES_PER_MINUTE',10,'새 조건 검색이 많아요. 잠시 후 다시 시도해 주세요.')
    # 같은 사용자의 새 둘러보기 검색: 이전 검색 보관분을 지운다(특약 2.4 '새 질의 시까지', app/naver_cache.py).
    naver_cache.new_query('explore',fingerprint=fingerprint)
    with httpx.Client(timeout=8) as client,ThreadPoolExecutor(max_workers=4) as pool:
        found=context_map(pool,lambda query:lookup(client,query),planned)
    blocks=[dict(query=query,status=status,items=original_items(items),
                 search_url='https://map.naver.com/p/search/'+quote(query)) for query,items,status in found]
    statuses=[b['status'] for b in blocks]
    if any(b['items'] for b in blocks):status,message='ready',None
    elif 'permission_required' in statuses:status,message='permission_required','네이버 지역 검색 권한을 확인해 주세요.'
    elif all(s!='available' for s in statuses):status,message='unavailable','네이버 검색에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.'
    else:status,message='empty','네이버 지역 검색 결과가 없어요.'
    result=dict(status=status,blocks=blocks,message=message,queries_used=len(planned))
    if status in ('ready','empty'):naver_cache.cache(key,result,3600)
    return result


def conditions(region,activity):
    canonical=normalize_region(region)
    if canonical not in REGIONS:raise HTTPException(422,'지원하지 않는 시·도예요.')
    activity=activity.strip()
    if activity=='전체':activity=''
    if activity and activity not in ACTIVITIES:raise HTTPException(422,'지원하지 않는 활동이에요.')
    return canonical,activity


@router.get('/api/explore')
def explore(region:str=Query(default='서울',max_length=20),activity:str=Query(default='',max_length=20),q:str=Query(default='',max_length=60),
            offset:int=Query(default=0,ge=0),limit:int=Query(default=24,ge=1,le=60)):
    canonical,activity=conditions(region,activity)
    data=results(canonical,activity,q);rows=data.get('places',[])
    return {k:v for k,v in data.items() if k!='places'}|dict(places=rows[offset:offset+limit],total=len(rows),offset=offset,has_more=offset+limit<len(rows),
        region=canonical,activity=activity or '전체',ranking_method=RANKING,data_note=DATA_NOTE,
        search='한국관광공사 관광정보 · 소상공인 상가정보',naver_more=search_enabled())


@router.get('/api/explore/naver')
def explore_naver(region:str=Query(default='서울',max_length=20),activity:str=Query(default='',max_length=20),q:str=Query(default='',max_length=60)):
    canonical,activity=conditions(region,activity)
    return naver_blocks(canonical,activity,q)|dict(region=canonical,activity=activity or '전체')
