"""자동차로 도착하는 장소 근처 주차장: 대상 장소, 검색 건수, 거르는 규칙, 캐시, 상태, 한도. 지역 검색은 모두 가짜."""
import copy
import uuid
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from app import intent_discovery, parking, store, web_security
from app.catalog import places
from app.condition_audit import audit_plan
from app.main import app
from app.models import Conditions
from app.planner import evaluate

ORIGIN = dict(name='서울 종로구 출발', lat=37.575, lon=126.985)
LOT_FIELDS = {'id', 'name', 'category', 'address', 'lat', 'lon', 'distance_m', 'walk_minutes', 'public_by_name'}


def unique_ip():
    n = uuid.uuid4().int
    return f'198.51.{n % 250}.{(n >> 8) % 250 + 1}'


def rows(count=3):
    """출발지에서 북쪽으로 약 1.1km씩 떨어진 실제 모드 장소. 이름은 테스트마다 달라 캐시가 섞이지 않는다."""
    tag = uuid.uuid4().hex[:6]
    picked = copy.deepcopy(places('demo')[:count])
    for i, p in enumerate(picked):
        p.update(hours=[0, 1440], closed_days=[], closed_dates=[], last_entry=None, breaks=None,
                 price=[1000, 1000], price_unit='person', stay=30, reservation=False, demo=False,
                 name=f'테스트장소{i + 1}-{tag}', address=f'서울특별시 종로구 삼청동 {i + 10}', region='서울',
                 lat=ORIGIN['lat'] + 0.01 * (i + 1), lon=ORIGIN['lon'])
    return picked


def make_plan(mode='real', transport='walk', car_legs=(), places_rows=None, **fields):
    picked = places_rows or rows()
    ids = ['origin', *[p['id'] for p in picked], 'home']
    leg_modes = [{'from': ids[i], 'to': ids[i + 1], 'mode': 'car'} for i in car_legs]
    base = dict(mode=mode, visit_date=date(2026, 10, 24), count=len(picked), budget=500000, max_leg=180,
                end='23:00', origin=ORIGIN, transport=transport, leg_modes=leg_modes)
    if mode == 'real':
        base['allow_estimates'] = True
    base.update(fields)
    c = Conditions(**base)
    plan, error = evaluate(picked, c)
    assert not error, error
    return audit_plan(plan, c)


def item(title, lat, lon, category='교통,수송>주차장', address='서울특별시 종로구 삼청로 1'):
    return dict(title=title, category=category, roadAddress=address,
                mapx=str(round(lon * 10000000)), mapy=str(round(lat * 10000000)))


@pytest.fixture
def search(monkeypatch):
    """가짜 지역 검색. answer(term, area) -> (items, status) 를 바꿔 끼운다. 부른 검색어를 남긴다."""
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID', 'test')
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET', 'secret')
    store.cache('discovery-local-permission', False, 1)
    state = dict(calls=[], answer=lambda term, area: ([], 'available'))

    def lookup(term, area, sort='random'):
        state['calls'].append((term, area))
        return state['answer'](term, area)

    monkeypatch.setattr(intent_discovery, 'local_lookup', lookup)
    yield state
    store.cache('discovery-local-permission', False, 1)


def test_all_walking_course_is_not_car_and_searches_nothing(search):
    result = parking.parking_near(make_plan())
    assert result['status'] == 'not_car' and result['stops'] == [] and search['calls'] == []
    assert result['diagnostics']['lookups'] == 0


def test_only_places_reached_by_car_are_searched(search):
    plan = make_plan(car_legs=(0, 2))
    assert [leg['mode'] for leg in plan['legs']] == ['car', 'walk', 'car']
    result = parking.parking_near(plan)
    assert [s['index'] for s in result['stops']] == [0, 2]
    assert [s['place_id'] for s in result['stops']] == [plan['places'][0]['id'], plan['places'][2]['id']]
    names = {area for term, area in search['calls'] if term == '주차장'}
    assert names == {plan['places'][0]['name'], plan['places'][2]['name']}
    # 장소마다 2건: 장소명 주차장, 동네 공영주차장.
    assert sorted(search['calls']) == sorted([('주차장', plan['places'][0]['name']), ('공영주차장', '종로구 삼청동'),
                                              ('주차장', plan['places'][2]['name']), ('공영주차장', '종로구 삼청동')])
    assert result['diagnostics']['queries'] == 4 and result['diagnostics']['lookups'] == 4
    assert result['status'] == 'not_found'
    assert all(s['message'] == '이 장소 800m 안에서 주차장을 찾지 못했어요.' for s in result['stops'])


