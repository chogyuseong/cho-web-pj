from datetime import date
from app.catalog import places,get_place
from app.models import Conditions
from app.planner import evaluate,recommend
from app.condition_audit import audit_plan
from app.restaurants import restaurants,meal_suggestions
from app.restaurants import search_nearby
import httpx

def test_restaurant_sources_and_distances_are_real_and_separate_from_itinerary():
    c=Conditions(mode='real',allow_estimates=True,visit_date=date(2026,10,24))
    plan=recommend(c)['plans'][0]
    before=[p['id'] for p in plan['places']]
    groups=meal_suggestions(plan)
    assert len(restaurants())==14
    assert groups and any(g['restaurants'] for g in groups)
    for group in groups:
        assert len(group['restaurants'])<=3
        for r in group['restaurants']:
            assert r['source'].startswith('https://') and r['recognition']
            assert r['route_offset_km']<=3 and r['extra_distance_km']<=5
            assert get_place(r['id'],'real')['id']==r['id']
    assert before==[p['id'] for p in plan['places']]
    assert not any(p['id'].startswith('food:') for p in places('real'))

def test_operating_facts_have_sources_and_weekday_hours():
    saturday={p['id']:p for p in places('real',date(2026,10,24))}
    thursday={p['id']:p for p in places('real',date(2026,10,22))}
    assert saturday['Q12592360']['hours']==[600,1260]
    assert thursday['Q12592360']['hours']==[600,1080]
    assert saturday['Q484880']['price']==[0,0]
    assert saturday['Q97205213']['reservation'] is False
    assert all(p.get('operations_source') and p.get('operations_checked_at') for p in saturday.values() if p['price'] is not None)

def test_verified_free_park_resolves_unknown_fees_and_reservation():
    park=get_place('Q484880','real')
    c=Conditions(mode='real',allow_estimates=True,visit_date=date(2026,10,24),count=2,
        origin=dict(name='도산공원',lat=park['lat'],lon=park['lon']))
    raw,error=evaluate([park],c,partial=True)
    assert not error
    audited=audit_plan(raw,c)
    assert not any(i['condition'] in ['people','transport','stay_minutes','reservation','budget','visit_date'] and i['state']=='unknown' for i in audited['condition_checks'])
    assert audited['confirmed_facts']

def test_curated_closed_day_is_not_recommended_for_meals():
    c=Conditions(mode='real',allow_estimates=True,visit_date=date(2026,10,25))
    groups=meal_suggestions(recommend(c)['plans'][0])
    assert all(r['id']!='food:gwanghwamun-gukbap' for g in groups for r in g['restaurants'])

def nearby_plan():
    a=dict(id='x',name='서울시청',lat=37.5665,lon=126.978,address='서울 중구 세종대로 110',region='서울')
    b=dict(a,id='y',name='광화문',lat=37.57)
    c=Conditions(mode='real',allow_estimates=True,visit_date=date(2026,10,24),origin=dict(name='서울시청',lat=37.5665,lon=126.978))
    return dict(places=[a,b],conditions=c.model_dump(mode='json'))


def test_nearby_search_without_the_public_data_key_points_to_the_map(monkeypatch):
    # 네이버 검색 키가 있어도 주변 식당은 네이버 지역 검색을 부르지 않는다(2026-11-20 2단계). 공공데이터포털 키가 없으면 지도 링크만 안내한다.
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID','test');monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET','secret')
    monkeypatch.setattr(httpx,'get',lambda url,**kwargs:(_ for _ in ()).throw(AssertionError('외부 호출')))
    result=search_nearby(nearby_plan(),0)
    assert result['status']=='key_missing' and result['restaurants']==[] and '네이버 지도' in result['message']
    assert result['search_url'].startswith('https://map.naver.com/p/search/') and 'secret' not in str(result)


def test_nearby_search_uses_public_food_rows_in_the_same_region(monkeypatch):
    from public_fakes import fake_public_api,store_item
    monkeypatch.setattr('app.restaurants.restaurants',lambda:[])
    api=fake_public_api(monkeypatch)
    api['stores']+=[store_item('R1','밥집',37.5665,126.9785,code='I20101',address='서울특별시 중구 세종대로 1'),
                    store_item('R2','카페',37.5665,126.9786,code='I21201',label='카페',address='서울특별시 중구 세종대로 2'),
                    store_item('R3','외부',37.5666,126.9785,code='I20101',address='경기도 성남시 분당구 1')]
    result=search_nearby(nearby_plan(),0)
    assert len(result['restaurants'])==1
    restaurant=result['restaurants'][0]
    assert restaurant['name']=='밥집' and restaurant['lat']==37.5665 and restaurant['id']=='public:store-R1'
    assert restaurant['recognition']=='소상공인 상가정보에 등록된 음식점' and not api['naver']
    assert get_place(restaurant['id'],'real')['name']=='밥집'
