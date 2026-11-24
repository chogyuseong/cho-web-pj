"""자정을 넘기는 지각 확인 (2026-11-24 점검 A5).

1. 영업시간 자료가 없어 '하루 종일 연다'고 가정한 곳은 자정을 넘겨도 '영업 종료 24:00'을 문제로 잡지 않는다.
   가정한 종료 시각(24:00)은 사실이 아니라서, 그걸로 대신 갈 곳 찾기까지 이어지면 안 된다. 그 줄은 '확인 필요'(unchecked)로 남는다.
   영업시간 자료가 실제로 24:00 종료인 곳은 예전처럼 문제로 잡는다.
2. 축제 방문 시각은 장소 시각과 같은 표기(planner.clock — 자정 뒤는 24:30)로 저장한다. 예전에는 24로 나눈 나머지('00:30')로 저장해
   지각 확인이 그 글을 다시 분으로 읽으면 하루가 앞당겨졌다. 이미 '00:30'으로 저장된 옛 코스도 코스 시작보다 이른 시각은 다음 날로 읽는다.
"""
from app.delay_check import delay_check
from app.festival_time import visit_record
from test_delay_check import conditions, hm, place, plan_of
from test_festival_middle import cond


def unknown(pid, name):
    return dict(place(pid, name, None, 60), hours=None)


def late_plan(second):
    """20:30 시작·23:30 종료, 장소 둘(첫 곳은 영업시간 모름). 120분 늦으면 둘째 곳 이용이 23:50~24:50 으로 자정을 넘긴다."""
    c = conditions(start='20:30', end='23:30', count=2)
    return plan_of(c, [unknown('a', '심야 카페'), second], [10, 10], [('20:40', '21:40'), ('21:50', '22:50')], '22:50')


def test_assumed_hours_do_not_close_at_midnight():
    result = delay_check(late_plan(unknown('b', '영업시간 모르는 바')), 0, 120)
    rows = result['rows']
    assert [r['name'] for r in rows] == ['심야 카페', '영업시간 모르는 바']
    assert rows[1]['arrival'] == '23:50' and rows[1]['departure'] == '24:50'
    # 가정한 24:00 종료는 문제가 아니다. 남는 문제는 사실인 '정한 종료 시각(23:30)을 넘김'뿐이다.
    assert all(r['state'] == 'unchecked' for r in rows), rows
    assert result['first_problem']['kind'] == 'end' and result['first_problem']['time'] == '24:50'
    assert [p['place'] for p in result['pending']] == ['심야 카페', '영업시간 모르는 바']


def test_real_midnight_closing_is_still_a_problem():
    # 자료로 확인한 24:00 종료는 그대로 문제다(가정만 바뀐다).
    known = place('k', '자정에 닫는 바', [hm('18:00'), hm('24:00')], 60)
    result = delay_check(late_plan(known), 0, 120)
    assert result['first_problem']['kind'] == 'closing' and result['first_problem']['limit'] == '24:00'


def test_festival_visit_after_midnight_is_stored_like_place_times():
    c = cond()
    record = visit_record(c, dict(arrival=hm('23:30'), departure=hm('24:30'), wait=0))
    assert (record['arrival'], record['departure']) == ('23:30', '24:30')


def festival_plan(arrival, departure):
    """20:30 시작 코스, 첫 장소 뒤 중간 축제(저장된 축제 시각을 그대로 받음), 둘째 장소는 행사장에서 10분."""
    c = conditions(start='20:30', end='23:59', count=2)
    rows = [place('a', '저녁 전시', [hm('10:00'), hm('24:00')], 60), place('b', '심야 바', [hm('18:00'), hm('24:00')], 30)]
    plan = plan_of(c, rows, [10, 10], [('20:40', '21:40'), ('23:30', '23:50')], '23:50')
    plan['festival_visit'] = dict(title='빛축제', hours='18:00~02:00', position='middle', after=0, arrival=arrival,
                                  departure=departure, stay=60, wait=0, leg=dict(minutes=10, status='estimated'))
    return plan


def test_delay_check_reads_festival_times_after_midnight():
    # 축제 23:20~24:20, 둘째 장소는 축제가 끝난 24:20 에 행사장에서 떠나 10분 뒤 도착 예정.
    for arrival, departure in (('23:20', '24:20'), ('23:20', '00:20')):  # 새 저장 표기, 옛 저장 표기
        result = delay_check(festival_plan(arrival, departure), 1, 0)
        assert result['planned_arrival'] == '24:30', (departure, result['planned_arrival'])


def test_delay_check_reads_an_old_festival_record_that_started_after_midnight():
    # 옛 표기로 시작·끝이 모두 자정 뒤인 축제(00:10~01:10). 코스 시작(20:30)보다 이른 시각은 다음 날이다.
    result = delay_check(festival_plan('00:10', '01:10'), 0, 0)
    festival = next(r for r in result['rows'] if r.get('festival'))
    assert festival['original_start'] == '00:10' and festival['shift'] <= 0, festival
