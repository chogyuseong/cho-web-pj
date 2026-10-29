from test_functional_audit import audit_page,generate


def test_reviewed_idea_buffer_feedback_and_nearby_replacements(audit_page):
    page,base,errors=audit_page
    reviewed=page.locator('.inspiration-card').filter(has_text='운영 자료를 확인한 박물관')
    reviewed.get_by_role('button').click()
    assert page.locator('[name=count]').input_value()=='2'
    assert not page.locator('[name=include_meal]').is_checked()
    page.evaluate("form.elements.request.value='';FormState.edited.clear()")
    page.locator('.simple-extra-options>summary').click()
    page.locator('[name=transition_buffer_minutes]').select_option('10')
    page.locator('[name=use_feedback]').check()
    generate(page)
    assert page.evaluate('selected.legs.every(r=>r.buffer_minutes===10)')
    assert '여유 10분' in page.locator('.execution-summary').inner_text()
    assert '시연 모드' in page.locator('.execution-summary').inner_text()
    page.locator('#plan-detail .stop').first.get_by_role('button',name='↻ 다른 장소로 변경',exact=True).click()
    page.wait_for_function("document.querySelector('#dialog-content').textContent.includes('기존 장소에서 약')")
    assert '직선거리' in page.locator('#dialog-content').inner_text()
    page.locator('#close-dialog').click()
    for width in (320,390,768,1440):
        page.set_viewport_size({'width':width,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
