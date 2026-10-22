import json
import math
import hashlib
import os
from urllib.parse import urlencode
import httpx
from .config import ROOT
from .routes import distance

def restaurants():
    path=ROOT/'data/restaurants.json'
    return json.loads(path.read_text('utf-8')) if path.exists() else []

def live_restaurant(place_id):
    from . import store
    return store.cached('restaurant:'+place_id)

def search_nearby(plan,index):
    """권한 활성화 후 바로 쓸 수 있는 주변 업체 검색. 영업·가격 API는 아니다."""
    from . import store
    from .image_search import search_enabled,plain
    if plan.get('conditions',{}).get('mode')=='demo':return dict(status='demo',restaurants=[],message='가상 장소에서는 실제 식당을 검색하지 않습니다.')
    if index<0 or index>=len(plan['places'])-1:raise ValueError('식사 추천 구간이 올바르지 않습니다.')
    a,b=plan['places'][index:index+2]
    query='서울 '+a['name']+' 맛집'
    search_url='https://map.naver.com/p/search/'+query
    if not search_enabled():return dict(status='key_missing',restaurants=[],message='네이버 검색 키를 설정해 주세요.',search_url=search_url)
    avoid=plan.get('conditions',{}).get('avoid',[])
    key='local-restaurants-v2:'+a['id']+':'+b['id']+':'+hashlib.sha256(json.dumps(avoid,ensure_ascii=False).encode()).hexdigest()[:12]
    cached=store.cached(key)
    if cached:return cached
    try:
        response=httpx.get('https://naverapihub.apigw.ntruss.com/search/v1/local',params=dict(query=query,display=5,sort='comment',format='json'),
            headers={'X-NCP-APIGW-API-KEY-ID':os.environ['NAVER_SEARCH_CLIENT_ID'],'X-NCP-APIGW-API-KEY':os.environ['NAVER_SEARCH_CLIENT_SECRET']},timeout=10)
        if response.status_code in (401,403):return dict(status='permission_required',restaurants=[],message='네이버 클라우드 NAVER API HUB의 기존 Application에서 NAVER 검색 > 지역 API를 활성화해 주세요. 이미지·블로그 키는 그대로 사용할 수 있습니다.',search_url=search_url)
        response.raise_for_status();items=response.json().get('items',[]);rows=[]
        from datetime import datetime,timezone
        for rank,item in enumerate(items,1):
            category=plain(item.get('category',''))
            if not any(word in category for word in ('음식점','한식','중식','일식','양식','분식')) or '카페' in category:continue
            address=plain(item.get('roadAddress') or item.get('address') or '')
            if not address.startswith('서울'):continue
            try:
                lon,lat=float(item['mapx']),float(item['mapy'])
                if abs(lon)>180:lon/=10000000
                if abs(lat)>90:lat/=10000000
                if not (37.4<lat<37.75 and 126.7<lon<127.3):continue
            except (KeyError,ValueError,TypeError):continue
            name=plain(item.get('title',''));r=dict(name=name,lat=lat,lon=lon)
            if any(word.casefold() in (name+' '+category).casefold() for word in avoid if word):continue
            offset=segment_distance(r,a,b);extra=max(0,distance(a,r)+distance(r,b)-distance(a,b))
            if offset>3 or extra>5:continue
            id='food:naver-'+hashlib.sha256((name+address).encode()).hexdigest()[:16]
            r.update(id=id,address=address,cuisine=category,category='카페·미식',region='서울',demo=False,review_search_rank=rank,meal=True,setting=None,breaks=None,last_entry=None,
                recognition=f'네이버 카페·블로그 리뷰순 검색 {rank}번째 결과 · 별점 미제공',source=search_url,source_type='네이버 지역 검색',
                hours_text='운영시간·메뉴는 지도에서 확인',extra_distance_km=round(extra,1),route_offset_km=round(offset,1),
                checked_at=datetime.now(timezone.utc).isoformat(),description=category,tags=[category],photos=[],videos=[],license='검색 결과',
                price=None,hours=None,closed_days=None,stay=None,reservation=None,rating=None,stay_basis=None,price_unit=None)
            store.cache('restaurant:'+id,r,604800);rows.append(r)
            if len(rows)==3:break
        result=dict(status='available' if rows else 'not_found',restaurants=rows,search_url=search_url,
            message='' if rows else '이 구간 가까이에 해당하는 음식점 검색 결과가 없습니다. 지도에서 더 찾아보세요.')
        store.cache(key,result,3600);return result
    except (httpx.HTTPError,ValueError,TypeError):return dict(status='unavailable',restaurants=[],message='지역 검색에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.',search_url=search_url)


