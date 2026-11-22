"""저녁 축제(코스 끝)의 돌아오는 구간(festival_visit.leg): 수단 바꾸기와 지도 구간 목록.
돌아오는 구간은 plan['legs'] 밖에 있어 구간 번호 대신 요청의 festival 항목과 수단 예외 키 (마지막 장소 id, 'festival')로 다룬다."""
from fastapi.testclient import TestClient

from app import store
from app.condition_audit import audit_plan
from app.main import app
from app.planner import evaluate
from test_festival_fixed_time import HOME, evening, rows
from test_functional_audit import audit_page  # noqa: F401  (브라우저 고정 장치)
from test_leg_modes import directions_api  # noqa: F401  (네이버 길찾기 가짜 응답 고정 장치)


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


def test_course_screen_changes_the_festival_leg(audit_page):  # noqa: F811
    page, base, errors = audit_page
    with TestClient(app) as client:
        plan = saved(client, return_home=True, home=HOME)
        owner = client.cookies['dm_session']
    page.route('**/api/festivals?*', lambda route: route.fulfill(json=dict(status='available', festivals=[], message='')))
    page.context.add_cookies([{'name': 'dm_session', 'value': owner, 'url': base}])
    page.goto(base + '/?plan=' + plan['id'])
    page.wait_for_function('(id)=>selected?.id===id', arg=plan['id'])
    block = page.locator('#plan-detail .festival-visit')
    toggle = block.locator('[data-transport-toggle="festival"]')
    assert toggle.count() == 1 and toggle.get_attribute('aria-expanded') == 'false'
    toggle.click()
    block.locator('.transport-chooser button[data-mode="transit"]').click()
    page.wait_for_function("selected?.festival_visit?.leg?.mode==='transit'")
    # 새 코스(바꾼 버전)를 다시 그린 뒤에도 축제 구간 줄이 대중교통이고, 단추에 포커스가 돌아온다.
    assert '대중교통' in page.locator('#plan-detail .festival-visit-leg').inner_text()
    page.wait_for_function("document.activeElement?.dataset?.transportToggle==='festival'")
    assert not errors


# --- 최종 검토에서 고친 것 ---
def test_change_that_loses_the_festival_is_refused():
    """빠른 수단으로 바꿔 개막까지 60분 넘게 기다리게 되면 축제가 일정에서 빠진다. 예전에는 저장돼 화면에 옛 축제 시각이 남았다(검토 지적)."""
    with TestClient(app) as client:
        plan = saved(client, start='15:12', return_home=True, home=HOME)
        assert plan['festival_visit']['wait'] >= 55
        response = change(client, plan, festival='car')
        assert response.status_code == 409, response.text
        assert '축제' in response.json()['detail']


def test_seven_leg_mode_pairs_are_allowed():
    """장소 5곳 + 귀가 + 축제 돌아오는 구간 = 구간 7개. 예외가 7개여도 조건이 받아야 한다."""
    from app.models import Conditions
    data = evening().model_dump(mode='json')
    data['leg_modes'] = [dict(zip(('from', 'to'), pair), mode='transit') for pair in
                         [('origin', 'a'), ('a', 'b'), ('b', 'c'), ('c', 'd'), ('d', 'e'), ('e', 'home'), ('e', 'festival')]]
    assert len(Conditions.model_validate(data).leg_modes) == 7


def test_replacing_a_middle_place_keeps_the_festival_override():
    import copy
    from app.catalog import places
    from app.models import Conditions
    from app.plan_changes import save_change
    with TestClient(app) as client:
        original = change(client, saved(client), festival='transit').json()
        other = copy.deepcopy(places('demo')[2])
        other.update(demo=False, hours=[0, 1440], closed_days=[], last_entry=None, breaks=None, price=[1000, 1000], price_unit='person', stay=30)
        moved, error = evaluate([other, original['places'][1]], Conditions.model_validate(original['conditions']))
        assert not error and moved['festival_visit']['leg']['mode'] == 'transit'
        stored = save_change(moved, original, store.owner_of(client.cookies['dm_session']))
        assert {'from': original['places'][1]['id'], 'to': 'festival', 'mode': 'transit'} in stored['conditions']['leg_modes']


