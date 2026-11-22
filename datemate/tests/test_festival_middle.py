"""축제를 코스 중간에 두기(app/planner.evaluate, docs/superpowers/specs/2026-11-23-festival-middle-design.md).

맨 앞(festival_slot)·코스 끝(evening_window + last_slot)이 맞지 않는 낮 축제를 장소 i 와 i+1 사이에 둔다:
장소 i → 행사장(festival_visit.leg, plan['legs'] 밖) → 축제 → 행사장 → 장소 i+1(plan['legs'][i+1]).
"""
import copy
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import delay_recovery, store
from app.catalog import places
from app.condition_audit import audit_plan
from app.delay_check import delay_check
from app.festival_time import LEG_FIELDS
from app.main import app
from app.models import Conditions
from app.planner import clock, evaluate, minutes
from test_festival_fixed_time import ANCHOR, HOME

MIDDLE = '11:30~13:00'
ORIGIN = dict(name='서울 종로구 · 점검 빛축제 행사장 주변', lat=ANCHOR['lat'], lon=ANCHOR['lon'])


def stops(count=2, stay=90, **extra):
    out = copy.deepcopy(places('demo')[:count])
    for p in out:
        p.update(demo=False, hours=[0, 1440], closed_days=[], last_entry=None, breaks=None, price=[1000, 1000], price_unit='person', stay=stay)
        p.update(extra)
    return out


def cond(hours=MIDDLE, start='10:00', end='19:00', count=2, **extra):
    festival = dict(ANCHOR, hours=hours) if hours else dict(ANCHOR)
    base = dict(mode='real', region='서울', visit_date=date(2026, 10, 24), allow_estimates=True, count=count, budget=200000,
                max_leg=180, start=start, end=end, festival=festival, origin=ORIGIN)
    base.update(extra)
    return Conditions(**base)


def planned(rows=None, c=None):
    plan, error = evaluate(rows or stops(), c or cond())
    assert not error, error
    return audit_plan(plan, c or cond())


def festival_check(plan):
    return next(r for r in plan['condition_checks'] if r['condition'] == 'festival')


# --- 배치 ---
def test_midday_festival_goes_between_the_two_places():
    plain = planned(c=cond(hours=None))
    plan = planned()
    visit = plan['festival_visit']
    assert visit['position'] == 'middle' and visit['after'] == 0 and visit['title'] == '점검 빛축제'
    # 첫 장소까지는 축제 없는 코스와 같다.
    assert plan['timeline'][0] == plain['timeline'][0] and plan['legs'][0] == plain['legs'][0]
    # 첫 장소 → 행사장(들어가는 구간, legs 밖) → 개막까지 기다림(60분 이하) → 체류 60분.
    back = visit['leg']
    assert set(back) <= set(LEG_FIELDS) | {'route_fallback'}
    reached = minutes(plan['timeline'][0]['departure']) + back['minutes'] + back['buffer_minutes']
    assert minutes(visit['arrival']) == max(reached, minutes('11:30')) and visit['wait'] == minutes(visit['arrival']) - reached
    assert visit['wait'] <= 60 and visit['stay'] == 60
    assert minutes(visit['departure']) == minutes(visit['arrival']) + 60 <= minutes('13:00')
    # 행사장 → 둘째 장소(나오는 구간)는 plan['legs'][1]. 구간 i 는 장소 i 에 도착한다는 약속 그대로.
    assert len(plan['legs']) == len(plan['places']) == 2
    out = plan['legs'][1]
    assert out['origin'] == '점검 빛축제 행사장' and out['destination'] == plan['places'][1]['name']
    assert f"slat={ANCHOR['lat']}" in out['link']
    assert minutes(plan['timeline'][1]['arrival']) == minutes(visit['departure']) + out['minutes'] + out['buffer_minutes']
    assert plan['finish'] == plan['timeline'][-1]['departure']
    assert any(row['category'] == '교통' and row['name'] == f"{plan['places'][0]['name']} → 점검 빛축제 행사장" for row in plan['costs'])
    check = festival_check(plan)
    assert check['state'] == 'met' and '중간' in check['message'] and f"{visit['arrival']}~{visit['departure']}" in check['message']


def test_earliest_fitting_gap_is_chosen():
    # 장소 3곳, 각 60분. 첫 장소 뒤는 개막(12:30)까지 60분 넘게 기다려야 해서 둘째 장소 뒤에 둔다. 코스 끝은 운영 종료(13:45)를 넘긴다.
    c = cond('12:30~13:45', count=3)
    plan = planned(stops(3, stay=60), c)
    visit = plan['festival_visit']
    assert visit['position'] == 'middle' and visit['after'] == 1
    assert plan['legs'][2]['origin'] == '점검 빛축제 행사장' and plan['legs'][1]['origin'] != '점검 빛축제 행사장'


