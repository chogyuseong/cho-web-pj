from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page()
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.wait_for_function('Boolean(statusData)')
    page.evaluate("showPlace('discovered:a78d4397eebb13f183bb','real')")
    page.locator('#dialog .place-photo-panel').first.scroll_into_view_if_needed()
    page.wait_for_function('Array.from(document.querySelectorAll("#dialog .place-photo-panel a img")).some(i=>i.complete&&i.naturalWidth>0)',timeout=45000)
    assert page.evaluate('''()=>{const img=Array.from(document.querySelectorAll('#dialog .place-photo-panel a img')).find(i=>i.complete&&i.naturalWidth>0);return img.closest('a').href===img.src;}''')
    print('La Main Secrete photo rendered successfully')
    browser.close()
