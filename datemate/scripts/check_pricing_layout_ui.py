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
    page.evaluate("locationState.origin={name:'서울시청',lat:37.5665,lon:126.978};form.elements.origin_name.value='서울시청'")
    page.locator('#submit-plan').click()
    page.wait_for_function('selected?.pricing_checked_at&&!document.querySelector("#submit-plan").disabled',timeout=60000)
    assert page.evaluate("document.querySelector('#plan-detail').previousElementSibling.classList.contains('selected')")
    assert page.locator('#results .plan-card').first.locator('.option-heading .inspect-plan').count()==1
    # 미확인만 있는 경우 차이 안내를 활성화하지 않는다.
    assert page.evaluate("(()=>{const p=structuredClone(selected);p.best_effort=false;p.deviations=[{state:'unknown',condition:'budget',message:'test'}];return conditionDifferences(p).nodeType===11})()")
    costs=page.evaluate('selected.costs')
    assert all(c['amount'] is not None for c in costs)
    assert page.locator('#plan-detail .price-basis').count()>0
    before=page.locator('.price-input-preview').inner_text()
    page.locator('[name=people]').fill('3')
    assert page.locator('.price-input-preview').inner_text()!=before
    page.locator('[name=people]').fill('2')
    first_id=page.evaluate('selected.id')
    page.locator('.price-refresh-control button').click()
    page.wait_for_function('id=>selected?.id!==id',arg=first_id,timeout=60000)
    if page.locator('.plan-option-tabs button').count()>1:
        page.locator('.plan-option-tabs button').nth(1).click()
        assert page.evaluate("document.querySelector('#plan-detail').previousElementSibling.classList.contains('selected')")
    page.wait_for_function("Array.from(document.querySelectorAll('#results .plan-card.selected .place-photo img')).filter(i=>i.naturalWidth>0).length===3",timeout=45000)
    page.locator('#results .plan-card.selected').screenshot(path=str(root/'docs/screenshots/pricing-layout.png'))
    assert not errors,errors
    result={'price_kinds':[c.get('price_kind',c['status']) for c in costs],'cost_rows':len(costs),'inline_detail':True,'unknown_only_notice_hidden':True,'refresh_worked':True,'page_errors':errors}
    (root/'docs/pricing-layout-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(result));browser.close()
