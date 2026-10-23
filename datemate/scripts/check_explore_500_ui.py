from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.get_by_role('button',name='서울 장소 둘러보기',exact=True).click()
    page.wait_for_function('document.querySelector("#search-info").textContent.includes("500 / 최대 500")',timeout=240000)
    assert page.locator('#catalog .place-card').count()==24
    page.get_by_role('button',name='장소 더 보기 · 24 / 500').click()
    page.wait_for_function('document.querySelectorAll("#catalog .place-card").length===48')
    page.locator('#catalog .place-card button').filter(has_text='장소 자세히 보기').first.click()
    page.locator('#dialog').wait_for(state='visible')
    assert page.locator('#dialog-content h2').inner_text()
    page.locator('#close-dialog').click()
    page.locator('#search').fill('중구');page.locator('#search-button').click()
    page.wait_for_function('document.querySelectorAll("#catalog .place-card>.hint").length>0&&Array.from(document.querySelectorAll("#catalog .place-card>.hint")).every(e=>e.textContent.includes("중구"))')
    assert page.locator('#catalog .place-card').count()>0
    assert all('중구' in t for t in page.locator('#catalog .place-card>.hint').all_text_contents())
    page.locator('#search').fill('없는장소테스트아무것도없음');page.locator('#search-button').click()
    page.wait_for_function('document.querySelector("#search-info").textContent.includes("검색 결과 0곳")')
    for width in [320,390,768]:
        page.set_viewport_size({'width':width,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert not errors,errors
    print('PASS: 500 count;24/48 paging;details;district filter;empty state;mobile;no JS errors')
    browser.close()
