import json
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.wait_for_function('Boolean(statusData)')
    page.evaluate("locationState.origin={name:'강동구청',lat:37.5301,lon:127.1238};form.elements.origin_name.value='강동구청'")
    page.locator('[name=transport]').select_option('transit')
    page.locator('[name=request]').fill('카페 3곳')
    page.locator('#submit-plan').click()
    page.wait_for_function('selected?.best_effort===true',timeout=45000)
    assert page.locator('#results .plan-card').count()>0
    assert page.locator('#results .condition-differences').count()>0
    assert page.locator('[name=max_leg]').input_value()=='30'
    assert page.evaluate('selected.conditions.max_leg')==30
    page.locator('#results .plan-card').first.screenshot(path=str(root/'docs/screenshots/best-effort-card.png'))
    page.locator('#plan-detail .place-photo-panel').first.scroll_into_view_if_needed()
    page.wait_for_function("document.querySelector('#plan-detail .place-photo img')?.naturalWidth>0",timeout=45000)
    page.locator('#plan-detail .place-photo-panel').first.screenshot(path=str(root/'docs/screenshots/best-effort-photo.png'))
    first=page.evaluate('selected.id')
    # 30분밖에 없는 요청에서도 초과를 설명한 대안을 제안한다.
    page.locator('[name=end]').fill('11:30')
    page.locator('#submit-plan').click()
    page.wait_for_function('id=>selected?.id!==id&&!document.querySelector("#submit-plan").disabled',arg=first,timeout=45000)
    assert page.evaluate("selected.deviations.some(d=>d.condition==='end')")
    assert page.locator('[name=end]').input_value()=='11:30'
    result=page.evaluate('({plans:plans.length,best_effort:selected.best_effort,deviations:selected.deviations})')
    assert not errors,errors
    result.update(loaded_photo=True,page_errors=errors)
    page.locator('[name=request]').fill('')
    page.locator('[name=end]').fill('19:00')
    page.locator('[name=max_leg]').evaluate("input=>input.closest('details').open=true")
    page.locator('[name=max_leg]').fill('1')
    page.evaluate("setDateClassification('날씨별','비 오는 날');locationState.origin={name:'강남',lat:37.5172,lon:127.0473}")
    previous=page.evaluate('selected.id')
    page.locator('#submit-plan').click()
    page.wait_for_function('id=>selected?.id!==id&&!document.querySelector("#submit-plan").disabled',arg=previous,timeout=45000)
    assert page.locator('#results .condition-summary').first.inner_text()
    notes=page.locator('#results .condition-differences').first.locator('.verification-notes summary')
    if notes.count():notes.click()
    assert '[날씨' in page.locator('#results .condition-differences').first.inner_text()
    result['weather_explanation']=page.locator('#results .condition-differences').first.inner_text()
    page.locator('#results .condition-differences').first.screenshot(path=str(root/'docs/screenshots/weather-condition-warning.png'))
    (root/'docs/best-effort-ui.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps({'plans':result['plans'],'loaded_photo':True,'page_errors':errors}))
    browser.close()
