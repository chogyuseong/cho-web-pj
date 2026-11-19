"""'지금 N분 늦으면' 읽기 전용 확인(app/delay_check.py). 지연 기준은 선택한 장소의 원래 도착 예정 시각이다."""
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import store
from app.delay_check import delay_check
from app.main import app
from app.models import Conditions
from app.planner import evaluate


def hm(text):
    h, m = map(int, text.split(':'))
    return h * 60 + m


def place(pid, name, hours, stay, last_entry=None, breaks=None, closed_days=None):
    return dict(id='fixture:' + pid, name=name, category='전시', lat=37.5446, lon=127.0557, hours=hours, stay=stay,
                last_entry=last_entry, breaks=breaks, closed_days=[] if closed_days is None else closed_days, price=[0, 0],
                price_unit='person', source='https://example.org/' + pid, checked_at='2026-11-01', reservation=False)


def plan_of(conditions, rows, leg_minutes, timeline, finish, return_leg=None):
    """저장된 코스 모양. 구간 이동은 저장값을 쓰므로 직접 넣는다(status 'estimated' = 거리 기반 추정)."""
    legs = [dict(origin='출발' if i == 0 else rows[i - 1]['name'], destination=r['name'], minutes=m, status='estimated',
                 source='직선거리 기반 도보 추정', buffer_minutes=0) for i, (r, m) in enumerate(zip(rows, leg_minutes))]
    if return_leg is not None:
        legs.append(dict(origin=rows[-1]['name'], destination='집', minutes=return_leg, status='estimated', source='직선거리 기반 추정', buffer_minutes=0))
    return dict(conditions=conditions.model_dump(mode='json'), places=rows, legs=legs,
                timeline=[dict(arrival=a, departure=d) for a, d in timeline], finish=finish)


def conditions(**kw):
    return Conditions(mode='real', visit_date=date(2026, 11, 20), allow_estimates=True, **kw)


def test_ten_minutes_fit_but_eleven_minutes_pass_closing():
    # 16:40 도착 예정, 17:00 입장 마감, 17:30 영업 종료, 관람 40분.
    c = conditions(start='16:30', end='22:00', count=2)
    gallery = place('g', '마감 직전 전시', [hm('10:00'), hm('17:30')], 40, last_entry=hm('17:00'))
    plan = plan_of(c, [gallery], [10], [('16:40', '17:20')], '17:20')
    ok = delay_check(plan, 0, 10)
    assert ok['planned_arrival'] == '16:40' and ok['delayed_arrival'] == '16:50'
    assert ok['status'] == 'ok' and ok['rows'][0]['departure'] == '17:30' and ok['first_problem'] is None
    late = delay_check(plan, 0, 11)
    assert late['status'] == 'problem'
    assert late['first_problem'] == dict(place='마감 직전 전시', time='16:51', reason='영업시간 밖 방문', kind='closing', limit='17:30', over=1)
    # 20분이면 입장 마감(17:00)은 맞추지만 영업 종료를 넘긴다. 입장 마감만 보면 '괜찮다'고 잘못 말하게 된다.
    assert delay_check(plan, 0, 20)['first_problem']['kind'] == 'closing'
    assert delay_check(plan, 0, 21)['first_problem']['kind'] == 'last_entry'


def test_waiting_for_opening_absorbs_the_delay():
    # 17:45 도착 예정, 18:00 개점: 10분 늦어도 이용 시작은 18:00 그대로.
    c = conditions(start='17:30', end='22:00', count=2)
    bistro = place('b', '여섯 시 식당', [hm('18:00'), hm('22:00')], 60)
    plan = plan_of(c, [bistro], [15], [('18:00', '19:00')], '19:00')
    result = delay_check(plan, 0, 10)
    row = result['rows'][0]
    assert result['planned_arrival'] == '17:45' and row['arrival'] == '17:55'
    assert row['start'] == '18:00' and row['shift'] == 0 and row['wait'] == 5 and result['status'] == 'ok'
    assert result['finish'] == '19:00' == result['original_finish']


