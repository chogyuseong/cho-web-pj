import json
import math
import hashlib
import os
from urllib.parse import urlencode
import httpx
from .telemetry import observed_http
from .config import ROOT
from .routes import distance

def restaurants():
    path=ROOT/'data/restaurants.json'
    from .operating_evidence import apply_evidence,evidence_rows
    evidence=evidence_rows()
    return [apply_evidence(p,evidence) for p in json.loads(path.read_text('utf-8'))] if path.exists() else []

def live_restaurant(place_id):
    from . import store
    from .operating_evidence import apply_evidence
    place=store.cached('restaurant:'+place_id)
    return apply_evidence(place) if place else None

def search_nearby(plan,index,*,district=None,query_suffix='맛집',radius_m=500):
    """권한 활성화 후 바로 쓸 수 있는 주변 업체 검색. 영업·가격 API는 아니다."""
    from . import store
    from .image_search import search_enabled,plain
    if plan.get('conditions',{}).get('mode')=='demo':return dict(status='demo',restaurants=[],message='가상 장소에서는 실제 식당을 검색하지 않습니다.')
    if index<0 or index>=len(plan['places']):raise ValueError('식사 추천 장소가 올바르지 않습니다.')
    a=plan['places'][index];b=plan['places'][min(index+1,len(plan['places'])-1)]
    query='서울 '+(district or a['name'])+' '+query_suffix
    search_url='https://map.naver.com/p/search/'+query
    if not search_enabled():return dict(status='key_missing',restaurants=[],message='네이버 검색 키를 설정해 주세요.',search_url=search_url)
    avoid=plan.get('conditions',{}).get('avoid',[])
    key='local-restaurants-radius-v3:'+hashlib.sha256(json.dumps([a,b,avoid,district,query_suffix,radius_m],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    cached=store.cached(key)
    if cached:return cached
    try:
        response=observed_http(httpx.get,'https://naverapihub.apigw.ntruss.com/search/v1/local',params=dict(query=query,display=5,sort='comment',format='json'),
            headers={'X-NCP-APIGW-API-KEY-ID':os.environ['NAVER_SEARCH_CLIENT_ID'],'X-NCP-APIGW-API-KEY':os.environ['NAVER_SEARCH_CLIENT_SECRET']},timeout=10)
        if response.status_code in (401,403):return dict(status='permission_required',restaurants=[],message='네이버 클라우드 NAVER API HUB의 기존 Application에서 NAVER 검색 > 지역 API를 활성화해 주세요. 이미지·블로그 키는 그대로 사용할 수 있습니다.',search_url=search_url)
        response.raise_for_status();items=response.json().get('items',[]);rows=[]
        from datetime import datetime,timezone
        for rank,item in enumerate(items,1):
            category=plain(item.get('category',''))
            if not any(word in category for word in ('음식점','한식','중식','일식','양식','분식')) or '카페' in category:continue
            address=plain(item.get('roadAddress') or item.get('address') or '')
            if not address.startswith('서울'):continue
            if district and district not in address.split():continue
            try:
                lon,lat=float(item['mapx']),float(item['mapy'])
                if abs(lon)>180:lon/=10000000
                if abs(lat)>90:lat/=10000000
                if not (37.4<lat<37.75 and 126.7<lon<127.3):continue
            except (KeyError,ValueError,TypeError):continue
            name=plain(item.get('title',''));r=dict(name=name,lat=lat,lon=lon)
            if any(word.casefold() in (name+' '+category).casefold() for word in avoid if word):continue
            offset=segment_distance(r,a,b);extra=max(0,distance(a,r)+distance(r,b)-distance(a,b))
            near=distance(a,r)
            if not district and near*1000>radius_m:continue
            id='food:naver-'+hashlib.sha256((name+address).encode()).hexdigest()[:16]
            r.update(id=id,address=address,cuisine=category,category='카페·미식',region='서울',demo=False,review_search_rank=rank,meal=True,setting=None,breaks=None,last_entry=None,
                recognition=f'네이버 카페·블로그 리뷰순 검색 {rank}번째 결과 · 별점 미제공',source=search_url,source_type='네이버 지역 검색',
                hours_text='운영시간·메뉴는 지도에서 확인',extra_distance_km=round(extra,1),route_offset_km=round(offset,1),
                distance_m=round(near*1000),search_radius_m=radius_m,
                checked_at=datetime.now(timezone.utc).isoformat(),description=category,tags=[category],photos=[],videos=[],license='검색 결과',
                price=None,hours=None,closed_days=None,stay=None,reservation=None,rating=None,stay_basis=None,price_unit=None)
            store.cache('restaurant:'+id,r,604800);rows.append(r)
            if len(rows)==(5 if district else 3):break
        result=dict(status='available' if rows else 'not_found',restaurants=rows,search_url=search_url,
            message='' if rows else ('해당 구의 음식점 검색 결과가 없습니다.' if district else f'이 장소 반경 {radius_m:,}m 안의 음식점 검색 결과가 없습니다.'))
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
    key='meal-rescue-500m-v2:'+hashlib.sha256(fingerprint.encode()).hexdigest()
    cached=store.cached(key)
    if cached:return cached
    indices=list(range(len(plan['places'])))
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
    from .quality import same_place,in_area
    from .models import Conditions
    conditions=Conditions.model_validate(plan['conditions'])
    groups=[];used=set()
    for i,a in enumerate(plan['places']):
        b=plan['places'][min(i+1,len(plan['places'])-1)]
        choices=[]
        for r in restaurants():
            if weekday in (r.get('closed_days') or []):continue
            if any(same_place(r,p) for p in plan['places']) or not in_area(r,conditions):continue
            if any(word.casefold() in (r['name']+' '+r['cuisine']).casefold() for word in plan['conditions'].get('avoid',[]) if word):continue
            offset=segment_distance(r,a,b)
            detour=max(0,distance(a,r)+distance(r,b)-distance(a,b))
            if distance(a,r)>0.5:continue
            choices.append((r['id'] in used,detour,offset,r))
        choices.sort(key=lambda x:x[:3])
        selected=[dict(r,extra_distance_km=round(detour,1),route_offset_km=round(offset,1),distance_m=round(distance(a,r)*1000)) for _,detour,offset,r in choices[:3]]
        used.update(r['id'] for r in selected)
        groups.append(dict(after_index=i,origin=a['name'],destination=b['name'],restaurants=selected,
            search_url='https://map.naver.com/p/search/'+a['name']+' 맛집',
            note='장소 중심 반경 500m 이내 · 직선거리 기준. 식사 후보는 현재 일정·방문 수·시간·예산에 미포함이며 대기·예약·메뉴 가격은 매장 확인이 필요해요.'))
    return groups


def restaurant_matches(plan):
    """Every stop, including the last, plus a separate district-wide review ranking."""
    from concurrent.futures import ThreadPoolExecutor
    from collections import Counter
    import re
    from .quality import same_place
    if plan['conditions']['mode']!='real':return dict(groups=[],popular=None)
    def district_of(address):
        match=re.search(r'(?:서울특별시|서울시|서울)\s+([가-힣]+구)(?:\s|$)',address or '')
        return match[1] if match else None
    districts=[district_of(p.get('address')) for p in plan['places']]
    districts=[d for d in districts if d]
    district=Counter(districts).most_common(1)[0][0] if districts else None
    curated=meal_suggestions(plan)
    jobs=list(range(len(plan['places'])))
    def nearby(i):
        choices=[];attempts=[];last={}
        for radius in (500,1000,1500):
            attempts.append(radius)
            # Keep closer matches first; never replace them with a wider search result.
            sources=[dict(food,search_radius_m=500) for food in curated[i]['restaurants']] if radius==500 else []
            for suffix in ('맛집','음식점'):
                last=search_nearby(plan,i,query_suffix=suffix,radius_m=radius)
                sources=last['restaurants']+sources
                for food in sources:
                    if distance(plan['places'][i],food)*1000>radius:continue
                    if any(same_place(food,p) for p in plan['places']+choices):continue
                    choices.append(dict(food,after_index=i,near_place=plan['places'][i]['name'],
                        search_radius_m=radius,distance_m=round(distance(plan['places'][i],food)*1000)))
                    if len(choices)>=3:break
                sources=[]
                if len(choices)>=3 or last['status'] not in ('available','not_found'):break
            if len(choices)>=3 or last.get('status') not in ('available','not_found'):break
        return dict(last,restaurants=choices[:3],status='available' if choices else last.get('status','not_found'),
            searched_radii_m=attempts,effective_radius_m=attempts[-1],
            note='500m부터 찾고, 3곳 미만이면 1,000m → 1,500m 순서로 보충해요. 표시는 코스 장소에서의 직선거리이며 일정에는 미포함입니다.')
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(nearby,jobs))
    groups=[]
    for i,(base,live) in enumerate(zip(curated,results)):
        groups.append(dict(base,**{key:value for key,value in live.items() if key!='search_url'}))
    popular=None
    if district:
        result=search_nearby(plan,0,district=district)
        rows=[]
        candidates=list(result['restaurants'])
        # 기본 검색의 카페·다른 구 결과를 제외한 뒤 부족하면 음식점 검색으로 보충한다.
        if len(candidates)<5 and result['status'] in ('available','not_found'):
            for suffix in ('음식점','한식 맛집'):
                extra=search_nearby(plan,0,district=district,query_suffix=suffix)
                for food in extra['restaurants']:
                    if not any(same_place(food,p) for p in candidates):candidates.append(food)
                if len(candidates)>=5:break
        for food in candidates:
            if any(same_place(food,p) for p in rows):continue
            nearest=min(jobs,key=lambda i:distance(food,plan['places'][i]))
            rows.append(dict(food,after_index=nearest,near_place=plan['places'][nearest]['name']))
        popular=dict(result,restaurants=rows[:5],district=district,status='available' if rows else result['status'],message='' if rows else result.get('message',''),
            ranking_basis='네이버 지역 검색의 카페·블로그 리뷰순 후보 5곳입니다. 맛집 검색에서 부족하면 음식점·한식 검색으로 보충합니다. 별점·절대 인기 순위가 아니며, 500m 제한과 별도로 해당 구 전체에서 찾습니다.')
    return dict(groups=groups,popular=popular,radius_m=500)
