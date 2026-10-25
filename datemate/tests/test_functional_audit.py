"""Full user journeys against a local server and disposable test storage."""
import os
import socket
import threading
import time
from urllib.parse import urlsplit
import pytest
import uvicorn
from app.main import app


@pytest.fixture
def audit_page():
    playwright=pytest.importorskip('playwright.sync_api')
    sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128)
    base=f'http://127.0.0.1:{sock.getsockname()[1]}'
    server=uvicorn.Server(uvicorn.Config(app,log_level='error'))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
    browser=None
    try:
        deadline=time.monotonic()+10
        while not server.started and time.monotonic()<deadline:time.sleep(.05)
        assert server.started
        with playwright.sync_playwright() as pw:
            browser=pw.chromium.launch(channel=os.getenv('DATEMATE_BROWSER_CHANNEL','msedge'),headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            def route(request):
                if not request.request.url.startswith(base):return request.abort()
                return request.continue_()
            page.route('**/*',route)
            page.goto(base,wait_until='networkidle')
            page.wait_for_function("typeof statusData!=='undefined'&&!!statusData&&document.querySelector('.simple-plan-form')")
            yield page,base,errors
            assert not errors,errors
            browser.close();browser=None
    finally:
        if browser:browser.close()
        server.should_exit=True;thread.join(10);sock.close()


def generate(page):
    page.evaluate("form.elements.mode.value='demo';form.elements.mode.dispatchEvent(new Event('change',{bubbles:true}));form.elements.visit_date.value='2026-10-24';form.elements.max_leg.value=180;form.elements.budget.value=1000000;")
    page.locator('#submit-plan').click()
    page.wait_for_function('selected?.id&&!document.querySelector("#submit-plan").disabled',timeout=45000)


def test_lock_replace_undo_chat_review_feedback_and_delete(audit_page):
    page,base,errors=audit_page
    generate(page)
    page.locator('.plan-option-tabs button').nth(1).click()
    page.wait_for_function('document.querySelector(".plan-option-tabs button:nth-child(2)").getAttribute("aria-pressed")==="true"')
    original=page.evaluate('selected.id');locked=page.evaluate('selected.places[0].id')
    page.locator('#plan-detail .stop').first.get_by_role('button',name='○ 장소 고정',exact=True).click()
    page.wait_for_function('Object.keys(selected.conditions.locked).length===1')
    page.locator('#plan-detail .stop').nth(1).get_by_role('button',name='↻ 다른 장소로 변경',exact=True).click()
    dialog=page.locator('#dialog')
    dialog.locator('[name=replacement_reason]').select_option('taste')
    dialog.get_by_role('button',name='이 장소로 교체',exact=True).first.click()
    page.wait_for_function('(id)=>selected.id!==id',arg=original)
    assert page.evaluate('selected.places[0].id')==locked
    page.get_by_role('button',name='교체 되돌리기',exact=True).click()
    page.wait_for_function('(id)=>selected.id===id',arg=original)
    chat=page.locator('#plan-detail .chat-form').first
    chat.locator('input').fill('총비용은 얼마야?')
    chat.get_by_role('button',name='질문하기',exact=True).click()
    page.wait_for_function("document.querySelector('#plan-detail .chat-form button').disabled===false")
    assert '메이트:' in page.locator('#plan-detail .chat-box').first.inner_text()
    review=page.locator('#plan-detail .review-form')
    review.locator('[name=nickname]').fill('기능점검')
    review.locator('[name=visited]').fill('2026-01-01')
    review.locator('[name=body]').fill('기능점검 전용 후기입니다.')
    with page.expect_response(lambda response:response.request.method=='PUT' and response.url.endswith('/review')) as response:
        review.get_by_role('button',name='후기 저장 / 내 후기 수정',exact=True).click()
    assert response.value.ok
    row=page.locator('.review').filter(has_text='기능점검 전용 후기입니다.')
    row.get_by_role('button',name='내 후기 삭제',exact=True).click()
    page.wait_for_function("![...document.querySelectorAll('.review')].some(row=>row.textContent.includes('기능점검 전용 후기입니다.'))")
    feedback=page.locator('.visit-feedback')
    feedback.locator('summary').click()
    page.wait_for_function('!document.querySelector(".visit-feedback select").disabled')
    feedback.locator('[name=visit_used]').select_option('yes')
    feedback.locator('[name=visit_issue]').select_option('none')
    feedback.locator('[name=visit_reuse]').select_option('yes')
    with page.expect_response(lambda response:response.request.method=='POST' and response.url.endswith('/feedback')) as response:
        feedback.get_by_role('button',name='방문 피드백 저장',exact=True).click()
    assert response.value.ok
    assert page.request.get(base+'/api/plans/'+original+'/feedback').json()['visit']['visited']=='yes'
    page.once('dialog',lambda dialog:dialog.accept())
    with page.expect_response(lambda response:response.request.method=='DELETE' and response.url.endswith('/me/data')) as response:
        page.get_by_role('button',name='이 브라우저의 저장 데이터 삭제',exact=True).click()
    assert response.value.ok
    page.wait_for_url(base+'/')
    assert page.request.get(base+'/api/plans/'+original).status==404


def test_address_keyboard_navigation_and_invalid_input(audit_page):
    page,base,errors=audit_page
    page.locator('#origin-location').get_by_role('button',name='주소 검색 · 지도에서 선택',exact=True).click()
    page.wait_for_function('!!locationMap',timeout=25000)
    page.locator('#dialog').get_by_role('button',name='지도 중심을 선택',exact=True).click()
    page.locator('#dialog').get_by_role('button',name='이 지역에서 데이트하기',exact=True).click()
    assert page.locator('[name=origin_name]').input_value()
    page.locator('[name=budget]').fill('-1')
    page.locator('#submit-plan').click()
    assert page.locator('[name=budget]').evaluate('element=>!element.validity.valid')
    assert page.locator('.conditions').is_visible()
    page.get_by_role('button',name='서울 장소 둘러보기',exact=True).click()
    assert page.locator('#explore-section').is_visible()
    page.get_by_role('button',name='코스 만들기',exact=True).click()
    assert page.locator('.conditions').is_visible()
    page.go_back()
    assert page.locator('#explore-section').is_visible()
    page.go_forward()
    assert page.locator('.conditions').is_visible()


def test_place_dialog_ignores_late_old_response(audit_page):
    page,base,errors=audit_page
    places=page.request.get(base+'/api/places?mode=demo').json()['places'][:2]
    result=page.evaluate('''async places=>{
        const original=api,waiting={};
        api=(path,...args)=>path.startsWith('/places/')&&!path.includes('/media')&&!path.includes('/blogs')?new Promise(resolve=>waiting[path]=resolve):original(path,...args);
        try{
          const first=showPlace(places[0].id,'demo'),second=showPlace(places[1].id,'demo');
          waiting['/places/'+places[1].id+'?mode=demo'](places[1]);await second;
          waiting['/places/'+places[0].id+'?mode=demo'](places[0]);await first;
          return document.querySelector('#dialog-content h2').textContent;
        }finally{api=original;}
    }''',places)
    assert result==places[1]['name']
