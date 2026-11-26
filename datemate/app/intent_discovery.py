"""요청한 활동과 동네에 모자란 종류의 추천 후보를 공공 자료에서 찾는다(app/public_places.py).

2026-11-20 2단계: 예전에는 네이버 지역 검색 결과를 후보로 썼다. 검색 결과를 우리 계산의 입력으로 쓰지 않기로 해(검색 API 특약 1.1·1.2 의
엄격한 읽기, docs/naver-terms-stage2-design.ko.md 3.8(b)) 한국관광공사 TourAPI 시·군·구 목록과 소상공인 상가정보 반경 조회로 바꿨다.
검색어를 만들지 않으므로 동네 이름이 아니라 좌표(동네 기준점 또는 출발지)와 반경으로 찾는다.
"""
import hashlib
from collections import Counter

from . import naver_cache, sports
from .quality import in_area
from .regions import same_region
from .request_intent import intent,INTENTS


def reach_km(c):
    """한 구간 이동 제한 안에서 닿는 대략적인 직선 반경. routes.leg 의 추정 속도·보정과 같은 값."""
    if c.area_center:return c.neighborhood_radius_km
    speed={'walk':4,'bicycle':12,'car':25,'transit':18}[c.transport]
    return max(1.0,speed*c.max_leg/60/1.35)


def nearby(place,c):
    from .routes import distance
    return in_area(place,c) and distance((c.area_center or c.origin).model_dump(),place)<=reach_km(c)


# 활동 요청이 없을 때 채우는 종류. 식사는 식사 시간대가 일정에 걸칠 때만 찾는다.
KIND_LABELS={'cafe':'카페·미식','culture':'문화·예술','walk':'산책·풍경','workshop':'체험·제작'}
MIN_PER_KIND=2
# 사용자가 직접 요청한 활동은 종류마다 이만큼까지 상가정보에서 고른다(기본 보충은 public_places.STORE_CAPS).
REQUEST_CAP=8
# 관광공사·상가정보를 받는 반경 상한(km). 자동차 구간 제한이 길어도 이보다 넓게 받지 않는다.
MAX_FETCH_KM=10
# 관광공사 항목을 후보에 넣는 수: 종류(식사·카페·그 밖은 활동 분류)마다 가까운 순으로 이만큼, 모두 합쳐 public_places.TOUR_CAP 까지.
TOUR_PER_KIND=12


def supply_gaps(c):
    """출발지에서 닿는 장소를 종류별로 세어, 보충이 필요한 종류 목록과 집계를 돌려준다."""
    from .catalog import places
    from .quality import is_meal,meal_due
    rows=places('real',c.visit_date)
    if c.include_meal:
        # 추천 후보 풀(quality.pool)과 같게 식사 조건이 켜져 있으면 식당 자료도 센다.
        from .restaurants import restaurants
        rows=rows+restaurants()
    supply=Counter();ids={}
    for p in rows:
        # 같은 시·도라도 출발지에서 닿지 않는 장소는 후보로 치지 않는다.
        if same_region(p,c.region) and nearby(p,c):
            kind='meal' if is_meal(p) else p.get('category') or '기타'
            supply[kind]+=1;ids.setdefault(kind,set()).add(p['id'])
    gaps=[]
    if meal_due(c) and supply['meal']<MIN_PER_KIND:gaps.append('meal')
    if sum(n>=MIN_PER_KIND for k,n in supply.items() if k!='meal')<2:
        gaps+=[k for k,label in KIND_LABELS.items() if supply[label]<MIN_PER_KIND]
    return gaps,dict(supply),ids


SPORT_KEYS=set(sports.KEYS)
# 종목을 직접 요청했을 때 함께 인정하는 더 구체적인 종목('테니스' 요청에 실내 테니스장).
RELATED_SPORTS={'tennis':{'indoor_tennis'},'surfing':{'indoor_surfing'},'ski':{'indoor_ski'},'futsal':set(),'boating':{'water_leisure','paddle'}}


def wanted(kind,tag,keys):
    """상가정보 장소(종류, 태그)가 찾는 활동 keys 중 어느 것에 드는지. 없으면 None."""
    for key in keys:
        if key==kind and kind!='sport':return key
        if kind=='sport' and (key==tag or tag in RELATED_SPORTS.get(key,()) or key=='activity'):return key
    return None


