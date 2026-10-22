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
    assert page.locator('[name=mode]').input_value()=='real'
    page.evaluate("locationState.origin={name:'서울시청',lat:37.5665,lon:126.978};form.elements.origin_name.value='서울시청'")
    page.locator('#submit-plan').click()
    page.wait_for_function('plans.length>0',timeout=45000)
    first=page.evaluate('selected.places.map(p=>p.id)')
    panels=page.locator('#plan-detail .place-photo-panel')
    for i in range(panels.count()):
        panels.nth(i).scroll_into_view_if_needed()
        page.wait_for_function("i=>document.querySelectorAll('#plan-detail .place-photo-panel')[i]?.querySelector('img')?.naturalWidth>0",arg=i,timeout=60000)
    page.screenshot(path=str(root/'docs/screenshots/real-plan-photos.png'))
    photo_count=page.locator('#plan-detail .place-photo img').evaluate_all('(imgs)=>imgs.filter(i=>i.naturalWidth>0).length')
    page.locator('[name=count]').select_option('2')
    page.evaluate("locationState.origin={name:'용산',lat:37.524,lon:126.98};form.elements.origin_name.value='용산'")
    page.locator('#submit-plan').click()
    page.wait_for_function('selected?.places.length===2',timeout=45000)
    second=page.evaluate('selected.places.map(p=>p.id)')
    assert first[0]!=second[0]
    assert not errors,errors
    result=dict(first=first,second=second,loaded_photos=photo_count,page_errors=errors)
    (root/'docs/real-plan-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(result))
    browser.close()
