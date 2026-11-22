"""축제 참석 시간 고정(app/festival_time.py): 고른 축제의 운영 시간에 맞춰 축제 방문을 코스 맨 앞에 두고,
나머지 장소를 그 뒤로 배치하는지. 시간을 모르거나 맞출 수 없으면 코스는 그대로 두고 조건 확인 문장으로 알리는지."""
import copy
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import store
from app.catalog import places
from app.condition_audit import audit_plan
from app.delay_check import delay_check
from app.main import app
from app.models import Conditions
from app.planner import evaluate, minutes
from app.recommendation_summary import festival_context
from test_functional_audit import audit_page  # noqa: F401  (브라우저 고정 장치)

ANCHOR = dict(id='770300', title='점검 빛축제', lat=37.5762, lon=126.9850)
CACHE_KEY = 'festival-detail:v1:770300'


def rows():
    out = copy.deepcopy(places('demo')[:2])
    for p in out:
        p.update(demo=False, hours=[0, 1440], closed_days=[], last_entry=None, breaks=None, price=[1000, 1000], price_unit='person', stay=30)
    return out


def conditions(hours=None, start='11:00', end='19:00', **extra):
    festival = dict(ANCHOR, hours=hours) if hours else dict(ANCHOR)
    return Conditions(mode='real', region='서울', visit_date=date(2026, 10, 24), allow_estimates=True, count=2, budget=200000,
                      max_leg=180, start=start, end=end, festival=festival,
                      origin=dict(name='서울 종로구 · 점검 빛축제 행사장 주변', lat=ANCHOR['lat'], lon=ANCHOR['lon']), **extra)


def planned(c):
    plan, error = evaluate(rows(), c)
    assert not error
    return audit_plan(plan, c)


def festival_check(plan):
    found = [r for r in plan['condition_checks'] if r['condition'] == 'festival']
    assert len(found) == 1
    return found[0]


def test_hours_text_is_used_only_when_it_has_one_clock_range():
    from app.festival_time import hours_range
    assert hours_range('10:00~18:00 (입장 마감 17:00)') == ('one', (600, 1080))
    assert hours_range('10:00 ~ 18:00, 10:00~18:00') == ('one', (600, 1080))
    assert hours_range('18:00~02:00') == ('one', (1080, 1560))
    assert hours_range('평일 10:00~18:00 / 주말 10:00~20:00') == ('many', None)
    assert hours_range('상시 개방') == ('none', None)
    assert hours_range(None) == ('none', None)


def test_open_festival_is_fixed_first_and_places_follow_it():
    plain = planned(conditions())
    fixed = planned(conditions('10:00~18:00 (입장 마감 17:00)'))
    assert 'festival_visit' not in plain
    assert fixed['festival_visit'] == dict(id='770300', title='점검 빛축제', hours='10:00~18:00 (입장 마감 17:00)', position='first',
                                           arrival='11:00', departure='12:00', stay=60, wait=0)
    # 첫 장소는 축제가 끝난 12:00 에 행사장에서 출발한다: 같은 구간이 정확히 체류 60분만큼 늦어진다.
    assert fixed['legs'][0]['origin'] == plain['legs'][0]['origin']
    for a, b in zip(fixed['timeline'], plain['timeline']):
        assert minutes(a['arrival']) - minutes(b['arrival']) == 60
    assert minutes(fixed['timeline'][0]['arrival']) == 720 + fixed['legs'][0]['minutes']
    assert fixed['minutes'] == plain['minutes'] + 60
    check = festival_check(fixed)
    assert check['state'] == 'met' and '11:00~12:00' in check['message'] and '맨 앞에 고정' in check['message']


def test_short_wait_until_the_festival_opens_is_kept_in_the_course():
    plan = planned(conditions('11:30~21:00', stay_minutes=90))
    assert plan['festival_visit']['arrival'] == '11:30' and plan['festival_visit']['departure'] == '13:00'
    assert plan['festival_visit']['wait'] == 30
    assert minutes(plan['timeline'][0]['arrival']) == 780 + plan['legs'][0]['minutes']
    assert '30분 기다려요' in festival_check(plan)['message']