def place_kind(place):
    """찾은 장소의 종류 이름(집계용): 식사, 보충 종류(cafe·culture·walk·workshop), 그 밖에는 첫 태그."""
    if place.get('meal'):return 'meal'
    tag=(place.get('tags') or [None])[0]
    if tag in KIND_LABELS or tag in INTENTS:return tag
    return next((k for k,label in KIND_LABELS.items() if label==place.get('category')),tag or '기타')


def discover_requested_places(c):
    from . import public_places
    from .catalog import places
    from .perf_trace import span
    from .request_intent import matches
    from .routes import distance
    keys=intent(c)['intents']
    if c.mode!='real' or not public_places.enabled():return dict(status='not_available',resolved=0)
    supplement=not keys;supply=None;existing={}
    if supplement:
        # 활동 요청이 없으면 모자란 종류를 채운다. 모자란 종류가 없어도 한국관광공사 항목은 받는다(하루 한 번 받아 나눠 쓰는 목록).
        with span('intent_discovery.supply_gaps'):
            keys,supply,existing=supply_gaps(c)
    else:keys=keys[:4]
    center=(c.area_center or c.origin).model_dump()
    radius_km=min(MAX_FETCH_KM,c.neighborhood_radius_km if c.area_center else reach_km(c))
    spot=[round(center['lat'],4),round(center['lon'],4),radius_km,c.region]
    cachekey='public-discovery-v1:'+hashlib.sha256(str([spot,keys,'default' if supplement else 'requested']).encode()).hexdigest()
    def kind_key(kind):
        return 'public-discovery-v1-kind:'+hashlib.sha256(str([spot,kind]).encode()).hexdigest()
    # 결과와 종류별 '방금 찾음' 표시를 한 번의 DB 조회로 읽는다(운영 DB 왕복을 줄임).
    known=naver_cache.cached_many([cachekey]+([kind_key(k) for k in keys] if supplement else []))
    cached=known.get(cachekey)
    if cached:
        from .perf_trace import cache_hit as traced_hit
        traced_hit('public_discovery');return dict(cached,cache_hit=True)
    if supplement and keys:
        # 같은 추천 안에서 다시 불려도(조건 완화 재검색) 방금 찾은 종류는 또 찾지 않는다.
        keys=[k for k in keys if not known.get(kind_key(k))]
        if not keys:return dict(status='recently_searched',resolved=0,coverage_supplement=True,searched_kinds=[],lookups=0,supply=supply)
    # 이미 있는 후보(카탈로그·식당 시드·앞서 찾은 공공 후보): 같은 가게를 두 번 넣지 않으려고 본다.
    have_rows=[p for p in places('real',c.visit_date) if same_region(p,c.region) and in_area(p,c)]
    from .restaurants import restaurants
    have_rows+=[p for p in restaurants() if same_region(p,c.region) and in_area(p,c)]
    stats={k:Counter() for k in keys};sources=[];found=[]
    adopted=Counter();reachable=Counter();reachable_ids={}
    def have(kind):
        # 찾기 전에 닿던 장소와 이번에 찾은 닿는 장소를 ID로 합쳐 센다.
        label='meal' if kind=='meal' else KIND_LABELS[kind]
        return len(existing.get(label,set())|reachable_ids.get(label,set()))
    def adopt(place,key):
        found.append(place)
        actual=place_kind(place);adopted[actual]+=1
        if key in stats:
            stats[key]['adopted']+=1
            if actual!=key and supplement:stats[key]['other_kind']+=1
        if nearby(place,c):
            reachable[actual]+=1
            reachable_ids.setdefault('meal' if place.get('meal') else place['category'],set()).add(place['id'])
    # 1) 한국관광공사: 반경 안 항목을 종류마다 가까운 순으로 몇 곳씩. 요청한 활동에 맞는 곳을 먼저 채운다.
    with span('intent_discovery.tour'):
        tour=public_places.tour_near(center['lat'],center['lon'],radius_km)
    sources.append(dict(source='tour',status=tour.get('status'),rows=len(tour.get('rows') or []),radius_m=round(radius_km*1000),
                        districts=tour.get('districts') or []))
    tour_rows=[]
    for row in tour.get('rows') or []:
        place=public_places.tour_place(row,c.region)
        if not place or not in_area(place,c):continue
        key=next((k for k in keys if matches(place,k)),None) if not supplement else place_kind(place)
        tour_rows.append((key not in keys,distance(center,place),place,key))
    taken=Counter()
    for _,_,place,key in sorted(tour_rows,key=lambda r:(r[0],r[1],r[2]['id'])):
        if len(found)>=public_places.TOUR_CAP:break
        group='meal' if place['meal'] else place['tags'][0] if place['tags'][0]=='cafe' else place['category']
        if taken[group]>=TOUR_PER_KIND:continue
        if key in stats:stats[key]['received']+=1
        if any(public_places.same_venue(place,other) for other in have_rows+found):
            if key in stats:stats[key]['duplicate']+=1
            continue
        taken[group]+=1
        adopt(place,key)
    # 2) 소상공인 상가정보: 카탈로그와 관광공사 항목으로도 모자란 종류만 채운다(사진·영업시간·평판이 없는 자료라 마지막에 쓴다).
    #    종류마다 지점 표기가 없는 곳 먼저, 가까운 순으로 몇 곳.
    def short(key):
        if supplement:return have(key)<MIN_PER_KIND
        return sum(matches(p,key) for p in have_rows+found)<MIN_PER_KIND
    need=[k for k in keys if short(k)]
    sheets=list(dict.fromkeys(s for k in need for s in public_places.KIND_SHEETS.get('activity' if k in SPORT_KEYS else k,())))
    with span('intent_discovery.stores'):
        for sheet in sheets:
            data,radius_m=public_places.stores_near(sheet,center['lat'],center['lon'])
            sources.append(dict(source='store:'+sheet,status=data.get('status'),rows=len(data.get('rows') or []),radius_m=radius_m,
                                truncated=bool(data.get('truncated'))))
            rows=[]
            for row in data.get('rows') or []:
                pair=public_places.store_place(row,None,data.get('data_month'))
                if not pair:continue
                kind,place=pair
                key=wanted(kind,place['tags'][0],need)
                if not key:continue
                stats[key]['received']+=1
                if place.get('region')!=c.region:stats[key]['other_region']+=1;continue
                if not in_area(place,c):stats[key]['out_of_radius']+=1;continue
                rows.append((kind,place))
            caps={k:(REQUEST_CAP if not supplement else n) for k,n in public_places.STORE_CAPS.items()}
            for kind,place in public_places.pick_stores(rows,center,caps,taken=have_rows+found):
                adopt(place,wanted(kind,place['tags'][0],need))
    public_places.remember(found)
    count=len(found)
    meal_supply=None
    if supplement and 'meal' in keys:
        total=have('meal')
        # enough=False 면 식사 후보가 2곳 미만인 채로 추천한다. 식사 조건은 그대로 검사하고(미충족 안은 버림) 지어내지 않는다.
        meal_supply=dict(before=(supply or {}).get('meal',0),found_reachable=len(reachable_ids.get('meal',())),after=total,enough=total>=MIN_PER_KIND)
    statuses=[s['status'] for s in sources]
    result=dict(status='available' if count else 'not_found',resolved=count,coverage_supplement=supplement,
                searched_kinds=list(keys) if supplement else None,store_kinds=need,lookups=len(sources),sources=sources,radius_km=radius_km,supply=supply,
                kind_stats={k:dict(v) for k,v in stats.items()},adopted=dict(adopted),adopted_reachable=dict(reachable),meal_supply=meal_supply,
                search_unavailable=bool(statuses) and all(s!='available' for s in statuses),
                data_note='후보는 한국관광공사 관광정보와 소상공인 상가정보에서 찾았어요. 사진·영업시간·후기가 없는 곳이 많아요.')
    ok=any(s=='available' for s in statuses)
    writes=[(cachekey,result,900 if ok else 30)]
    if supplement:
        # 자료가 응답했으면(0곳 포함) 15분, 실패했으면 30초 뒤 다시 찾을 수 있다.
        writes+=[(kind_key(kind),True,900 if ok else 30) for kind in keys]
    naver_cache.cache_many(writes)
    return result
