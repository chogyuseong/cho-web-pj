from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True);page=browser.new_page(viewport={'width':1440,'height':900})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.get_by_role('button',name='서울 장소 둘러보기',exact=True).click()
    page.wait_for_function('location.hash==="#explore-section"&&!document.querySelector("#explore-section").hidden')
    assert page.locator('#explore-section h2').bounding_box()['y']<200
    assert not page.locator('.hero').is_visible()
    page.reload(wait_until='networkidle');assert page.locator('#explore-section').is_visible()
    page.get_by_role('button',name='코스 만들기',exact=True).click()
    assert page.locator('#planner-section').is_visible() and not page.locator('#explore-section').is_visible()
    page.set_viewport_size({'width':390,'height':844})
    page.get_by_role('button',name='서울 장소 둘러보기',exact=True).click()
    assert page.locator('#explore-section h2').bounding_box()['y']<250
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert not errors,errors
    print('PASS: desktop/mobile navigation, heading visible, reload restore, return to planner, no JS errors')
    browser.close()
