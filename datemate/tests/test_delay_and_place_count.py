"""2026-11-24 전체 점검(docs/reviews/2026-11-24-full-review.md)의 A1~A4 와 그 공통 원인.
설계: docs/superpowers/specs/2026-11-24-delay-and-place-count-design.md

- A1: 지각을 반영한 코스에서 다른 장소 번호로 지각을 다시 확인·복구해도 앞서 반영한 다른 장소의 지연이 남는다.
- A2: '빼고 진행'(묶음의 '바꾸고 뒤 장소 빼기' 포함)으로 저장한 코스에서도 장소 바꾸기·레저 후보가 나온다.
- A3: 구간별 수단 예외가 있는 코스에 식당을 끼우면(또는 합의 코스를 만들면) 끊긴 구간의 예외가 조건에 남지 않는다.
- A4: 1곳 남은 코스의 '식사로 교체'가 내부 검증 오류 원문을 보여 주지 않는다.
- 공통: 이미 있는 코스를 다시 계산하는 곳은 app/plan_rules.reevaluate 만 쓴다(지연·종료 허용·장소 수 규칙이 한 곳)."""
import copy
import re
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import delay_recovery, planner, store
from app.condition_audit import audit_plan
from app.delay_check import delay_check
from app.main import app
from app.models import Conditions
from app.planner import evaluate, minutes
from test_delay_kept_meal_consensus import agree
from test_delay_recovery import NEAR, OTHER_WALK, conditions, course, hm, place, pool, recover, saved, stops  # noqa: F401  (pool: 후보 고정 장치)
from test_experience import food_fixture


def check(client, plan, index, late):
    response = client.get(f"/api/plans/{plan['id']}/delay-check", params=dict(index=index, minutes=late))
    assert response.status_code == 200, response.text
    return response.json()


def with_delays(plan, delays):
    """같은 장소·같은 조건에 delays 만 넣어 계산한 시간표(견줄 기준)."""
    result, error = evaluate(plan['places'], Conditions.model_validate(plan['conditions']), soft=True, delays=delays)
    assert not error, error
    return result


def late_at_third(client, pool):
    """A 전시 → B 카페 → (C 산책 대신) 다른 산책길. 3번째 장소(번호 2)에 60분 지연을 반영한 코스."""
    pool.append(OTHER_WALK)
    stored = saved(client, course(rows=stops(c_hours=[0, hm('18:40')])))
    response = recover(client, stored, index=2, minutes=60, target=2, replacement_id=OTHER_WALK['id'])
    assert response.status_code == 200, response.text
    new = response.json()
    assert new['delay_recovery']['delays'] == {'2': 60}
    return new


# --- A1: 다른 번호에서 다시 확인·복구해도 앞서 반영한 지연이 남는다 ---
def test_check_from_an_earlier_place_keeps_the_later_delay(pool):
    with TestClient(app) as client:
        new = late_at_third(client, pool)
        zero = check(client, new, 0, 0)
        # 0분이면 지금 시간표 그대로다(예전에는 3번째 줄이 -60분, 끝나는 시각이 60분 일찍 나왔다).
        assert [r['shift'] for r in zero['rows']] == [0, 0, 0]
        assert [r['start'] for r in zero['rows']] == [t['arrival'] for t in new['timeline']]
        assert zero['finish'] == zero['original_finish'] == new['finish'] and zero['status'] == 'ok'
        ten = check(client, new, 0, 10)
        assert [r['shift'] for r in ten['rows']] == [10, 10, 10]
        assert minutes(ten['finish']) == minutes(new['finish']) + 10
        # 뒤 장소에 넣은 지연을 계산에 넣었다고 알린다.
        assert '다른 산책길' in ten['basis'] and '60분' in ten['basis']


