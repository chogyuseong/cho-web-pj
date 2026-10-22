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

def test_live_search_permission_problem_is_actionable_without_secret(monkeypatch):
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID','test');monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET','secret')
    monkeypatch.setattr(httpx,'get',lambda url,**kwargs:httpx.Response(401,request=httpx.Request('GET',url)))
    p={'places':[{'id':'a','name':'서울시청'},{'id':'b','name':'광화문'}]}
    result=search_nearby(p,0)
    assert result['status']=='permission_required' and '지역 API' in result['message']
    assert 'secret' not in str(result)

def test_live_search_wgs84_coordinates_and_food_filter(monkeypatch):
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID','test');monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET','secret')
    def get(url,**kwargs):
        return httpx.Response(200,request=httpx.Request('GET',url),json={'items':[
            dict(title='<b>밥집</b>',category='음식점>한식',roadAddress='서울 중구 세종대로',mapx='1269780000',mapy='375665000'),
            dict(title='카페',category='카페,디저트',roadAddress='서울 중구 세종대로',mapx='1269780000',mapy='375665000'),
            dict(title='외부',category='음식점>한식',roadAddress='경기도 성남시',mapx='1271000000',mapy='374000000')
        ]})
    monkeypatch.setattr(httpx,'get',get)
    p={'places':[dict(id='x',name='서울시청',lat=37.5665,lon=126.978),dict(id='y',name='광화문',lat=37.57,lon=126.978)]}
    result=search_nearby(p,0)
    assert len(result['restaurants'])==1
    restaurant=result['restaurants'][0]
    assert restaurant['name']=='밥집' and restaurant['lat']==37.5665
    assert get_place(restaurant['id'],'real')['name']=='밥집'