@pytest.mark.parametrize('hours,words', [
    (None, '확인하지 못했어요'),
    ('상시 개방', '읽지 못해'),
    ('평일 10:00~18:00 / 주말 10:00~20:00', '시간대가 여러 개'),
    ('18:00~22:00', '18:00 무렵으로 늦추면'),
    ('20:00~23:00', '20:00부터'),
    ('06:00~10:00', '10:00에 끝나'),
    ('10:00~11:30', '겹치지 않아'),
])
def test_unfixable_festival_keeps_the_course_and_explains_why(hours, words):
    plain = planned(conditions())
    plan = planned(conditions(hours))
    assert 'festival_visit' not in plan
    assert plan['timeline'] == plain['timeline'] and plan['finish'] == plain['finish']
    check = festival_check(plan)
    assert check['state'] == 'unknown' and words in check['message']


def test_course_without_a_festival_has_no_festival_check():
    c = Conditions(mode='real', region='서울', visit_date=date(2026, 10, 24), allow_estimates=True, count=2, budget=200000, max_leg=180)
    plan, error = evaluate(rows(), c)
    assert not error and 'festival_visit' not in plan
    assert not [r for r in audit_plan(plan, c)['condition_checks'] if r['condition'] == 'festival']


def test_saved_conditions_keep_the_hours_so_reopening_gives_the_same_time():
    plan = planned(conditions('10:00~18:00'))
    assert plan['conditions']['festival']['hours'] == '10:00~18:00'
    again, error = evaluate(plan['places'], Conditions.model_validate(plan['conditions']))
    assert not error and again['festival_visit'] == plan['festival_visit'] and again['timeline'] == plan['timeline']
    # 시간이 없던 축제는 저장된 조건 모양이 예전과 같다(hours 키 없음).
    assert 'hours' not in planned(conditions())['conditions']['festival']


def test_festival_context_describes_the_fixed_visit():
    context = festival_context(planned(conditions('10:00~18:00')))
    assert context['hours'] == '10:00~18:00'
    assert any('11:00~12:00' in note for note in context['notes'])
    assert not any('코스에 넣지 않았어요' in note for note in context['notes'])
    late = festival_context(planned(conditions('18:00~22:00')))
    assert any('18:00 무렵으로 늦추면' in note for note in late['notes'])


def test_delay_check_starts_the_first_place_after_the_festival():
    plan = planned(conditions('10:00~18:00'))
    result = delay_check(plan, 0, 0)
    assert result['planned_arrival'] == plan['timeline'][0]['arrival']
    assert result['rows'][0]['shift'] == 0


def test_festival_hours_are_bounded():
    payload = conditions().model_dump(mode='json')
    payload['festival']['hours'] = '가' * 301
    with TestClient(app) as client:
        assert client.post('/api/plans', json=payload).status_code == 422


def test_new_recommendation_reads_hours_from_the_detail_cache_only(monkeypatch):
    from app import recommendation_service

    class Stop(Exception):
        pass

    seen = []

    def capture(data):
        seen.append(data)
        raise Stop

    def no_lookup(*args, **kwargs):
        raise AssertionError('축제 상세를 새로 조회하면 안 된다')

    monkeypatch.setattr(recommendation_service, '_research', capture)
    monkeypatch.setattr('app.festivals.fetch_festival_detail', no_lookup)
    monkeypatch.setattr('httpx.Client.get', no_lookup)
    with TestClient(app):
        store.cache(CACHE_KEY, dict(status='available', hours='10:00~18:00'), 3600)
        # 화면이 보낸 시간은 믿지 않고 서버 캐시 값으로 바꾼다.
        with pytest.raises(Stop):
            recommendation_service.generate(conditions('00:00~23:59'), 'festival-owner')
        assert seen[-1].festival.hours == '10:00~18:00'
        with store.connect() as db:
            db.execute('DELETE FROM cache WHERE key=?', (CACHE_KEY,))
        with pytest.raises(Stop):
            recommendation_service.generate(conditions('00:00~23:59'), 'festival-owner')
        assert seen[-1].festival.hours is None