def test_later_delay_can_make_a_later_place_the_problem(pool):
    """뒤 지연이 살아 있어야 영업 종료에 걸리는 장소를 '문제 없음'으로 답하지 않는다."""
    rows = stops(b_closes='22:00', c_hours=[0, hm('19:10')])
    plan, error = evaluate(rows, conditions(), delays={2: 60})
    assert not error, error
    plan = audit_plan(plan)
    plan['delay_recovery'] = dict(delays={'2': 60}, index=2, target=1, action='skip', place='옛 장소', replacement=None)
    # 지금 시간표: C 산책 17:59~18:44(영업 종료 19:10). 1번째부터 40분 더 늦으면 C 는 19:24 에 끝나 영업 종료를 넘긴다.
    result = delay_check(plan, 0, 40)
    assert result['status'] == 'problem' and result['first_problem']['place'] == 'C 산책'


def test_recovery_from_an_earlier_place_keeps_the_later_delay(pool):
    with TestClient(app) as client:
        new = late_at_third(client, pool)
        response = recover(client, new, index=0, minutes=40, target=1, replacement_id=NEAR['id'])
        assert response.status_code == 200, response.text
        newer = response.json()
        # 3번째 장소의 60분은 그대로, 1번째에 40분이 더해진다(예전에는 {'0': 40} 만 남았다).
        assert newer['delay_recovery']['delays'] == {'0': 40, '2': 60}
        assert minutes(newer['timeline'][2]['arrival']) == minutes(with_delays(newer, {0: 40})['timeline'][2]['arrival']) + 60
        assert minutes(newer['finish']) > minutes(new['finish'])
        assert '40분 늦어진 것을 반영해' in newer['change_reason'] and '60분 지연' in newer['change_reason']
        # 새 코스의 지각 확인도 0분이면 그대로다.
        again = check(client, newer, 0, 0)
        assert [r['shift'] for r in again['rows']] == [0, 0, 0] and again['finish'] == newer['finish']


def test_skip_moves_the_later_delay_to_the_new_number(pool):
    with TestClient(app) as client:
        new = late_at_third(client, pool)
        response = recover(client, new, index=0, minutes=40, target=1)  # B 카페를 빼고 진행
        assert response.status_code == 200, response.text
        newer = response.json()
        assert [p['name'] for p in newer['places']] == ['A 전시', '다른 산책길']
        # 다른 산책길이 번호 1 로 당겨졌다 — 그 장소의 60분도 따라간다.
        assert newer['delay_recovery']['delays'] == {'0': 40, '1': 60}
        assert minutes(newer['timeline'][1]['arrival']) == minutes(with_delays(newer, {0: 40})['timeline'][1]['arrival']) + 60
        again = check(client, newer, 0, 0)
        assert [r['shift'] for r in again['rows']] == [0, 0] and again['finish'] == newer['finish']


def late_last_place(client):
    """A 전시 → B 카페(22:00 까지) → C 산책(19:10 까지). 3번째 장소(번호 2)에 60분 지연이 적힌 코스."""
    rows = stops(b_closes='22:00', c_hours=[0, hm('19:10')])
    plan, error = evaluate(rows, conditions(), delays={2: 60})
    assert not error, error
    plan = audit_plan(plan)
    plan['delay_recovery'] = dict(delays={'2': 60}, index=2, target=1, action='skip', place='옛 장소', replacement=None)
    return saved(client, plan)


def test_skipping_the_place_that_held_a_delay_says_the_delay_went_with_it(pool):
    with TestClient(app) as client:
        stored = late_last_place(client)
        response = recover(client, stored, index=0, minutes=40, target=2)  # C 산책을 빼고 진행
        assert response.status_code == 200, response.text
        new = response.json()
        assert [p['name'] for p in new['places']] == ['A 전시', 'B 카페']
        assert new['delay_recovery']['delays'] == {'0': 40}
        # 기준이 된 장소가 빠져 버린 지연은 문장으로 알린다.
        assert 'C 산책에 앞서 반영한 60분 지연' in new['change_reason']


