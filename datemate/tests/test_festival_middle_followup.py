"""코스 중간 축제 후속(2026-11-23, 77차 검토에서 남긴 것 줄이기).

1. 자리 지키기: 이미 중간 축제가 있는 코스를 다시 계산할 때(장소 바꾸기·자동차 실제 길찾기 재확인) 저장된 자리를 먼저 둔다
   (planner.evaluate festival_hint). 못 두면 실패하지 않고 예전 순서로 다시 찾는다.
2. 길찾기 조회 줄이기: 자리를 먼저 두면 쓰지 않을 구간(장소 i → i+1, 마지막 장소 → 행사장)을 실제 길찾기로 조회하지 않는다.
3. 알리기: 바꾼 탓에 축제가 새로 들어가거나 빠지거나 자리가 바뀌면 plan['festival_change'] 한 줄(app/festival_time.change_note).
"""
import copy

from fastapi.testclient import TestClient

from app import store
from app.festival_time import change_note, set_change_note
from app.main import app
from app.models import Conditions
from app.planner import evaluate
from test_festival_middle import cond, planned, save, stops


def after_of(plan):
    visit = plan.get('festival_visit') or {}
    return (visit.get('position'), visit.get('after'))


# --- 1. 자리 지키기 ---
def test_hint_keeps_the_saved_gap_when_an_earlier_gap_also_fits():
    # 장소 3곳·각 60분, 축제 11:15~14:00: 첫 장소 뒤와 둘째 장소 뒤가 모두 맞고 코스 끝은 운영 종료를 넘긴다.
    rows, c = stops(3, stay=60), cond('11:15~14:00', count=3)
    auto, error = evaluate(rows, c)
    assert not error and after_of(auto) == ('middle', 0)
    kept, error = evaluate(rows, c, festival_hint=1)
    assert not error and after_of(kept) == ('middle', 1)
    assert kept['legs'][2]['origin'] == '점검 빛축제 행사장'


def test_hint_that_does_not_fit_falls_back_to_the_usual_order():
    plan = planned()
    c = Conditions.model_validate(plan['conditions'])
    # 장소 사이가 아닌 자리(없는 번호)·시간이 맞지 않는 자리(마지막 장소 뒤)는 실패가 아니라 예전 순서로 다시 찾는다.
    for hint in (5, 1):
        again, error = evaluate(plan['places'], c, festival_hint=hint)
        assert not error and again['festival_visit'] == plan['festival_visit']
    # 축제가 없는 조건에서는 hint 가 있어도 축제 없는 코스 그대로.
    plain_c = cond(hours=None)
    plain, error = evaluate(stops(), plain_c, festival_hint=0)
    assert not error and 'festival_visit' not in plain


def test_leading_festival_is_not_moved_by_a_hint():
    # 맨 앞 고정이 맞는 조건이면 hint 는 무시된다(맨 앞 규칙이 이긴다).
    plan, error = evaluate(stops(), cond('10:00~18:00'), festival_hint=0)
    assert not error and plan['festival_visit']['position'] == 'first'


# --- 2. 길찾기 조회 줄이기 ---
def forced_calls(monkeypatch, rows, c, **kwargs):
    """verify_routes=True 로 다시 계산할 때 실제 길찾기를 강제한 구간 (출발 이름, 도착 이름) 목록.
    테스트에는 길찾기 키가 없으므로 강제 조회는 기록만 하고 추정값으로 답한다."""
    from app import planner
    real, calls = planner.leg, []

    def spy(a, b, conditions, force_api=False):
        if force_api:
            calls.append((a['name'], b['name']))
        return real(a, b, conditions)

    monkeypatch.setattr(planner, 'leg', spy)
    plan, error = evaluate(rows, c, verify_routes=True, **kwargs)
    monkeypatch.setattr(planner, 'leg', real)
    assert not error, error
    return plan, calls


def test_reverifying_with_the_hint_skips_legs_that_are_not_used(monkeypatch):
    # 자동차 3곳·각 60분, 축제 12:30~13:45: 첫 장소 뒤는 개막까지 60분 넘게 기다리고 코스 끝은 운영 종료를 넘겨 둘째 장소 뒤에 둔다.
    rows, c = stops(3, stay=60), cond('12:30~13:45', count=3, transport='car')
    saved, error = evaluate(rows, c)
    assert not error and after_of(saved) == ('middle', 1)
    venue, (a, b, last) = c.origin.name, (p['name'] for p in rows)
    unused = {(b, last), (last, venue)}  # 축제가 사이에 들어가 쓰지 않는 구간, 코스 끝 축제를 시도하느라 부르는 구간
    plain, before = forced_calls(monkeypatch, rows, c)
    assert after_of(plain) == ('middle', 1) and unused <= set(before)  # 고치기 전 순서: 낭비 조회가 있다
    kept, calls = forced_calls(monkeypatch, rows, c, festival_hint=1)
    assert after_of(kept) == ('middle', 1)
    assert calls == [(venue, a), (a, b), (b, venue), (venue, last)]
    assert not unused & set(calls)


def test_car_route_verification_passes_the_saved_gap(monkeypatch):
    from app import planner, recommendation_service
    plan = planned(stops(3, stay=60), cond('12:30~13:45', count=3))
    assert after_of(plan) == ('middle', 1)
    seen = {}

    def fake(places, c, **kwargs):
        seen.update(kwargs)
        return copy.deepcopy(plan), None

    monkeypatch.setattr(planner, 'evaluate', fake)
    recommendation_service._verify_car_routes(Conditions.model_validate(plan['conditions']), [copy.deepcopy(plan)])
    assert seen['festival_hint'] == 1 and seen['verify_routes'] is True


