"""코스 장소 주변의 식당 후보.

우리 식당 자료(data/restaurants.json)와 공공 자료(한국관광공사 관광정보의 음식점, 소상공인 상가정보의 음식 업종 — app/public_places.py)에서만 찾는다.
2026-11-20 2단계: 예전에는 네이버 지역 검색의 '맛집'·'음식점' 결과를 리뷰순으로 받아 거르고 줄 세워 보여 줬다. 검색 결과를 우리 목록의
입력으로 쓰지 않기로 해 뺐다(검색 API 특약 1.1·1.2, docs/naver-terms-stage2-design.ko.md 3.8(b)). 그래서 '리뷰가 많은 순'과 구 단위
'유명 맛집' 목록은 없다(대신할 공공 자료가 없음). 화면은 네이버 지도 검색 링크를 따로 둔다.
"""
import json
import math
from .config import ROOT
from .routes import distance

# 장소에서 이 거리 안의 식당을 가까운 구간부터 보여 준다(500m → 1,000m → 1,500m).
RADII_M=(500,1000,1500)
PER_STOP=3
TOUR_RECOGNITION='한국관광공사 관광정보에 실린 음식점'
STORE_RECOGNITION='소상공인 상가정보에 등록된 음식점'
RANKING_BASIS='한국관광공사 관광정보에 실린 음식점을 먼저, 그다음 소상공인 상가정보의 음식점을 가까운 순으로 보여 드려요. 후기·별점 순위가 아니에요.'
DATA_NOTE='공공 자료에는 사진·영업시간·메뉴 가격·후기가 없는 곳이 많아요. 네이버 지도에서 확인해 주세요.'


def restaurants():
    path=ROOT/'data/restaurants.json'
    from .operating_evidence import apply_evidence,evidence_rows
    evidence=evidence_rows()
    return [apply_evidence(p,evidence) for p in json.loads(path.read_text('utf-8'))] if path.exists() else []


def search_url(name):
    return 'https://map.naver.com/p/search/'+name+' 맛집'


def public_food(plan,indices):
    """코스 장소(indices)마다 주변의 공공 자료 음식점. (상태, {장소 번호: [식당, …]}).

    식당은 가까운 구간(500m·1,000m·1,500m) 먼저, 같은 구간에서는 관광공사 항목 → 지점 표기 없는 상가정보 업소 → 가까운 순.
    코스에 이미 있는 곳, 피할 낱말이 든 곳, 다른 시·도, 동네 범위 밖은 뺀다. 찾은 식당은 이 사용자의 보관분(24시간)에 둔다."""
    from concurrent.futures import ThreadPoolExecutor
    from . import public_places
    from .intent_discovery import MAX_FETCH_KM,reach_km
    from .models import Conditions
    from .quality import in_area,same_place
    from .regions import region_from_address
    from .request_usage import context_map
    if not public_places.enabled():return 'key_missing',{}
    c=Conditions.model_validate(plan['conditions'])
    places=plan['places']
    region=c.region or region_from_address(places[0].get('address')) or '서울'
    avoid=[w.casefold() for w in c.avoid if w]
    center=(c.area_center or c.origin).model_dump()
    # 추천이 후보를 찾을 때와 같은 중심·반경이라 관광공사 목록은 대개 캐시에서 나온다(app/intent_discovery.py).
    tour=public_places.tour_near(center['lat'],center['lon'],min(MAX_FETCH_KM,c.neighborhood_radius_km if c.area_center else reach_km(c)))
    tour_food=[p for p in (public_places.tour_place(row,region) for row in tour.get('rows') or []) if p and p['meal']]
    with ThreadPoolExecutor(max_workers=3) as pool:
        sheets=context_map(pool,lambda i:public_places.stores_near('food',places[i]['lat'],places[i]['lon'])[0],indices)
    statuses=[tour.get('status'),*(s.get('status') for s in sheets)]
    groups={};shown=[]
    for i,sheet in zip(indices,sheets):
        a=places[i];b=places[min(i+1,len(places)-1)]
        store_food=[pair[1] for pair in (public_places.store_place(row,region,sheet.get('data_month')) for row in sheet.get('rows') or []) if pair and pair[0]=='meal']
        rows=[]
        for food in tour_food+store_food:
            meters=distance(a,food)*1000
            if meters>RADII_M[-1] or not in_area(food,c):continue
            if any(w in (food['name']+' '+food['description']).casefold() for w in avoid):continue
            if any(same_place(food,p) or public_places.same_venue(food,p) for p in places):continue
            radius=next(r for r in RADII_M if meters<=r)
            rows.append((radius,food['public_source']!='tour',bool(food.get('branch')),meters,food['id'],food))
        chosen=[]
        for radius,_,_,meters,_,food in sorted(rows,key=lambda r:r[:5]):
            if any(public_places.same_venue(food,other) for other in chosen):continue
            tour_row=food['public_source']=='tour'
            chosen.append(dict(food,cuisine=food['description'].split('>')[-1],recognition=TOUR_RECOGNITION if tour_row else STORE_RECOGNITION,
                # hours_text: 메뉴는 카드의 메뉴 칸이 안내하므로 영업시간만(2026-11-26, 예전 '영업시간·메뉴는 지도에서 확인'은 같은 말 두 번).
                hours_text='영업시간은 지도에서 확인',search_radius_m=radius,distance_m=round(meters),after_index=i,near_place=a['name'],
                extra_distance_km=round(max(0,distance(a,food)+distance(food,b)-distance(a,b)),1),route_offset_km=round(segment_distance(food,a,b),1)))
            if len(chosen)==PER_STOP:break
        groups[i]=chosen;shown+=chosen
    public_places.remember(shown,prefix=public_places.NEARBY_PREFIX)
    status='available' if shown else ('not_found' if 'available' in statuses else 'unavailable')
    return status,groups


