"""'늦어지면 어디서 문제가 생길까?' 상자(static/delay-check.js)를 휴대폰 폭에서 직접 눌러 본다."""
from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401 (fixture)


def test_delay_check_answers_on_a_phone_and_changes_nothing(audit_page):
    page, _, _ = audit_page
    generate(page)
    wait_for_selected_detail(page)
    page.set_viewport_size({'width': 390, 'height': 844})
    before = page.evaluate('JSON.stringify({id:selected.id,places:selected.places.map(p=>p.id),count:plans.length})')
    box = page.locator('#plan-detail details.delay-check')
    box.locator('summary').click()
    box.locator('select').select_option('1')
    box.locator('input[type=number]').fill('10')
    box.get_by_role('button', name='확인').click()
    result = box.locator('.delay-check-result')
    page.wait_for_function("document.querySelector('#plan-detail .delay-check-basis')", timeout=20000)
    text = result.inner_text()
    second = page.evaluate('selected.places[1].name')
    assert f'{second}의 원래 도착 예정 시각' in text and '10분 늦는다고 보고' in text
    # 결론 세 갈래(2026-11-24 말하듯이 다듬은 문구, static/delay-check.js delayCheckView).
    assert any(word in text for word in ('그대로 가면 돼요', '여기서 처음 문제가 생겨요', '시간표로는 괜찮아 보여요'))
    assert result.locator('li').count() >= 1
    # 범위 밖 값은 서버에 보내지 않고 바로 알려 준다.
    box.locator('input[type=number]').fill('500')
    box.get_by_role('button', name='확인').click()
    assert '0~180분' in result.inner_text()
    assert page.evaluate('JSON.stringify({id:selected.id,places:selected.places.map(p=>p.id),count:plans.length})') == before
    assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth')