def test_leading_and_closing_rules_win_over_the_middle():
    # 맨 앞 고정이 맞으면 맨 앞.
    assert planned(c=cond('10:00~18:00'))['festival_visit']['position'] == 'first'
    # 개막이 늦어 맨 앞은 안 되지만 코스 끝이 맞으면(중간도 맞더라도) 예전처럼 끝.
    assert planned(c=cond('11:30~22:00'))['festival_visit']['position'] == 'last'


def test_no_festival_when_the_middle_does_not_fit_either():
    plain = planned(c=cond(hours=None))
    # 첫 장소 뒤 행사장에 닿으면 개막(12:50)까지 60분 넘게 기다림, 코스 끝은 운영 종료(14:00) 넘김.
    waiting = planned(c=cond('12:50~14:00'))
    # 중간에 두면 둘째 장소가 종료 시각(13:30)을 넘김(축제 없는 코스는 13:12 에 끝나 맞음).
    late = planned(c=cond(end='13:30'))
    for plan in (waiting, late):
        assert 'festival_visit' not in plan
        assert festival_check(plan)['state'] == 'unknown'
    assert waiting['timeline'] == plain['timeline'] and waiting['legs'] == plain['legs']
    assert '중간에 들르' in festival_check(waiting)['message']


def test_middle_festival_is_kept_when_the_course_is_reopened():
    plan = planned(c=cond(return_home=True, home=HOME))
    again, error = evaluate(plan['places'], Conditions.model_validate(plan['conditions']))
    assert not error and again['festival_visit'] == plan['festival_visit'] and again['timeline'] == plan['timeline']
    # 귀가는 마지막 장소에서 떠난다.
    assert plan['legs'][-1]['origin'] == plan['places'][-1]['name'] and len(plan['legs']) == 3


def test_forced_gap_that_does_not_fit_is_an_error():
    plan = planned()
    c = Conditions.model_validate(plan['conditions'])
    failure = {}
    _, error = evaluate(plan['places'], c, festival_after=1, failure=failure)
    assert error == '축제 운영 시간 불일치' and failure['place'] == '점검 빛축제'
    forced, error = evaluate(plan['places'], c, festival_after=0)
    assert not error and forced['festival_visit'] == plan['festival_visit']


# --- 공유·수단 예외 키·차 위치 ---
def test_shared_visit_says_after_which_place():
    from app.sharing import festival_visit
    plan = planned()
    visit = plan['festival_visit']
    assert festival_visit(plan) == dict(title='점검 빛축제', arrival=visit['arrival'], departure=visit['departure'], position='middle', after=0)
    broken = dict(plan, festival_visit=dict(visit, after=5))
    assert festival_visit(broken)['position'] == 'first' and 'after' not in festival_visit(broken)


def test_leg_keys_for_the_middle_festival():
    from app.leg_modes import car_position_notes, endpoints, festival_pair
    plan = planned()
    a, b = (p['id'] for p in plan['places'])
    assert endpoints(plan) == [('origin', a), ('festival', b)]
    assert festival_pair(plan) == (a, 'festival')
    # 행사장 = 출발지라 '행사장 → 둘째 장소'를 자동차로 가도 차가 있는 곳에서 떠난다(안내 없음).
    plan['legs'][1]['mode'] = 'car'
    assert car_position_notes(plan) == []
    plan['festival_visit']['leg']['mode'] = 'car'
    plan['legs'][1]['mode'] = 'walk'
    assert any('차는' in note for note in car_position_notes(plan))


def save(client, plan):
    client.get('/api/places?mode=demo')
    return store.save_plan(plan, store.owner_of(client.cookies['dm_session']))


def change(client, plan, **body):
    return client.post(f"/api/plans/{plan['id']}/transport", json=body)


