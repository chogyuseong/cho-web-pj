"""SDK 최초 요청 실패 후 실제 지도 재연결을 검증한다. 비밀값·URL 출력 없음."""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    calls=[]
    def sdk(route):
        calls.append(1)
        if len(calls)==1:route.abort()
        else:route.continue_()
    page.route('https://oapi.map.naver.com/openapi/v3/maps.js?*',sdk)
    page.goto('http://localhost:8000',wait_until='networkidle')
    page.locator('#submit-plan').click()
    page.locator('.map-reconnect').wait_for()
    assert page.locator('.map-schematic').get_attribute('open') is None
    page.get_by_role('button',name='지도 다시 연결',exact=True).click()
    page.locator('.route-marker').first.wait_for(timeout=25000)
    assert page.locator('.route-marker').count()==4
    assert page.locator('.map-reconnect').count()==0
    browser.close()
print('First SDK failure -> visible retry -> actual Naver map with 4 markers: PASS')
