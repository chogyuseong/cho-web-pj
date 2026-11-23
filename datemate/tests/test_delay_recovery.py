"""지각 복구(app/delay_recovery.py): 늦어서 맞출 수 없게 된 장소를 같은 종류의 다른 곳으로 바꾸거나 빼고, 지연을 반영해 새 코스로 저장한다.
후보는 코스를 만들 때 쓰던 동네 후보에서만 찾는다 — 여기서는 candidate_pool 을 고정 목록으로 바꿔 본다."""
import copy
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import delay_recovery, store
from app.condition_audit import audit_plan
from app.delay_check import delay_check
from app.main import app
from app.models import Conditions
from app.planner import clock, evaluate, minutes
from test_leg_modes import directions_api  # noqa: F401  (네이버 길찾기 가짜 응답 고정 장치)

FRIDAY = date(2026, 11, 20)  # weekday 4
LAT, LON = 37.5446, 127.0557


def hm(text):
    h, m = map(int, text.split(':'))
    return h * 60 + m


def place(pid, name, category, hours, stay=60, dlat=0.0, dlon=0.0, **extra):
    row = dict(id='fixture:' + pid, name=name, category=category, lat=LAT + dlat, lon=LON + dlon, hours=hours, stay=stay,
               last_entry=None, breaks=None, closed_days=[], price=[0, 0], price_unit='person', source='https://example.org/' + pid,
               checked_at='2026-11-01', reservation=False, tags=[], setting='indoor', region='서울', address='서울 성동구')
    row.update(extra)
    return row


def conditions(**extra):
    base = dict(mode='real', region='서울', visit_date=FRIDAY, allow_estimates=True, count=3, budget=200000, max_leg=30,
                start='15:00', end='22:00', transport='walk', origin=dict(name='성수역', lat=LAT, lon=LON))
    base.update(extra)
    return Conditions(**base)


def stops(b_closes='17:30', c_hours=None, **b_extra):
    return [place('a', 'A 전시', '문화·예술', [hm('10:00'), hm('21:00')], 60, dlat=0.001),
            place('b', 'B 카페', '카페·미식', [hm('10:00'), hm(b_closes)], 50, dlat=0.002, **b_extra),
            place('c', 'C 산책', '산책·풍경', c_hours or [0, 1440], 45, dlat=0.003)]


def course(c=None, rows=None):
    plan, error = evaluate(rows or stops(), c or conditions())
    assert not error, error
    return audit_plan(plan)


NEAR = place('c1', '가까운 늦은 카페', '카페·미식', [hm('10:00'), hm('22:00')], 50, dlat=0.0022)
FARTHER = place('c2', '조금 먼 카페', '카페·미식', [hm('10:00'), hm('22:00')], 50, dlat=0.002, dlon=0.006)
UNKNOWN = place('c3', '영업시간 모르는 카페', '카페·미식', None, 50, dlat=0.002, dlon=0.0005, closed_days=None)
POOL = [
    NEAR, FARTHER, UNKNOWN,
    place('c4', '예약 카페', '카페·미식', [hm('10:00'), hm('22:00')], 50, dlat=0.0021, reservation=True),
    place('c5', '금요일 휴무 카페', '카페·미식', [hm('10:00'), hm('22:00')], 50, dlat=0.0021, closed_days=[4]),
    place('c6', '일찍 닫는 카페', '카페·미식', [hm('10:00'), hm('17:30')], 50, dlat=0.0021),
    place('c7', '먼 카페', '카페·미식', [hm('10:00'), hm('22:00')], 50, dlat=0.03),
    place('g1', '다른 종류 전시', '문화·예술', [hm('10:00'), hm('22:00')], 50, dlat=0.0021),
]  # fmt: skip


@pytest.fixture
def pool(monkeypatch):
    rows = list(POOL)
    monkeypatch.setattr(delay_recovery, 'candidate_pool', lambda plan, c: copy.deepcopy(rows))
    return rows


