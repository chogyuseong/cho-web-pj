from .search_address_text import place_query
"""Supplement requested venue types with verified public local-search coordinates."""
import hashlib
import re
from datetime import datetime,timezone
from urllib.parse import quote
from . import store
from .request_intent import intent,INTENTS
from .image_search import search_enabled,plain
from .discovery import local_lookup
from .explore import classify_local
from .quality import in_area
from .regions import region_from_address, korean_coordinates, same_region


def reach_km(c):
    """한 구간 이동 제한 안에서 닿는 대략적인 직선 반경. routes.leg 의 추정 속도·보정과 같은 값."""
    if c.area_center:return c.neighborhood_radius_km
    speed={'walk':4,'bicycle':12,'car':25,'transit':18}[c.transport]
    return max(1.0,speed*c.max_leg/60/1.35)


def nearby(place,c):
    from .routes import distance
    return in_area(place,c) and distance((c.area_center or c.origin).model_dump(),place)<=reach_km(c)


def search_area(name,region):
    """출발지 이름에서 검색어에 쓸 시·군·구(읍·면) 표기를 고른다. ' · ' 뒤는 설명이라 쓰지 않는다."""
    from .regions import normalize_region
    head=name.split(' · ')[0]
    district=re.search(r'[가-힣]{1,8}구(?:\s|$)',head)
    if district:return district[0].strip()
    words=[w for w in head.split() if not normalize_region(w)]
    admin=[w for w in words if re.fullmatch(r'[가-힣]{1,8}(?:시|군)',w)][:1]
    admin+=[w for w in words if re.fullmatch(r'[가-힣0-9]{1,8}(?:읍|면|동)',w)][:1]
    return ' '.join(admin or words)


# 활동 요청이 없을 때 종류별 기본 검색어(총 8건). 식사는 식사 시간대가 일정에 걸칠 때만 찾는다.
DEFAULT_SEARCHES={'meal':['맛집','음식점'],'cafe':['카페'],'culture':['전시','미술관'],'walk':['공원','산책'],'workshop':['공방']}
KIND_LABELS={'cafe':'카페·미식','culture':'문화·예술','walk':'산책·풍경','workshop':'체험·제작'}
MIN_PER_KIND=2
MAX_PARALLEL_LOOKUPS=4


def supply_gaps(c):
    """출발지에서 닿는 장소를 종류별로 세어, 기본 검색이 필요한 종류 목록과 집계를 돌려준다."""
    from collections import Counter
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


def area_terms(name,region):
    """기본 검색에 쓸 (동네 검색 지역, 되돌아갈 구·시 지역 또는 None).

    search_area 는 구가 있으면 구만 돌려줘 '해운대구 우동'의 동네가 빠진다. 구 뒤에 동·명소 이름이 있으면 함께 쓴다.
    도로명 주소(…로 12)는 동네 이름으로 보지 않는다.
    """
    from .regions import normalize_region
    primary=search_area(name,region)
    words=[w for w in name.split(' · ')[0].split() if not normalize_region(w)]
    def admin(w):return bool(re.fullmatch(r'[가-힣]{1,8}(?:시|군|구|도)',w))
    def street(w):return bool(re.fullmatch(r'[가-힣0-9]+(?:로|길)(?:\d+(?:번)?길)?',w) or re.fullmatch(r'[\d\-]+',w))
    district=next((w for w in words if re.fullmatch(r'[가-힣]{1,8}구',w)),None)
    city=next((w for w in words if re.fullmatch(r'[가-힣]{1,8}(?:시|군)',w)),None)
    local=[w for w in words if not admin(w) and not street(w)]
    if district and local:primary=district+' '+local[0]
    coarse=district or city or (words[0] if len(words)>1 and not street(words[0]) else None)
    return primary,(coarse if coarse and coarse!=primary else None)


