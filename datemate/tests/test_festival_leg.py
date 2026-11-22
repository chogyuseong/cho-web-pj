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


# --- 지도 구간 목록(static/maps.js planSegments) ---
PLAN = """(extra)=>Object.assign({
  conditions:{mode:'real',origin:{name:'O',lat:37.5,lon:127},return_home:true,home:{name:'H',lat:37.4,lon:127.1}},
  places:[{name:'A',lat:37.51,lon:127.01},{name:'B',lat:37.52,lon:127.02}],
  legs:[{tag:'l0'},{tag:'l1'},{tag:'l2'}]
},extra)"""


def segments(page, extra='{}'):
    return page.evaluate(f"()=>planSegments(({PLAN})({extra})).map(s=>[s.from.name,s.to.name,s.leg?.tag])")


def test_segments_for_plain_course_unchanged(audit_page):  # noqa: F811
    page, _, _ = audit_page
    assert segments(page) == [['O', 'A', 'l0'], ['A', 'B', 'l1'], ['B', 'H', 'l2']]
    assert segments(page, "{conditions:{origin:{name:'O'},return_home:false},legs:[{tag:'l0'},{tag:'l1'}]}") == [['O', 'A', 'l0'], ['A', 'B', 'l1']]


def test_segments_go_through_the_venue(audit_page):  # noqa: F811
    page, _, _ = audit_page
    got = segments(page, "{festival_visit:{position:'last',leg:{tag:'lf'}}}")
    assert got == [['O', 'A', 'l0'], ['A', 'B', 'l1'], ['B', 'O', 'lf'], ['O', 'H', 'l2']]


def test_segments_without_home(audit_page):  # noqa: F811
    page, _, _ = audit_page
    got = segments(page, "{conditions:{origin:{name:'O'},return_home:false},legs:[{tag:'l0'},{tag:'l1'}],festival_visit:{position:'last',leg:{tag:'lf'}}}")
    assert got == [['O', 'A', 'l0'], ['A', 'B', 'l1'], ['B', 'O', 'lf']]
