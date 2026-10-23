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
      form.elements.request.value='';form.elements.course_query.value='';
      form.elements.visit_date.value='2026-10-24';
      form.elements.budget.value='200000';form.elements.include_meal.checked=false;
      setDateClassification('콘셉트별','');form.requestSubmit();
    }''')
    page.wait_for_function('selected?.id&&!document.querySelector("#submit-plan").disabled',timeout=60000)
    saved=page.evaluate('({plans, status:"ok"})')
    pending=[]
    page.route('**/api/plans',lambda route:pending.append(route))
    page.locator('#edit-conditions').click()
    page.locator('#submit-plan').click()
    page.wait_for_function('document.querySelector("#progress").classList.contains("is-searching")')
    page.wait_for_timeout(250)
    assert pending
    assert page.locator('#results .plan-card').count()==0
    assert page.locator('#plan-detail').inner_text()==''
    assert page.locator('#plan-map-rail').is_hidden()
    assert page.locator('.search-spinner').is_visible()
    assert page.locator('#results').get_attribute('aria-busy')=='true'
    assert page.locator('#submit-plan').is_disabled()
    assert page.locator('.search-spinner').evaluate('(e)=>getComputedStyle(e).animationName')=='search-spin'
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.emulate_media(reduced_motion='reduce')
    assert page.locator('.search-spinner').evaluate('(e)=>getComputedStyle(e).animationName')=='search-spin'
    first=page.locator('.search-spinner').evaluate('(e)=>getComputedStyle(e).transform')
    page.wait_for_timeout(200)
    assert page.locator('.search-spinner').evaluate('(e)=>getComputedStyle(e).transform')!=first
    pending.pop().fulfill(status=503,content_type='application/json',body=json.dumps({'detail':'검색 연결을 다시 확인해 주세요.'}))
    page.wait_for_function('!document.querySelector("#submit-plan").disabled')
    assert page.locator('.search-spinner').count()==0
    assert page.locator('#results .plan-card').count()==0
    assert page.locator('#results').get_attribute('aria-busy')=='false'
    page.locator('#edit-conditions').click()
    page.locator('#submit-plan').click()
    page.wait_for_timeout(250)
    pending.pop().fulfill(status=200,content_type='application/json',body=json.dumps(saved))
    page.wait_for_function('selected?.id&&!document.querySelector("#submit-plan").disabled')
    assert page.locator('#results .plan-card.selected').is_visible()
    assert page.locator('.search-spinner').count()==0
    assert not errors,errors
    print(json.dumps({'previous_results_cleared':True,'previous_map_cleared':True,'loading_animation':True,'mobile_overflow':False,'reduced_motion':True,'failure_and_retry':True,'page_errors':errors}))
    browser.close()
