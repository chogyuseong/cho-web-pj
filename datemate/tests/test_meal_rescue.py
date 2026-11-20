from datetime import date
from app.models import Conditions
from app import restaurants as module


def test_meal_rescue_prefers_tour_listed_places_then_detour(monkeypatch):
    c=Conditions(mode='real',visit_date=date(2026,10,24),area_center=dict(name='연남동',lat=37.56,lon=126.925))
    plan=dict(conditions=c.model_dump(mode='json'),places=[dict(id='a',name='a'),dict(id='b',name='b')],deviations=[dict(condition='meal',state='unmet')])
    def food(pid,source,extra,meters=100):return dict(id=pid,name=pid,lat=37.56,lon=126.925,public_source=source,extra_distance_km=extra,route_offset_km=0.1,distance_m=meters)
    # 공공 자료에는 후기 수가 없다: 한국관광공사에 실린 곳을 먼저, 그다음 추가 이동이 적은 순. 같은 식당이 두 장소에서 나와도 한 번만.
    groups={0:[food('store_close','store',0.1),food('tour_far','tour',1.2)],1:[food('tour_close','tour',0.2),food('store_close','store',0.3),food('store_far','store',2.0)]}
    monkeypatch.setattr(module,'public_food',lambda p,indices:('available',groups))
    result=module.meal_rescue(plan)
    assert [p['id'] for p in result['restaurants']]==['tour_close','tour_far','store_close']
    assert '후기·별점 순위가 아니에요' in result['ranking_basis'] and '네이버' not in result['ranking_basis']
    assert '아직 포함되지' in result['note'] and '공공 자료' in result['note']


def test_no_meal_mismatch_does_not_search(monkeypatch):
    monkeypatch.setattr(module,'public_food',lambda *_:(_ for _ in ()).throw(AssertionError('unexpected lookup')))
    assert module.meal_rescue(dict(deviations=[]))['status']=='not_needed'
