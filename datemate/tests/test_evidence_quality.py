from datetime import datetime, timezone
import httpx
from app.data_quality import place_coverage, plan_coverage
from app.models import Conditions
from app.routes import leg


def test_discovery_date_is_not_operating_evidence():
    place=dict(checked_at=datetime.now(timezone.utc).isoformat(),hours=[9,18],closed_days=[],reservation=False,price=[0,0])
    assert not place_coverage(place)['confirmed']
    place.update(operations_source='https://example.org/official',operations_checked_at=datetime.now(timezone.utc).isoformat(),operations_verified_fields=['hours','closed_days','reservation','price'])
    assert len(place_coverage(place)['confirmed'])==4
    place['operations_checked_at']='2020-01-01'
    assert len(place_coverage(place)['missing'])==4


def test_menu_block_stops_repeated_requests_even_when_refreshing(monkeypatch):
    from app import menus,store
    calls=[]
    def blocked(*args):
        calls.append(1)
        response=httpx.Response(403,request=httpx.Request('GET','https://search.naver.com'))
        response.raise_for_status()
    monkeypatch.setattr(menus,'fetch_page',blocked)
    try:
        first=menus.restaurant_menu(dict(id='blocked-a',name='A',address='서울'),force=True)
        second=menus.restaurant_menu(dict(id='blocked-b',name='B',address='서울'),force=True)
        assert first['reason']=='access_restricted'
        assert second['reason']=='provider_cooldown'
        assert len(calls)==1 and second['items']==[]
    finally:
        with store.connect() as db:db.execute('DELETE FROM cache WHERE key=?',('menu-provider-cooldown',))


def test_estimated_route_has_explicit_non_statistical_buffer():
    c=Conditions(visit_date='2026-11-01',mode='real',allow_estimates=True)
    route=leg(dict(name='A',lat=37.56,lon=126.98),dict(name='B',lat=37.57,lon=126.98),c)
    assert route['status']=='estimated'
    assert route['planning_minutes_range'][1]>route['minutes']
    assert '통계적 예측 범위가 아니' in route['planning_note']


def test_coverage_does_not_count_estimated_price_as_verified():
    coverage=plan_coverage({'places':[{'price':[1000,2000]}],'legs':[{'status':'estimated'}],'costs':[{'price_kind':'planning_assumption'}]})
    assert coverage['confirmed_fields']==0
    assert coverage['assumed_prices']==1


def test_assumed_closed_days_do_not_complete_partial_source():
    from app.preferences import operating_source_current
    place=dict(hours=[9,18],closed_days=[],operations_source='https://example.org',
               operations_checked_at=datetime.now(timezone.utc).isoformat(),operations_verified_fields=['hours'])
    assert not operating_source_current(place)
    assert place_coverage(place)['confirmed']==['영업시간']