def saved(client, plan):
    client.get('/api/places?mode=demo')
    return store.save_plan(plan, store.owner_of(client.cookies['dm_session']))


def recover(client, plan, **body):
    data = dict(index=0, minutes=40, target=1)
    data.update(body)
    return client.post(f"/api/plans/{plan['id']}/delay-recovery", json=data)


# --- 후보 고르기 ---
def test_problem_is_the_cafe_that_closes(pool):
    plan = course()
    check = delay_check(plan, 0, 40)
    assert check['first_problem']['place'] == 'B 카페' and check['first_problem']['kind'] == 'closing'


def test_options_are_same_kind_open_near_and_unknown_hours_last(pool):
    plan = course()
    rec = delay_recovery.recovery_for(plan, delay_check(plan, 0, 40))
    assert rec['index'] == 1 and rec['place'] == 'B 카페' and rec['kind'] == '카페' and rec['blocked'] is None
    # 예약 필요·방문일 휴무·늦게 열려 있지 않음·구간 30분 초과·다른 종류는 빠지고, 영업시간 모르는 곳은 맨 뒤.
    assert [o['name'] for o in rec['options']] == ['가까운 늦은 카페', '조금 먼 카페', '영업시간 모르는 카페']
    assert [o['hours_known'] for o in rec['options']] == [True, True, False]
    first, second, _ = rec['options']
    assert first['extra_minutes'] < second['extra_minutes']
    assert all(leg <= 30 for o in rec['options'] for leg in o['legs'] if leg is not None)
    assert first['closes'] == '22:00' and minutes(first['start']) >= hm('16:46')
    assert all('plan' not in o for o in rec['options'])
    assert rec['skip']['allowed'] and rec['skip']['reason'].startswith('B 카페를 빼면 C 산책에')


def test_at_most_three_and_known_hours_come_first(pool):
    pool.append(place('c8', '네 번째 카페', '카페·미식', [hm('10:00'), hm('22:00')], 50, dlat=0.002, dlon=0.008))
    plan = course()
    rec = delay_recovery.recovery_for(plan, delay_check(plan, 0, 40))
    assert [o['name'] for o in rec['options']] == ['가까운 늦은 카페', '조금 먼 카페', '네 번째 카페']


def test_no_recovery_when_nothing_is_late(pool):
    plan = course()
    check = delay_check(plan, 0, 5)
    assert check['status'] != 'problem' and delay_recovery.recovery_for(plan, check) is None


def test_reserved_problem_place_is_not_replaced(pool):
    plan = course(rows=stops(reservation=True), c=conditions(reservation=True))
    rec = delay_recovery.recovery_for(plan, delay_check(plan, 0, 40))
    assert '예약처에 연락' in rec['blocked'] and rec['options'] == [] and rec['skip'] is None


def test_locked_problem_place_is_not_offered(pool):
    rows = stops()
    plan = course(c=conditions(locked={1: rows[1]['id']}), rows=rows)
    rec = delay_recovery.recovery_for(plan, delay_check(plan, 0, 40))
    assert '고정' in rec['blocked'] and rec['options'] == []


def test_no_candidates_explains_and_still_offers_skip(monkeypatch):
    monkeypatch.setattr(delay_recovery, 'candidate_pool', lambda plan, c: [])
    plan = course()
    rec = delay_recovery.recovery_for(plan, delay_check(plan, 0, 40))
    assert rec['options'] == [] and '같은 종류(카페)의 다른 곳이 없어요' in rec['note'] and rec['skip']['allowed']


def test_later_place_also_late_blocks_candidates_but_skip_fits(pool):
    """문제 장소가 여럿: B 를 바꿔도 뒤 C 가 영업 종료를 넘기면 그 후보는 내지 않는다. B 를 빼면 C 에 일찍 닿아 맞는다."""
    plan = course(rows=stops(c_hours=[0, hm('17:50')]))
    rec = delay_recovery.recovery_for(plan, delay_check(plan, 0, 40))
    assert rec['index'] == 1 and rec['options'] == []
    assert 'C 산책에서 영업 종료(17:50)' in rec['note']
    assert rec['skip']['allowed']