def test_skipping_a_middle_place_that_held_a_delay_does_not_move_it_to_the_next_place(pool):
    """뺀 장소에 앞서 적어 둔 지연은 다음 장소에 붙이지 않는다(기준이 된 장소가 없다 — 82차 합의 코스와 같은 판단). 버리고 알린다."""
    rows = stops(b_closes='18:30')
    plan, error = evaluate(rows, conditions(), delays={1: 60})
    assert not error, error
    plan = audit_plan(plan)
    plan['delay_recovery'] = dict(delays={'1': 60}, index=1, target=2, action='skip', place='옛 장소', replacement=None)
    with TestClient(app) as client:
        stored = saved(client, plan)
        response = recover(client, stored, index=0, minutes=40, target=1)  # B 카페(17:06~17:56 → 40분 더 늦으면 18:30 을 넘김)를 뺀다
        assert response.status_code == 200, response.text
        new = response.json()
        assert [p['name'] for p in new['places']] == ['A 전시', 'C 산책']
        assert new['delay_recovery']['delays'] == {'0': 40}
        assert new['timeline'][1] == with_delays(new, {0: 40})['timeline'][1]
        assert 'B 카페에 앞서 반영한 60분 지연은 그 장소를 빼서 넣지 않았어요' in new['change_reason']


def test_delays_after_removal_rules():
    from app.delay_check import delays_after_removal

    # 뒤 번호는 당기고, 뺀 장소에 적어 둔 지연은 버린다.
    assert delays_after_removal({0: 40, 2: 60}, [1]) == ({0: 40, 1: 60}, {})
    assert delays_after_removal({0: 40, 1: 60}, [1]) == ({0: 40}, {1: 60})
    # 지금 다루는 지연(current)은 그 장소를 빼도 번호에 남고, 그 자리로 온 다음 장소의 지연과 더한다.
    assert delays_after_removal({1: 30, 2: 60}, [1], current=1) == ({1: 90}, {})
    assert delays_after_removal({}, [0]) == ({}, {})


def test_replacing_the_place_that_held_a_delay_keeps_it_in_that_slot(pool):
    pool.append(OTHER_WALK)
    with TestClient(app) as client:
        stored = late_last_place(client)
        shown = check(client, stored, 0, 40)
        assert shown['recovery']['index'] == 2 and shown['recovery']['options'][0]['id'] == OTHER_WALK['id']
        # 후보의 시각도 그 자리의 60분을 넣어 계산돼 있다.
        response = recover(client, stored, index=0, minutes=40, target=2, replacement_id=OTHER_WALK['id'])
        assert response.status_code == 200, response.text
        new = response.json()
        assert new['delay_recovery']['delays'] == {'0': 40, '2': 60}
        assert shown['recovery']['options'][0]['start'] == new['timeline'][2]['arrival']
        assert minutes(new['timeline'][2]['arrival']) == minutes(with_delays(new, {0: 40})['timeline'][2]['arrival']) + 60


def test_kept_note_names_every_carried_delay():
    from app.delay_check import kept_note

    plan = dict(places=[{}, {}, {}], delay_recovery=dict(delays={'0': 40, '2': 60}))
    assert kept_note(plan) == ' 앞서 반영한 지연 2건(40분·60분)은 그대로 뒀어요.'
    assert kept_note(dict(plan, delay_recovery=dict(delays={'0': 40}))) == ' 앞서 반영한 40분 지연은 그대로 뒀어요.'


# --- A2: 장소를 뺀 코스(장소 수 < 요청 수)에서도 후보가 나온다 ---
def skipped(client):
    """A 전시 → C 산책. B 카페를 '빼고 진행'한 코스(요청 3곳, 2곳)."""
    stored = saved(client, course())
    response = recover(client, stored)
    assert response.status_code == 200, response.text
    new = response.json()
    assert [p['name'] for p in new['places']] == ['A 전시', 'C 산책'] and new['conditions']['count'] == 3
    return new


