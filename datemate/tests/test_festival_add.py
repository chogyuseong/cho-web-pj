"""결과 화면 축제 카드의 「+ 내 코스에 추가」(app/festival_add.py, 2026-11-24).

이미 만든 코스(출발지는 사용자의 원래 출발지)에 축제를 끼워 넣는다. 출발지 ≠ 행사장인 코스가 처음 생기므로
행사장 좌표를 축제(conditions.festival)에서 읽는지(festival_time.venue), 맨 앞 자리를 쓰지 않는지,
그리고 지각 확인·지각 복구·수단 바꾸기·차 위치 안내가 그 좌표를 쓰는지를 본다. 출발지 = 행사장인 예전 코스는
test_festival_fixed_time·test_festival_middle 등이 그대로 지킨다.
"""
import copy
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import delay_recovery, store
from app.condition_audit import audit_plan
from app.delay_check import delay_check
from app.festival_time import venue, venue_apart
from app.main import app
from app.models import Conditions
from app.planner import evaluate, minutes, route_leg
from test_festival_middle import stops

DAY = date(2026, 10, 24)
ORIGIN = dict(name='서울 종로구 점검 출발지', lat=37.5700, lon=126.9820)
HOME = dict(name='서울 종로구 점검 집', lat=37.5690, lon=126.9800)
FESTIVAL_ID = '880100'
VENUE = dict(lat=37.5800, lon=126.9900)
LIST_KEY = f'festivals:v5:{DAY}:{DAY}:서울'


def festival_row(**extra):
    row = dict(id=FESTIVAL_ID, title='점검 등축제', start='2026-10-01', end='2026-10-31', region='서울', address='서울특별시 종로구 점검로',
               source_url='https://korean.visitkorea.or.kr/search/search_list.do?keyword=x', image_url=None, image_license=None, **VENUE)
    row.update(extra)
    return row


@pytest.fixture
def listed(monkeypatch):
    """서버가 읽는 축제 목록·상세 캐시(외부 호출 없음). hours(...) 로 상세의 운영 시간을 바꾼다."""
    monkeypatch.setenv('TOUR_API_KEY', 'test-key')

    def put(hours='14:00~20:00', rows=None, detail=True):
        store.cache(LIST_KEY, dict(status='available', festivals=rows or [festival_row()], total_matches=1, truncated=False,
                                   message='점검'), 3600)
        with store.connect() as db:
            db.execute('DELETE FROM cache WHERE key LIKE ?', ('festival-detail:v1:%',))
        if detail:
            store.cache('festival-detail:v1:' + FESTIVAL_ID, dict(status='available', fee='무료', hours=hours, place=None,
                                                                  checked_at='2026-10-24', message=''), 86400)
    put()
    return put


def base_conditions(**extra):
    values = dict(mode='real', region='서울', visit_date=DAY, allow_estimates=True, count=2, budget=200000, max_leg=180,
                  start='10:00', end='19:00', origin=ORIGIN)
    values.update(extra)
    return Conditions(**values)


def base_plan(c=None, rows=None):
    c = c or base_conditions()
    plan, error = evaluate(rows or stops(), c)
    assert not error, error
    return audit_plan(plan, c)


def with_festival(c, hours):
    return Conditions.model_validate(dict(c.model_dump(mode='json'), festival=dict(id=FESTIVAL_ID, title='점검 등축제', hours=hours, **VENUE)))


def save(client, plan):
    client.get('/api/places?mode=demo')
    return store.save_plan(plan, store.owner_of(client.cookies['dm_session']))


def preview(client, plan, festival_id=FESTIVAL_ID):
    return client.post(f"/api/plans/{plan['id']}/festival-preview", json=dict(festival_id=festival_id))


def walk_minutes(a, b, c):
    return route_leg(a, b, c, 'walk')['minutes']


