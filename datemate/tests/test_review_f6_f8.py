"""점검 보고서 2026-11-24 F6~F8(docs/reviews/2026-11-24-full-review.md).

- F6: 되돌리기 단추 문구가 응답에만 있는 transport_change 에 기대, 고정 토글·새로고침 뒤 '수단 변경 되돌리기'가 '교체 되돌리기'로 바뀌었다.
  → 수단 변경으로 만든 코스는 저장된 표시(change_kind='transport')로 문구를 정한다. 다음 변경은 그 표시를 물려받지 않는다.
- F7: 고정 토글·제보 저장처럼 같은 코스를 다시 그리면 지각 확인·순서 제안 상자가 접히고 입력·결과가 사라졌다.
  → 같은 코스면 열림·입력·결과를 그대로 두고, 고정 장소만 바뀌었으면 같은 입력으로 다시 계산해 그렇다고 알린다.
- F8: 순서 제안을 한 번 받은 뒤에는 닫았다 열어도 다시 묻지 않았다(409 의 '다시 열어 주세요'가 통하지 않음). → 열 때마다 다시 묻는다.
"""
import copy

from fastapi.testclient import TestClient

from app import store
from app.main import app
from test_delay_recovery import conditions, course, pool, saved, stops  # noqa: F401  (pool: 후보 고정 장치)
from test_delay_recovery_ui import open_saved, run_check
from test_functional_audit import audit_page, wait_for_selected_detail  # noqa: F401  (브라우저 고정 장치)
from test_order_suggestion import course as order_course


def toggle_lock(page, index, locked):
    """index 번째 장소의 고정 단추를 누르고, 서버가 준 코스로 상세를 다시 그릴 때까지 기다린다."""
    stop = page.locator('#plan-detail article.stop').nth(index)
    stop.get_by_role('button', name='● 고정됨' if not locked else '○ 장소 고정').click()
    page.wait_for_function('([i,on])=>Object.keys(selected.conditions.locked||{}).includes(String(i))===on', arg=[index, locked])
    wait_for_selected_detail(page)
    page.wait_for_function(
        "([i,on])=>[...document.querySelectorAll('#plan-detail article.stop')[i].querySelectorAll('button')].some(b=>b.textContent===(on?'● 고정됨':'○ 장소 고정'))",
        arg=[index, locked])


def redraw_same_course(page):
    """제보 저장(experience.js showPlaceReport)과 같은 다시 그리기: 같은 코스를 서버에서 다시 받아 commitPlanChange 로 그린다."""
    page.evaluate("document.querySelector('#plan-detail .detail').dataset.stale='1'")
    page.evaluate("(async()=>{const r=await api('/plans/'+selected.id);commitPlanChange(selected.id,r)})()")
    page.wait_for_function("document.querySelector('#plan-detail .detail')&&!document.querySelector('#plan-detail .detail').dataset.stale")


def count_order_requests(page):
    asked = []
    page.on('request', lambda r: asked.append(r.url) if '/api/plans/' in r.url and r.url.endswith('/order-suggestion') else None)
    return asked


def order_box_open(page):
    return page.evaluate("document.querySelector('#plan-detail details.order-suggestion')?.open")


def wait_order_result(page):
    page.wait_for_function("document.querySelector('#plan-detail .order-suggestion-result p:not(.hint), #plan-detail .order-suggestion-none')", timeout=20000)


# --- F7: 지각 확인 상자 ---
def test_delay_check_keeps_open_inputs_and_result_when_a_lock_changes_elsewhere(audit_page, pool):  # noqa: F811
    page, base, errors = audit_page
    with TestClient(app) as client:
        plan = saved(client, course())
        owner = client.cookies['dm_session']
    open_saved(page, base, plan, owner)
    run_check(page, index='0', minutes='40')
    page.locator('#plan-detail .delay-recovery-options li').first.wait_for()
    # 문제와 관계없는 C 산책(3번)을 고정한다. 같은 코스 id 로 상세를 다시 그린다.
    toggle_lock(page, 2, True)
    box = page.locator('#plan-detail details.delay-check')
    assert box.evaluate('d=>d.open')
    assert box.locator('input[type=number]').input_value() == '40'
    assert box.locator('select').input_value() == '0'
    page.wait_for_function("document.querySelectorAll('#plan-detail .delay-recovery-options li').length===3", timeout=20000)
    assert '고정한 장소가 바뀌어' in box.locator('.delay-check-result').inner_text()
    assert not errors


