# [예전 기준 점검 스크립트] 예전 로컬 캐시에만 있던 특정 장소 ID(discovered:...) 하나를 여는 일회성 점검입니다.
# 그대로 실행하면 실패할 수 있습니다. 자동 테스트(pytest)가 기준이며, 같은 내용은 tests/test_saan_images.py, tests/test_media.py 에서 확인합니다.
print('[예전 기준 점검 스크립트] 예전 로컬 캐시에만 있던 특정 장소 ID(discovered:...) 하나를 여는 일회성 점검입니다. 그대로 실행하면 실패할 수 있습니다. 대신 볼 테스트: tests/test_saan_images.py, tests/test_media.py', flush=True)
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(bypass_csp=True)
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.wait_for_function('Boolean(statusData)')
    page.evaluate("showPlace('discovered:1ebc7194742b9d2e9acd','real')")
    page.locator('#dialog .place-photo-panel').first.scroll_into_view_if_needed()
    page.wait_for_function('Array.from(document.querySelectorAll("#dialog .place-photo-panel img")).some(i=>i.complete&&i.naturalWidth>0)',timeout=45000)
    print('SAAN 2 photo rendered successfully')
    browser.close()