# --- 자리 고르기(플래너 규칙 그대로: 끝 → 중간, 맨 앞은 없음) ---
def test_late_festival_goes_at_the_end_and_the_course_still_starts_at_the_origin():
    c = base_conditions(return_home=True, home=HOME)
    plain = base_plan(c)
    added = with_festival(c, '14:00~20:00')
    assert venue_apart(added) and venue(added) == dict(name='점검 등축제 행사장', **VENUE)
    plan, error = evaluate(plain['places'], added)
    assert not error
    visit = plan['festival_visit']
    assert visit['position'] == 'last' and visit['arrival'] == '14:00'
    # 장소 시간표·첫 구간은 그대로(출발지 그대로).
    assert plan['timeline'] == plain['timeline'] and plan['legs'][0] == plain['legs'][0]
    assert plan['legs'][0]['origin'] == ORIGIN['name']
    # 마지막 장소 → 행사장 구간은 축제 좌표로 계산한다(출발지 좌표가 아니라).
    last = plain['places'][-1]
    assert visit['leg']['minutes'] == walk_minutes(last, venue(added), added) != walk_minutes(last, ORIGIN, added)
    # 귀가는 행사장에서 떠난다 — 출발 좌표가 축제 좌표다.
    home = plan['legs'][-1]
    assert home['origin'] == '점검 등축제 행사장' and f"slat={VENUE['lat']}" in home['link'] and f"slng={VENUE['lon']}" in home['link']


def test_midday_festival_goes_between_places_with_the_venue_coordinates():
    c = base_conditions()
    plain = base_plan(c, stops(2, stay=90))
    added = with_festival(c, '11:30~13:00')
    plan, error = evaluate(plain['places'], added)
    assert not error
    visit = plan['festival_visit']
    assert visit['position'] == 'middle' and visit['after'] == 0
    first = plain['places'][0]
    assert visit['leg']['minutes'] == walk_minutes(first, venue(added), added)
    out = plan['legs'][1]
    assert out['origin'] == '점검 등축제 행사장' and f"slat={VENUE['lat']}" in out['link']
    assert out['minutes'] == walk_minutes(venue(added), plain['places'][1], added)


def test_open_festival_is_never_put_first_when_the_venue_is_not_the_origin():
    c = base_conditions()
    plain = base_plan(c)
    added = with_festival(c, '10:00~18:00')
    # 같은 운영 시간이라도 출발지 = 행사장이면 맨 앞에 고정한다(예전 규칙).
    together = Conditions.model_validate(dict(added.model_dump(mode='json'), origin=dict(name='행사장 주변', **VENUE)))
    assert evaluate(plain['places'], together)[0]['festival_visit']['position'] == 'first'
    plan, error = evaluate(plain['places'], added)
    assert not error and plan['festival_visit']['position'] == 'last'
    assert plan['timeline'] == plain['timeline']
    from app.festival_time import festival_slot, places_start
    assert festival_slot(added) is None and places_start(added) == minutes('10:00')


def test_origin_and_venue_together_keeps_the_old_values():
    c = with_festival(base_conditions(), '10:00~18:00')
    together = Conditions.model_validate(dict(c.model_dump(mode='json'), origin=dict(name='행사장 주변', **VENUE)))
    assert not venue_apart(together) and venue(together) == together.origin.model_dump()


