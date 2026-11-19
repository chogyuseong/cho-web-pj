import json
from .config import ROOT

def places(mode='demo',visit_date=None):
    from .perf_trace import span
    with span('catalog.places'):
        return _places(mode,visit_date)

def _places(mode,visit_date):
    path = ROOT / 'data' / f'{mode}_places.json'
    rows = json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    if mode=='real':
        # 네이버 검색으로 찾은 장소(discovered-place)는 지금 요청의 사용자 것만 합친다(특약 2.3·2.4).
        # 예전에는 모든 사용자가 찾은 장소를 7일 동안 공용 후보로 썼다. 소유자가 없는 문맥(시작 색인 등)에는 들어가지 않는다.
        from . import naver_cache
        discovered=list(naver_cache.owned_values('discovered-place:').values())
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
        from .operating_evidence import apply_evidence,evidence_rows,field_current
        evidence=evidence_rows()
        for p in rows:
            p.update(facts.get(p['id'],{}))
            p['operations_verified_fields']=[key for key in ('hours','closed_days','reservation','price') if facts.get(p['id'],{}).get(key) is not None]
            p.update(apply_evidence(p,evidence))
            if visit_date and str(visit_date.weekday()) in p.get('weekly_hours',{}):p['hours']=p['weekly_hours'][str(visit_date.weekday())]
            if p.get('last_entry_offset') is not None and p.get('hours'):p['last_entry']=p['hours'][1]-p['last_entry_offset']
            if p.get('price') is not None:p['price_status']='confirmed' if field_current(p,'price') else 'estimated'
    from .regions import normalize_region, region_from_address
    return [p for p in rows if normalize_region(p.get('region')) or region_from_address(p.get('address'))]

def get_place(place_id, mode):
    found=next((p for p in places(mode) if p['id']==place_id), None)
    if found is None and mode=='real':
        from . import naver_cache
        found=naver_cache.cached('explore-place:'+place_id)
    if found is None and mode=='real' and place_id.startswith('food:'):
        from .restaurants import restaurants,live_restaurant
        found=next((p for p in restaurants() if p['id']==place_id),None) or (live_restaurant(place_id) if place_id.startswith('food:naver-') else None)
    if found is None and mode=='real':
        # 개인화 보관(24시간)이 지난 네이버 검색 장소는 같은 사용자의 저장 코스(이력 조회, 최대 21일)에서 찾는다.
        from .naver_terms import place_from_owner_plans
        found=place_from_owner_plans(place_id)
    return found

def text(p):
    return json.dumps({k:v for k,v in p.items() if k not in ('photos','videos')}, ensure_ascii=False)