def test_replacement_is_offered_after_skip_and_go_on(pool, monkeypatch):
    monkeypatch.setattr(planner, 'candidates', lambda c: copy.deepcopy([OTHER_WALK]))
    with TestClient(app) as client:
        new = skipped(client)
        listed = client.post(f"/api/plans/{new['id']}/alternatives", json={'index': 1, 'locked': []})
        assert listed.status_code == 200, listed.text
        options = listed.json()['alternatives']
        assert [o['places'][1]['id'] for o in options] == [OTHER_WALK['id']]
        # 후보도 지연을 넣은 시간표다(81차).
        assert options[0]['timeline'][0] == new['timeline'][0]
        response = client.post(f"/api/plans/{new['id']}/replace", json={'index': 1, 'locked': [], 'replacement_id': OTHER_WALK['id']})
        assert response.status_code == 200, response.text
        changed = response.json()
        assert [p['name'] for p in changed['places']] == ['A 전시', '다른 산책길']
        # 요청한 장소 수와 '요청 3곳, 2곳' 안내는 그대로다.
        assert changed['conditions']['count'] == 3
        assert any(r['condition'] == 'count' and r['state'] == 'unmet' for r in changed['condition_checks'])
        assert changed['delay_recovery'] == dict(new['delay_recovery'], kept='place')


def test_replacement_is_offered_after_a_bundle_that_skipped_the_later_place(pool, monkeypatch):
    monkeypatch.setattr(planner, 'candidates', lambda c: copy.deepcopy([place('g9', '가까운 전시', '문화·예술', [hm('10:00'), hm('21:00')], 60, dlat=0.0011)]))
    with TestClient(app) as client:
        stored = saved(client, course(rows=stops(c_hours=[0, hm('17:50')])))
        new = recover(client, stored, replacement_id=NEAR['id']).json()
        assert new['delay_recovery']['also']['action'] == 'skip' and len(new['places']) == 2
        options = client.post(f"/api/plans/{new['id']}/alternatives", json={'index': 0, 'locked': []}).json()['alternatives']
        assert [o['places'][0]['name'] for o in options] == ['가까운 전시']


def test_leisure_is_offered_after_skip_and_go_on(pool, monkeypatch):
    with TestClient(app) as client:
        new = skipped(client)
        sport = dict(copy.deepcopy(new['places'][1]), id='fixture:sport', name='성수 클라이밍 센터', category='레저·활동',
                     themes=['레저·활동'], tags=['climbing'], hours=[0, 1440], price=[0, 0])
        monkeypatch.setattr('app.catalog.places', lambda *args: [sport, *new['places']])
        response = client.post(f"/api/plans/{new['id']}/leisure-options", json={'index': 1, 'locked': []})
        assert response.status_code == 200, response.text
        body = response.json()
        assert [o['place']['id'] for o in body['options']] == ['fixture:sport'], body['diagnostics']
        chosen = client.post(f"/api/plans/{new['id']}/leisure-select", json={'index': 1, 'replacement_id': 'fixture:sport'})
        assert chosen.status_code == 200, chosen.text
        assert chosen.json()['conditions']['count'] == 3


def one_place(client):
    """A 전시 한 곳. 2곳 코스에서 B 카페를 '빼고 진행'한 코스(요청 2곳, 1곳)."""
    rows = stops()[:2]
    plan, error = evaluate(rows, conditions(count=2))
    assert not error, error
    response = recover(client, saved(client, audit_plan(plan)))
    assert response.status_code == 200, response.text
    new = response.json()
    assert [p['name'] for p in new['places']] == ['A 전시'] and new['conditions']['count'] == 2
    return new


def test_replacement_is_offered_for_a_one_place_course(pool, monkeypatch):
    other = place('g9', '가까운 전시', '문화·예술', [hm('10:00'), hm('21:00')], 60, dlat=0.0011)
    monkeypatch.setattr(planner, 'candidates', lambda c: copy.deepcopy([other]))
    with TestClient(app) as client:
        new = one_place(client)
        options = client.post(f"/api/plans/{new['id']}/alternatives", json={'index': 0, 'locked': []}).json()['alternatives']
        assert [o['places'][0]['name'] for o in options] == ['가까운 전시']