# --- 미리보기 → 확정 → 되돌리기 ---
def test_preview_apply_and_undo(listed):
    with TestClient(app) as client:
        original = save(client, base_plan(base_conditions(return_home=True, home=HOME)))
        response = preview(client, original)
        assert response.status_code == 200, response.text
        draft = response.json()
        plan = draft['plan']
        assert draft['kind'] == 'festival' and draft['can_apply'] is True
        assert '‘점검 등축제’ 축제를 넣고' in draft['summary'] and '요금은 비용에 넣지 않았어요' in draft['summary']
        visit = plan['festival_visit']
        assert visit['position'] == 'last' and visit['hours'] == '14:00~20:00'
        # 서버가 목록·상세에서 정한 근거. 출발지는 그대로.
        assert plan['conditions']['festival'] == dict(id=FESTIVAL_ID, title='점검 등축제', hours='14:00~20:00', **VENUE)
        assert plan['conditions']['origin'] == original['conditions']['origin']
        assert plan['festival_change'] == f"‘점검 등축제’ 축제를 일정에 넣을 수 있게 됐어요(코스 끝, {visit['arrival']}~{visit['departure']})."
        assert draft['delta']['minutes'] == plan['minutes'] - original['minutes'] > 0
        # 축제 요금은 비용 표에 없다. 행사장으로 가는 구간만 교통으로 들어간다.
        assert not any('무료' in str(row) or row.get('category') == '축제' for row in plan['costs'])
        assert any(row['name'] == f"{original['places'][-1]['name']} → 점검 등축제 행사장" for row in plan['costs'])
        context = plan['festival_context']['notes']
        assert '출발지와 장소는 그대로' in context[0] and '행사장으로 가서' in context[1]
        check = next(r for r in plan['condition_checks'] if r['condition'] == 'festival')
        assert check['state'] == 'met'
        # 원래 코스는 그대로다(미리보기는 저장하지 않는다).
        assert 'festival' not in client.get(f"/api/plans/{original['id']}").json()['conditions'] or \
            client.get(f"/api/plans/{original['id']}").json()['conditions']['festival'] is None
        applied = client.post(f"/api/plans/{original['id']}/draft-apply", json=dict(token=draft['token']))
        assert applied.status_code == 200, applied.text
        new = applied.json()
        assert new['id'] != original['id'] and new['parent'] == original['id']
        assert new['festival_visit'] == visit and new['change_reason'] == draft['summary']
        reopened = client.get(f"/api/plans/{new['id']}").json()
        assert reopened['festival_visit'] == visit and reopened['conditions']['festival']['hours'] == '14:00~20:00'
        # 같은 초안을 다시 보내도 코스는 하나만 생긴다.
        assert client.post(f"/api/plans/{original['id']}/draft-apply", json=dict(token=draft['token'])).json()['id'] == new['id']
        undone = client.post(f"/api/plans/{new['id']}/undo").json()
        assert undone['id'] == original['id'] and 'festival_visit' not in undone


def test_reopened_course_recalculates_to_the_same_schedule(listed):
    with TestClient(app) as client:
        original = save(client, base_plan(base_conditions(), stops(2, stay=90)))
        listed('11:30~13:00')
        draft = preview(client, original).json()
        new = client.post(f"/api/plans/{original['id']}/draft-apply", json=dict(token=draft['token'])).json()
    assert new['festival_visit']['position'] == 'middle'
    again, error = evaluate(new['places'], Conditions.model_validate(new['conditions']))
    assert not error and again['festival_visit'] == new['festival_visit'] and again['timeline'] == new['timeline']
    assert again['legs'] == new['legs']


# --- 거절 ---
@pytest.mark.parametrize('hours,words', [
    (None, '운영 시간을 알리지 않아'),
    ('평일 10:00~18:00 / 주말 10:00~20:00', '시간대가 여러 개'),
    ('상시 개방', '시작·끝 시각을 읽지 못해'),
])
def test_unknown_hours_are_refused(listed, hours, words):
    listed(hours)
    with TestClient(app) as client:
        original = save(client, base_plan())
        response = preview(client, original)
        assert response.status_code == 409 and words in response.json()['detail'], response.text


def test_missing_detail_is_refused_without_inventing_hours(listed, monkeypatch):
    listed(detail=False)
    from app import festivals
    monkeypatch.setattr(festivals, 'fetch_festival_detail', lambda content_id: dict(status='unavailable', hours=None))
    with TestClient(app) as client:
        original = save(client, base_plan())
        response = preview(client, original)
    assert response.status_code == 409 and '운영 시간을 지금 확인하지 못했어요' in response.json()['detail']


def test_detail_is_fetched_once_when_not_cached(listed, monkeypatch):
    listed(detail=False)
    from app import festivals
    calls = []
    monkeypatch.setattr(festivals, 'fetch_festival_detail', lambda content_id: calls.append(content_id) or dict(status='available', hours='14:00~20:00'))
    with TestClient(app) as client:
        original = save(client, base_plan())
        response = preview(client, original)
    assert response.status_code == 200, response.text
    assert calls == [FESTIVAL_ID] and response.json()['plan']['conditions']['festival']['hours'] == '14:00~20:00'