def meal_rescue(plan):
    """식사 시간대 구성이 불가능한 코스에 주변 리뷰순 음식점 후보를 제시한다."""
    from concurrent.futures import ThreadPoolExecutor
    from . import store
    from .models import Conditions
    from .quality import in_area
    if not any(d['condition']=='meal' and d['state']=='unmet' for d in plan.get('deviations',[])):
        return dict(status='not_needed',restaurants=[])
    c=Conditions.model_validate(plan['conditions'])
    fingerprint=json.dumps([c.model_dump(mode='json'),[p['id'] for p in plan['places']]],sort_keys=True,ensure_ascii=False)
    key='meal-rescue-v1:'+hashlib.sha256(fingerprint.encode()).hexdigest()
    cached=store.cached(key)
    if cached:return cached
    indices=list(range(min(3,len(plan['places'])-1)))
    with ThreadPoolExecutor(max_workers=3) as pool:groups=list(pool.map(lambda i:search_nearby(plan,i),indices))
    rows={};existing={p['id'] for p in plan['places']}
    for index,group in zip(indices,groups):
        for food in group['restaurants']:
            if food['id'] in existing or not in_area(food,c):continue
            if any(''.join(food['name'].split()).casefold()==''.join(p['name'].split()).casefold() for p in plan['places']):continue
            if c.visit_date.weekday() in (food.get('closed_days') or []):continue
            candidate=dict(food,after_index=index,near_place=plan['places'][index]['name'])
            score=(candidate.get('review_search_rank',99),candidate['extra_distance_km'],candidate['route_offset_km'])
            old=rows.get(food['id'])
            if not old or score<(old.get('review_search_rank',99),old['extra_distance_km'],old['route_offset_km']):rows[food['id']]=candidate
    ranked=sorted(rows.values(),key=lambda p:(p.get('review_search_rank',99),p['extra_distance_km'],p['route_offset_km']))[:3]
    result=dict(status='available' if ranked else 'not_found',restaurants=ranked,
        ranking_basis='네이버 지역 검색의 카페·블로그 리뷰순 결과를 우선하고, 순위가 같으면 추가 이동이 적은 곳부터 표시해요. 별점은 제공되지 않아요.',
        note='별도 식사 후보이며 현재 일정·방문 수·시간·예산에는 아직 포함되지 않아요. 영업시간·대기·예약·메뉴 가격을 확인해 주세요.',
        message='' if ranked else next((g.get('message') for g in groups if g.get('status') in ('permission_required','unavailable','key_missing')),'설정한 동네 범위 안의 주변 식당을 찾지 못했어요. 이동 범위를 넓히거나 지도에서 확인해 주세요.'))
    store.cache(key,result,600 if ranked else 30)
    return result

def segment_distance(p,a,b):
    scale=math.cos(math.radians((a['lat']+b['lat'])/2))
    ax,ay=a['lon']*scale,a['lat'];bx,by=b['lon']*scale,b['lat'];px,py=p['lon']*scale,p['lat']
    denominator=(bx-ax)**2+(by-ay)**2
    t=max(0,min(1,((px-ax)*(bx-ax)+(py-ay)*(by-ay))/denominator)) if denominator else 0
    return math.hypot(px-(ax+t*(bx-ax)),py-(ay+t*(by-ay)))*111.2

def meal_suggestions(plan):
    if plan['conditions']['mode']!='real':return []
    from datetime import date
    weekday=date.fromisoformat(plan['conditions']['visit_date']).weekday()
    groups=[];used=set()
    for i,(a,b) in enumerate(zip(plan['places'],plan['places'][1:])):
        choices=[]
        for r in restaurants():
            if weekday in (r.get('closed_days') or []):continue
            if r['id'] in {p['id'] for p in plan['places']}:continue
            if any(word.casefold() in (r['name']+' '+r['cuisine']).casefold() for word in plan['conditions'].get('avoid',[]) if word):continue
            offset=segment_distance(r,a,b)
            detour=max(0,distance(a,r)+distance(r,b)-distance(a,b))
            if offset>3 or detour>5:continue
            choices.append((r['id'] in used,detour,offset,r))
        choices.sort(key=lambda x:x[:3])
        selected=[dict(r,extra_distance_km=round(detour,1),route_offset_km=round(offset,1)) for _,detour,offset,r in choices[:3]]
        used.update(r['id'] for r in selected)
        groups.append(dict(after_index=i,origin=a['name'],destination=b['name'],restaurants=selected,
            search_url='https://map.naver.com/p/search/'+a['name']+' 맛집',
            note='식사 후보 · 현재 일정·방문 수·시간·예산에는 미포함. 거리 차이는 직선 기준이며 대기·예약·메뉴 가격은 매장 확인이 필요해요.'))
    return groups