def test_unlocking_as_advised_shows_the_alternatives(audit_page, pool):  # noqa: F811
    page, base, errors = audit_page
    rows = stops()
    with TestClient(app) as client:
        plan = saved(client, course(c=conditions(locked={1: rows[1]['id']}), rows=rows))
        owner = client.cookies['dm_session']
    open_saved(page, base, plan, owner)
    box = run_check(page, index='0', minutes='40')
    assert '고정을 풀면 대신 갈 곳을 고를 수 있어요' in box.locator('.delay-recovery-blocked').inner_text()
    # 안내대로 B 카페(2번)의 고정을 푼다 → 같은 입력으로 다시 확인해 대신 갈 곳이 나온다.
    toggle_lock(page, 1, False)
    box = page.locator('#plan-detail details.delay-check')
    assert box.evaluate('d=>d.open')
    assert box.locator('input[type=number]').input_value() == '40'
    page.wait_for_function("document.querySelectorAll('#plan-detail .delay-recovery-options li').length===3", timeout=20000)
    assert page.locator('#plan-detail .delay-recovery-blocked').count() == 0
    assert '고정한 장소가 바뀌어 같은 조건으로 다시 확인했어요' in box.locator('.delay-check-result').inner_text()
    assert not errors


def test_delay_check_input_survives_a_same_course_redraw(audit_page, pool):  # noqa: F811
    # 제보 저장(experience.js showPlaceReport)은 같은 코스를 다시 받아 commitPlanChange 로 다시 그린다. 확인 전 입력도 남는다.
    page, base, errors = audit_page
    with TestClient(app) as client:
        plan = saved(client, course())
        owner = client.cookies['dm_session']
    open_saved(page, base, plan, owner)
    box = page.locator('#plan-detail details.delay-check')
    box.locator('summary').click()
    box.locator('select').select_option('1')
    box.locator('input[type=number]').fill('25')
    redraw_same_course(page)
    box = page.locator('#plan-detail details.delay-check')
    assert box.evaluate('d=>d.open')
    assert box.locator('input[type=number]').input_value() == '25' and box.locator('select').input_value() == '1'
    assert not errors


# --- F7·F8: 순서 제안 상자 ---
def test_order_suggestion_survives_a_report_redraw_and_asks_again_when_reopened(audit_page):  # noqa: F811
    page, base, errors = audit_page
    with TestClient(app) as client:
        plan = saved(client, order_course())
        owner = client.cookies['dm_session']
    asked = count_order_requests(page)
    open_saved(page, base, plan, owner)
    page.locator('#plan-detail details.order-suggestion summary').click()
    wait_order_result(page)
    assert len(asked) == 1
    order = page.locator('#plan-detail .order-suggestion-order').inner_text()
    # 제보 저장과 같은 다시 그리기(같은 코스 id·같은 고정). 상자는 열린 채, 결과는 그대로이고 다시 묻지 않는다.
    redraw_same_course(page)
    assert order_box_open(page)
    assert page.locator('#plan-detail .order-suggestion-order').inner_text() == order
    assert page.locator('#plan-detail .order-suggestion').get_by_role('button', name='이 순서로 바꾸기').count() == 1
    assert len(asked) == 1
    # F8: 닫았다 열면 다시 묻는다.
    page.locator('#plan-detail details.order-suggestion summary').click()
    page.wait_for_function("!document.querySelector('#plan-detail details.order-suggestion').open")
    page.locator('#plan-detail details.order-suggestion summary').click()
    wait_order_result(page)
    page.wait_for_timeout(300)
    assert len(asked) == 2 and order_box_open(page)
    assert not errors