def test_course_screen_shows_the_fixed_festival_before_the_first_place(audit_page):  # noqa: F811
    page, base, errors = audit_page
    with TestClient(app) as client:
        client.get('/api/places?mode=demo')
        plan, error = evaluate(rows(), conditions('10:00~18:00'))
        assert not error
        saved = store.save_plan(audit_plan(plan), store.owner_of(client.cookies['dm_session']))
        owner = client.cookies['dm_session']
    page.route('**/api/festivals?*', lambda route: route.fulfill(json=dict(status='available', festivals=[], message='')))
    page.context.add_cookies([{'name': 'dm_session', 'value': owner, 'url': base}])
    page.goto(base + '/?plan=' + saved['id'])
    page.wait_for_function('(id)=>selected?.id===id', arg=saved['id'])
    block = page.locator('#plan-detail .festival-visit')
    assert block.count() == 1 and block.is_visible()
    assert '11:00~12:00' in block.inner_text() and '점검 빛축제' in block.inner_text()
    # 축제는 장소 칸(.stop)이 아니다: 장소 순번·지도 표시·교체 단추는 장소 2곳만 센다. 그리고 첫 장소보다 앞에 있다.
    assert page.locator('#plan-detail .stop').count() == 2
    assert page.evaluate("""()=>{const f=document.querySelector('#plan-detail .festival-visit'),s=document.querySelector('#plan-detail .stop');
        return !!(f.compareDocumentPosition(s)&Node.DOCUMENT_POSITION_FOLLOWING);}""")
    text = page.evaluate('fieldItineraryText(selected)')
    assert '11:00~12:00 축제 · 점검 빛축제' in text
    assert text.index('축제 · 점검 빛축제') < text.index('1. ')
    assert not errors


# 저녁 축제: 개막이 코스 시작보다 MAX_WAIT(60분) 넘게 늦으면, 장소를 먼저 돌고 행사장으로 돌아와 축제로 마무리한다.
EVENING = '17:30~22:00'
HOME = dict(name='점검 귀가지', lat=37.5700, lon=126.9800)


def evening(hours=EVENING, start='16:00', end='22:00', **extra):
    return conditions(hours, start=start, end=end, **extra)


def test_evening_festival_closes_the_course_after_the_places():
    plain = planned(evening(hours=None))
    plan = planned(evening())
    visit = plan['festival_visit']
    assert visit['position'] == 'last' and visit['title'] == '점검 빛축제'
    # 장소 일정은 그대로다. 마지막 장소를 떠나 행사장으로 돌아온 뒤, 개막(17:30)까지 기다렸다가 체류 60분.
    assert plan['timeline'] == plain['timeline'] and plan['legs'] == plain['legs']
    back = visit['leg']
    reached = minutes(plain['finish']) + back['minutes'] + back['buffer_minutes']
    assert minutes(visit['arrival']) == max(reached, 1050) and visit['wait'] == minutes(visit['arrival']) - reached
    assert minutes(visit['departure']) == minutes(visit['arrival']) + 60 and visit['stay'] == 60
    assert plan['finish'] == visit['departure'] and plan['minutes'] == minutes(visit['departure']) - 960
    # 돌아오는 구간은 축제 방문 기록 안에만 있다(구간 목록 = 장소 도착 구간 + 귀가). 이름·링크·경로 모양은 싣지 않는다.
    assert set(back) <= {'minutes', 'mode', 'walking', 'status', 'source', 'buffer_minutes', 'cost'}
    assert any(row['category'] == '교통' and row['name'].endswith('행사장') for row in plan['costs'])
    check = festival_check(plan)
    assert check['state'] == 'met' and '마무리' in check['message'] and f"{visit['arrival']}~{visit['departure']}" in check['message']


def test_evening_festival_sends_the_return_home_from_the_venue():
    plan = planned(evening(return_home=True, home=HOME))
    visit = plan['festival_visit']
    assert visit['position'] == 'last'
    assert len(plan['legs']) == len(plan['places']) + 1
    home = plan['legs'][-1]
    assert home['origin'] == '서울 종로구 · 점검 빛축제 행사장 주변' and home['destination'] == '점검 귀가지'
    assert minutes(plan['finish']) == minutes(visit['departure']) + home['minutes'] + home['buffer_minutes']