def test_first_place_is_the_problem(pool):
    rows = stops()
    rows[0]['hours'] = [hm('10:00'), hm('16:20')]
    plan = course(rows=rows)
    rec = delay_recovery.recovery_for(plan, delay_check(plan, 0, 30))
    assert rec['index'] == 0 and rec['kind'] == '전시·관람'
    assert [o['name'] for o in rec['options']] == ['다른 종류 전시']
    # 첫 장소 대신 가는 곳의 도착은 출발 시각 + 새 구간 + 지연.
    assert minutes(rec['options'][0]['start']) >= hm('15:30')


def test_last_place_is_the_problem(pool):
    rows = stops()
    rows[2].update(category='카페·미식', name='C 카페', hours=[hm('10:00'), hm('18:00')])
    rows[1].update(category='휴식·힐링', hours=[hm('10:00'), hm('22:00')])
    plan = course(rows=rows)
    check = delay_check(plan, 0, 40)
    assert check['first_problem']['place'] == 'C 카페'
    rec = delay_recovery.recovery_for(plan, check)
    assert rec['index'] == 2 and rec['options'] and rec['options'][0]['legs'][1] is None
    assert rec['skip']['allowed'] and rec['skip']['reason'] == f"C 카페를 빼면 끝나는 시각은 {rec['skip']['finish']}예요."


# --- 저장 ---
def test_replace_saves_a_child_course_with_the_delayed_timeline(pool):
    with TestClient(app) as client:
        stored = saved(client, course())
        before = store.get_plan(stored['id'])['payload']
        shown = client.get(f"/api/plans/{stored['id']}/delay-check", params=dict(index=0, minutes=40)).json()
        assert shown['recovery']['options'][0]['id'] == NEAR['id']
        response = recover(client, stored, replacement_id=NEAR['id'])
        assert response.status_code == 200, response.text
        new = response.json()
        assert new['parent'] == stored['id'] and new['id'] != stored['id']
        assert [p['id'] for p in new['places']] == [stored['places'][0]['id'], NEAR['id'], stored['places'][2]['id']]
        assert new['delay_recovery']['delays'] == {'0': 40} and new['delay_recovery']['action'] == 'replace'
        # 첫 장소는 원래 도착 예정 + 40분, 그 뒤는 같은 규칙으로 이어서.
        planned = shown['planned_arrival']
        assert new['timeline'][0]['arrival'] == clock(hm(planned) + 40)
        assert new['timeline'][1]['arrival'] == shown['recovery']['options'][0]['start']
        assert minutes(new['finish']) > minutes(stored['finish'])
        assert '40분 늦어진 것을 반영해 B 카페를 가까운 늦은 카페로 바꾸고' in new['change_reason']
        assert new['delay_recovery_result']['message'].startswith(new['change_reason'])
        assert store.get_plan(stored['id'])['payload'] == before
        # 새 코스에서 다시 확인하면 지금 시간표가 기준이라 0분이면 그대로다.
        again = client.get(f"/api/plans/{new['id']}/delay-check", params=dict(index=0, minutes=0)).json()
        assert again['status'] == 'ok' and again['planned_arrival'] == new['timeline'][0]['arrival']
        assert again['carried'] == 40 and '앞서 40분 늦음을 반영해 저장한 시각' in again['basis']
        assert [r['shift'] for r in again['rows']][:2] == [0, 0] and again['recovery'] is None
        # 되돌리기는 원래 코스.
        assert client.post(f"/api/plans/{new['id']}/undo").json()['id'] == stored['id']


