"""구간별 이동 수단: 계산, 저장 모델, API 제한, 차 위치 안내. 외부 호출은 모두 가짜로 바꾼다."""
import copy
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from app import store
from app.catalog import places
from app.condition_audit import audit_plan
from app.main import app
from app.models import Conditions
from app.planner import evaluate

ORIGIN = dict(name='데모 출발점', lat=37.575, lon=126.985)
HOME = dict(name='우리 집', lat=37.575, lon=126.995)


def rows(mode='demo', count=3):
    """출발지에서 북쪽으로 약 1.1km씩 떨어진 장소들. 도보 17분, 자동차 3분, 대중교통 12분 구간이 된다."""
    picked = copy.deepcopy(places('demo')[:count])
    for i, p in enumerate(picked):
        p.update(hours=[0, 1440], closed_days=[], closed_dates=[], last_entry=None, breaks=None,
                 price=[1000, 1000], price_unit='person', stay=30, reservation=False,
                 lat=ORIGIN['lat'] + 0.01 * (i + 1), lon=ORIGIN['lon'])
        if mode == 'real':
            p['demo'] = False
    return picked


def conditions(mode='demo', **fields):
    base = dict(mode=mode, visit_date=date(2026, 10, 24), count=3, budget=500000, max_leg=180, end='23:00', origin=ORIGIN)
    if mode == 'real':
        base['allow_estimates'] = True
    base.update(fields)
    return Conditions(**base)


def owned(client, mode='demo', places_rows=None, **fields):
    client.get('/api/status')
    c = conditions(mode, **fields)
    plan, error = evaluate(places_rows or rows(mode, c.count), c)
    assert not error, error
    plan = audit_plan(plan, c)
    return store.save_plan(plan, store.owner_of(client.cookies['dm_session']))


def change(client, plan, **body):
    return client.post(f"/api/plans/{plan['id']}/transport", json=body)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def without_mode(legs):
    return [{k: v for k, v in leg.items() if k != 'mode'} for leg in legs]


def test_one_leg_to_car_changes_only_that_leg_and_timeline(client):
    plan = owned(client)
    response = change(client, plan, legs=[dict(index=1, mode='car')])
    assert response.status_code == 200, response.text
    saved = response.json()
    assert [leg['mode'] for leg in saved['legs']] == ['walk', 'car', 'walk']
    assert saved['legs'][1]['minutes'] < plan['legs'][1]['minutes']
    assert saved['legs'][0]['minutes'] == plan['legs'][0]['minutes'] and saved['legs'][2]['minutes'] == plan['legs'][2]['minutes']
    assert saved['timeline'][1]['arrival'] < plan['timeline'][1]['arrival'] and saved['finish'] < plan['finish']
    assert saved['conditions']['transport'] == 'walk'
    assert saved['conditions']['leg_modes'] == [{'from': plan['places'][0]['id'], 'to': plan['places'][1]['id'], 'mode': 'car'}]
    assert saved['parent'] == plan['id'] and saved['delta']['minutes'] < 0
    shift = saved['transport_change']['arrivals'][1]['shift']
    assert saved['transport_change']['messages'] == [
        f"이 구간을 자동차로 바꿨어요. 이후 도착이 {-shift}분 당겨지고 종료는 {plan['finish']} → {saved['finish']}이에요."]
    # 주차비는 자동차로 도착한 장소에만, 통행료는 자동차 구간이 있을 때만 미확인으로 남긴다.
    assert saved['unknown'].count(plan['places'][1]['name'] + ' 주차비') == 1
    assert not any(plan['places'][i]['name'] + ' 주차비' in saved['unknown'] for i in (0, 2))
    assert '통행료' in saved['unknown'] and '통행료' not in plan['unknown']
    summary = saved['decision_summary']['travel_mode']
    assert summary['name'] == '도보·자동차' and summary['count_label'] == '도보 2구간·자동차 1구간'
    # 저장한 코스를 다시 열어도 같은 값이다.
    reopened = client.get('/api/plans/' + saved['id']).json()
    assert [leg['mode'] for leg in reopened['legs']] == ['walk', 'car', 'walk'] and reopened['finish'] == saved['finish']
    assert 'transport_change' not in reopened