def search_nearby(plan,index):
    """코스 장소 한 곳 주변의 공공 자료 음식점(GET /api/plans/{id}/restaurants)."""
    if plan.get('conditions',{}).get('mode')=='demo':return dict(status='demo',restaurants=[],message='가상 장소에서는 실제 식당을 검색하지 않습니다.')
    if index<0 or index>=len(plan['places']):raise ValueError('식사 추천 장소가 올바르지 않습니다.')
    status,groups=public_food(plan,[index])
    rows=groups.get(index,[])
    return dict(status='available' if rows else status,restaurants=rows,search_url=search_url(plan['places'][index]['name']),
        ranking_basis=RANKING_BASIS,message='' if rows else MESSAGES.get(status,MESSAGES['not_found']))


MESSAGES={
    'key_missing':'주변 식당을 찾으려면 공공데이터포털 키 설정이 필요해요. 네이버 지도에서 찾아 주세요.',
    'unavailable':'공공 자료 조회에 연결하지 못했어요. 잠시 후 다시 시도하거나 네이버 지도에서 찾아 주세요.',
    'not_found':'이 장소 1,500m 안에서 공공 자료에 실린 음식점을 찾지 못했어요. 네이버 지도에서 찾아 주세요.',
}


def meal_rescue(plan):
    """식사 시간대 구성이 불가능한 코스에 주변 음식점 후보(공공 자료)를 제시한다."""
    import hashlib
    from . import naver_cache as store
    from .models import Conditions
    if not any(d['condition']=='meal' and d['state']=='unmet' for d in plan.get('deviations',[])):
        return dict(status='not_needed',restaurants=[])
    c=Conditions.model_validate(plan['conditions'])
    fingerprint=json.dumps([c.model_dump(mode='json'),[p['id'] for p in plan['places']]],sort_keys=True,ensure_ascii=False)
    key='public-nearby:rescue-v1:'+hashlib.sha256(fingerprint.encode()).hexdigest()
    cached=store.cached(key)
    if cached:return cached
    status,groups=public_food(plan,list(range(len(plan['places']))))
    rows={}
    for foods in groups.values():
        for food in foods:
            if c.visit_date.weekday() in (food.get('closed_days') or []):continue
            score=(food['public_source']!='tour',food['extra_distance_km'],food['route_offset_km'],food['distance_m'])
            old=rows.get(food['id'])
            if not old or score<old[0]:rows[food['id']]=(score,food)
    ranked=[food for _,food in sorted(rows.values(),key=lambda pair:pair[0])][:3]
    result=dict(status='available' if ranked else 'not_found',restaurants=ranked,ranking_basis=RANKING_BASIS,
        note='별도 식사 후보이며 현재 일정·방문 수·시간·예산에는 아직 포함되지 않아요. '+DATA_NOTE,
        message='' if ranked else MESSAGES.get(status,'설정한 동네 범위 안의 주변 식당을 찾지 못했어요. 이동 범위를 넓히거나 지도에서 확인해 주세요.'))
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
            search_url=search_url(a['name']),
            note='장소 중심 반경 500m 이내 · 직선거리 기준. 식사 후보는 현재 일정·방문 수·시간·예산에 미포함이며 대기·예약·메뉴 가격은 매장 확인이 필요해요.'))
    return groups


def restaurant_matches(plan):
    """코스 장소마다 주변 식당 3곳까지: 우리 식당 자료(500m 안)를 먼저, 모자라면 공공 자료를 500m → 1,000m → 1,500m 순으로."""
    from .quality import same_place
    from . import public_places
    if plan['conditions']['mode']!='real':return dict(groups=[],radius_m=500)
    curated=meal_suggestions(plan)
    jobs=list(range(len(plan['places'])))
    status,found=public_food(plan,jobs)
    groups=[]
    for i,base in enumerate(curated):
        choices=[dict(food,after_index=i,near_place=plan['places'][i]['name'],search_radius_m=500) for food in base['restaurants']]
        for food in found.get(i,[]):
            if len(choices)>=PER_STOP:break
            if any(same_place(food,p) or public_places.same_venue(food,p) for p in choices):continue
            choices.append(food)
        choices.sort(key=lambda food:food['search_radius_m'])
        radius=max((food['search_radius_m'] for food in choices),default=RADII_M[-1])
        groups.append(dict(base,restaurants=choices,status='available' if choices else status,
            message='' if choices else MESSAGES.get(status,MESSAGES['not_found']),
            searched_radii_m=[r for r in RADII_M if r<=radius],effective_radius_m=radius,ranking_basis=RANKING_BASIS,
            note='500m부터 찾고, 3곳 미만이면 1,000m → 1,500m 순서로 보충해요. 표시는 코스 장소에서의 직선거리이며 일정에는 미포함입니다. '+DATA_NOTE))
    return dict(groups=groups,radius_m=500)