def test_skip_removes_the_place_and_shifts_locks(pool):
    rows = stops()
    with TestClient(app) as client:
        stored = saved(client, course(c=conditions(locked={2: rows[2]['id']}), rows=rows))
        response = recover(client, stored)
        assert response.status_code == 200, response.text
        new = response.json()
        assert [p['name'] for p in new['places']] == ['A 전시', 'C 산책']
        assert new['conditions']['locked'] == {'1': rows[2]['id']} and new['conditions']['count'] == 3
        assert new['legs'][1]['origin'] == 'A 전시' and new['legs'][1]['destination'] == 'C 산책'
        assert new['delay_recovery']['action'] == 'skip' and 'B 카페를 빼고' in new['change_reason']
        assert any(r['condition'] == 'count' and r['state'] == 'unmet' for r in new['condition_checks'])


def test_skip_is_refused_when_no_place_would_be_left(pool):
    rows = [place('b', 'B 카페', '카페·미식', [hm('10:00'), hm('16:20')], 50, dlat=0.002)]
    plan, error = evaluate(rows, conditions(count=2), soft=True)
    assert not error
    with TestClient(app) as client:
        stored = saved(client, audit_plan(plan))
        rec = client.get(f"/api/plans/{stored['id']}/delay-check", params=dict(index=0, minutes=40)).json()['recovery']
        assert rec['index'] == 0 and rec['skip'] == dict(allowed=False, reason='이 장소를 빼면 남는 장소가 없어요.')
        response = recover(client, stored, target=0)
        assert response.status_code == 409 and response.json()['detail'] == '이 장소를 빼면 남는 장소가 없어요.'


def test_stale_or_unoffered_choice_is_409(pool):
    with TestClient(app) as client:
        stored = saved(client, course())
        stale = recover(client, stored, target=2, replacement_id=NEAR['id'])
        assert stale.status_code == 409 and '결과가 바뀌었어요' in stale.json()['detail']
        far = recover(client, stored, replacement_id='fixture:c7')
        assert far.status_code == 409 and '대신 갈 곳이 아니에요' in far.json()['detail']
        assert recover(client, stored, minutes=5).status_code == 409
        with store.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM plans WHERE parent=?', (stored['id'],)).fetchone()[0] == 0


def test_other_browser_cannot_recover(pool):
    with TestClient(app) as owner, TestClient(app) as other:
        stored = saved(owner, course())
        other.get('/api/places?mode=demo')
        assert recover(other, stored, replacement_id=NEAR['id']).status_code == 404


def test_transport_change_keeps_the_delay(pool):
    # 지각을 반영해 고친 코스에서 수단을 바꿔도 지연은 그대로다(예전에는 시간표가 말없이 지연 없는 것으로 돌아갔다).
    with TestClient(app) as client:
        stored = saved(client, course())
        new = recover(client, stored, replacement_id=NEAR['id']).json()
        response = client.post(f"/api/plans/{new['id']}/transport", json={'default': 'transit'})
        assert response.status_code == 200, response.text
        changed = response.json()
        # 기록은 그대로 이어지고, 이 코스가 수단 변경으로 만들어졌다는 표시(kept)만 붙는다(되돌리기 단추 문구용).
        assert changed['delay_recovery'] == dict(new['delay_recovery'], kept='transport') and changed['delay_recovery']['delays'] == {'0': 40}
        assert 'kept' not in new['delay_recovery']
        # 첫 장소 도착 = 새 수단으로 지연 없이 계산한 도착 + 40분.
        plain, error = evaluate(changed['places'], Conditions.model_validate(changed['conditions']), soft=True)
        assert not error
        assert minutes(changed['timeline'][0]['arrival']) == minutes(plain['timeline'][0]['arrival']) + 40
        assert changed['legs'][0]['mode'] == 'transit'
        assert '앞서 반영한 40분 지연은 그대로 뒀어요' in changed['change_reason']
        # 지각 확인도 계속 '지금 시간표' 기준이다.
        again = client.get(f"/api/plans/{changed['id']}/delay-check", params=dict(index=0, minutes=0)).json()
        assert again['status'] == 'ok' and again['carried'] == 40
        assert again['planned_arrival'] == changed['timeline'][0]['arrival']
        # 되돌리기는 수단을 바꾸기 전(지각을 반영한 코스).
        assert client.post(f"/api/plans/{changed['id']}/undo").json()['id'] == new['id']