def lookup_all(queries):
    """지역 검색을 동시 4건 이하로 실행한다. context_map 이 요청별 외부 호출 예산(request_usage)을 작업 스레드에 넘긴다."""
    from concurrent.futures import ThreadPoolExecutor
    from .request_usage import context_map
    def one(query):
        _,term,area=query
        # 맛집은 후기(카페·블로그 리뷰) 수 순으로, 나머지는 기본 정렬로 찾는다.
        return local_lookup(term,area,sort='comment') if term=='맛집' else local_lookup(term,area)
    if not queries:return []
    with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_LOOKUPS,len(queries))) as pool:
        return context_map(pool,one,queries)


# 기본 검색 한 번에 쓰는 지역 검색 상한(되돌아가기 검색 포함).
MAX_DEFAULT_LOOKUPS=8
# 동네 검색으로 반경 안 결과가 모자란 종류를 한 번 더 찾을 때의 검색어.
FALLBACK_TERMS={'meal':'식당','cafe':'디저트','culture':'갤러리','walk':'명소','workshop':'체험'}
REQUEST_CHECKS={'cafe':['카페','디저트','베이커리'],'meal':['음식점','한식','양식','일식','중식'],
    'cinema':['영화관','극장','시네마'],'performance':['공연','연극','뮤지컬','극장'],
    'jazz':['재즈','라이브'],
    'culture':['미술','박물관','전시','갤러리'],'museum':['박물관','문화재','유적'],
    'book':['서점','도서관','북카페','책방'],'walk':['공원','정원','산책','숲'],
    'game':['방탈출','보드','오락','게임','만화'],'workshop':['공방','공예','체험'],
    'activity':['스포츠','레저','볼링','클라이밍'],'view':['전망','공원','관광'],'shopping':['쇼핑','소품','편집']}
from . import sports
SPORT_KEYS=set(sports.KEYS)
# 종목을 직접 요청했을 때 함께 인정하는 더 구체적인 종목('테니스' 요청에 실내 테니스장).
RELATED_SPORTS={'tennis':{'indoor_tennis'},'surfing':{'indoor_surfing'},'ski':{'indoor_ski'},'futsal':set(),'boating':{'water_leisure','paddle'}}


def place_area(c):
    area=(c.area_center or c.origin).name.replace(' 지역 중심','').replace(' 중심','')
    if area.startswith('지도에서 선택'):
        from .geocoding import district_at
        area=district_at(c.origin.lat,c.origin.lon) or c.region
    return area


