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
        # 공공 자료(한국관광공사·소상공인 상가정보)에서 찾은 후보는 지금 요청의 사용자가 찾은 것만 합친다(app/public_places.py).
        # 네이버 지역 검색 결과는 후보로 쓰지 않는다(2026-11-20 2단계, 특약 1.1·1.2). 소유자가 없는 문맥(시작 색인 등)에는 들어가지 않는다.
        from . import public_places
        rows += public_places.candidates()
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
    if found is None and mode=='real' and place_id.startswith('food:'):
        from .restaurants import restaurants
        found=next((p for p in restaurants() if p['id']==place_id),None)
    if found is None and mode=='real':
        # 주변 식당으로 보여 준 공공 자료 장소(24시간), 둘러보기 목록의 장소, 보관이 끝난 뒤에는 같은 사용자의 저장 코스에서 찾는다.
        from . import public_places
        found=public_places.lookup(place_id)
    if found is None and mode=='real':
        # 예전에 저장한 코스의 네이버 검색 장소는 같은 사용자의 저장 코스(이력 조회, 최대 21일)에서 찾는다.
        from .naver_terms import place_from_owner_plans
        found=place_from_owner_plans(place_id)
    return found

def text(p):
    return json.dumps({k:v for k,v in p.items() if k not in ('photos','videos')}, ensure_ascii=False)
