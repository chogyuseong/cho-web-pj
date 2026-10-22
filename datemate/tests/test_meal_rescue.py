from datetime import date
from app.models import Conditions
from app import restaurants as module
from app import store


def test_meal_rescue_prefers_review_rank_then_detour_and_stays_local(monkeypatch):
    c=Conditions(mode='real',visit_date=date(2026,10,24),area_center=dict(name='연남동',lat=37.56,lon=126.925))
    plan=dict(conditions=c.model_dump(mode='json'),places=[dict(id='a',name='a'),dict(id='b',name='b')],deviations=[dict(condition='meal',state='unmet')])
    def food(pid,rank,extra,lat=37.56):return dict(id=pid,name=pid,lat=lat,lon=126.925,review_search_rank=rank,extra_distance_km=extra,route_offset_km=0.1)
    foods=[food('many_reviews',1,1.2),food('close',2,0.1),food('distant',1,0.1,37.7),food('a',1,0)]
    monkeypatch.setattr(module,'search_nearby',lambda *_:dict(status='available',restaurants=foods))
    monkeypatch.setattr(store,'cached',lambda _:None)
    monkeypatch.setattr(store,'cache',lambda *_:None)
    result=module.meal_rescue(plan)
    assert [p['id'] for p in result['restaurants']]==['many_reviews','close']
    assert '별점은 제공되지' in result['ranking_basis']
    assert '아직 포함되지' in result['note']


def test_no_meal_mismatch_does_not_search(monkeypatch):
    monkeypatch.setattr(module,'search_nearby',lambda *_:(_ for _ in ()).throw(AssertionError('unexpected network')))
    assert module.meal_rescue(dict(deviations=[]))['status']=='not_needed'
