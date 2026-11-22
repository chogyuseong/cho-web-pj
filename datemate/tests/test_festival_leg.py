"""저녁 축제(코스 끝)의 돌아오는 구간(festival_visit.leg): 수단 바꾸기와 지도 구간 목록.
돌아오는 구간은 plan['legs'] 밖에 있어 구간 번호 대신 요청의 festival 항목과 수단 예외 키 (마지막 장소 id, 'festival')로 다룬다."""
from fastapi.testclient import TestClient

from app import store
from app.condition_audit import audit_plan
from app.main import app
from app.planner import evaluate
from test_festival_fixed_time import HOME, evening, rows
from test_functional_audit import audit_page  # noqa: F401  (브라우저 고정 장치)


def saved(client, **extra):
    client.get('/api/places?mode=demo')
    plan, error = evaluate(rows(), evening(**extra))
    assert not error and plan['festival_visit']['position'] == 'last'
    return store.save_plan(audit_plan(plan), store.owner_of(client.cookies['dm_session']))


def change(client, plan, **body):
    return client.post(f"/api/plans/{plan['id']}/transport", json=body)


def test_change_festival_leg_mode():
    with TestClient(app) as client:
        plan = saved(client, return_home=True, home=HOME)
        assert plan['festival_visit']['leg']['mode'] == 'walk'
        response = change(client, plan, festival='transit')
        assert response.status_code == 200, response.text
        updated = response.json()
        assert updated['festival_visit']['leg']['mode'] == 'transit'
        last = plan['places'][-1]['id']
        assert {'from': last, 'to': 'festival', 'mode': 'transit'} in updated['conditions']['leg_modes']
        # 장소 도착 구간·귀가 구간은 그대로 도보.
        assert [leg['mode'] for leg in updated['legs']] == ['walk', 'walk', 'walk']
        assert updated['transport_change']['messages']


def test_other_leg_change_keeps_festival_override():
    with TestClient(app) as client:
        plan = change(client, saved(client), festival='transit').json()
        updated = change(client, plan, legs=[{'index': 0, 'mode': 'transit'}]).json()
        assert updated['festival_visit']['leg']['mode'] == 'transit'
        assert updated['legs'][0]['mode'] == 'transit'


def test_default_change_clears_it():
    with TestClient(app) as client:
        plan = change(client, saved(client), festival='transit').json()
        updated = change(client, plan, default='bicycle').json()
        assert updated['festival_visit']['leg']['mode'] == 'bicycle'
        assert updated['conditions']['leg_modes'] == []


def test_festival_without_evening_festival_is_422():
    from test_festival_fixed_time import conditions
    with TestClient(app) as client:
        client.get('/api/places?mode=demo')
        plan, error = evaluate(rows(), conditions('10:00~18:00'))
        assert not error and plan['festival_visit']['position'] == 'first'
        stored = store.save_plan(audit_plan(plan), store.owner_of(client.cookies['dm_session']))
        response = change(client, stored, festival='transit')
        assert response.status_code == 422 and '축제' in response.json()['detail']


def test_same_mode_is_no_change():
    with TestClient(app) as client:
        response = change(client, saved(client), festival='walk')
        assert response.status_code == 422 and response.json()['detail'] == '이미 그 이동 수단이에요.'