def test_transport_change_without_a_delay_record_is_unchanged(pool):
    with TestClient(app) as client:
        stored = saved(client, course())
        changed = client.post(f"/api/plans/{stored['id']}/transport", json={'default': 'transit'}).json()
        assert 'delay_recovery' not in changed and '지연' not in changed['change_reason']


def test_change_that_does_not_carry_the_delay_drops_the_record(pool):
    # 지연을 넣어 다시 계산했다고 알려 주지 않은 변경(recovery 없음 — 예: 식사 추가·합의 코스)은 기록을 이어받지 않는다.
    from app.plan_changes import save_change
    with TestClient(app) as client:
        stored = saved(client, course())
        new = recover(client, stored, replacement_id=NEAR['id']).json()
        owner = store.owner_of(client.cookies['dm_session'])
        assert 'delay_recovery' not in save_change(copy.deepcopy(new), new, owner)


# C 산책과 같은 자리의 다른 장소(이동 시간이 같아 끝나는 시각도 같다).
OTHER_WALK = place('w2', '다른 산책길', '산책·풍경', [0, 1440], 45, dlat=0.003)


def test_place_replacement_keeps_the_delay(pool, monkeypatch):
    # 지각을 반영해 고친 코스에서 다른 장소를 바꿔도 지연은 그대로다(예전에는 후보·저장 모두 '늦지 않은' 시간표로 돌아갔다).
    from app import planner
    monkeypatch.setattr(planner, 'candidates', lambda c: copy.deepcopy([OTHER_WALK]))
    with TestClient(app) as client:
        stored = saved(client, course())
        new = recover(client, stored, replacement_id=NEAR['id']).json()
        listed = client.post(f"/api/plans/{new['id']}/alternatives", json={'index': 2, 'locked': []})
        assert listed.status_code == 200, listed.text
        option = listed.json()['alternatives'][0]
        # 후보의 시간표부터 지연이 들어 있다(첫 장소 도착이 복구한 코스와 같다).
        assert option['timeline'][0] == new['timeline'][0] and option['timeline'][1] == new['timeline'][1]
        assert '앞서 반영한 40분 지연은 그대로 뒀어요' in option['change_reason']
        response = client.post(f"/api/plans/{new['id']}/replace", json={'index': 2, 'locked': [], 'replacement_id': OTHER_WALK['id']})
        assert response.status_code == 200, response.text
        changed = response.json()
        assert changed['places'][2]['id'] == OTHER_WALK['id'] and changed['timeline'][:2] == new['timeline'][:2]
        assert changed['delay_recovery'] == dict(new['delay_recovery'], kept='place')
        again = client.get(f"/api/plans/{changed['id']}/delay-check", params=dict(index=0, minutes=0)).json()
        assert again['status'] == 'ok' and again['carried'] == 40
        assert client.post(f"/api/plans/{changed['id']}/undo").json()['id'] == new['id']


def test_replacement_is_offered_when_the_delay_already_passed_the_end_time(pool, monkeypatch):
    # 지각 탓에 이미 정한 종료 시각을 넘긴 코스: 지금보다 늦게 끝나지 않는 후보는 낸다(종료 시각 때문에 후보가 0곳이 되지 않게).
    from app import planner
    monkeypatch.setattr(planner, 'candidates', lambda c: copy.deepcopy([OTHER_WALK]))
    with TestClient(app) as client:
        stored = saved(client, course(conditions(end='18:20')))
        new = recover(client, stored, replacement_id=NEAR['id']).json()
        assert minutes(new['finish']) > minutes('18:20')
        options = client.post(f"/api/plans/{new['id']}/alternatives", json={'index': 2, 'locked': []}).json()['alternatives']
        assert [o['places'][2]['id'] for o in options] == [OTHER_WALK['id']]
        assert options[0]['finish'] == new['finish'] and options[0]['conditions']['end'] == '18:20'
        changed = client.post(f"/api/plans/{new['id']}/replace", json={'index': 2, 'locked': [], 'replacement_id': OTHER_WALK['id']}).json()
        assert changed['conditions']['end'] == '18:20' and changed['finish'] == new['finish']


