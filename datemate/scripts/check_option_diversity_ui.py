import json
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.wait_for_function('Boolean(statusData)')
    page.evaluate('''()=>{
      form.elements.mode.value='demo';clearLocationsForMode();
      form.elements.visit_date.value='2026-10-24';form.elements.budget.value='200000';
      form.elements.request.value='';form.elements.course_query.value='';
      form.elements.include_meal.checked=false;setDateClassification('콘셉트별','');form.requestSubmit();
    }''')
    page.wait_for_function('selected?.id&&!document.querySelector("#submit-plan").disabled',timeout=60000)
    rows=page.evaluate('plans.map(p=>({purpose:p.option_purpose,ids:p.places.map(v=>v.id),note:p.diversity_note}))')
    assert len(rows)==3,rows
    assert [r['purpose'] for r in rows]==['취향 우선','다른 매력','편안한 동선']
    for i,a in enumerate(rows):
        for b in rows[i+1:]:assert len(set(a['ids'])-set(b['ids']))>=2,(a,b)
    for i in range(3):
        page.locator('.plan-option-tabs button').nth(i).click()
        assert rows[i]['purpose'] in page.locator('#results .plan-card.selected').inner_text()
        assert page.locator('.map-option-tabs button').nth(i).get_attribute('aria-pressed')=='true'
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert not errors,errors
    print(json.dumps({'options':len(rows),'at_least_two_different_places':True,'purposes_visible':True,'map_sync':True,'mobile_overflow':False,'errors':errors}))
    browser.close()