def test_bulk_change_clears_exceptions_and_default_mode_removes_one(client):
    plan = owned(client)
    first = change(client, plan, legs=[dict(index=0, mode='car'), dict(index=2, mode='bicycle')]).json()
    assert [m['mode'] for m in first['conditions']['leg_modes']] == ['car', 'bicycle']
    back = change(client, first, legs=[dict(index=0, mode='walk')]).json()
    assert back['conditions']['leg_modes'] == [{'from': plan['places'][1]['id'], 'to': plan['places'][2]['id'], 'mode': 'bicycle'}]
    assert [leg['mode'] for leg in back['legs']] == ['walk', 'walk', 'bicycle']
    bulk = change(client, back, default='transit').json()
    assert bulk['conditions']['transport'] == 'transit' and bulk['conditions']['leg_modes'] == []
    assert {leg['mode'] for leg in bulk['legs']} == {'transit'}
    assert bulk['transport_change']['messages'][0].startswith('모든 구간을 대중교통으로 바꿨어요. 따로 고른 구간 설정은 지웠어요.')
    same = change(client, bulk, default='transit')
    assert same.status_code == 422 and '이미' in same.json()['detail']
    assert change(client, bulk).status_code == 422
    assert change(client, bulk, legs=[dict(index=3, mode='car')]).status_code == 422
    assert change(client, bulk, legs=[dict(index=0, mode='car'), dict(index=0, mode='walk')]).status_code == 422
    assert change(client, bulk, legs=[dict(index=0, mode='plane')]).status_code == 422
    assert change(client, bulk, legs=[dict(index=0, mode='car', extra=1)]).status_code == 422
    assert change(client, bulk, legs=[dict(index=i % 3, mode='car') for i in range(7)]).status_code == 422


def test_replacing_a_place_drops_its_neighbouring_exceptions(client):
    plan = owned(client)
    changed = change(client, plan, legs=[dict(index=i, mode='car') for i in range(3)]).json()
    assert len(changed['conditions']['leg_modes']) == 3
    options = client.post(f"/api/plans/{changed['id']}/alternatives", json={'index': 1}).json()['alternatives']
    assert options
    # 대안 계산에서도 끊긴 구간은 기본 수단이다.
    assert [leg['mode'] for leg in options[0]['legs']] == ['car', 'walk', 'walk']
    replaced = client.post(f"/api/plans/{changed['id']}/replace",
                           json={'index': 1, 'replacement_id': options[0]['places'][1]['id']}).json()
    assert [leg['mode'] for leg in replaced['legs']] == ['car', 'walk', 'walk']
    assert replaced['conditions']['leg_modes'] == [{'from': 'origin', 'to': plan['places'][0]['id'], 'mode': 'car'}]
    assert client.post(f"/api/plans/{replaced['id']}/undo", json={}).json()['id'] == changed['id']


def test_legacy_plan_without_leg_modes_opens_and_keeps_values(client):
    plan = owned(client)
    legacy = copy.deepcopy(plan)
    legacy.pop('id')
    legacy['conditions'].pop('leg_modes')
    for leg in legacy['legs']:
        leg.pop('mode')
    saved = store.save_plan(legacy, store.owner_of(client.cookies['dm_session']))
    opened = client.get('/api/plans/' + saved['id'])
    assert opened.status_code == 200
    data = opened.json()
    assert data['timeline'] == plan['timeline'] and data['finish'] == plan['finish']
    assert data['decision_summary']['travel_mode']['label'] == '도보 · 가상 직선거리 추정'
    again, error = evaluate(data['places'], Conditions.model_validate(data['conditions']))
    assert not error and again['timeline'] == plan['timeline'] and without_mode(again['legs']) == without_mode(plan['legs'])
    # 예전 코스도 구간 수단을 바꿀 수 있다(구간 수단이 없으면 기본 수단으로 읽는다).
    moved = change(client, saved, legs=[dict(index=1, mode='car')]).json()
    assert [leg['mode'] for leg in moved['legs']] == ['walk', 'car', 'walk']


