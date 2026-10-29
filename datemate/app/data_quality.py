"""Field-level evidence coverage; discovery timestamps never verify opening hours."""
from .preferences import operating_source_current
from datetime import datetime,timezone


def place_coverage(place):
    current=operating_source_current(place)
    try:age=(datetime.now(timezone.utc).date()-datetime.fromisoformat(place['operations_checked_at']).date()).days
    except (KeyError,TypeError,ValueError):age=-1
    fresh=bool(place.get('operations_source')) and 0<=age<=90
    verified=set(place.get('operations_verified_fields',[]))
    fields={
        label:(place.get('operations_evidence',{}).get(key,{}).get('current',fresh and key in verified)) and place.get(key) is not None
        for label,key in [('영업시간','hours'),('휴무일','closed_days'),('예약','reservation'),('가격','price')]
    }
    return dict(confirmed=[k for k,v in fields.items() if v],missing=[k for k,v in fields.items() if not v],
                source_current=current,scope='최근 운영 출처가 있는 입력 자료 기준 · 실시간 영업 보장 아님')


def plan_coverage(plan):
    places=[place_coverage(p) for p in plan['places']]
    return dict(places=len(places),current_operating_sources=sum(p['source_current'] for p in places),
                confirmed_fields=sum(len(p['confirmed']) for p in places),total_fields=4*len(places),
                estimated_routes=sum(r.get('status')!='api' for r in plan.get('legs',[])),
                assumed_prices=sum(c.get('price_kind')=='planning_assumption' for c in plan.get('costs',[])))