def test_evening_festival_that_does_not_fit_keeps_the_course_and_explains():
    plain = planned(evening(hours=None, end='18:00'))
    plan = planned(evening(end='18:00'))
    assert 'festival_visit' not in plan
    assert plan['timeline'] == plain['timeline'] and plan['finish'] == plain['finish'] and plan['legs'] == plain['legs']
    check = festival_check(plan)
    assert check['state'] == 'unknown' and '마무리하기에도 시간이 맞지 않았어요' in check['message']


def test_evening_festival_is_kept_when_the_course_is_reopened():
    plan = planned(evening(return_home=True, home=HOME))
    again, error = evaluate(plan['places'], Conditions.model_validate(plan['conditions']))
    assert not error and again['festival_visit'] == plan['festival_visit'] and again['finish'] == plan['finish']


def test_plans_with_the_festival_come_before_plans_without_it():
    from app.planner import prefer_festival
    with_visit, without = dict(festival_visit={'position': 'last'}), dict()
    assert prefer_festival([without, with_visit, without]) == [with_visit]
    assert prefer_festival([without, without]) == [without, without]


def test_delay_check_carries_on_to_the_evening_festival_and_home():
    plan = planned(evening(return_home=True, home=HOME))
    on_time = delay_check(plan, 0, 0)
    assert on_time['finish'] == plan['finish'] and on_time['status'] != 'problem'
    # 일찍 끝나는 축제(19:30)에 두 시간 늦으면 축제 줄에서 처음 문제가 난다.
    short = planned(evening(hours='17:30~19:30', return_home=True, home=HOME))
    assert short['festival_visit']['position'] == 'last'
    late = delay_check(short, 0, 120)
    assert late['status'] == 'problem' and late['first_problem']['kind'] == 'festival'
    assert late['first_problem']['limit'] == '19:30' and late['rows'][-1]['name'] == '축제 · 점검 빛축제'


def test_shared_link_says_where_the_festival_sits():
    from app.sharing import festival_visit
    assert festival_visit(planned(evening()))['position'] == 'last'
    assert festival_visit(planned(conditions('10:00~18:00')))['position'] == 'first'


def test_course_screen_shows_the_evening_festival_after_the_last_place(audit_page):  # noqa: F811
    page, base, errors = audit_page
    with TestClient(app) as client:
        client.get('/api/places?mode=demo')
        plan, error = evaluate(rows(), evening(return_home=True, home=HOME))
        assert not error and plan['festival_visit']['position'] == 'last'
        saved = store.save_plan(audit_plan(plan), store.owner_of(client.cookies['dm_session']))
        owner = client.cookies['dm_session']
    page.route('**/api/festivals?*', lambda route: route.fulfill(json=dict(status='available', festivals=[], message='')))
    page.context.add_cookies([{'name': 'dm_session', 'value': owner, 'url': base}])
    page.goto(base + '/?plan=' + saved['id'])
    page.wait_for_function('(id)=>selected?.id===id', arg=saved['id'])
    block = page.locator('#plan-detail .festival-visit')
    visit = plan['festival_visit']
    assert block.count() == 1 and f"{visit['arrival']}~{visit['departure']}" in block.inner_text()
    assert page.locator('#plan-detail .stop').count() == 2
    # 마지막 장소 뒤, 귀가 구간 앞.
    assert page.evaluate("""()=>{const f=document.querySelector('#plan-detail .festival-visit'),s=[...document.querySelectorAll('#plan-detail .stop')].at(-1);
        return !!(s.compareDocumentPosition(f)&Node.DOCUMENT_POSITION_FOLLOWING);}""")
    assert page.evaluate("""()=>{const f=document.querySelector('#plan-detail .festival-visit'),h=[...document.querySelectorAll('#plan-detail .route-line-text')].find(n=>n.textContent.startsWith('귀가'));
        return !!(f.compareDocumentPosition(h.closest('.route-line-block'))&Node.DOCUMENT_POSITION_FOLLOWING);}""")
    text = page.evaluate('fieldItineraryText(selected)')
    assert text.index('2. ') < text.index('축제 · 점검 빛축제') < text.index('귀가')
    assert not errors