def test_without_exceptions_results_are_unchanged():
    c = conditions()
    plain, _ = evaluate(rows(), c)
    unrelated = c.model_copy(update={'leg_modes': Conditions(
        visit_date=date(2026, 10, 24), leg_modes=[{'from': 'origin', 'to': 'not-in-course', 'mode': 'car'}]).leg_modes})
    other, _ = evaluate(rows(), unrelated)
    plain.pop('conditions'), other.pop('conditions')
    assert plain == other
    assert all(leg['mode'] == 'walk' for leg in plain['legs'])
    # 추천 API로는 구간 수단 예외를 넣을 수 없다.
    with TestClient(app) as client:
        injected = [{'from': 'origin', 'to': 'demo-01', 'mode': 'car'}]
        result = client.post('/api/plans', json={'visit_date': '2026-10-24', 'leg_modes': injected}).json()
        assert result['plans'] and all(p['conditions']['leg_modes'] == [] for p in result['plans'])
        assert all(leg['mode'] == 'walk' for p in result['plans'] for leg in p['legs'])


def test_plan_jobs_ignore_injected_leg_modes(monkeypatch):
    from app import plan_jobs
    seen = []
    monkeypatch.setattr(plan_jobs._pool, 'submit', lambda run, fn, key, data, owner: seen.append(data))
    with TestClient(app) as client:
        response = client.post('/api/plan-jobs', json={'visit_date': '2026-10-24',
                                                       'leg_modes': [{'from': 'origin', 'to': 'x', 'mode': 'car'}]})
        assert response.status_code == 202
        plan_jobs._jobs.pop(response.json()['id'], None)
    assert seen and seen[0].leg_modes == []


def test_return_home_leg_can_change(client):
    plan = owned(client, return_home=True, home=HOME)
    assert len(plan['legs']) == 4
    saved = change(client, plan, legs=[dict(index=3, mode='car')]).json()
    assert [leg['mode'] for leg in saved['legs']] == ['walk', 'walk', 'walk', 'car']
    assert saved['conditions']['leg_modes'] == [{'from': plan['places'][2]['id'], 'to': 'home', 'mode': 'car'}]
    assert saved['minutes'] < plan['minutes']
    # 자동차로 귀가하면 차가 집 앞에 있다고 보지 않는다(출발지에서 출발했어야 함): 차 위치 안내가 나온다.
    notes = [c['message'] for c in saved['condition_checks'] if c['condition'] == 'car_position']
    assert len(notes) == 1 and '우리 집' in notes[0] and notes[0].startswith('차는 데모 출발점 근처에 있어요.')


def test_car_position_notes_only_for_mismatched_car_use_and_never_block(client):
    from app.leg_modes import car_position_notes
    plan = owned(client, return_home=True, home=HOME, hard_constraints=['end', 'max_leg'])
    def with_modes(modes):
        p = copy.deepcopy(plan)
        for leg, mode in zip(p['legs'], modes):
            leg['mode'] = mode
        return p
    assert car_position_notes(with_modes(['car', 'car', 'car', 'car'])) == []
    assert car_position_notes(with_modes(['walk', 'walk', 'walk', 'walk'])) == []
    assert car_position_notes(with_modes(['car', 'car', 'walk', 'walk'])) == [
        f"차는 {plan['places'][1]['name']} 근처에 있어요. 귀가를 도보로 하면 차를 그곳에 두고 가게 돼요. 차를 가지러 가는 시간은 계산에 없어요."]
    notes = car_position_notes(with_modes(['car', 'walk', 'car', 'car']))
    assert len(notes) == 1 and notes[0].startswith(f"차는 {plan['places'][0]['name']} 근처에 있어요. {plan['places'][1]['name']} → {plan['places'][2]['name']}")
    # 감사 항목은 unknown이지만 필수 조건 검사에는 걸리지 않는다.
    saved = change(client, plan, legs=[dict(index=1, mode='car')])
    assert saved.status_code == 200, saved.text
    checks = [c for c in saved.json()['condition_checks'] if c['condition'] == 'car_position']
    assert checks and all(c['state'] == 'unknown' for c in checks)


