import json
from .config import ROOT

def places(mode='demo',visit_date=None):
    path = ROOT / 'data' / f'{mode}_places.json'
    rows = json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    if mode=='real':
        from . import store
        import time
        with store.connect() as db:
            saved=db.execute("SELECT payload FROM cache WHERE key LIKE 'discovered-place:%' AND expires>?",(time.time(),)).fetchall()
        discovered=[json.loads(r['payload']) for r in saved]
        # Cached local results may have matched 'gallery' inside a car showroom category.
        discovered=[p for p in discovered if not (
            p.get('source_type')=='네이버 지역 검색 · 요청 활동 유형 연결' and
            any(word in ' '.join(p.get('tags',[])) for word in ('자동차','주차장','부동산','병원','의원')))]
        rows += discovered
        curated=ROOT/'data'/'curated_places.json'
        if curated.exists():
            additions=json.loads(curated.read_text(encoding='utf-8'))
            overrides={p['id']:p for p in additions}
            rows=[overrides.pop(p['id'],p) for p in rows]+list(overrides.values())
        facts_path=ROOT/'data/operating_facts.json'
        facts=json.loads(facts_path.read_text('utf-8')) if facts_path.exists() else {}
        for p in rows:
            p.update(facts.get(p['id'],{}))
            if visit_date and str(visit_date.weekday()) in p.get('weekly_hours',{}):p['hours']=p['weekly_hours'][str(visit_date.weekday())]
            if p.get('last_entry_offset') is not None:p['last_entry']=p['hours'][1]-p['last_entry_offset']
            if p.get('price') is not None and p.get('operations_source'):p['price_status']='confirmed'
    # 검색·상세·추천이 같은 카탈로그를 사용하므로 다른 지역 자료가 섞여도 노출하지 않는다.
    return [p for p in rows if p.get('region') in ('서울', '서울시', '서울특별시')]

def get_place(place_id, mode):
    found=next((p for p in places(mode) if p['id']==place_id), None)
    if found is None and mode=='real':
        from . import store
        found=store.cached('explore-place:'+place_id)
    if found is None and mode=='real' and place_id.startswith('food:'):
        from .restaurants import restaurants,live_restaurant
        return next((p for p in restaurants() if p['id']==place_id),None) or (live_restaurant(place_id) if place_id.startswith('food:naver-') else None)
    return found

def text(p):
    return json.dumps({k:v for k,v in p.items() if k not in ('photos','videos')}, ensure_ascii=False)
