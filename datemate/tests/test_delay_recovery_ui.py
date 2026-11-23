"""지각 복구 화면(static/delay-check.js delayRecoveryBlock): 문제 장소 줄 아래 '대신 갈 곳'과 [빼고 진행]을 휴대폰 폭에서 눌러 본다."""
import json

from fastapi.testclient import TestClient

from app.main import app
from test_delay_recovery import LATE_C, LATE_WALK, NEAR, course, pool, saved, stops  # noqa: F401  (pool: 후보 고정 장치)
from test_functional_audit import audit_page, wait_for_selected_detail  # noqa: F401  (브라우저 고정 장치)

NO_OVERFLOW = 'document.documentElement.scrollWidth<=document.documentElement.clientWidth'


def open_saved(page, base, plan, owner):
    page.route('**/api/festivals?*', lambda route: route.fulfill(json=dict(status='available', festivals=[], message='')))
    page.context.add_cookies([{'name': 'dm_session', 'value': owner, 'url': base}])
    page.goto(base + '/?plan=' + plan['id'])
    page.wait_for_function('(id)=>selected?.id===id', arg=plan['id'])
    wait_for_selected_detail(page)


def run_check(page, index='0', minutes='40'):
    box = page.locator('#plan-detail details.delay-check')
    if not page.evaluate("document.querySelector('#plan-detail details.delay-check').open"):
        box.locator('summary').click()
    box.locator('select').select_option(index)
    box.locator('input[type=number]').fill(minutes)
    box.get_by_role('button', name='확인').click()
    page.wait_for_function("document.querySelector('#plan-detail .delay-check-basis')", timeout=20000)
    return box


def test_replace_on_a_phone_saves_a_new_course_and_keeps_checks(audit_page, pool):  # noqa: F811
    page, base, errors = audit_page
    with TestClient(app) as client:
        plan = saved(client, course())
        owner = client.cookies['dm_session']
    page.set_viewport_size({'width': 390, 'height': 844})
    # 바꾸기 전 코스에서 체크한 장소별 항목(A 확인)은 새 코스로 이어받고, 빠진 B 의 항목은 따라오지 않는다.
    page.add_init_script(f"localStorage.setItem('datemate:action-card:{plan['id']}', {json.dumps(json.dumps(['check:fixture:a', 'check:fixture:b', 'depart']))})")
    open_saved(page, base, plan, owner)
    box = run_check(page)
    block = box.locator('.delay-check-bad .delay-recovery')
    block.wait_for()
    assert '대신 갈 곳 · 같은 종류(카페)' in block.inner_text()
    options = block.locator('.delay-recovery-options li')
    assert options.count() == 3
    assert '영업시간 미확인' in options.nth(2).inner_text()
    choose = block.get_by_role('button', name='B 카페 대신 가까운 늦은 카페로 바꾸기')
    assert choose.count() == 1
    assert block.get_by_role('button', name='B 카페 빼고 진행').count() == 1
    assert page.evaluate(NO_OVERFLOW)
    page.set_viewport_size({'width': 320, 'height': 700})
    assert page.evaluate(NO_OVERFLOW)
    # 키보드로 고른다.
    choose.focus()
    page.keyboard.press('Enter')
    page.wait_for_function('(id)=>selected?.parent===id', arg=plan['id'])
    new_id = page.evaluate('selected.id')
    assert page.evaluate('selected.places.map(p=>p.id)')[1] == NEAR['id']
    notice = page.locator('#plan-detail .delay-recovery-notice')
    assert '40분 늦어진 것을 반영해 B 카페를 가까운 늦은 카페로 바꾸고' in notice.inner_text()
    page.wait_for_function("document.activeElement?.classList.contains('delay-recovery-notice')")
    assert page.locator('#plan-detail .undo-actions button').inner_text() == '지각 반영 되돌리기'
    # 복구한 코스의 상자는 같은 장소·0분으로 열려 있다.
    assert page.locator('#plan-detail details.delay-check').evaluate('d=>d.open')
    assert page.locator('#plan-detail details.delay-check input[type=number]').input_value() == '0'
    assert page.evaluate(NO_OVERFLOW)
    carried = page.evaluate(f"JSON.parse(localStorage.getItem('datemate:action-card:{new_id}')||'[]')")
    assert 'check:fixture:a' in carried and 'check:fixture:b' not in carried and 'depart' not in carried
    assert not errors


