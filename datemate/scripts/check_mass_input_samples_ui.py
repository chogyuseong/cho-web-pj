import json
from playwright.sync_api import sync_playwright
from check_10000_inputs import chat_ok

with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.wait_for_function('Boolean(statusData)')
    page.get_by_role('button',name='주소 검색 · 지도에서 선택',exact=True).first.click()
    page.locator('#dialog .location-search input').fill('종로구')
    page.locator('#dialog .location-search button').click()
    page.locator('#dialog .location-result').first.wait_for(timeout=20000)
    page.locator('#dialog .location-result').first.click()
    page.get_by_role('button',name='이 지역에서 데이트하기',exact=True).click()
    page.locator('[name=visit_date]').fill('2026-10-24')
    page.locator('[name=request]').fill('카페 투어 하고 싶어. 볼링은 안 좋아해. 2명 10만원 3곳')
    page.locator('#submit-plan').click()
    page.wait_for_function('selected?.id&&!document.querySelector("#submit-plan").disabled',timeout=180000)
    plan=page.evaluate('selected')
    assert plan['request_interpretation']['excluded']
    assert not any('볼링' in p['name'] for p in plan['places'])
    assert plan['conditions']['people']==2 and plan['conditions']['budget']==100000
    chat=page.locator('#plan-detail .chat-form')
    samples=[('cost','총비용은 얼마야?'),('movement','몇 분 걸려?'),('location','address of each place?'),
        ('caution','주의할 점 알려줘'),('weather','비가 오면 어떻게 해?'),('menu','뭘 주문하면 좋아?'),
        ('reservation','예약해야 돼?'),('meal','어디서 밥 먹어?'),('parking','parking information?'),('change','이 장소 대신 다른 곳으로 해줘')]
    for topic,text in samples:
        chat.locator('input').fill(text)
        with page.expect_response(lambda r:'/api/chat/plan/' in r.url and r.request.method=='POST') as response:
            chat.get_by_role('button',name='질문하기').click()
        data=response.value.json()
        assert chat_ok(topic,data,plan),(topic,data)
        page.wait_for_function('!document.querySelector("#plan-detail .chat-form button").disabled')
    assert page.evaluate('selected.id')==plan['id']
    page.goto('http://127.0.0.1:8000/?plan='+plan['id'],wait_until='networkidle')
    page.wait_for_function('document.querySelector("#plan-detail .chat-box")?.textContent.includes("parking information")')
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert not errors,errors
    print(json.dumps({'real_preference_input':True,'excluded_activity_recognized':True,'live_chat_categories':10,'history_reload':True,'no_unapproved_plan_change':True,'mobile_overflow':False,'errors':errors}))
    browser.close()
