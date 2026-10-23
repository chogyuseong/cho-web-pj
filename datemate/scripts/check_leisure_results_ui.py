import json
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.wait_for_function('Boolean(statusData)')
    assert page.locator('.leisure-choices').count()==0
    page.evaluate("form.elements.mode.value='demo';clearLocationsForMode();form.elements.visit_date.value='2026-10-24';form.elements.budget.value='1000000';form.elements.max_leg.value='180';form.elements.request.value='';form.requestSubmit()")
    page.wait_for_function('selected?.id&&!document.querySelector("#submit-plan").disabled',timeout=60000)
    assert page.locator('#plan-detail .leisure-results').count()==0
    assert page.locator('.leisure-course-panel').count()==1
    assert page.evaluate('''()=>{const card=document.querySelector('#results>.plan-card');const leisure=document.querySelector('.leisure-course-panel');const detail=document.querySelector('#plan-detail');return Boolean(card.compareDocumentPosition(leisure)&Node.DOCUMENT_POSITION_FOLLOWING)&&Boolean(leisure.compareDocumentPosition(detail)&Node.DOCUMENT_POSITION_FOLLOWING)}''')
    for width in [320,390,768,1440]:
        page.set_viewport_size({'width':width,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
    page.set_viewport_size({'width':390,'height':844})
    before=page.evaluate('({id:selected.id,ids:selected.places.map(p=>p.id)})')
    chosen_index=None
    for i in range(len(before['ids'])):
        panel=page.locator('.leisure-results').nth(i)
        panel.locator('summary').click()
        page.wait_for_function('(i)=>document.querySelectorAll(".leisure-results")[i].getAttribute("aria-busy")==="false"',arg=i)
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        if panel.get_by_role('button',name='이 레저로 교체',exact=True).count():
            chosen_index=i
            panel.get_by_role('button',name='이 레저로 교체',exact=True).first.click()
            break
    assert chosen_index is not None,'No demo alternatives available'
    page.wait_for_function('(old)=>selected.id!==old',arg=before['id'])
    after=page.evaluate('({id:selected.id,ids:selected.places.map(p=>p.id)})')
    assert after['ids'][chosen_index]!=before['ids'][chosen_index]
    assert all(after['ids'][j]==v for j,v in enumerate(before['ids']) if j!=chosen_index)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.get_by_role('button',name='교체 되돌리기',exact=True).click()
    page.wait_for_function('(old)=>selected.id===old',arg=before['id'])
    assert not errors,errors
    print(json.dumps({'mobile_result_choices':True,'single_stop_replace':True,'other_stops_preserved':True,'undo':True,'no_overflow':True,'js_errors':errors}))
    browser.close()