def test_replacement_without_a_delay_record_is_unchanged(monkeypatch):
    from app import planner
    monkeypatch.setattr(planner, 'candidates', lambda c: copy.deepcopy([OTHER_WALK]))
    with TestClient(app) as client:
        stored = saved(client, course())
        option = client.post(f"/api/plans/{stored['id']}/alternatives", json={'index': 2, 'locked': []}).json()['alternatives'][0]
        assert option['timeline'][:2] == stored['timeline'][:2] and '지연' not in option['change_reason']
        changed = client.post(f"/api/plans/{stored['id']}/replace", json={'index': 2, 'locked': [], 'replacement_id': OTHER_WALK['id']}).json()
        assert 'delay_recovery' not in changed


def test_second_recovery_on_a_recovered_course_adds_to_the_saved_delay(pool):
    with TestClient(app) as client:
        stored = saved(client, course(rows=stops(c_hours=[0, hm('18:40')])))
        new = recover(client, stored, replacement_id=NEAR['id']).json()
        check = client.get(f"/api/plans/{new['id']}/delay-check", params=dict(index=0, minutes=30)).json()
        assert check['first_problem'] and check['first_problem']['place'] == 'C 산책'
        assert check['recovery']['delays'] == {'0': 70}
        response = recover(client, new, minutes=30, target=2)
        assert response.status_code == 200, response.text
        newer = response.json()
        assert newer['parent'] == new['id'] and [p['name'] for p in newer['places']] == ['A 전시', '가까운 늦은 카페']
        assert newer['delay_recovery']['delays'] == {'0': 70}


def test_expired_course_offers_nothing(pool):
    plan = course()
    plan['places'][2]['naver_expired'] = True
    rec = delay_recovery.recovery_for(plan, delay_check(plan, 0, 40))
    assert '21일' in rec['blocked'] and rec['options'] == []


# --- 축제 ---
def festival_course(hours):
    from test_festival_fixed_time import evening, rows

    places = rows()
    places[1]['hours'] = [0, hm('17:20')]
    c = evening(hours=hours)
    plan, error = evaluate(places, c)
    assert not error and plan['festival_visit']['position'] == 'last', error
    return audit_plan(plan), places


def test_evening_festival_course_keeps_the_festival_or_refuses(monkeypatch):
    plan, places = festival_course('17:30~19:00')
    late = places[1]
    near = dict(copy.deepcopy(late), id='fixture:f1', name='가까운 대체', hours=[0, 1440], lat=late['lat'] + 0.0003)
    far = dict(copy.deepcopy(late), id='fixture:f2', name='먼 대체', hours=[0, 1440], lat=late['lat'] - 0.012)
    monkeypatch.setattr(delay_recovery, 'candidate_pool', lambda p, c: copy.deepcopy([near, far]))
    check = delay_check(plan, 0, 30)
    assert check['first_problem']['place'] == late['name']
    rec = delay_recovery.recovery_for(plan, check)
    assert [o['name'] for o in rec['options']] == ['가까운 대체']
    with TestClient(app) as client:
        stored = saved(client, plan)
        refused = recover(client, stored, minutes=30, replacement_id='fixture:f2')
        assert refused.status_code == 409 and '코스 끝 축제 시간에 맞출 수 없어요' in refused.json()['detail']
        response = recover(client, stored, minutes=30, replacement_id='fixture:f1')
        assert response.status_code == 200, response.text
        visit = response.json()['festival_visit']
        assert visit['position'] == 'last' and minutes(visit['departure']) <= hm('19:00')
        assert minutes(visit['arrival']) > minutes(plan['festival_visit']['arrival'])