def test_screen_values_are_not_used(listed):
    # 화면은 축제 id 만 보낸다. 좌표·시간을 실어 보내도 받지 않는다(extra='forbid').
    with TestClient(app) as client:
        original = save(client, base_plan())
        response = client.post(f"/api/plans/{original['id']}/festival-preview",
                               json=dict(festival_id=FESTIVAL_ID, hours='10:00~23:00', lat=37.0, lon=127.0))
    assert response.status_code == 422


@pytest.mark.parametrize('row,words', [
    (dict(start='2026-11-01', end='2026-11-30'), '방문일(2026-10-24)에는 들를 수 없어요'),
    (dict(lat=None, lon=None), '행사장 위치 정보가 없어'),
    (dict(id='점검 등축제:2026-10-01'), '운영 시간 정보를 받을 수 없어'),
])
def test_festival_data_problems_are_refused(listed, row, words):
    festival_id = row.get('id', FESTIVAL_ID)
    listed(rows=[festival_row(**row)])
    with TestClient(app) as client:
        original = save(client, base_plan())
        response = preview(client, original, festival_id)
    assert response.status_code == 409 and words in response.json()['detail'], response.text


def test_festival_not_in_the_list_is_refused(listed):
    with TestClient(app) as client:
        original = save(client, base_plan())
        response = preview(client, original, '999999')
    assert response.status_code == 409 and '목록에서 이 축제를 찾지 못했어요' in response.json()['detail']


def test_course_with_a_festival_is_refused(listed):
    with TestClient(app) as client:
        original = save(client, base_plan(with_festival(base_conditions(), '14:00~20:00')))
        assert original['festival_visit']['position'] == 'last'
        same = preview(client, original)
        assert same.status_code == 409 and '이미 이 코스에 들어 있어요' in same.json()['detail']
        other = preview(client, original, '880200')
        assert other.status_code == 409 and '축제를 하나만' in other.json()['detail']


@pytest.mark.parametrize('hours,extra,words', [
    # 운영이 코스 종료 뒤에 시작한다.
    ('20:00~22:00', {}, '코스가 끝나는 19:00 뒤'),
    # 행사장까지 걸어서 20분 남짓인데 구간 이동 제한 15분 — 끝에도 중간에도 둘 수 없다.
    ('14:00~20:00', dict(max_leg=15), '구간 이동 제한(15분)'),
    # 종료 시각이 빠듯해 행사장에 들르면 넘긴다(축제 없이는 13:10, 중간에 들르면 14:49 에 끝난다).
    ('11:30~13:00', dict(end='14:40'), '종료 시각(14:40)'),
])
def test_course_without_room_is_refused(listed, hours, extra, words):
    listed(hours)
    with TestClient(app) as client:
        original = save(client, base_plan(base_conditions(**extra), stops(2, stay=90)))
        response = preview(client, original)
    assert response.status_code == 409 and words in response.json()['detail'], response.text
    assert '넣을 자리가 없어요' in response.json()['detail']


def test_demo_course_is_refused(listed):
    with TestClient(app) as client:
        plan = client.post('/api/plans', json=dict(visit_date='2026-10-24', max_leg=180, budget=1000000)).json()['plans'][0]
        response = preview(client, plan)
    assert response.status_code == 409 and '실제 축제를 넣을 수 없어요' in response.json()['detail']


def test_other_browser_gets_404(listed):
    with TestClient(app) as owner, TestClient(app) as other:
        original = save(owner, base_plan())
        other.get('/api/places?mode=demo')
        assert preview(other, original).status_code == 404
        draft = preview(owner, original).json()
        assert other.post(f"/api/plans/{original['id']}/draft-apply", json=dict(token=draft['token'])).status_code == 404


def test_best_effort_course_is_refused_when_the_festival_breaks_the_end_time(listed):
    # 조건 차이가 있던 코스(soft 계산)라도 축제 때문에 종료 시각을 넘기게 되면 넣지 않는다.
    listed('14:00~20:00')
    c = base_conditions(end='14:30')
    plan = base_plan(c, stops(2, stay=90))
    plan['best_effort'] = True
    with TestClient(app) as client:
        original = save(client, plan)
        response = preview(client, original)
    assert response.status_code == 409 and '종료 시각(14:30)을 넘겨요' in response.json()['detail'], response.text