def test_return_home_by_car_is_not_a_parking_stop(search):
    plan = make_plan(car_legs=(3,), return_home=True, home=dict(name='우리 집', lat=37.575, lon=126.995))
    assert [leg['mode'] for leg in plan['legs']] == ['walk', 'walk', 'walk', 'car']
    result = parking.parking_near(plan)
    assert result['status'] == 'not_car' and search['calls'] == []


def test_five_car_stops_stay_within_ten_lookups(search):
    plan = make_plan(transport='car', places_rows=rows(5), count=5)
    result = parking.parking_near(plan)
    assert len(result['stops']) == 5 and len(search['calls']) == 10 and result['diagnostics']['queries'] == 10


def test_filters_dedupe_and_diagnostics(search):
    plan = make_plan(transport='car', places_rows=rows(2), count=2)
    a, b = plan['places']
    north = 0.0045  # 약 500m

    def answer(term, area):
        if term == '공영주차장':
            # 두 장소(약 1.1km 간격) 모두 800m 안에 드는 같은 공영주차장 → 더 가까운 a 아래에만.
            return [item('<b>삼청</b> 공영주차장', a['lat'] + 0.004, a['lon'], address='서울특별시 종로구 삼청로 9')], 'available'
        base = a if area == a['name'] else b
        road = '서울특별시 종로구 삼청로 ' + ('1' if base is a else '2')
        return [
            item('가까운 주차장', base['lat'] + 0.001, base['lon'], address=road),
            item('먼 주차장', base['lat'] + north, base['lon'], address=road),
            item('한식당', base['lat'], base['lon'], category='음식점>한식', address=road),
            item('발렛파킹 주차대행', base['lat'], base['lon'], address=road),
            item('다른 지역 주차장', base['lat'], base['lon'], address='경기도 성남시 분당구 1'),
            item('좌표 없는 주차장', 0, 0, address=road),
            item('가까운  주차장', base['lat'] + 0.001, base['lon'], address=road),
            item('900m 주차장', base['lat'] + 0.0081, base['lon'], address=road),
        ], 'available'

    search['answer'] = answer
    result = parking.parking_near(plan)
    assert result['status'] == 'available'
    first, second = result['stops']
    assert [lot['name'] for lot in first['lots']] == ['가까운 주차장', '삼청 공영주차장', '먼 주차장']
    assert [lot['name'] for lot in second['lots']] == ['가까운 주차장', '먼 주차장']
    public = first['lots'][1]
    assert public['public_by_name'] is True and first['lots'][0]['public_by_name'] is False
    near = first['lots'][0]
    assert 100 <= near['distance_m'] <= 120 and near['walk_minutes'] == 3
    assert set(near) == LOT_FIELDS
    diagnostics = result['diagnostics']
    assert diagnostics['received'] == 8 * 2 + 2
    # 장소마다: 업종 아님 2(음식점·발렛), 다른 지역 1, 좌표 1, 800m 초과 1, 같은 이름·주소 1. 장소를 넘는 중복 1.
    assert diagnostics['rejected'] == dict(not_parking=4, other_region=2, bad_coordinates=2, out_of_radius=2, duplicate=3)
    assert result['source_type'] == '네이버 지역 검색' and '포함하지 않았어요' in result['note']


def test_second_request_uses_the_cache(search):
    plan = make_plan(car_legs=(0,), places_rows=rows(2), count=2)
    place = plan['places'][0]
    search['answer'] = lambda term, area: ([item('캐시 주차장', place['lat'] + 0.001, place['lon'])], 'available')
    first = parking.parking_near(plan)
    calls = len(search['calls'])
    second = parking.parking_near(plan)
    assert calls == 2 and len(search['calls']) == 2
    assert second['diagnostics']['cache_hit'] is True and second['diagnostics']['lookups'] == 0
    assert second['stops'] == first['stops']