def test_change_the_legs_into_and_out_of_the_festival():
    with TestClient(app) as client:
        plan = save(client, planned())
        a, b = (p['id'] for p in plan['places'])
        response = change(client, plan, festival='transit')
        assert response.status_code == 200, response.text
        updated = response.json()
        assert updated['festival_visit']['position'] == 'middle' and updated['festival_visit']['after'] == 0
        assert updated['festival_visit']['leg']['mode'] == 'transit'
        assert {'from': a, 'to': 'festival', 'mode': 'transit'} in updated['conditions']['leg_modes']
        assert [leg['mode'] for leg in updated['legs']] == ['walk', 'walk']
        out = change(client, updated, legs=[{'index': 1, 'mode': 'bicycle'}])
        assert out.status_code == 200, out.text
        moved = out.json()
        assert moved['legs'][1]['mode'] == 'bicycle' and moved['legs'][1]['origin'] == '점검 빛축제 행사장'
        assert {'from': 'festival', 'to': b, 'mode': 'bicycle'} in moved['conditions']['leg_modes']
        assert moved['festival_visit']['leg']['mode'] == 'transit'
        cleared = change(client, moved, default='walk').json()
        assert cleared['conditions']['leg_modes'] == [] and cleared['festival_visit']['position'] == 'middle'


def test_mode_that_misses_the_middle_festival_is_refused():
    # 도보로는 운영 종료 시각에 딱 끝나게 시간을 맞춘 뒤, 대기 시간이 붙어 1분 더 걸리는 대중교통으로 바꾸면 축제를 못 마친다.
    probe = planned()
    hours = f"11:30~{probe['festival_visit']['departure']}"
    plan = planned(c=cond(hours))
    assert plan['festival_visit']['position'] == 'middle'
    with TestClient(app) as client:
        stored = save(client, plan)
        response = change(client, stored, festival='transit')
        assert response.status_code == 409 and '중간 축제' in response.json()['detail']


def test_change_that_moves_the_festival_is_refused(monkeypatch):
    from app import leg_modes, planner
    plan = planned()
    prepared = leg_modes.prepare_change(plan, festival='transit')
    moved = copy.deepcopy(plan)
    moved['festival_visit'] = dict(moved['festival_visit'], position='last')
    monkeypatch.setattr(planner, 'evaluate', lambda *a, **k: (copy.deepcopy(moved), None))
    with pytest.raises(leg_modes.Blocked):
        leg_modes.apply_change(plan, prepared)


def test_evening_festival_that_would_move_to_the_middle_is_refused(monkeypatch):
    from app import leg_modes, planner
    from test_festival_fixed_time import evening, rows
    plan, error = evaluate(rows(), evening())
    assert not error and plan['festival_visit']['position'] == 'last'
    prepared = leg_modes.prepare_change(plan, festival='transit')
    moved = copy.deepcopy(plan)
    moved['festival_visit'] = dict(moved['festival_visit'], position='middle', after=0)
    monkeypatch.setattr(planner, 'evaluate', lambda *a, **k: (copy.deepcopy(moved), None))
    with pytest.raises(leg_modes.Blocked):
        leg_modes.apply_change(plan, prepared)


# --- 지각 확인 ---
def test_delay_check_puts_the_festival_between_the_places():
    plan = planned()
    on_time = delay_check(plan, 0, 0)
    assert [row['name'] for row in on_time['rows']] == [plan['places'][0]['name'], '축제 · 점검 빛축제', plan['places'][1]['name']]
    festival = on_time['rows'][1]
    assert festival['festival'] is True and festival['start'] == plan['festival_visit']['arrival'] and festival['shift'] == 0
    assert on_time['finish'] == plan['finish'] and on_time['status'] == 'ok'
    assert any(e['leg'] == f"{plan['places'][0]['name']} → 점검 빛축제 행사장" for e in on_time['estimated_legs'])
    # 둘째 장소부터 보면 축제가 끝난 시각에 행사장에서 출발한다.
    second = delay_check(plan, 1, 0)
    assert second['planned_arrival'] == plan['timeline'][1]['arrival'] and second['rows'][0]['shift'] == 0
    # 많이 늦으면 축제 줄에서 처음 문제가 난다(운영 종료 13:00).
    late = delay_check(plan, 0, 60)
    assert late['first_problem']['kind'] == 'festival' and late['first_problem']['limit'] == '13:00'
    assert late['rows'][-1]['name'] == '축제 · 점검 빛축제'


# --- 지각 복구 ---
def recovery_course():
    rows = stops()
    rows[1]['hours'] = [0, minutes('14:30')]
    plan = planned(rows)
    assert plan['festival_visit']['position'] == 'middle' and minutes(plan['timeline'][1]['departure']) <= minutes('14:30')
    return plan


def near(plan, pid='fixture:m1', name='가까운 대체', dlat=0.0003):
    late = plan['places'][1]
    return dict(copy.deepcopy(late), id=pid, name=name, hours=[0, 1440], lat=late['lat'] + dlat)