def test_festival_leg_over_max_leg_warns():
    """돌아오는 구간도 다른 구간처럼 요청한 구간 이동 시간을 넘으면 경고한다(74차에서 남긴 것)."""
    with TestClient(app) as client:
        client.get('/api/places?mode=demo')
        plan, error = evaluate(rows(), evening())
        assert not error and [leg['minutes'] for leg in plan['legs']] == [9, 3]
        plan['conditions']['max_leg'] = 9
        stored = store.save_plan(audit_plan(plan), store.owner_of(client.cookies['dm_session']))
        response = change(client, stored, festival='transit')
        assert response.status_code == 200, response.text
        data = response.json()
        leg = data['festival_visit']['leg']
        assert leg['mode'] == 'transit' and leg['minutes'] > 9
        last = stored['places'][-1]['name']
        assert f"{last} → 점검 빛축제 행사장 이동이 {leg['minutes']}분으로 요청한 9분보다 길어요. 그대로 저장했어요." in data['transport_change']['warnings']


def test_festival_leg_route_failure_warns(directions_api):  # noqa: F811
    """돌아오는 구간을 자동차로 바꿨는데 길찾기 조회가 실패하면 다른 구간처럼 추정 시간이라고 알린다(74차에서 남긴 것)."""
    calls, state = directions_api
    state['fail'] = True
    with TestClient(app) as client:
        plan = saved(client)
        response = change(client, plan, festival='car')
        assert response.status_code == 200, response.text
        data = response.json()
        leg = data['festival_visit']['leg']
        assert calls and leg['mode'] == 'car' and leg['route_fallback'] and '자동차 길찾기 조회 실패' in leg['source']
        last = plan['places'][-1]['name']
        assert f"자동차 길찾기 조회에 실패해 이 구간은 추정 시간이에요. ({last} → 점검 빛축제 행사장)" in data['transport_change']['warnings']
        assert data['route_verification'] == '자동차 길찾기 조회에 실패한 구간은 추정 시간이에요.'


def test_festival_leg_without_failure_has_no_fallback_key():
    """조회 실패가 없으면 저장되는 돌아오는 구간 모양은 예전과 같다(route_fallback 키 없음)."""
    with TestClient(app) as client:
        plan = saved(client)
        assert 'route_fallback' not in plan['festival_visit']['leg']


def test_bulk_chooser_counts_the_festival_leg(audit_page):  # noqa: F811
    """'이동 수단 한 번에 바꾸기'의 지금 수단 표시가 돌아오는 구간도 센다(74차에서 남긴 것)."""
    page, base, errors = audit_page
    with TestClient(app) as client:
        plan = change(client, saved(client), festival='transit').json()
        owner = client.cookies['dm_session']
    page.route('**/api/festivals?*', lambda route: route.fulfill(json=dict(status='available', festivals=[], message='')))
    page.context.add_cookies([{'name': 'dm_session', 'value': owner, 'url': base}])
    page.goto(base + '/?plan=' + plan['id'])
    page.wait_for_function('(id)=>selected?.id===id', arg=plan['id'])
    bulk = page.locator('#plan-detail .transport-bulk')
    bulk.locator('summary').click()
    # 장소 도착 2구간은 도보, 돌아오는 구간은 대중교통 — 섞인 경우의 기존 표시를 따른다.
    assert '지금은 도보 2구간·대중교통 1구간이에요.' in bulk.locator('.hint').first.inner_text()
    assert bulk.locator('button[aria-pressed="true"]').count() == 0
    assert not errors


def test_car_notes_follow_the_festival_leg():
    from app.leg_modes import car_position_notes
    with TestClient(app) as client:
        plan = change(client, saved(client, return_home=True, home=HOME), festival='car').json()
        notes = car_position_notes(plan)
        # 차는 출발지(= 행사장)에 있는데 마지막 장소에서 행사장까지 자동차로 가고, 귀가는 도보라 차를 행사장에 두고 간다.
        assert any('자동차로 가려면' in n for n in notes)
        assert any('귀가를 도보로 하면' in n and '행사장' in n for n in notes)