def test_failed_search_is_unavailable_and_cached_briefly(search):
    plan = make_plan(car_legs=(0,), places_rows=rows(2), count=2)
    search['answer'] = lambda term, area: ([], 'unavailable')
    result = parking.parking_near(plan)
    assert result['status'] == 'unavailable' and result['stops'][0]['status'] == 'unavailable'
    key = parking.cache_key(plan['places'][0], '서울')
    with store.connect() as db:
        expires = db.execute('SELECT expires FROM cache WHERE key=?', (key,)).fetchone()[0]
    import time
    assert expires - time.time() <= parking.CACHE_EMPTY_SECONDS + 1


def test_demo_and_missing_key_statuses(search, monkeypatch):
    assert parking.parking_near(make_plan(mode='demo', transport='car'))['status'] == 'demo'
    monkeypatch.delenv('NAVER_SEARCH_CLIENT_ID')
    missing = parking.parking_near(make_plan(transport='car'))
    assert missing['status'] == 'key_missing' and missing['message'] == '네이버 검색 키를 설정해 주세요.'
    assert search['calls'] == []


def test_permission_problem_from_the_provider(monkeypatch):
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID', 'test')
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET', 'secret')
    store.cache('discovery-local-permission', False, 1)
    monkeypatch.setattr('app.discovery.httpx.get', lambda url, **kwargs: httpx.Response(401, request=httpx.Request('GET', url)))
    try:
        result = parking.parking_near(make_plan(car_legs=(0,), places_rows=rows(2), count=2))
    finally:
        store.cache('discovery-local-permission', False, 1)
    assert result['status'] == 'permission_required' and '지역 API' in result['message']
    assert 'secret' not in str(result)


def test_route_is_expensive_rate_limited_and_leaves_the_plan_alone(search, monkeypatch):
    assert any(p.match('GET /api/plans/abc/parking') for p in web_security.EXPENSIVE)
    with TestClient(app, client=(unique_ip(), 1)) as client:
        client.get('/api/status')
        plan = store.save_plan(make_plan(transport='car'), store.owner_of(client.cookies['dm_session']))
        place = plan['places'][1]
        search['answer'] = lambda term, area: ([item('경로 주차장', place['lat'] + 0.001, place['lon'])], 'available')
        before = client.get('/api/plans/' + plan['id']).json()
        response = client.get(f"/api/plans/{plan['id']}/parking")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['status'] == 'available'
        assert set(body) == {'status', 'stops', 'note', 'source_type', 'message', 'diagnostics'}
        # 요금·운영시간·만차 정보는 확인하지 않으므로 응답에 그런 칸이 없다.
        lots = [lot for stop in body['stops'] for lot in stop['lots']]
        assert lots and all(set(lot) == LOT_FIELDS for lot in lots)
        # 같은 브라우저의 1초 안 연속 요청은 막는다.
        assert client.get(f"/api/plans/{plan['id']}/parking").status_code == 429
        after = client.get('/api/plans/' + plan['id']).json()
        assert after['total'] == before['total'] and after['places'] == before['places'] and after['legs'] == before['legs']
    # IP 한도는 기존 지역 검색 한도를 함께 쓴다.
    monkeypatch.setenv('DATEMATE_IP_LOCAL_SEARCHES_PER_MINUTE', '1')
    # 같은 IP 의 다른 브라우저(세션)도 함께 센다. 계획은 만든 브라우저만 열 수 있어 각자 하나씩 만든다.
    address = unique_ip()
    codes = []
    for _ in range(2):
        with TestClient(app, client=(address, 1)) as client:
            client.get('/api/status')
            plan = store.save_plan(make_plan(transport='car'), store.owner_of(client.cookies['dm_session']))
            response = client.get(f"/api/plans/{plan['id']}/parking")
            codes.append(response.status_code)
    assert codes == [200, 429] and response.json()['detail'] == '주차장 검색은 잠시 후 다시 시도해 주세요.'