def test_last_entry_and_required_end_block_but_plain_end_overrun_warns(client):
    late = rows()
    plan = owned(client, places_rows=late, transport='car')
    # 2번 장소 마지막 입장을 자동차 도착 시각으로 두면, 그 구간을 걸어서 가면 늦는다.
    late[1]['last_entry'] = int(plan['timeline'][1]['arrival'][:2]) * 60 + int(plan['timeline'][1]['arrival'][3:])
    plan = owned(client, places_rows=late, transport='car')
    blocked = change(client, plan, legs=[dict(index=1, mode='walk')])
    assert blocked.status_code == 409
    assert blocked.json()['detail'] == f"이 수단으로는 {late[1]['name']} 마지막 입장({plan['timeline'][1]['arrival']}) 전에 도착하지 못해 바꾸지 않았어요."
    assert client.get('/api/plans/' + plan['id']).json()['legs'][1]['mode'] == 'car'
    # 종료 시각: 일반 조건이면 경고와 함께 저장, 필수 조건이면 409.
    tight = owned(client, transport='car', end=plan['finish'])
    warned = change(client, tight, default='walk')
    assert warned.status_code == 200
    late_minutes = warned.json()['minutes'] - tight['minutes']
    assert late_minutes > 0
    assert warned.json()['transport_change']['warnings'][0] == f"종료가 요청한 {plan['finish']}보다 {late_minutes}분 늦어져요. 그대로 저장했어요."
    assert any(c['condition'] == 'end' and c['state'] == 'unmet' for c in warned.json()['condition_checks'])
    required = owned(client, transport='car', end=plan['finish'], hard_constraints=['end'])
    refused = change(client, required, default='walk')
    assert refused.status_code == 409 and '종료 시간' in refused.json()['detail']


def directions(start, goal):
    (slon, slat), (glon, glat) = [map(float, x.split(',')) for x in (start, goal)]
    return {'currentDateTime': '2026-10-24T10:00:00', 'route': {'traoptimal': [{
        'summary': {'duration': 420000, 'distance': 1500, 'fuelPrice': 300, 'tollFare': 0},
        'path': [[slon, slat], [glon, glat]]}]}}


@pytest.fixture
def directions_api(monkeypatch):
    calls = []
    state = {'fail': False}

    def get(self, url, params=None, headers=None, **kwargs):
        calls.append((params['start'], params['goal']))
        request = httpx.Request('GET', url)
        if state['fail']:
            return httpx.Response(400, json={'error': 'denied'}, request=request)
        return httpx.Response(200, json=directions(params['start'], params['goal']), request=request)

    monkeypatch.setenv('NAVER_MAPS_KEY_ID', 'test-id')
    monkeypatch.setenv('NAVER_MAPS_KEY', 'test-key')
    monkeypatch.setattr(httpx.Client, 'get', get)
    with store.connect() as db:
        db.execute("DELETE FROM cache WHERE key LIKE 'route-v2:%'")
    clear_rate_limit()
    return calls, state


def clear_rate_limit():
    with store.connect() as db:
        db.execute("DELETE FROM cache WHERE key LIKE '%-refresh:%'")


def coordinates(point):
    return f"{point['lon']},{point['lat']}"


