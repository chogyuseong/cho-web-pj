from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page()
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.evaluate('''()=>{const p={places:[{id:'test',name:'테스트'}],reasons:['추천 근거: https://blog.naver.com/test/123'],place_evidence:[]};const box=placeEvidencePanel(p,0);box.id='link-test';box.open=true;document.body.append(box);document.body.append(linkedText('p','근거: https://example.com/source. javascript:alert(1)','link-safety-test'));}''')
    a=page.locator('#link-test a').first;assert a.get_attribute('href')=='https://blog.naver.com/test/123'
    assert a.get_attribute('target')=='_blank'
    page.context.route('https://blog.naver.com/test/123',lambda r:r.fulfill(status=200,body='source page'))
    with page.expect_popup() as popup:a.click()
    popup.value.wait_for_load_state()
    assert popup.value.url=='https://blog.naver.com/test/123'
    assert page.locator('.link-safety-test a:not(.source-search-fallback)').count()==1
    assert page.locator('.link-safety-test a').first.get_attribute('href')=='https://example.com/source'
    assert page.evaluate("normalizeLink('nmap://route/walk?dname=%EC%A4%91%EA%B5%AC')")== 'https://map.naver.com/p/search/%EC%A4%91%EA%B5%AC'
    assert page.evaluate("normalizeLink('/api/plans/abc123')")== '/?plan=abc123'
    assert page.evaluate("normalizeLink('https://blog.naver.com/PostView.naver?blogId=sample&amp;logNo=123')")== 'https://blog.naver.com/sample/123'
    assert page.evaluate("normalizeLink(null)") is None
    assert page.evaluate("normalizeLink('javascript:alert(1)')") is None
    assert page.evaluate("linkedText('p','https://example.com/A_(B)').querySelector('a').href")== 'https://example.com/A_(B)'
    assert page.locator('#link-test .source-search-fallback').count()==1
    print('PASS: evidence URL is an anchor; click opens source in new tab; unsafe text stays text')
    browser.close()
