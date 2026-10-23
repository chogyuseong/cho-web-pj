from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page()
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.wait_for_function('Boolean(statusData)')
    page.evaluate("showPlace('discovered:1ebc7194742b9d2e9acd','real')")
    page.locator('#dialog .place-photo-panel').first.scroll_into_view_if_needed()
    page.wait_for_function('Array.from(document.querySelectorAll("#dialog .place-photo-panel img")).some(i=>i.complete&&i.naturalWidth>0)',timeout=45000)
    print('SAAN 2 photo rendered successfully')
    browser.close()