def test_order_suggestion_reasks_after_a_lock_change(audit_page):  # noqa: F811
    page, base, errors = audit_page
    with TestClient(app) as client:
        plan = saved(client, order_course())
        owner = client.cookies['dm_session']
    asked = count_order_requests(page)
    open_saved(page, base, plan, owner)
    page.locator('#plan-detail details.order-suggestion summary').click()
    wait_order_result(page)
    toggle_lock(page, 2, True)
    assert order_box_open(page)
    page.wait_for_function("document.querySelector('#plan-detail .order-suggestion-refreshed')", timeout=20000)
    wait_order_result(page)
    assert len(asked) == 2
    assert not errors


def test_order_suggestion_409_then_reopen_asks_again(audit_page):  # noqa: F811
    # 보고서의 재현: 가짜 409 를 받은 뒤 안내대로 상자를 닫았다 열면 다시 묻는다.
    page, base, errors = audit_page
    with TestClient(app) as client:
        plan = saved(client, order_course())
        owner = client.cookies['dm_session']
    asked = count_order_requests(page)
    open_saved(page, base, plan, owner)
    page.route('**/reorder', lambda route: route.fulfill(status=409, json=dict(detail='순서 제안이 바뀌었어요. 순서 제안을 다시 열어 주세요.')))
    page.locator('#plan-detail details.order-suggestion summary').click()
    wait_order_result(page)
    page.locator('#plan-detail .order-suggestion').get_by_role('button', name='이 순서로 바꾸기').click()
    page.wait_for_function("document.querySelector('#plan-detail .order-suggestion-status')?.textContent.includes('다시 열어')")
    page.locator('#plan-detail details.order-suggestion summary').click()
    page.locator('#plan-detail details.order-suggestion summary').click()
    page.wait_for_function("!document.querySelector('#plan-detail .order-suggestion-status')?.textContent.includes('다시 열어')", timeout=20000)
    wait_order_result(page)
    assert len(asked) == 2
    assert not errors


# --- F6: 되돌리기 단추 문구 ---
def test_transport_change_is_remembered_in_the_saved_course(pool):  # noqa: F811
    from app.plan_changes import save_change
    with TestClient(app) as client:
        stored = saved(client, course())
        changed = client.post(f"/api/plans/{stored['id']}/transport", json={'default': 'transit'}).json()
        assert changed['change_kind'] == 'transport'
        assert client.get(f"/api/plans/{changed['id']}").json()['change_kind'] == 'transport'
        # 고정 토글 응답에도 남는다(같은 저장 자료).
        locked = client.post(f"/api/plans/{changed['id']}/locks", json={'locked': [0]}).json()
        assert locked['change_kind'] == 'transport'
        # 그 코스에서 다른 변경을 하면 표시를 물려받지 않는다.
        owner = store.owner_of(client.cookies['dm_session'])
        assert 'change_kind' not in save_change(copy.deepcopy(locked), locked, owner)
        # 처음 만든 코스에는 표시가 없다.
        assert 'change_kind' not in client.get(f"/api/plans/{stored['id']}").json()


def test_transport_undo_label_survives_reload_and_lock_toggle(audit_page, pool):  # noqa: F811
    page, base, errors = audit_page
    with TestClient(app) as client:
        stored = saved(client, course())
        changed = client.post(f"/api/plans/{stored['id']}/transport", json={'default': 'transit'}).json()
        owner = client.cookies['dm_session']
    open_saved(page, base, changed, owner)
    undo = page.locator('#plan-detail .undo-actions button')
    assert undo.inner_text() == '수단 변경 되돌리기'
    toggle_lock(page, 0, True)
    assert page.locator('#plan-detail .undo-actions button').inner_text() == '수단 변경 되돌리기'
    assert not errors