def test_skip_on_a_narrow_phone(audit_page, pool):  # noqa: F811
    page, base, errors = audit_page
    with TestClient(app) as client:
        plan = saved(client, course())
        owner = client.cookies['dm_session']
    page.set_viewport_size({'width': 320, 'height': 700})
    open_saved(page, base, plan, owner)
    box = run_check(page)
    box.locator('.delay-recovery').get_by_role('button', name='B 카페 빼고 진행').click()
    page.wait_for_function('(id)=>selected?.parent===id', arg=plan['id'])
    assert page.evaluate('selected.places.map(p=>p.name)') == ['A 전시', 'C 산책']
    assert 'B 카페를 빼고' in page.locator('#plan-detail .delay-recovery-notice').inner_text()
    assert page.evaluate(NO_OVERFLOW)
    assert not errors


def test_no_buttons_when_the_course_cannot_be_changed(audit_page):  # noqa: F811
    page, _, _ = audit_page
    data = dict(index=0, delay=40, basis='기준', status='problem', pending=[], estimated_legs=[], no_last_entry=[],
                first_problem=dict(place='B', time='16:46', reason='영업시간 밖 방문', kind='closing', limit='17:30', over=6),
                rows=[dict(name='A', arrival='15:43', start='15:43', departure='16:43', wait=0, shift=40, stay=60, state='ok', missing=[]),
                      dict(name='B', arrival='16:46', start='16:46', departure='17:36', wait=0, shift=40, stay=50, state='problem', missing=[])],
                recovery=dict(index=1, place='B', kind='카페', blocked=None, note=None,
                              options=[dict(id='x', name='X', distance_m=100, extra_minutes=1, hours_known=True, closes='22:00',
                                            start='16:46', departure='17:36', over_end=0)],
                              skip=dict(allowed=True, reason='B를 빼면')))  # fmt: skip
    count = """([data, plan])=>{const box=document.createElement('div');box.append(...delayCheckView(data, plan));
      return box.querySelectorAll('.delay-recovery button').length;}"""
    assert page.evaluate(count, [data, dict(id='p1', places=[])]) == 2
    assert page.evaluate(count, [data, dict(id='p1', places=[], can_edit=False)]) == 0
    assert page.evaluate(count, [data, dict(id='p1', places=[dict(naver_expired=True)])]) == 0
    reserved = dict(data, recovery=dict(data['recovery'], blocked='예약한 곳이라 대신 갈 곳을 고르지 않았어요. 예약처에 연락해 …', options=[], skip=None))
    text = page.evaluate("""([data, plan])=>{const box=document.createElement('div');box.append(...delayCheckView(data, plan));
      return [box.querySelectorAll('.delay-recovery button').length, box.textContent];}""", [reserved, dict(id='p1', places=[])])
    assert text[0] == 0 and '예약처에 연락' in text[1]
    none = dict(data, recovery=dict(data['recovery'], options=[], note='이 동네 후보에 같은 종류(카페)의 다른 곳이 없어요.'))
    text = page.evaluate("""([data, plan])=>{const box=document.createElement('div');box.append(...delayCheckView(data, plan));
      return box.textContent;}""", [none, dict(id='p1', places=[])])
    assert '대체 후보 없음 — 이 동네 후보에 같은 종류(카페)의 다른 곳이 없어요.' in text


def test_bundle_on_a_narrow_phone_changes_two_places_at_once(audit_page, pool):  # noqa: F811
    """묶음 후보: B 를 바꿔도 뒤 C 가 또 늦으면 그 줄에 까닭과 함께 바꿀 곳을 적고, 단추 하나로 두 곳을 바꾼다."""
    page, base, errors = audit_page
    pool.append(LATE_WALK)
    with TestClient(app) as client:
        plan = saved(client, course(rows=stops(**LATE_C)))
        owner = client.cookies['dm_session']
    page.set_viewport_size({'width': 320, 'height': 700})
    open_saved(page, base, plan, owner)
    box = run_check(page)
    block = box.locator('.delay-check-bad .delay-recovery')
    block.wait_for()
    first = block.locator('.delay-recovery-options li').first
    also = first.locator('.delay-recovery-also').inner_text()
    assert 'C 산책에서 영업 종료(17:50)' in also and '늦게까지 여는 산책길로 함께 바꿔요' in also
    choose = first.get_by_role('button', name='B 카페 대신 가까운 늦은 카페로 바꾸기, C 산책은 늦게까지 여는 산책길로 함께 바꾸기')
    assert choose.inner_text() == '두 곳 함께 바꾸기'
    assert page.evaluate(NO_OVERFLOW)
    choose.click()
    page.wait_for_function('(id)=>selected?.parent===id', arg=plan['id'])
    assert page.evaluate('selected.places.map(p=>p.name)') == ['A 전시', '가까운 늦은 카페', '늦게까지 여는 산책길']
    notice = page.locator('#plan-detail .delay-recovery-notice').inner_text()
    assert 'B 카페를 가까운 늦은 카페로 바꾸고 C 산책을 늦게까지 여는 산책길로 바꾸고' in notice
    assert page.evaluate(NO_OVERFLOW)
    assert not errors