def test_directions_called_only_for_car_legs_and_failure_falls_back(client, directions_api):
    calls, state = directions_api
    plan = owned(client, 'real')
    points = [ORIGIN, *plan['places']]
    pair = lambda i: (coordinates(points[i]), coordinates(points[i + 1]))
    state['fail'] = True
    failed = change(client, plan, legs=[dict(index=1, mode='car')])
    assert failed.status_code == 200, failed.text
    data = failed.json()
    assert calls == [pair(1)]
    assert data['legs'][1]['mode'] == 'car' and data['legs'][1]['status'] == 'estimated' and data['legs'][1]['route_fallback']
    assert '자동차 길찾기 조회 실패' in data['legs'][1]['source']
    assert any('자동차 길찾기 조회에 실패해 이 구간은 추정 시간이에요.' in w for w in data['transport_change']['warnings'])
    # 바로 다시 요청하면 재요청 제한(자동차 구간이 있는 실제 장소 코스).
    assert change(client, data, legs=[dict(index=2, mode='car')]).status_code == 429
    clear_rate_limit()
    state['fail'] = False
    calls.clear()
    ok = change(client, data, legs=[dict(index=2, mode='car')]).json()
    assert sorted(calls) == sorted([pair(1), pair(2)]) and len(calls) <= 2
    assert [leg['status'] for leg in ok['legs']] == ['estimated', 'api', 'api']
    assert [leg['mode'] for leg in ok['legs']] == ['walk', 'car', 'car']
    assert ok['transport_change']['warnings'] == []
    # 캐시된 구간은 다시 부르지 않는다.
    clear_rate_limit()
    calls.clear()
    third = change(client, ok, legs=[dict(index=0, mode='car')]).json()
    assert calls == [pair(0)] and [leg['status'] for leg in third['legs']] == ['api', 'api', 'api']
    # 공유 응답에는 구간 상세가 없다.
    url = client.post(f"/api/plans/{third['id']}/shares", json={}).json()['url']
    shared = client.get('/api/shared-plan', headers={'Authorization': 'Bearer ' + url.split('#', 1)[1]}).json()
    assert 'legs' not in shared and 'leg_modes' not in str(shared) and set(shared['places'][0]) == {
        'id', 'name', 'category', 'address', 'arrival', 'departure'}


def test_route_calls_stop_at_the_change_budget(client, directions_api, monkeypatch):
    calls, _ = directions_api
    monkeypatch.setattr('app.leg_modes.MAX_ROUTE_CALLS', 1)
    monkeypatch.setattr('app.collection.time.sleep', lambda seconds: None)
    plan = owned(client, 'real', return_home=True, home=HOME)
    saved = change(client, plan, default='car')
    assert saved.status_code == 200, saved.text
    assert len(calls) == 1
    legs = saved.json()['legs']
    assert sum(leg['status'] == 'api' for leg in legs) == 1 and sum(bool(leg.get('route_fallback')) for leg in legs) == 3


def test_other_owner_cannot_change_and_demo_changes_are_not_rate_limited(client):
    plan = owned(client)
    with TestClient(app) as other:
        assert change(other, plan, legs=[dict(index=0, mode='car')]).status_code == 404
    first = change(client, plan, legs=[dict(index=0, mode='car')])
    second = change(client, first.json(), legs=[dict(index=1, mode='car')])
    assert first.status_code == 200 and second.status_code == 200
    assert client.post(f"/api/plans/{second.json()['id']}/undo", json={}).json()['id'] == first.json()['id']


def test_real_car_replace_is_rate_limited(client, directions_api):
    plan = owned(client, 'real', transport='car')
    options = client.post(f"/api/plans/{plan['id']}/alternatives", json={'index': 1}).json()['alternatives']
    assert options
    body = {'index': 1, 'replacement_id': options[0]['places'][1]['id']}
    clear_rate_limit()
    assert client.post(f"/api/plans/{plan['id']}/replace", json=body).status_code == 200
    assert client.post(f"/api/plans/{plan['id']}/replace", json=body).status_code == 429


def test_expensive_route_list_covers_change_paths():
    from app.web_security import EXPENSIVE
    for path in ('POST /api/plans/abc/transport', 'POST /api/plans/abc/replace'):
        assert any(pattern.match(path) for pattern in EXPENSIVE)
