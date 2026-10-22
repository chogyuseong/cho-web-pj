import json
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.wait_for_function('Boolean(statusData)')
    page.screenshot(path=str(root/'docs/screenshots/selle-desktop.png'))
    page.locator('[data-region="연남"]').click()
    page.locator('[data-quick-mood]').nth(1).click()
    page.locator('#quick-budget').fill('150000')
    page.locator('#quick-budget').dispatch_event('input')
    page.locator('#quick-start').click()
    page.wait_for_function('selected?.pricing_checked_at&&!document.querySelector("#submit-plan").disabled',timeout=60000)
    assert page.evaluate('selected.conditions.origin.name')=='홍대입구역 지역 중심'
    assert page.evaluate('selected.conditions.budget')==150000
    assert page.evaluate('selected.conditions.date_subcategory')=='활동적인'
    assert page.locator('.timeline-stamp').count()>0
    assert page.locator('.timeline-card').count()>0
    page.locator('#plan-detail').screenshot(path=str(root/'docs/screenshots/selle-timeline.png'))
    page.locator('#curation').screenshot(path=str(root/'docs/screenshots/selle-curation.png'))
    page.set_viewport_size({'width':390,'height':844})
    page.evaluate('window.scrollTo(0,0)')
    page.screenshot(path=str(root/'docs/screenshots/selle-mobile.png'))
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),page.evaluate('document.documentElement.scrollWidth')
    assert not errors,errors
    print(json.dumps({'quick_builder':True,'timeline':True,'mobile_overflow':False,'page_errors':errors}))
    browser.close()
