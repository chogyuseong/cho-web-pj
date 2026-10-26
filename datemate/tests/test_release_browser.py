"""End-to-end local UI check. Uses demo data and blocks external browser traffic."""
import os
import socket
import threading
import time
from urllib.parse import urlsplit
import pytest
import uvicorn
from app.main import app


def test_input_result_share_and_mobile_flow(tmp_path):
    playwright=pytest.importorskip('playwright.sync_api')
    sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128)
    base=f'http://127.0.0.1:{sock.getsockname()[1]}'
    server=uvicorn.Server(uvicorn.Config(app,log_level='error'))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
    try:
        deadline=time.monotonic()+10
        while not server.started and time.monotonic()<deadline:time.sleep(.05)
        assert server.started
        with playwright.sync_playwright() as pw:
            browser=pw.chromium.launch(channel=os.getenv('DATEMATE_BROWSER_CHANNEL','msedge'),headless=True)
            context=browser.new_context(viewport={'width':1440,'height':1000},permissions=['clipboard-read','clipboard-write'])
            def offline(route):
                path=urlsplit(route.request.url).path
                if not route.request.url.startswith(base):return route.abort()
                if path.endswith(('/media','/blogs','/menu')):return route.fulfill(json={'items':[],'photos':[],'videos':[],'blogs':[]})
                return route.continue_()
            context.route('**/*',offline)
            page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(base,wait_until='networkidle')
            page.wait_for_function("typeof statusData !== 'undefined' && !!statusData && document.querySelector('.simple-plan-form')")
            assert page.locator('.conditions').is_visible()
            assert not page.locator('.results-area').is_visible()
            page.evaluate("form.elements.mode.value='demo';form.elements.mode.dispatchEvent(new Event('change',{bubbles:true}));form.elements.visit_date.value='2026-10-24';form.elements.max_leg.value=180;")
            page.locator('[name=request]').fill('2명 5만원')
            page.locator('[name=budget]').fill('80000')
            page.locator('[name=budget]').press('Tab')
            page.locator('#submit-plan').click()
            page.wait_for_function("selected && selected.id",timeout=45000)
            assert page.locator('.results-area').is_visible()
            assert not page.locator('.conditions').is_visible()
            assert page.evaluate('selected.conditions.budget')==80000
            assert page.evaluate("node('p','근거 원문').textContent")=='근거 원문'
            # Synchronous handler errors must use the same toast path as rejected promises.
            assert page.evaluate('''async () => {
                const original=toast;let message;
                toast=value=>{message=value;};
                try {
                    button('failure',()=>{throw new Error('handled button error');}).click();
                    await new Promise(resolve=>setTimeout(resolve,0));
                    return message==='handled button error';
                } finally {toast=original;}
            }''')
            # Timeout is per fetch, not just a timer around the polling loop.
            assert page.evaluate('''async () => {
                const original=window.fetch;
                window.fetch=(url,options)=>new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('aborted','AbortError'))));
                try{await api('/timeout-test',null,'GET',{timeout:20});return false;}
                catch(error){return error.message.includes('대기 시간');}
                finally{window.fetch=original;}
            }''')
            # Cancelling before POST returns must cancel the newly issued job.
            assert page.evaluate('''async () => {
                const original=api;let resolveStart;const deleted=[];
                api=(path,body,method)=>method==='DELETE'?(deleted.push(path),Promise.resolve({cancelled:true})):new Promise(resolve=>resolveStart=resolve);
                try{const pending=createPlanWithProgress({}).catch(error=>error.message);await PlanSearch.cancel();resolveStart({id:'late-job'});await pending;return deleted.includes('/plan-jobs/late-job');}
                finally{api=original;}
            }''')
            with page.expect_response(lambda r:r.url.endswith('/shares') and r.request.method=='POST') as response:
                page.get_by_role('button',name='공유 링크 복사',exact=True).click()
            share=response.value.json()['url']
            guest=browser.new_context();guest.route('**/*',offline)
            shared=guest.new_page();shared.on('pageerror',lambda e:errors.append(str(e)))
            shared.goto(base+share,wait_until='networkidle')
            assert shared.locator('#shared-form').is_visible()
            shared.get_by_role('button',name='내 의견 전달하기').click()
            playwright.expect(shared.locator('#shared-status')).to_have_text('의견을 전달했어요.')
            with page.expect_response(lambda r:r.url.endswith('/shares') and r.request.method=='DELETE'):
                page.get_by_role('button',name='공유 취소',exact=True).click()
            shared.reload(wait_until='networkidle')
            assert not shared.locator('#shared-form').is_visible()
            assert '취소' in shared.locator('#shared-status').inner_text()
            page.locator('#edit-conditions').click()
            assert page.locator('[name=budget]').input_value()=='80000'
            assert page.locator('.conditions').is_visible()
            for width in (390,768,1440):
                page.set_viewport_size({'width':width,'height':900})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),width
            page.screenshot(path=str(tmp_path/'mobile-input.png'),full_page=True)
            assert not errors,errors
            browser.close()
    finally:
        server.should_exit=True;thread.join(10);sock.close()
