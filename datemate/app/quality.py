"""동네 범위와 식사 구성에 사용하는 공통 규칙."""
from .routes import distance

AREAS={'연남동':(37.562,126.925),'성수동':(37.5446,127.0559),'종로':(37.5765,126.9855),'강남':(37.4979,127.0276),'홍대':(37.5572,126.9254),'잠실':(37.5133,127.1001),'익선동':(37.5742,126.9895),'혜화':(37.5823,127.0019),'망원동':(37.556,126.901),'이태원':(37.5345,126.9946)}

def configure(c,query):
    from .models import Point
    # 축제를 고른 코스는 검색어에 동네 이름이 있어도 축제 위치를 중심으로 찾는다.
    if c.region == '서울' and not c.festival:
        for name,(lat,lon) in AREAS.items():
            if name.rstrip('동') in query:
                return c.model_copy(update={'area_center':Point(name=name+' 중심',lat=lat,lon=lon)})
    return c.model_copy(update={'area_center':c.origin})

def in_area(place,c):
    return not c.area_center or distance(c.area_center.model_dump(),place)<=c.neighborhood_radius_km

def is_meal(place):
    return place.get('meal',False) or place['id'].startswith('food:')

def same_place(a,b):
    from urllib.parse import urlsplit,unquote
    import re
    def names(p):
        rows=[p['name'],*(p.get('search_aliases') or [])]
        wiki=urlsplit(p.get('wikipedia') or '')
        if wiki.hostname=='ko.wikipedia.org':rows.append(unquote(wiki.path.rsplit('/',1)[-1]).replace('_',' '))
        return {re.sub(r'\s+','',n).casefold() for n in rows}
    return a['id']==b['id'] or bool(names(a)&names(b)) and distance(a,b)<.8

def meal_due(c):
    def mins(s):h,m=map(int,s.split(':'));return h*60+m
    start,end=mins(c.start),mins(c.end)
    return c.include_meal and any(min(end,b)-max(start,a)>=45 for a,b in [(690,870),(1050,1230)])

LEISURE_SEARCH_SOURCE='레저 종목 분류'

def wants_leisure(c):
    """운동·레저를 요청했거나, 고른 테마·데이트 분류가 레저를 포함하는지.
    데이트 분류는 사용자가 직접 골랐을 때만 센다(taxonomy.classification_strict). 홈 동네 카드가 넣은 '활동적인'은
    기본 추천과 같으므로 레저 조회로 찾은 운동 시설을 섞지 않는다."""
    from .request_intent import intent,INTENTS
    from .taxonomy import filtering_themes
    if any(INTENTS.get(key,('',))[0]=='레저·활동' for key in intent(c)['intents']):return True
    return '레저·활동' in set(c.themes or [])|set(filtering_themes(c))

def from_leisure_search(place):
    return LEISURE_SEARCH_SOURCE in (place.get('source_type') or '')

def pool(c):
    from .catalog import places
    from .regions import same_region
    rows=places(c.mode,c.visit_date)
    # 레저 후보 조회로 찾아 둔 운동 시설(탁구장·볼링장 등)은 운동을 원한 요청에서만 추천 후보로 쓴다.
    # 그대로 두면 누군가 레저 패널을 연 동네의 기본 추천에 '탁구장 → 식사 → 볼링장' 같은 코스가 섞인다.
    # 사용자가 이미 고른(고정한) 장소는 남긴다. 레저 패널의 교체 후보는 이 함수를 거치지 않는다.
    if not wants_leisure(c):
        kept=set((c.locked or {}).values()) if isinstance(c.locked,dict) else set()
        rows=[p for p in rows if not from_leisure_search(p) or p['id'] in kept]
    if c.mode=='real' and c.include_meal:
        from .restaurants import restaurants
        rows+=restaurants()
    from .preferences import operating_source_current
    from .request_intent import intent,matches
    denied=intent(c)['excluded']
    from . import store
    with store.connect() as db:pending={r[0] for r in db.execute('SELECT DISTINCT place_id FROM place_reports WHERE resolved=0')}
    excluded=[p for p in rows if p['id'] in c.excluded_place_ids]
    return list({p['id']:dict(p,price_unit=p.get('price_unit') or 'person',meal=is_meal(p),report_pending=p['id'] in pending) for p in rows if same_region(p,c.region) and in_area(p,c) and not any(matches(p,k) for k in denied) and p['id'] not in c.excluded_place_ids and not any(same_place(p,other) for other in excluded) and (c.trust_mode!='operating_sources' or operating_source_current(p) and p['id'] not in pending)}.values())

def meal_time_matches(plan):
    def mins(s):h,m=map(int,s.split(':'));return h*60+m
    return [i for i,p in enumerate(plan['places']) if is_meal(p) and any(min(mins(plan['timeline'][i]['departure']),b)-max(mins(plan['timeline'][i]['arrival']),a)>=30 for a,b in [(690,870),(1050,1230)])]

MEAL_WINDOWS=[(690,870),(1050,1230)]
FOOD_TOUR=r'맛집\s*(?:탐방|투어|순례|도장\s*깨기|뿌시기|뿌수기)|먹방|먹부림|식도락|먹으러\s*다니'

def meal_stack_allowed(c):
    """음식 위주 요청이면 한 코스에 식사 장소를 여러 곳 넣어도 된다.
    priority=food, 한 종류 집중(focus), 자유 입력의 식사 단독 요청('맛집 위주')·맛집 탐방류가 해당한다."""
    import re
    from .request_intent import intent
    if c.priority=='food' or c.theme_mode=='focus':return True
    parsed=intent(c)
    if parsed['exclusive'] and parsed['intents']==['meal']:return True
    return bool(re.search(FOOD_TOUR,c.course_query+' '+c.request))

def extra_meals(plan,c):
    """식사 시간대(점심 11:30–14:30·저녁 17:30–20:30)마다 식당 1곳까지. 넘는 식사 장소 수를 센다.
    식사 시간대와 30분 이상 겹치지 않는 식당은 시간대 밖 식사로 묶어, 시간대 식사가 있으면 모두 초과로 보고 없으면 1곳까지 둔다.
    음식 위주 요청이거나 사용자가 식당을 두 곳 이상 고정했으면 0이다. 부분 일정에도 쓴다(뒤에 장소를 붙여도 앞 장소의 시각은 그대로다)."""
    if meal_stack_allowed(c):return 0
    locked=set((c.locked or {}).values()) if isinstance(c.locked,dict) else set()
    if sum(is_meal(p) and p['id'] in locked for p in plan['places'])>=2:return 0
    def mins(s):h,m=map(int,s.split(':'));return h*60+m
    groups={}
    for p,t in zip(plan['places'],plan['timeline']):
        if not is_meal(p):continue
        arrival,departure=mins(t['arrival']),mins(t['departure'])
        window=next((i for i,(a,b) in enumerate(MEAL_WINDOWS) if min(departure,b)-max(arrival,a)>=30),None)
        groups[window]=groups.get(window,0)+1
    outside=groups.pop(None,0)
    extra=sum(n-1 for n in groups.values())
    return extra+(outside if groups else max(0,outside-1))

def meal_penalty(plan,c):
    if not meal_due(c):return 0
    meal_indices=[i for i,p in enumerate(plan['places']) if is_meal(p)]
    if not meal_indices:return 4
    if not meal_time_matches(plan):return 2
    return max(0,len(meal_indices)-1)