def test_order_suggestion_does_not_refuse_a_course_for_its_place_count():
    """장소 수가 요청 수와 달라도(뺀 코스) 순서 견주기 자체는 계산된다 — '다시 계산하지 못해'로 거절하지 않는다."""
    from app.order_suggestion import suggest

    plan, error = evaluate(stops()[:2] + [place('d', 'D 전시', '문화·예술', [0, 1440], 30, dlat=0.004)], conditions(count=4), soft=True)
    assert not error, error
    reason = suggest(audit_plan(plan))['reason'] or ''
    assert '다시 계산하지 못해' not in reason


def test_evaluate_still_checks_the_place_count_for_new_recommendations():
    assert evaluate(stops()[:2], conditions())[1] == '방문 장소 수 불일치'


# --- A3: 끊긴 구간의 수단 예외는 식사·합의 초안에서도 남지 않는다 ---
def with_leg_mode(client, index, mode='transit', **course_args):
    stored = saved(client, course(rows=stops(b_closes='22:00'), **course_args))
    response = client.post(f"/api/plans/{stored['id']}/transport", json={'legs': [{'index': index, 'mode': mode}]})
    assert response.status_code == 200, response.text
    return response.json()


def meal(client, plan, monkeypatch, **where):
    food = food_fixture(monkeypatch, plan)
    response = client.post(f"/api/plans/{plan['id']}/meal-preview", json=dict(restaurant_id=food['id'], locked=[], **where))
    assert response.status_code == 200, response.text
    draft = response.json()
    applied = client.post(f"/api/plans/{plan['id']}/draft-apply", json=dict(token=draft['token']))
    assert applied.status_code == 200, applied.text
    return draft, applied.json()


def test_meal_between_two_places_drops_the_leg_mode_of_the_broken_leg(monkeypatch):
    with TestClient(app) as client:
        plan = with_leg_mode(client, 1)  # A → B 만 대중교통
        assert plan['conditions']['leg_modes'] == [{'from': 'fixture:a', 'to': 'fixture:b', 'mode': 'transit'}]
        draft, applied = meal(client, plan, monkeypatch, after_index=0)  # A 와 B 사이에 식당
        assert [leg['mode'] for leg in applied['legs']] == ['walk'] * 4
        assert draft['plan']['conditions']['leg_modes'] == [] and applied['conditions']['leg_modes'] == []
        # 순서 제안이 '구간마다 수단을 따로 정한 코스'라는 틀린 까닭으로 거절하지 않는다.
        order = client.get(f"/api/plans/{applied['id']}/order-suggestion").json()
        assert '구간마다 이동 수단' not in (order['reason'] or '')


def test_meal_keeps_the_leg_mode_of_a_leg_that_still_exists(monkeypatch):
    with TestClient(app) as client:
        plan = with_leg_mode(client, 2)  # B → C 만 대중교통
        _, applied = meal(client, plan, monkeypatch, after_index=0)
        assert applied['conditions']['leg_modes'] == [{'from': 'fixture:b', 'to': 'fixture:c', 'mode': 'transit'}]
        assert [leg['mode'] for leg in applied['legs']] == ['walk', 'walk', 'walk', 'transit']


def test_stale_car_leg_mode_does_not_claim_a_car_route_check(monkeypatch):
    with TestClient(app) as client:
        plan = with_leg_mode(client, 1, mode='car')
        draft, applied = meal(client, plan, monkeypatch, after_index=0)
        assert applied['conditions']['leg_modes'] == [] and all(leg['mode'] == 'walk' for leg in applied['legs'])
        # 자동차 구간이 없는데 '자동차 길찾기 재조회'를 적지 않는다.
        assert '자동차' not in (draft['plan'].get('route_verification') or '')
        assert '자동차' not in (applied.get('route_verification') or '')