# --- 새 코스에서 지각 확인·지각 복구·수단 바꾸기·차 위치 ---
def added_middle(listed):
    listed('11:30~13:00')
    with TestClient(app) as client:
        original = save(client, base_plan(base_conditions(), stops(2, stay=90)))
        draft = preview(client, original).json()
        new = client.post(f"/api/plans/{original['id']}/draft-apply", json=dict(token=draft['token'])).json()
        return new, store.owner_of(client.cookies['dm_session'])


def test_delay_check_uses_the_saved_venue_legs(listed):
    plan, _ = added_middle(listed)
    check = delay_check(plan, 0, 0)
    assert [row['name'] for row in check['rows']] == [plan['places'][0]['name'], '축제 · 점검 등축제', plan['places'][1]['name']]
    assert check['finish'] == plan['finish'] and check['rows'][1]['start'] == plan['festival_visit']['arrival']
    assert any(e['leg'] == f"{plan['places'][0]['name']} → 점검 등축제 행사장" for e in check['estimated_legs'])


def test_delay_recovery_starts_from_the_venue_not_the_origin(listed, monkeypatch):
    plan, _ = added_middle(listed)
    c = Conditions.model_validate(plan['conditions'])
    assert delay_recovery._previous_point(plan, c, 1, plan['places']) == venue(c)
    assert delay_recovery._previous_point(plan, c, 0, plan['places']) == ORIGIN
    assert delay_recovery._next_point(plan, c, 0, plan['places']) == venue(c)
    late = plan['places'][1]
    replacement = dict(copy.deepcopy(late), id='fixture:add1', name='가까운 대체', hours=[0, 1440], lat=late['lat'] + 0.0003)
    monkeypatch.setattr(delay_recovery, 'candidate_pool', lambda p, cc: copy.deepcopy([replacement]))
    rows = copy.deepcopy(plan)
    rows['places'][1]['hours'] = [0, minutes(plan['timeline'][1]['departure'])]
    check = delay_check(rows, 1, 30)
    assert check['first_problem']['place'] == late['name']
    rec = delay_recovery.recovery_for(rows, check)
    option = rec['options'][0]
    assert option['legs'][0] == delay_recovery._estimate(venue(c), replacement, c)['minutes'] != \
        delay_recovery._estimate(ORIGIN, replacement, c)['minutes']


def test_transport_change_keeps_the_venue_coordinates(listed):
    plan, _ = added_middle(listed)
    with TestClient(app) as client:
        client.get('/api/places?mode=demo')
        stored = store.save_plan(copy.deepcopy(plan), store.owner_of(client.cookies['dm_session']))
        response = client.post(f"/api/plans/{stored['id']}/transport", json=dict(festival='transit'))
        assert response.status_code == 200, response.text
        updated = response.json()
    c = Conditions.model_validate(updated['conditions'])
    visit = updated['festival_visit']
    assert visit['position'] == 'middle' and visit['leg']['mode'] == 'transit'
    assert visit['leg']['minutes'] == route_leg(plan['places'][0], venue(c), c, 'transit')['minutes']
    assert f"slat={VENUE['lat']}" in updated['legs'][1]['link']


def test_car_position_notes_treat_the_venue_as_its_own_place(listed):
    from app.leg_modes import car_position_notes
    plan, _ = added_middle(listed)
    plan = copy.deepcopy(plan)
    # 행사장 → 둘째 장소만 자동차: 차는 출발지에 있으므로(행사장이 출발지가 아니다) 안내가 나온다.
    plan['legs'][1]['mode'] = 'car'
    notes = car_position_notes(plan)
    assert len(notes) == 1 and '차는 서울 종로구 점검 출발지 근처' in notes[0]


def test_shared_view_says_the_venue_is_visited_not_returned_to(listed):
    from app.sharing import festival_visit
    plan, _ = added_middle(listed)
    assert festival_visit(plan)['apart'] is True