def discover_requested_places(c):
    from collections import Counter
    keys=intent(c)['intents']
    if c.mode!='real' or not search_enabled():return dict(status='not_available',resolved=0)
    supplement=False;supply=None;existing={}
    from .perf_trace import span
    if not keys:
        with span('intent_discovery.supply_gaps'):
            keys,supply,existing=supply_gaps(c)
        if not keys:return dict(status='not_needed',resolved=0,searched_kinds=[],lookups=0,supply=supply)
        supplement=True
    name=place_area(c)
    if supplement:area,coarse=area_terms(name,c.region)
    else:area,coarse=search_area(name,c.region),None
    center=(c.area_center or c.origin).model_dump()
    fingerprint=hashlib.sha256(str([area,center,c.neighborhood_radius_km,keys,'default' if supplement else 'requested']).encode()).hexdigest()
    cachekey='intent-local-v6:'+fingerprint
    cached=store.cached(cachekey)
    # 캐시된 결과의 lookups 는 처음 검색했을 때의 건수다. 이번에는 외부 호출이 없다.
    if cached:
        from .perf_trace import cache_hit as traced_hit
        traced_hit('intent_local');return dict(cached,cache_hit=True)
    count=0;statuses=[];resolved_ids=set()
    variations={'cafe':['카페','로스터리','디저트 카페'],'culture':['전시','미술관','갤러리'],
                'walk':['공원','산책','정원'],'workshop':['공방','도자기 공방','체험 공방']}
    def kind_key(kind):
        return 'intent-local-v6-kind:'+hashlib.sha256(str([area,center,c.neighborhood_radius_km,kind]).encode()).hexdigest()
    def full(a):return (c.region+' '+a).strip()
    if supplement:
        # 같은 추천 안에서 다시 불려도(조건 완화 재검색) 방금 찾은 종류는 또 검색하지 않아 지역 검색이 8건을 넘지 않는다.
        keys=[k for k in keys if not store.cached(kind_key(k))]
        if not keys:return dict(status='recently_searched',resolved=0,query_area=area,coverage_supplement=True,searched_kinds=[],lookups=0,supply=supply)
        queries=[(key,term,full(area)) for key in keys for term in DEFAULT_SEARCHES[key]][:MAX_DEFAULT_LOOKUPS]
    else:queries=[(key,term,full(area)) for key in keys[:4] for term in (sports.BY_KEY[key].terms if key in SPORT_KEYS else variations.get(key,[INTENTS[key][1][0]]))]
    # 진단: 검색한 종류별로 받은 수와 버린 이유, 실제 분류별 채택 수(반경 안 / 출발지에서 닿는 곳).
    stats={k:Counter() for k in keys}
    adopted=Counter();reachable=Counter();reachable_ids={}
    def have(kind):
        # 검색 전에 닿던 장소와 이번에 찾은 닿는 장소를 ID로 합쳐 센다(같은 장소를 다시 찾아도 두 번 세지 않음).
        label='meal' if kind=='meal' else KIND_LABELS[kind]
        return len(existing.get(label,set())|reachable_ids.get(label,set()))
    def absorb(key,items):
        nonlocal count
        st=stats.setdefault(key,Counter())
        for item in items:
            st['received']+=1
            category=plain(item.get('category',''));name=plain(item.get('title',''))
            address=plain(item.get('roadAddress') or item.get('address',''))
            if not name or region_from_address(address)!=c.region:st['other_region']+=1;continue
            if any(word in category for word in ('자동차','주차장','부동산','병원','의원')):st['unclassified']+=1;continue
            if supplement:
                # 기본 검색은 검색어가 아니라 실제 업종 분류를 따른다(맛집 검색에 나온 카페는 카페).
                kind=classify_local(category,name)
                if not kind:st['unclassified']+=1;continue
                label,meal=kind
                tag='meal' if meal else next((k for k,v in KIND_LABELS.items() if v==label),None)
            else:
                label,meal,tag=INTENTS[key][0],key=='meal',key
                if key in SPORT_KEYS:
                    # 종목은 sports.classify 로 판별한다(업종의 종목 낱말, 또는 레저 업종 + 상호). 용품점·학원·협회 등은 뺀다.
                    found=sports.classify(category,name)
                    if not found or (found.key!=key and found.key not in RELATED_SPORTS.get(key,())):st['unclassified']+=1;continue
                elif not any(word in category for word in REQUEST_CHECKS.get(key,INTENTS[key][1])):st['unclassified']+=1;continue
                if key=='meal' and ('카페' in category or '디저트' in category):st['unclassified']+=1;continue
            try:
                lon,lat=float(item['mapx']),float(item['mapy'])
                if abs(lon)>180:lon/=10000000
                if abs(lat)>90:lat/=10000000
                if not korean_coordinates(lat,lon):st['bad_coordinates']+=1;continue
            except (KeyError,ValueError,TypeError):st['bad_coordinates']+=1;continue
            if not in_area(dict(lat=lat,lon=lon),c):st['out_of_radius']+=1;continue
            pid='discovered:'+hashlib.sha256((name+address).encode()).hexdigest()[:20]
            if pid in resolved_ids:st['duplicate']+=1;continue
            resolved_ids.add(pid);st['adopted']+=1
            if tag!=key:st['other_kind']+=1
            actual=tag or label
            adopted[actual]+=1
            source='https://map.naver.com/p/search/'+quote(place_query({'name':name,'address':address}))
            row=dict(id=pid,name=name,address=address,lat=lat,lon=lon,region=c.region,demo=False,
                category=label,themes=[label],tags=[t for t in (tag,category) if t],meal=meal,
                description=category,source=source,source_type='네이버 지역 검색 · 요청 활동 유형 연결',
                checked_at=datetime.now(timezone.utc).isoformat(),discovery_verification='네이버 업체 분류·상호·주소·좌표 연결 · 영업 여부 별도 확인',
                price=None,price_unit='person',hours=None,closed_days=None,breaks=None,last_entry=None,
                reservation=None,stay=None,stay_basis=None,rating=None,setting=None,photos=[],videos=[],license='검색 결과')
            if nearby(row,c):
                reachable[actual]+=1
                reachable_ids.setdefault('meal' if meal else label,set()).add(pid)
            # Preserve richer blog evidence for a previously resolved venue.
            if not store.cached('discovered-place:'+pid):store.cache('discovered-place:'+pid,row,604800)
            count+=1
    with span('intent_discovery.lookups'):
        found=lookup_all(queries)
    with span('intent_discovery.absorb'):
        for (key,_,_),(items,status) in zip(queries,found):
            statuses.append(status);absorb(key,items)
    fallback=[];fallback_found=[]
    if supplement:
        from .quality import meal_due
        # 반경 안에서 닿는 결과가 모자란 종류만, 남은 상한 안에서 한 번 더 찾는다(식사 먼저).
        # 동네 이름 검색이 아무것도 돌려주지 않았으면 구·시 단위로 되돌아가고, 아니면 다른 검색어로 같은 동네를 찾는다.
        def short(kind):
            if kind=='meal':return meal_due(c) and have('meal')<MIN_PER_KIND
            return have(kind)==0
        for kind in keys:
            if len(queries)+len(fallback)>=MAX_DEFAULT_LOOKUPS:break
            if not short(kind):continue
            answered=[s for (k,_,_),(_,s) in zip(queries,found) if k==kind]
            # 검색 자체가 실패(권한·장애)했으면 같은 실패를 되풀이하지 않는다.
            if answered and all(s!='available' for s in answered):continue
            if stats[kind]['received']==0 and coarse:fallback.append((kind,DEFAULT_SEARCHES[kind][0],full(coarse)))
            else:fallback.append((kind,FALLBACK_TERMS[kind],full(area)))
        with span('intent_discovery.fallback_lookups'):
            fallback_found=lookup_all(fallback)
        with span('intent_discovery.absorb'):
            for (key,_,_),(items,status) in zip(fallback,fallback_found):
                statuses.append(status);absorb(key,items)
    meal_supply=None
    if supplement and 'meal' in keys:
        total=have('meal')
        # enough=False 면 식사 후보가 2곳 미만인 채로 추천한다. 식사 조건은 그대로 검사하고(미충족 안은 버림) 지어내지 않는다.
        meal_supply=dict(before=(supply or {}).get('meal',0),found_reachable=len(reachable_ids.get('meal',())),after=total,enough=total>=MIN_PER_KIND)
    result=dict(status='available' if count else 'not_found',resolved=count,query_area=area,fallback_area=coarse,coverage_supplement=supplement,
                searched_kinds=list(keys) if supplement else None,lookups=len(queries)+len(fallback),
                fallback_queries=[dict(kind=k,term=t,area=a) for k,t,a in fallback],supply=supply,
                kind_stats={k:dict(v) for k,v in stats.items()},adopted=dict(adopted),adopted_reachable=dict(reachable),meal_supply=meal_supply,
                permission_required='permission_required' in statuses,search_unavailable=bool(statuses) and all(s=='unavailable' for s in statuses))
    store.cache(cachekey,result,900 if count else 30)
    if supplement:
        for kind in keys:
            # 검색이 응답했으면(결과 0건 포함) 15분, 실패했으면 30초 뒤 다시 찾을 수 있다.
            ok=any(s=='available' for (k,_,_),(_,s) in zip(queries+fallback,found+fallback_found) if k==kind)
            store.cache(kind_key(kind),True,900 if ok else 30)
    return result


