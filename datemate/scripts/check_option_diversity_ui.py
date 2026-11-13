import json
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(bypass_csp=True,viewport={'width':1440,'height':1000})
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
    # 기본 선택기(experience): 첫 안은 기준 코스, 나머지는 실제 차이에서 만든 이름. place 모드면 이전 이름이 나온다.
    purposes=[r['purpose'] for r in rows]
    assert purposes==['취향 우선','다른 매력','편안한 동선'] or (purposes[0]=='기준 코스' and all(purposes)),purposes
    for i,a in enumerate(rows):
        for b in rows[i+1:]:assert set(a['ids'])!=set(b['ids']),(a,b)
    for i in range(3):
        page.locator('.plan-option-tabs button').nth(i).click()
        assert rows[i]['purpose'] in page.locator('#results .plan-card.selected').inner_text()
        assert page.locator('.map-option-tabs button').nth(i).get_attribute('aria-pressed')=='true'
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert not errors,errors
    print(json.dumps({'options':len(rows),'distinct_place_sets':True,'purposes_visible':True,'map_sync':True,'mobile_overflow':False,'errors':errors}))
    browser.close()