def test_saving_a_changed_car_course_passes_the_gap_and_notes_a_dropped_festival(monkeypatch):
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
        seen = {}

        def fake(places, c, **kwargs):
            seen.update(kwargs)
            return copy.deepcopy(checked), None

        monkeypatch.setattr(planner, 'evaluate', fake)
        result = save_change(updated, stored, owner)
        assert seen['festival_hint'] == 0
        # 다시 계산한 코스에서 축제가 빠졌으면 말없이 빠지지 않고 안내가 붙는다.
        assert 'festival_visit' not in result and '빠져요' in result['festival_change']


# --- 3. 알리기 ---
VISIT = dict(title='빛축제', arrival='11:50', departure='12:50')


def test_change_note_says_what_happened_to_the_festival():
    middle0, middle1 = dict(VISIT, position='middle', after=0), dict(VISIT, position='middle', after=1)
    first, last = dict(VISIT, position='first'), dict(VISIT, position='last')
    assert change_note(None, None) is None
    # 같은 자리에서 시각만 달라진 것은 알리지 않는다.
    assert change_note(middle0, dict(middle0, arrival='11:55', departure='12:55')) is None
    assert change_note(first, dict(first)) is None and change_note(last, dict(last)) is None
    assert change_note(None, middle1) == '‘빛축제’ 축제를 일정에 넣을 수 있게 됐어요(2번째 장소 뒤, 11:50~12:50).'
    assert change_note(None, last) == '‘빛축제’ 축제를 일정에 넣을 수 있게 됐어요(코스 끝, 11:50~12:50).'
    assert change_note(middle0, None) == '‘빛축제’ 축제가 일정에서 빠져요(바꾼 코스로는 운영 시간에 맞지 않아요).'
    assert change_note(middle0, middle1) == '‘빛축제’ 축제 자리가 바뀌어요: 1번째 장소 뒤 → 2번째 장소 뒤(11:50~12:50).'
    assert change_note(last, middle0) == '‘빛축제’ 축제 자리가 바뀌어요: 코스 끝 → 1번째 장소 뒤(11:50~12:50).'


def test_note_from_an_earlier_change_is_cleared():
    original = dict(festival_visit=dict(VISIT, position='middle', after=0))
    updated = dict(festival_visit=dict(VISIT, position='middle', after=0), festival_change='앞선 변경의 안내')
    assert 'festival_change' not in set_change_note(updated, original)


def test_mode_change_that_brings_the_festival_in_says_so(monkeypatch):
    from app import leg_modes, planner
    # 도보로는 개막(12:50)까지 60분 넘게 기다려 축제를 못 넣은 코스. 수단을 바꾼 계산이 축제를 넣어 돌려주면 안내가 붙는다.
    without = planned(c=cond('12:50~14:00'))
    assert 'festival_visit' not in without
    with_festival = planned()
    prepared = leg_modes.prepare_change(without, default='transit')
    monkeypatch.setattr(planner, 'evaluate', lambda *a, **k: (copy.deepcopy(with_festival), None))
    updated, _ = leg_modes.apply_change(without, prepared)
    assert updated['festival_visit']['position'] == 'middle'
    assert '넣을 수 있게 됐어요' in updated['festival_change'] and '1번째 장소 뒤' in updated['festival_change']
    # 축제가 그대로인 수단 변경에는 안내가 없다.
    prepared = leg_modes.prepare_change(with_festival, festival='transit')
    kept, _ = leg_modes.apply_change(with_festival, prepared)
    assert 'festival_change' not in kept


# --- 식사 추가·교체(app/experience.meal_draft): 장소 번호가 밀려도 축제는 같은 장소 뒤에 먼저 둔다 ---
def meal_hint(monkeypatch, **where):
    """식당을 넣거나 바꿀 때 evaluate 에 넘어간 festival_hint 와, 그 결과 코스."""
    from app import experience, planner
    from test_experience import food_fixture
    real, seen = planner.evaluate, []

    def spy(places, c, **kwargs):
        seen.append(kwargs.get('festival_hint'))
        return real(places, c, **kwargs)

    with TestClient(app) as client:
        # 장소 3곳·각 60분, 축제 12:30~13:45 → 둘째 장소(번호 1) 뒤에 있는 중간 축제.
        stored = save(client, planned(stops(3, stay=60), cond('12:30~13:45', count=3, end='22:00')))
        assert after_of(stored) == ('middle', 1)
        food = food_fixture(monkeypatch, stored)
        monkeypatch.setattr(planner, 'evaluate', spy)
        owner = store.owner_of(client.cookies['dm_session'])
        args = dict(after_index=0, replace_index=None)
        args.update(where)
        draft = experience.meal_draft(stored, owner, food['id'], args['after_index'], args['replace_index'], [], 0)
    return seen, draft


def test_meal_added_before_the_festival_shifts_the_gap(monkeypatch):
    # 첫 장소 뒤(번호 1 자리)에 식당을 넣으면 축제 앞 장소가 번호 2 가 된다.
    seen, _ = meal_hint(monkeypatch, after_index=0)
    assert seen[0] == 2


def test_meal_added_after_the_festival_keeps_the_gap(monkeypatch):
    # 마지막 장소 뒤에 넣으면 축제 앞 장소 번호는 그대로 1.
    seen, _ = meal_hint(monkeypatch, after_index=2)
    assert seen[0] == 1


def test_meal_replacing_a_place_keeps_the_gap(monkeypatch):
    # 같은 자리의 장소를 식당으로 바꾸면 번호가 밀리지 않는다.
    seen, _ = meal_hint(monkeypatch, replace_index=2)
    assert seen[0] == 1
