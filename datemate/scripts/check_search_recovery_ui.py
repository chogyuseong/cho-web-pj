import json
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.wait_for_function('Boolean(statusData)')
    page.get_by_role('button',name='주소 검색 · 지도에서 선택',exact=True).first.click()
    page.locator('#dialog .location-search input').fill('은평구')
    page.locator('#dialog .location-search button').click()
    page.locator('#dialog .location-result').first.wait_for(timeout=20000)
    page.locator('#dialog .location-result').first.click()
    page.get_by_role('button',name='이 지역에서 데이트하기',exact=True).click()
    page.locator('[name=request]').fill('비 오는 날 실내에서 카페 투어, 2명 5만원, 볼링은 제외')
    page.route('**/api/plan-jobs/*',lambda route:(page.wait_for_timeout(800),route.continue_()))
    page.locator('#submit-plan').click()
    page.wait_for_function('Boolean(sessionStorage.getItem("datemate-active-search"))')
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function('selected?.id&&!document.querySelector("#submit-plan").disabled',timeout=240000)
    assert page.locator('.option-comparison').count()==1
    assert page.locator('.place-evidence').count()>0
    plan=page.evaluate('selected')
    assert plan['conditions']['budget']==50000
    assert plan['place_evidence'] and plan['decision_summary']
    assert not any('볼링' in p['name'] for p in plan['places'])
    if page.evaluate('plans.length')>1:
        page.locator('.plan-option-tabs button').nth(1).click()
        page.wait_for_function('selected.id===plans[1].id')
        assert page.locator('#results > .plan-card').count()==1
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert not errors,errors
    print(json.dumps({'area':'eunpyeong','plans':page.evaluate('plans.length'),'comparison':True,'evidence':True,'mobile':True,'errors':errors}))
    page.evaluate('sessionStorage.setItem("datemate-active-search","missing-job")')
    page.reload(wait_until='networkidle')
    page.get_by_role('button',name='조건 확인하고 다시 검색',exact=True).wait_for(timeout=15000)
    page.get_by_role('button',name='조건 확인하고 다시 검색',exact=True).click()
    assert page.locator('.conditions.panel').is_visible()
    browser.close()
