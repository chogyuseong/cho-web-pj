import json
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1200,'height':900})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    plan=page.evaluate("async()=>await api('/plans',{mode:'demo',visit_date:'2026-10-24'})")['plans'][0]
    page.goto('http://127.0.0.1:8000/?plan='+plan['id'],wait_until='networkidle')
    chat=page.locator('#plan-detail .chat-form')
    chat.locator('input').fill('총비용은 얼마야?')
    chat.get_by_role('button',name='질문하기').click()
    page.wait_for_function("document.querySelector('#plan-detail .chat-box').textContent.includes('계산된 총비용')")
    assert f"{plan['total'][0]:,}" in page.locator('#plan-detail .chat-box').inner_text()
    chat.locator('input').fill('이동시 주의할점 알려줘')
    chat.get_by_role('button',name='질문하기').click()
    page.wait_for_function("document.querySelector('#plan-detail .chat-box').textContent.includes('종료 예정')")
    assert plan['finish'] in page.locator('#plan-detail .chat-box').inner_text()
    assert '자차 이용 시 약' in page.locator('#plan-detail .chat-box').inner_text()
    assert '시속 4km' in page.locator('#plan-detail .chat-box').inner_text()
    page.reload(wait_until='networkidle')
    page.wait_for_function("document.querySelector('#plan-detail .chat-box')?.textContent.includes('종료 예정')")
    assert not errors,errors
    print(json.dumps({'cost_answer':True,'schedule_answer':True,'history_after_reload':True,'page_errors':errors}))
    browser.close()
