"""Live public-area UI check with disposable storage and existing API settings.

Uses port 8000 (must be free), so configured localhost map URLs can be tested.
Writes screenshots/report only under runtime/live-browser-check. No user data.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:8000'


def main():
    with socket.socket() as sock:sock.bind(('127.0.0.1',8000))
    output=ROOT/'runtime'/'live-browser-check';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='datemate-live-browser-') as runtime:
        env=os.environ.copy()
        env.update(DATEMATE_RUNTIME=runtime,DATABASE_URL='',DATEMATE_ENV='development',
                   DATEMATE_PUBLIC_ORIGIN='',DATEMATE_ALLOWED_HOSTS='',DATEMATE_BACKUP_DIR='',
                   DATEMATE_BOOTSTRAP_INDEX='1',EMBEDDING_MODE='demo',PORT='8000',PYTHONIOENCODING='utf-8')
        env.pop('K_SERVICE',None)
        with (output/'server.log').open('w',encoding='utf-8') as log:
            server=subprocess.Popen([sys.executable,'-m','app.cloud_start'],cwd=ROOT,env=env,stdout=log,stderr=log)
            try:
                deadline=time.monotonic()+60
                while time.monotonic()<deadline:
                    if server.poll() is not None:raise AssertionError('server failed to start; see server.log')
                    try:
                        if httpx.get(BASE+'/readyz',timeout=2).status_code==200:break
                    except httpx.HTTPError:pass
                    time.sleep(.2)
                else:raise AssertionError('startup timeout')
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(channel=os.getenv('DATEMATE_BROWSER_CHANNEL','msedge'),headless=True)
                    page=browser.new_page(viewport={'width':1440,'height':1000})
                    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(BASE,wait_until='networkidle')
                    page.wait_for_function("typeof statusData!=='undefined'&&!!statusData")
                    page.locator('#origin-location').get_by_role('button',name='주소 검색 · 지도에서 선택',exact=True).click()
                    page.wait_for_function('!!locationMap || !!window.naver?.maps',timeout=30000)
                    page.locator('.location-search input').fill('서울특별시 마포구 동교로 227')
                    page.locator('.location-search').get_by_role('button',name='주소 검색',exact=True).click()
                    page.locator('.location-result').first.wait_for(timeout=30000)
                    page.locator('.location-result').first.click()
                    page.screenshot(path=str(output/'location.png'),full_page=True)
                    page.locator('#dialog').get_by_role('button',name='이 지역에서 데이트하기',exact=True).click()
                    # Public fixture coordinates; no personal address or existing plan.
                    page.evaluate('''() => {
                        form.elements.mode.value='real';
                        form.elements.visit_date.value='2026-10-31';
                        form.elements.max_leg.value='45';
                        form.elements.budget.value='100000';
                        form.elements.count.value='3';
                    }''')
                    page.locator('[name=request]').fill('연남동에서 카페 보고 산책하고 식사하고 싶어요')
                    page.locator('#submit-plan').click()
                    page.wait_for_function('selected?.id&&!document.querySelector("#submit-plan").disabled',timeout=180000)
                    count=page.evaluate('plans.length')
                    assert count>0
                    ids=page.evaluate('selected.places.map(p=>p.id)')
                    assets=[]
                    for pid in ids:
                        media=page.request.get(BASE+'/api/places/'+pid+'/media?mode=real',timeout=45000).json()
                        menu=page.request.get(BASE+'/api/places/'+pid+'/menu?mode=real',timeout=45000).json()
                        assets.append({'photos':len(media.get('photos',[])),'menu_items':len(menu.get('items',[])),'menu_status':menu.get('status')})
                    page.wait_for_timeout(2500)
                    page.screenshot(path=str(output/'desktop-results.png'),full_page=True)
                    for width in (390,768,1440):
                        page.set_viewport_size({'width':width,'height':900})
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
                        if width==390:page.screenshot(path=str(output/'mobile-results.png'),full_page=True)
                    assert not errors,errors
                    result={'real_course_count':count,'assets':assets,'browser_errors':errors,'responsive_widths':[390,768,1440],
                            'map_dialog_opened':True,'personal_storage_used':False}
                    (output/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                    print(json.dumps(result,ensure_ascii=True,indent=2))
                    browser.close()
            finally:
                if os.name=='nt':
                    # The Windows venv launcher can have a child interpreter.
                    subprocess.run(['taskkill','/PID',str(server.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                else:server.terminate()
                try:server.wait(timeout=15)
                except subprocess.TimeoutExpired:server.kill();server.wait()


if __name__=='__main__':main()
