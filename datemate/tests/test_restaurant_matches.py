"""코스 장소 주변 식당(app/restaurants.restaurant_matches): 우리 식당 자료와 공공 자료에서, 가까운 구간부터 3곳까지.

네이버 지역 검색은 쓰지 않는다(2026-11-20 2단계). 그래서 리뷰순과 구 단위 '유명 맛집' 목록(popular)은 없다. 외부 호출은 가짜 응답이다."""
from app.models import Conditions
from app.restaurants import restaurant_matches, search_nearby

from public_fakes import fake_public_api, store_item, tour_item


def sample():
    a=dict(id='near-stop',name='광화문',lat=37.575,lon=126.977,address='서울 종로구 세종로',region='서울')
    b=dict(a,id='last-stop',name='마지막 코스',lat=37.576)
    return dict(places=[a,b],conditions=Conditions(mode='real',allow_estimates=True,visit_date='2026-10-24').model_dump(mode='json'))


def test_last_stop_and_progressive_radius_without_a_popularity_list(monkeypatch):
    monkeypatch.setattr('app.restaurants.restaurants',lambda:[])
    api=fake_public_api(monkeypatch)
    api['tour'].append(tour_item(1,'가까운 식당',37.576,126.977,address='서울특별시 종로구 세종로 1'))
    api['stores']+=[store_item('F1','조금 먼 식당',37.583,126.977,code='I20101',address='서울특별시 종로구 세종로 2'),
                    store_item('F2','경기 식당',37.5762,126.977,code='I20101',address='경기도 고양시 덕양구 1'),
                    store_item('F3','가까운 카페',37.5761,126.977,code='I21201',label='카페',address='서울특별시 종로구 세종로 3')]
    plan=sample()
    last=search_nearby(plan,1)
    assert [r['name'] for r in last['restaurants']]==['가까운 식당','조금 먼 식당']
    result=restaurant_matches(plan)
    assert len(result['groups'])==len(plan['places']) and 'popular' not in result
    assert all(r['distance_m']<=1500 for g in result['groups'] for r in g['restaurants'])
    assert all(g['restaurants'][0]['name']=='가까운 식당' for g in result['groups'])
    assert any(r['search_radius_m']==1000 for g in result['groups'] for r in g['restaurants'])
    assert all(g['searched_radii_m']==[500,1000] and g['effective_radius_m']==1000 for g in result['groups'])
    assert all('별점 순위가 아니에요' in g['ranking_basis'] for g in result['groups'])
    assert len(plan['places'])==2 and not api['naver']


def test_no_results_outside_1500m_are_invented(monkeypatch):
    monkeypatch.setattr('app.restaurants.restaurants',lambda:[])
    api=fake_public_api(monkeypatch)
    api['stores'].append(store_item('F1','먼 동네 식당',37.6145,126.95,code='I20101',address='서울특별시 은평구 통일로 1'))
    plan=sample();plan['places']=[dict(plan['places'][0],id='far-stop',name='범위 테스트',lat=37.6,lon=126.95)]
    group=restaurant_matches(plan)['groups'][0]
    assert not group['restaurants'] and group['status']=='not_found' and '네이버 지도' in group['message']


def test_curated_matches_come_first_and_public_rows_fill_up_to_three(monkeypatch):
    from app import restaurants as module
    plan=sample();plan['places']=[dict(plan['places'][0],address='')]
    base=plan['places'][0]
    def food(n,delta,radius=None):
        row=dict(id='food:'+str(n),name='식당'+str(n),lat=base['lat']+delta,lon=base['lon'],address='서울 종로구 테스트 '+str(n),distance_m=round(delta*111200))
        return dict(row,search_radius_m=radius) if radius else row
    monkeypatch.setattr(module,'meal_suggestions',lambda p:[dict(after_index=0,restaurants=[food(0,.001)],search_url='')])
    monkeypatch.setattr(module,'public_food',lambda p,indices:('available',{0:[food(0,.001,500),food(1,.008,1000),food(2,.012,1500),food(3,.013,1500)]}))
    group=module.restaurant_matches(plan)['groups'][0]
    # 우리 식당 자료가 먼저, 같은 식당은 한 번만, 모두 3곳까지.
    assert [r['id'] for r in group['restaurants']]==['food:0','food:1','food:2']
    assert [r['search_radius_m'] for r in group['restaurants']]==[500,1000,1500]
    assert group['searched_radii_m']==[500,1000,1500] and group['status']=='available'
    assert all(r['distance_m']>0 for r in group['restaurants'])


def test_curated_three_need_no_public_rows(monkeypatch):
    from app import restaurants as module
    plan=sample();plan['places']=[dict(plan['places'][0],address='')]
    base=plan['places'][0]
    curated=[dict(id='food:'+str(n),name='식당'+str(n),lat=base['lat']+.001*n,lon=base['lon'],address='서울 종로구 '+str(n),distance_m=111*n) for n in range(3)]
    monkeypatch.setattr(module,'meal_suggestions',lambda p:[dict(after_index=0,restaurants=curated)])
    monkeypatch.setattr(module,'public_food',lambda p,indices:('available',{0:[dict(id='public:x',name='공공 식당',lat=base['lat'],lon=base['lon']+.001,search_radius_m=500)]}))
    group=module.restaurant_matches(plan)['groups'][0]
    assert [r['id'] for r in group['restaurants']]==['food:0','food:1','food:2'] and group['searched_radii_m']==[500]