def test_leading_festival_is_kept(pool):
    from test_festival_fixed_time import ANCHOR

    festival = dict(ANCHOR, hours='14:00~16:00', lat=LAT, lon=LON)
    c = conditions(start='14:00', festival=festival, origin=dict(name='행사장 주변', lat=LAT, lon=LON))
    plan = course(c=c)
    assert plan['festival_visit']['position'] == 'first'
    check = delay_check(plan, 0, 40)
    assert check['first_problem']['place'] == 'B 카페'
    with TestClient(app) as client:
        stored = saved(client, plan)
        response = recover(client, stored, replacement_id=NEAR['id'])
        assert response.status_code == 200, response.text
        assert response.json()['festival_visit'] == plan['festival_visit']


# --- 자동차 코스: 새 외부 호출 없음 ---
def test_car_course_makes_no_route_calls(directions_api, pool):  # noqa: F811
    calls, _ = directions_api
    c = conditions(transport='car', allow_estimates=False)
    plan = course(c=c)
    assert calls and all(leg['status'] == 'api' for leg in plan['legs'])
    plan['places'][1]['hours'] = [hm('10:00'), minutes(plan['timeline'][1]['departure']) + 5]
    calls.clear()
    with TestClient(app) as client:
        stored = saved(client, plan)
        shown = client.get(f"/api/plans/{stored['id']}/delay-check", params=dict(index=0, minutes=20)).json()
        rec = shown['recovery']
        # 추정을 허용하지 않은 코스라 영업시간 모르는 후보는 내지 않는다.
        assert rec['index'] == 1 and '영업시간 모르는 카페' not in [o['name'] for o in rec['options']] and rec['options']
        response = recover(client, stored, minutes=20, replacement_id=rec['options'][0]['id'])
        assert response.status_code == 200, response.text
        new = response.json()
    assert calls == []
    # 바뀌지 않은 첫 구간은 저장된 실제 길찾기 값 그대로, 바뀐 앞뒤 구간은 추정.
    assert new['legs'][0]['status'] == 'api' and new['legs'][0]['minutes'] == plan['legs'][0]['minutes']
    assert new['legs'][1]['status'] == 'estimated' and new['legs'][2]['status'] == 'estimated'
    assert '다시 확인했어요' not in (new.get('route_verification') or '')
    assert any('직선거리로 추정' in w for w in new['delay_recovery_result']['warnings'])


def test_required_end_time_filters_options_but_skip_fits(pool):
    """최종 점검: 종료를 꼭 지킬 조건으로 골랐으면 늦게 끝나는 대체 후보는 미리 빼고(저장 때 409 로 처음 알지 않게), 빼고 진행은 맞으면 남긴다."""
    plan = course(c=conditions(end='18:00', hard_constraints=['end']))
    rec = delay_recovery.recovery_for(plan, delay_check(plan, 0, 40))
    assert rec['options'] == [] and '꼭 지킬 조건으로 고른 종료 시간을 지키지 못해요' in rec['note']
    assert rec['skip']['allowed']


def test_recovery_failure_keeps_the_read_only_check(pool, monkeypatch):
    def broken(plan, check):
        raise KeyError('legs')

    monkeypatch.setattr(delay_recovery, 'recovery_for', broken)
    with TestClient(app) as client:
        stored = saved(client, course())
        response = client.get(f"/api/plans/{stored['id']}/delay-check", params=dict(index=0, minutes=40))
        assert response.status_code == 200 and response.json()['status'] == 'problem' and response.json()['recovery'] is None


def test_walking_course_has_no_route_warning(pool):
    with TestClient(app) as client:
        stored = saved(client, course())
        new = recover(client, stored, replacement_id=NEAR['id']).json()
        assert not any('길찾기' in w for w in new['delay_recovery_result']['warnings'])


def test_saved_payload_is_json(pool):
    with TestClient(app) as client:
        stored = saved(client, course())
        new = recover(client, stored, replacement_id=NEAR['id']).json()
        payload = json.loads(store.get_plan(new['id'])['payload'])
        assert payload['delay_recovery']['delays'] == {'0': 40} and 'delay_recovery_result' not in payload