def test_break_time_pushes_the_next_place_and_the_end_time_is_checked():
    c = conditions(start='13:30', end='18:30', count=2)
    tea = place('t', '휴게 있는 찻집', [hm('10:00'), hm('21:00')], 60, breaks=[[hm('15:00'), hm('16:00')]])
    shop = place('s', '다섯 시 반 마감 공방', [hm('10:00'), hm('17:30')], 60)
    plan = plan_of(c, [tea, shop], [20, 10], [('13:50', '14:50'), ('15:00', '16:00')], '16:00')
    # 15분 늦으면 찻집 이용(14:05~15:05)이 휴게(15:00~16:00)와 겹쳐 16:00 에 시작 → 공방 17:10 도착 → 18:10 > 17:30 마감.
    result = delay_check(plan, 0, 15)
    assert result['rows'][0]['start'] == '16:00' and result['rows'][0]['shift'] == 130
    assert result['first_problem']['place'] == '다섯 시 반 마감 공방' and result['first_problem']['kind'] == 'closing'
    # 5분이면 휴게 전에 끝나고 공방도 시간 안이다.
    assert delay_check(plan, 0, 5)['status'] == 'ok'
    # 남은 첫 장소를 두 번째로 고르면 그 장소의 원래 도착(찻집 출발 14:50 + 10분 = 15:00)이 기준이다.
    second = delay_check(plan, 1, 30)
    assert second['planned_arrival'] == '15:00' and second['rows'][0]['start'] == '15:30' and second['status'] == 'ok'
    # 종료 조건: 정한 종료 시각을 넘기면 마지막에 알린다.
    tight = plan_of(conditions(start='13:30', end='16:10', count=2), [tea, shop], [20, 10], [('13:50', '14:50'), ('15:00', '16:00')], '16:00')
    assert delay_check(tight, 1, 15)['first_problem'] == dict(place='일정 종료', time='16:15', reason='정한 종료 시각을 넘겨요', kind='end', limit='16:10', over=5)


def test_estimated_legs_are_named_and_missing_hours_defer_the_judgment():
    c = conditions(start='13:30', end='20:00', count=2, return_home=True, home=dict(name='집', lat=37.55, lon=127.06))
    tea = place('t', '찻집', [hm('10:00'), hm('21:00')], 60)
    unknown = dict(place('u', '영업시간 모르는 전시', None, 60), hours=None)
    plan = plan_of(c, [tea, unknown], [20, 10], [('13:50', '14:50'), ('15:00', '16:00')], '16:30', return_leg=30)
    result = delay_check(plan, 0, 10)
    assert result['status'] == 'unknown' and result['pending'] == [dict(place='영업시간 모르는 전시', fields=['영업시간'])]
    assert result['first_problem'] is None and result['finish'] is None
    assert result['estimated_legs'][0] == dict(leg='출발 → 찻집', minutes=20, basis='직선거리 기반 도보 추정')
    known = plan_of(c, [tea, place('k', '영업시간 아는 전시', [hm('10:00'), hm('21:00')], 60)], [20, 10],
                    [('13:50', '14:50'), ('15:00', '16:00')], '16:30', return_leg=30)
    done = delay_check(known, 0, 10)
    assert done['status'] == 'ok' and done['finish'] == '16:40', '귀가 구간까지 더한 끝나는 시각'
    assert any(e['leg'] == '영업시간 아는 전시 → 집' for e in done['estimated_legs'])
    with pytest.raises(ValueError):
        delay_check(known, 5, 10)
    with pytest.raises(ValueError):
        delay_check(known, 0, 181)


def test_evaluate_and_delay_check_share_the_same_rules():
    # 플래너가 만든 실제 코스에서 지연 0분이면 원래 시간표와 같아야 한다(같은 규칙을 쓰는지).
    c = conditions(start='16:30', end='22:00', count=2, transport='walk', max_leg=60, origin=dict(name='성수역', lat=37.5446, lon=127.0557))
    rows = [dict(place('a', '첫 전시', [hm('10:00'), hm('20:00')], 50), lat=37.5452, lon=127.0566),
            dict(place('b', '저녁 식당', [hm('18:00'), hm('22:00')], 60), lat=37.5440, lon=127.0580)]
    plan, error = evaluate(rows, c)
    assert not error
    same = delay_check(plan, 0, 0)
    assert [r['start'] for r in same['rows']] == [t['arrival'] for t in plan['timeline']]
    assert same['finish'] == plan['finish']


def test_api_is_read_only_and_owner_only():
    with TestClient(app) as owner, TestClient(app) as other:
        plan = owner.post('/api/plans', json={'visit_date': '2026-10-24', 'max_leg': 180, 'budget': 1000000}).json()['plans'][0]
        before = store.get_plan(plan['id'])['payload']
        response = owner.get('/api/plans/' + plan['id'] + '/delay-check', params=dict(index=0, minutes=10))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['status'] in ('ok', 'problem', 'unknown') and body['basis'].endswith('다시 계산했어요.')
        assert store.get_plan(plan['id'])['payload'] == before
        with store.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM plans WHERE parent=?', (plan['id'],)).fetchone()[0] == 0
        # 다른 브라우저에는 코스가 없는 것처럼 보인다(다른 일정 API 와 같은 공개 범위).
        assert other.get('/api/plans/' + plan['id'] + '/delay-check', params=dict(index=0, minutes=10)).status_code == 404
        assert owner.get('/api/plans/' + plan['id'] + '/delay-check', params=dict(index=9, minutes=10)).status_code == 409
        assert json.loads(store.get_plan(plan['id'])['payload']) == json.loads(before)
