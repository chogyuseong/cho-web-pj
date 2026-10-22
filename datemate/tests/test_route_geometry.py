from app import store
from app.models import Conditions
from app.routes import leg


def test_driving_geometry_and_cache(monkeypatch):
    monkeypatch.setenv('NAVER_MAPS_KEY_ID','test')
    monkeypatch.setenv('NAVER_MAPS_KEY','test')
    calls=[]
    def response(*args,**kwargs):
        calls.append(1)
        return {'route':{'traoptimal':[{'summary':{'duration':120000,'distance':1000,'fuelPrice':100,'tollFare':0},
            'path':[[126.98,37.57],[126.99,37.58],['bad',37.5],[200,100]]}]}}
    monkeypatch.setattr('app.collection.fetch_json',response)
    c=Conditions(mode='real',transport='car',visit_date='2026-10-24')
    a=dict(name='출발',lat=37.57,lon=126.98)
    b=dict(name='도착',lat=37.58,lon=126.99)
    result=leg(a,b,c)
    assert result['path']==[[126.98,37.57],[126.99,37.58]]
    assert result['minutes']==2 and result['status']=='api'
    assert leg(a,b,c)==result and len(calls)==1


def test_demo_and_walk_do_not_claim_road_geometry():
    for mode,transport in [('demo','car'),('real','walk')]:
        c=Conditions(mode=mode,transport=transport,visit_date='2026-10-24')
        result=leg(dict(name='A',lat=37.57,lon=126.98),dict(name='B',lat=37.58,lon=126.99),c)
        assert result['path']==[] and result['status']!='api'
