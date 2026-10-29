from test_functional_audit import audit_page,generate


def test_optional_measurement_decision_restore_and_saved_list(audit_page):
    page,base,errors=audit_page
    assert not page.locator('[name=measure_planning]').is_checked()
    page.locator('.simple-extra-options>summary').click()
    page.locator('.planning-study>summary').click()
    page.locator('[name=measure_planning]').check()
    generate(page)
    box=page.locator('.planning-decision')
    box.locator('.decision-survey>summary').click()
    box.locator('[name=decision_extra_search]').select_option('none')
    box.locator('[name=manual_planning_minutes]').fill('35')
    box.get_by_role('button',name='이 코스로 결정',exact=True).click()
    page.wait_for_function("document.querySelector('.planning-decision [role=status]').textContent.includes('✓')")
    pid=page.evaluate('selected.id')
    saved=page.request.get(base+'/api/plans/'+pid+'/decision').json()['decision']
    assert saved['extra_search']=='none' and saved['manual_planning_minutes']==35
    assert saved['elapsed_seconds']>=0
    page.goto(base+'/?plan='+pid,wait_until='networkidle')
    page.wait_for_function("document.querySelector('.planning-decision [role=status]')?.textContent.includes('✓')")
    page.locator('#edit-conditions').click()
    page.get_by_role('button',name='내가 결정한 코스 다시 보기',exact=True).click()
    page.wait_for_function("document.querySelector('.saved-decision')")
    page.locator('.saved-decision a').first.click()
    page.wait_for_function("document.querySelector('.planning-decision [role=status]')?.textContent.includes('✓')")
    page.set_viewport_size({'width':320,'height':900})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')


def test_shared_must_conflict_resolves_and_survives_guest_reload(audit_page):
    page,base,errors=audit_page
    generate(page)
    pid=page.evaluate('selected.id')
    ids=page.evaluate('selected.places.map(p=>p.id)')
    page.locator('.partner-agreement>summary').click()
    page.wait_for_function("document.querySelector('.partner-agreement select')")
    page.locator('.partner-agreement select').first.select_option('must')
    page.get_by_role('button',name='내 의견 저장',exact=True).click()
    page.wait_for_function("document.querySelector('.partner-agreement select')?.value==='must'")
    token=page.request.post(base+'/api/plans/'+pid+'/shares',data={}).json()['url']
    context=page.context.browser.new_context(viewport={'width':390,'height':844})
    guest=context.new_page()
    try:
        guest.goto(base+token,wait_until='networkidle')
        guest.locator('#shared-form select').first.select_option('no')
        guest.get_by_role('button',name='내 의견 전달하기',exact=True).click()
        guest.wait_for_function("document.querySelector('#shared-status').textContent.includes('의견을 전달')")
        page.get_by_role('button',name='상대방 의견 새로고침',exact=True).click()
        page.wait_for_function("document.querySelector('.partner-agreement').textContent.includes('의견 조정 필요')")
        assert page.get_by_role('button',name='합의한 취향으로 다시 계산',exact=True).is_disabled()
        guest.reload(wait_until='networkidle')
        assert guest.locator('#shared-form select').first.input_value()=='no'
        guest.locator('#shared-form select').first.select_option('neutral')
        guest.get_by_role('button',name='내 의견 전달하기',exact=True).click()
        guest.wait_for_function("document.querySelector('#shared-status').textContent.includes('의견을 전달')")
        page.get_by_role('button',name='상대방 의견 새로고침',exact=True).click()
        page.wait_for_function("[...document.querySelectorAll('.partner-agreement button')].some(b=>b.textContent==='합의한 취향으로 다시 계산'&&!b.disabled)")
        page.get_by_role('button',name='합의한 취향으로 다시 계산',exact=True).click()
        page.wait_for_function("document.querySelector('#dialog').open&&document.querySelector('#dialog-content').textContent.includes('변경 전후를 확인')")
        draft=page.request.post(base+'/api/plans/'+pid+'/agreement-preview',data={}).json()
        assert draft['plan']['places'][0]['id']==ids[0]
        page.get_by_role('button',name='이 변경안으로 확정',exact=True).click()
        page.wait_for_function('old=>selected.id!==old',arg=pid)
        assert page.evaluate('selected.places[0].id')==ids[0]
        assert guest.evaluate('document.documentElement.scrollWidth<=innerWidth')
    finally:context.close()


def test_measurement_failure_does_not_block_recommendation(audit_page):
    page,base,errors=audit_page
    page.route('**/api/planning-sessions',lambda route:route.fulfill(status=503,json={'detail':'測定 test outage'}))
    page.evaluate("form.elements.measure_planning.checked=true")
    generate(page)
    assert page.evaluate('selected.conditions.planning_session_id')==''
    assert page.locator('.planning-decision .decision-survey').count()==0