def test_recovery_counts_places_not_the_festival_row(monkeypatch):
    plan = recovery_course()
    replacement = near(plan)
    monkeypatch.setattr(delay_recovery, 'candidate_pool', lambda p, c: copy.deepcopy([replacement]))
    check = delay_check(plan, 0, 10)
    assert [row['name'] for row in check['rows']][1] == '축제 · 점검 빛축제'
    assert check['first_problem']['place'] == plan['places'][1]['name']
    rec = delay_recovery.recovery_for(plan, check)
    assert rec['index'] == 1 and [o['name'] for o in rec['options']] == ['가까운 대체']
    # 바꿀 장소의 앞 지점은 행사장이다(첫 장소가 아니라).
    from app.delay_recovery import _estimate
    from app.models import Conditions as C
    come = _estimate(ORIGIN, replacement, C.model_validate(plan['conditions']))
    assert rec['options'][0]['legs'][0] == come['minutes']
    # 빼면 축제가 코스 끝이 되어 자리가 바뀌므로 허용하지 않는다.
    assert rec['skip']['allowed'] is False and '중간 축제' in rec['skip']['reason']
    with TestClient(app) as client:
        stored = save(client, plan)
        response = client.post(f"/api/plans/{stored['id']}/delay-recovery", json=dict(index=0, minutes=10, target=1, replacement_id=replacement['id']))
        assert response.status_code == 200, response.text
        visit = response.json()['festival_visit']
        assert visit['position'] == 'middle' and visit['after'] == 0
        assert minutes(visit['arrival']) > minutes(plan['festival_visit']['arrival'])


def test_recovery_after_the_festival_starts_from_the_venue(monkeypatch):
    plan = recovery_course()
    replacement = near(plan)
    monkeypatch.setattr(delay_recovery, 'candidate_pool', lambda p, c: copy.deepcopy([replacement]))
    check = delay_check(plan, 1, 30)
    assert check['first_problem']['place'] == plan['places'][1]['name']
    rec = delay_recovery.recovery_for(plan, check)
    assert rec['index'] == 1 and rec['options']
    # 축제가 끝난 시각에 행사장에서 출발 + 이동 + 지연 30분(대체 장소는 하루 종일 연다).
    option = rec['options'][0]
    c = Conditions.model_validate(plan['conditions'])
    expected = minutes(plan['festival_visit']['departure']) + option['legs'][0] + c.transition_buffer_minutes + 30
    assert option['start'] == clock(expected)
    from app.delay_recovery import _estimate
    assert option['legs'][0] == _estimate(ORIGIN, replacement, c)['minutes']


def test_candidate_that_breaks_the_middle_festival_is_left_out(monkeypatch):
    # 첫 장소(축제 바로 앞)가 문제인 코스에서, 행사장에서 먼 대체 장소는 축제 시각을 못 맞춘다.
    rows = stops()
    rows[0]['hours'] = [0, minutes('11:45')]
    plan = planned(rows)
    assert plan['festival_visit']['position'] == 'middle'
    first = plan['places'][0]
    close = dict(copy.deepcopy(first), id='fixture:m2', name='가까운 첫 장소', hours=[0, 1440], lat=first['lat'] + 0.0002)
    far = dict(copy.deepcopy(first), id='fixture:m3', name='먼 첫 장소', hours=[0, 1440], lat=first['lat'] - 0.02)
    monkeypatch.setattr(delay_recovery, 'candidate_pool', lambda p, c: copy.deepcopy([close, far]))
    check = delay_check(plan, 0, 8)
    assert check['first_problem']['place'] == first['name']
    rec = delay_recovery.recovery_for(plan, check)
    assert [o['name'] for o in rec['options']] == ['가까운 첫 장소']
    _, _, rejected = delay_recovery._recover(plan, check)
    assert '중간 축제' in rejected['fixture:m3']


# --- 최종 점검에서 고친 것 ---
def test_reverified_course_does_not_keep_an_old_festival_record(monkeypatch):
    # 장소를 바꾼 자동차 코스는 실제 길찾기로 다시 계산한다. 다시 계산한 코스에 축제가 없으면 옛 축제 기록이 남지 않아야 한다.
    from app import planner
    from app.plan_changes import save_change
    with TestClient(app) as client:
        stored = save(client, planned())
        owner = store.owner_of(client.cookies['dm_session'])
        updated = copy.deepcopy(stored)
        updated['places'] = list(reversed(updated['places']))
        updated['conditions']['transport'] = 'car'
        checked = copy.deepcopy(stored)
        checked.pop('festival_visit')
        monkeypatch.setattr(planner, 'evaluate', lambda *a, **k: (copy.deepcopy(checked), None))
        result = save_change(updated, stored, owner)
        assert 'festival_visit' not in result
