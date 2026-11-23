"""방문 순서 제안(app/order_suggestion.py): 같은 장소를 다른 순서로 돌면 이동이 줄어드는지 보고, 줄어들면 그 순서 하나를 제안한다.

고정 코스: 출발지(성수역) 가까이에 A·C, 북쪽으로 1km 남짓 떨어진 곳에 B. 저장된 순서 A → B → C 는 B 까지 갔다가 되돌아온다.
A → C → B 로 돌면 이동이 줄어든다.
"""
import copy

from fastapi.testclient import TestClient

from app import order_suggestion, store
from app.condition_audit import audit_plan
from app.main import app
from app.models import Conditions
from app.planner import evaluate
from test_delay_recovery import LAT, LON, FRIDAY, hm, place, saved

OPEN = [hm('10:00'), hm('22:00')]


def stops(b_hours=OPEN, b_dlat=0.010, **b_extra):
    return [place('a', 'A 전시', '문화·예술', OPEN, 60, dlat=0.001),
            place('b', 'B 카페', '카페·미식', b_hours, 50, dlat=b_dlat, **b_extra),
            place('c', 'C 산책', '산책·풍경', [0, 1440], 45, dlat=0.002)]


def conditions(**extra):
    base = dict(mode='real', region='서울', visit_date=FRIDAY, allow_estimates=True, count=3, budget=200000, max_leg=60,
                start='15:00', end='22:00', transport='walk', origin=dict(name='성수역', lat=LAT, lon=LON))
    base.update(extra)
    return Conditions(**base)


def course(c=None, rows=None):
    plan, error = evaluate(rows or stops(), c or conditions())
    assert not error, error
    return audit_plan(plan)


def names(result):
    return result['suggestion'] and result['suggestion']['names']


def test_shorter_order_is_suggested_with_the_minutes_saved():
    plan = course()
    result = order_suggestion.suggest(plan)
    found = result['suggestion']
    assert found['names'] == ['A 전시', 'C 산책', 'B 카페'] and found['order'] == ['fixture:a', 'fixture:c', 'fixture:b']
    # 줄어든 분은 두 순서를 같은 방식으로 계산한 이동 시간의 차다.
    again, error = evaluate([plan['places'][i] for i in (0, 2, 1)], conditions())
    assert not error
    before, after = order_suggestion.travel_minutes(plan), order_suggestion.travel_minutes(again)
    assert (found['travel_before'], found['travel_after'], found['saved_minutes']) == (before, after, before - after)
    assert found['saved_minutes'] >= order_suggestion.MIN_SAVING
    assert found['finish_before'] == plan['finish'] and found['finish_after'] == again['finish']
    assert 'plan' not in found and result['reason'] is None and '추정' in result['basis']


def test_no_suggestion_when_the_order_is_already_the_shortest():
    rows = stops()
    plan = course(rows=[rows[0], rows[2], rows[1]])
    result = order_suggestion.suggest(plan)
    assert result['suggestion'] is None and '가장 짧거나' in result['reason']


def test_locked_and_reserved_places_stay_where_they_are():
    # B 를 둘째 자리에 고정하면 A·C 만 자리를 바꿀 수 있다 — 어떤 제안이 나오든 B 는 둘째다.
    locked = course(conditions(locked={1: 'fixture:b'}))
    found = order_suggestion.suggest(locked)['suggestion']
    assert found is None or found['names'][1] == 'B 카페'
    reserved = course(rows=stops(reservation=True))
    found = order_suggestion.suggest(reserved)['suggestion']
    assert found is None or found['names'][1] == 'B 카페'
    # 움직일 수 있는 곳이 하나뿐이면 까닭을 말한다.
    both = course(conditions(locked={0: 'fixture:a', 1: 'fixture:b'}))
    result = order_suggestion.suggest(both)
    assert result['suggestion'] is None and '자리를 바꿀 곳이 없어요' in result['reason']


