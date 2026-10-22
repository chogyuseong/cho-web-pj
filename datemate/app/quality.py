"""동네 범위와 식사 구성에 사용하는 공통 규칙."""
from .routes import distance

AREAS={'연남동':(37.562,126.925),'성수동':(37.5446,127.0559),'종로':(37.5765,126.9855),'강남':(37.4979,127.0276),'홍대':(37.5572,126.9254),'잠실':(37.5133,127.1001),'익선동':(37.5742,126.9895),'혜화':(37.5823,127.0019),'망원동':(37.556,126.901),'이태원':(37.5345,126.9946)}

def configure(c,query):
    from .models import Point
    for name,(lat,lon) in AREAS.items():
        if name in query or name.rstrip('동')+'역' in query:
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

def pool(c):
    from .catalog import places
    rows=places(c.mode,c.visit_date)
    if c.mode=='real' and c.include_meal:
        from .restaurants import restaurants
        rows+=restaurants()
    return list({p['id']:dict(p,price_unit=p.get('price_unit') or 'person',meal=is_meal(p)) for p in rows if in_area(p,c)}.values())

def meal_penalty(plan,c):
    if not meal_due(c):return 0
    meal_indices=[i for i,p in enumerate(plan['places']) if is_meal(p)]
    if not meal_indices:return 4
    def mins(s):h,m=map(int,s.split(':'));return h*60+m
    if not any(any(min(mins(plan['timeline'][i]['departure']),b)-max(mins(plan['timeline'][i]['arrival']),a)>=30 for a,b in [(690,870),(1050,1230)]) for i in meal_indices):return 2
    return max(0,len(meal_indices)-1)
