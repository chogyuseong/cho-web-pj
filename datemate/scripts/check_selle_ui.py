# [예전 기준 점검 스크립트] 예전 조건 화면(예산 칸이 처음부터 보임) 기준이고 부산 실제 장소 검색 키가 필요합니다.
# 그대로 실행하면 실패할 수 있습니다. 자동 테스트(pytest)가 기준이며, 같은 내용은 tests/test_quick_conditions_ui.py, tests/test_nationwide_home.py 에서 확인합니다.
print('[예전 기준 점검 스크립트] 예전 조건 화면(예산 칸이 처음부터 보임) 기준이고 부산 실제 장소 검색 키가 필요합니다. 그대로 실행하면 실패할 수 있습니다. 대신 볼 테스트: tests/test_quick_conditions_ui.py, tests/test_nationwide_home.py', flush=True)
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(bypass_csp=True,viewport={'width':1440,'height':1000})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.wait_for_function('Boolean(statusData)')
    page.screenshot(path=str(root/'docs/screenshots/selle-desktop.png'))
    page.locator('[data-preset="부산 해운대"]').click()
    page.locator('[name=budget]').fill('150000')
    page.locator('#submit-plan').click()
    page.wait_for_function('selected?.pricing_checked_at&&!document.querySelector("#submit-plan").disabled',timeout=60000)
    assert page.evaluate('selected.conditions.origin.name')=='부산 해운대역 지역 중심'
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
    print(json.dumps({'theme_card':True,'timeline':True,'mobile_overflow':False,'page_errors':errors}))
    browser.close()