def test_order_that_misses_opening_hours_is_not_suggested():
    # B 는 지금 순서(둘째)로는 문 닫기 전에 마치지만, 마지막으로 미루면 영업 종료(17:20)를 넘긴다.
    plan = course(rows=stops(b_hours=[hm('10:00'), hm('17:20')]))
    late, error = evaluate([plan['places'][i] for i in (0, 2, 1)], conditions())
    assert error == '영업시간 밖 방문'
    found = order_suggestion.suggest(plan)['suggestion']
    assert found is None or found['names'][-1] != 'B 카페'


def test_courses_that_are_not_compared_say_why():
    whole = course()
    one = dict(whole, places=whole['places'][:1])
    assert '한 곳' in order_suggestion.suggest(one)['reason']
    delayed = dict(course(), delay_recovery=dict(delays={'0': 40}))
    assert '지각을 반영' in order_suggestion.suggest(delayed)['reason']
    per_leg = course(conditions(leg_modes=[{'from': 'fixture:a', 'to': 'fixture:b', 'mode': 'transit'}]))
    assert '이동 수단을 따로 정한' in order_suggestion.suggest(per_leg)['reason']


def test_estimates_are_used_for_both_orders(monkeypatch):
    # 자동차 코스도 비교에는 실제 길찾기를 부르지 않는다(지금 순서와 새 순서를 같은 추정으로 견준다).
    from app import planner
    real, forced = planner.leg, []

    def spy(a, b, conditions, force_api=False):
        if force_api:
            forced.append((a['name'], b['name']))
        return real(a, b, conditions, force_api=force_api)

    monkeypatch.setattr(planner, 'leg', spy)
    # 자동차는 빨라서 B 를 더 멀리(약 4km) 둬야 줄어드는 분이 제안 기준을 넘는다.
    plan = course(conditions(transport='car'), stops(b_dlat=0.04))
    assert order_suggestion.suggest(plan)['suggestion']
    assert forced == []


def test_api_suggests_and_saves_the_new_order_as_a_child_course():
    with TestClient(app) as client:
        stored = saved(client, course())
        before = copy.deepcopy(store.get_plan(stored['id'])['payload'])
        shown = client.get(f"/api/plans/{stored['id']}/order-suggestion")
        assert shown.status_code == 200, shown.text
        found = shown.json()['suggestion']
        assert found['names'] == ['A 전시', 'C 산책', 'B 카페']
        assert store.get_plan(stored['id'])['payload'] == before  # 보기만 해서는 저장하지 않는다
        response = client.post(f"/api/plans/{stored['id']}/reorder", json={'order': found['order']})
        assert response.status_code == 200, response.text
        new = response.json()
        assert new['parent'] == stored['id'] and [p['name'] for p in new['places']] == found['names']
        assert order_suggestion.travel_minutes(new) == found['travel_after'] and new['finish'] == found['finish_after']
        assert f"이동을 추정 기준 {found['saved_minutes']}분 줄였어요" in new['change_reason']
        # 새 순서에서는 더 줄일 순서가 없다.
        assert client.get(f"/api/plans/{new['id']}/order-suggestion").json()['suggestion'] is None
        # 되돌리기는 원래 코스.
        assert client.post(f"/api/plans/{new['id']}/undo").json()['id'] == stored['id']


def test_api_refuses_an_order_that_was_not_suggested_and_other_browsers():
    with TestClient(app) as client:
        stored = saved(client, course())
        wrong = client.post(f"/api/plans/{stored['id']}/reorder", json={'order': ['fixture:c', 'fixture:b', 'fixture:a']})
        assert wrong.status_code == 409 and '순서 제안이 바뀌었어요' in wrong.json()['detail']
        with TestClient(app) as other:
            other.get('/api/places?mode=demo')
            assert other.get(f"/api/plans/{stored['id']}/order-suggestion").status_code == 404
            assert other.post(f"/api/plans/{stored['id']}/reorder", json={'order': ['fixture:a', 'fixture:c', 'fixture:b']}).status_code == 404
