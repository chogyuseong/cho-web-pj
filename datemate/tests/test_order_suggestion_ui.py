"""방문 순서 제안 화면(static/order-suggestion.js): 접힌 상자를 펼치면 줄어드는 순서를 보여 주고, 누르면 새 코스로 바뀐다(휴대폰 폭)."""
from fastapi.testclient import TestClient

from app.main import app
from test_delay_recovery import saved
from test_delay_recovery_ui import NO_OVERFLOW, open_saved
from test_functional_audit import audit_page  # noqa: F401  (브라우저 고정 장치)
from test_order_suggestion import course, stops


def panel(page):
    box = page.locator('#plan-detail details.order-suggestion')
    box.locator('summary').click()
    page.wait_for_function("document.querySelector('#plan-detail .order-suggestion-result p:not(.hint), #plan-detail .order-suggestion-none')", timeout=20000)
    return box


def test_suggested_order_is_applied_on_a_narrow_phone(audit_page):  # noqa: F811
    page, base, errors = audit_page
    with TestClient(app) as client:
        plan = saved(client, course())
        owner = client.cookies['dm_session']
    page.set_viewport_size({'width': 320, 'height': 700})
    open_saved(page, base, plan, owner)
    box = panel(page)
    text = box.locator('.order-suggestion-order').inner_text()
    assert '1. A 전시 → 2. C 산책 → 3. B 카페 순서로 돌면 이동이 약' in text and '분 줄어요' in text
    assert page.evaluate(NO_OVERFLOW)
    box.get_by_role('button', name='이 순서로 바꾸기').click()
    page.wait_for_function('(id)=>selected?.parent===id', arg=plan['id'])
    assert page.evaluate('selected.places.map(p=>p.name)') == ['A 전시', 'C 산책', 'B 카페']
    assert '방문 순서를 바꿔 이동을 추정 기준' in page.locator('#plan-detail').inner_text()
    # 바꾼 코스에서는 더 줄일 순서가 없다는 까닭이 나온다.
    again = panel(page)
    assert '가장 짧거나' in again.locator('.order-suggestion-none').inner_text()
    assert page.evaluate(NO_OVERFLOW)
    assert not errors


def test_no_panel_for_a_single_place_course(audit_page):  # noqa: F811
    page, base, errors = audit_page
    with TestClient(app) as client:
        whole = course()
        one = dict(whole, places=whole['places'][:1], timeline=whole['timeline'][:1], legs=whole['legs'][:1])
        plan = saved(client, one)
        owner = client.cookies['dm_session']
    open_saved(page, base, plan, owner)
    assert page.locator('#plan-detail details.delay-check').count() >= 1
    assert page.locator('#plan-detail details.order-suggestion').count() == 0
    assert not errors