def test_agreement_drops_the_leg_mode_of_a_leg_that_no_longer_exists(monkeypatch):
    with TestClient(app) as client, TestClient(app) as guest:
        plan = with_leg_mode(client, 1)  # A → B 만 대중교통
        a, b, c = (p['id'] for p in plan['places'])
        response = agree(client, guest, plan, monkeypatch, [a, c, b])  # A → C → B: A → B 구간이 없다
        assert response.status_code == 200, response.text
        draft = response.json()
        assert draft['plan']['conditions']['leg_modes'] == []
        applied = client.post(f"/api/plans/{plan['id']}/draft-apply", json=dict(token=draft['token'])).json()
        assert applied['conditions']['leg_modes'] == []


# --- A4: 1곳 남은 코스의 식사 교체 ---
def test_meal_replace_on_a_one_place_course_does_not_leak_a_validation_error(pool, monkeypatch):
    with TestClient(app) as client:
        new = one_place(client)
        food = food_fixture(monkeypatch, new)
        response = client.post(f"/api/plans/{new['id']}/meal-preview", json=dict(restaurant_id=food['id'], locked=[], replace_index=0))
        assert 'validation error' not in response.text and 'pydantic' not in response.text
        assert response.status_code == 200, response.text
        draft = response.json()
        assert [p['id'] for p in draft['plan']['places']] == [food['id']]
        # 요청 수는 모델 하한(2곳)으로 두고, 조건 확인이 '요청 2곳, 1곳'을 알린다.
        assert draft['plan']['conditions']['count'] == 2
        assert any(r['condition'] == 'count' and r['state'] == 'unmet' for r in draft['plan']['condition_checks'])
        applied = client.post(f"/api/plans/{new['id']}/draft-apply", json=dict(token=draft['token']))
        assert applied.status_code == 200, applied.text
        assert [p['id'] for p in applied.json()['places']] == [food['id']]


def test_internal_validation_errors_are_not_shown_as_they_are():
    from app.experience_api import run

    def broken():
        Conditions.model_validate(dict(conditions().model_dump(mode='json'), count=1))

    with pytest.raises(HTTPException) as caught:
        run(broken)
    assert caught.value.status_code == 409
    assert 'validation error' not in str(caught.value.detail) and 'pydantic' not in str(caught.value.detail)
    assert '다시' in caught.value.detail


# --- 공통: 다시 계산하는 길은 하나 ---
def test_only_the_planner_and_plan_rules_call_evaluate_directly():
    """이미 있는 코스를 다시 계산하는 변경 경로는 app/plan_rules.reevaluate 를 쓴다(저장된 지연·종료 허용·장소 수 규칙이 거기 있다).
    planner.evaluate 를 직접 부르면 그 규칙을 빠뜨리기 쉽다 — 80~82차와 2026-11-24 점검 A1·A2 가 모두 그렇게 생겼다.
    새 추천을 만드는 곳만 아래 목록에 둔다. 새 변경 경로를 만들었다면 목록에 더하지 말고 reevaluate 를 쓸 것."""
    allowed = {
        'planner.py',  # evaluate 자체와 추천 탐색
        'plan_rules.py',  # reevaluate
        'best_effort.py',  # 조건에 가까운 대안 탐색(새 추천)
        'recommendation_service.py',  # 새 추천의 자동차 실제 길찾기 확인
    }
    app_dir = Path(__file__).resolve().parents[1] / 'app'
    callers = set()
    for path in app_dir.glob('*.py'):
        code = '\n'.join(line.split('#')[0] for line in path.read_text(encoding='utf-8').splitlines())
        code = re.sub(r'"""[\s\S]*?"""', '', code)
        if re.search(r'(?<![\w.])evaluate\(', code):
            callers.add(path.name)
    assert callers <= allowed, sorted(callers - allowed)
