"""Asset UI regression tests: hidden lazy photos, menus, and map SDK failure."""
import base64
import os
import socket
import threading
import time
from urllib.parse import urlsplit
import pytest
import uvicorn
from app.main import app

PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6L3sAAAAASUVORK5CYII=')


def test_real_plan_assets_and_map_fallback():
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
            page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            def route(request):
                url=request.request.url;path=urlsplit(url).path
                if path.endswith('/asset-test.png') or 'tile.openstreetmap.org' in url:
                    return request.fulfill(body=PNG,content_type='image/png')
                if not url.startswith(base):return request.abort()
                if path.endswith('/media'):
                    return request.fulfill(json={'status':'available','photos':[{'kind':'search_result','title':'검증 사진','source':base+'/asset-test.png','image_url':base+'/asset-test.png','search_url':base,'checked_at':'2026-10-25'}]})
                if path.endswith('/menu'):
                    return request.fulfill(json={'status':'available','items':[{'name':'대표 메뉴','display_price':'12,000원'}],'menu_images':[base+'/asset-test.png'],'checked_at':'2026-10-25','source_url':base})
                if path.endswith('/blogs'):return request.fulfill(json={'items':[],'blogs':[]})
                if path.endswith('/restaurant-matches'):return request.fulfill(json={'groups':[],'popular':{'restaurants':[]}})
                return request.continue_()
            page.route('**/*',route)
            page.goto(base,wait_until='networkidle')
            page.wait_for_function("typeof statusData!=='undefined' && !!statusData")
            page.evaluate('''()=>{
              const img=document.createElement('img');img.id='hidden-lazy-regression';
              img.loading='lazy';img.width=100;img.height=100;document.body.append(img);
              loadSafePhoto(img,[{title:'지연 로딩 검증',image_url:location.origin+'/asset-test.png?lazy-check'}]);
            }''')
            playwright.expect(page.locator('#hidden-lazy-regression')).to_be_visible(timeout=10000)
            assert page.locator('#hidden-lazy-regression').evaluate('img=>img.naturalWidth>0')
            response=page.request.post(base+'/api/plans',data={'visit_date':'2026-10-25','max_leg':180,'budget':1000000})
            assert response.ok,response.text()
            plan=response.json()['plans'][0]
            page.evaluate('''plan=>{
              plan.conditions.mode='real';plan.conditions.allow_estimates=true;
              plan.places.forEach(place=>{place.demo=false;place.category='카페·미식';});
              plans=[plan];selected=plan;statusData.map_js_key='';
              setTab(false);showPlannerPage(true);renderResults();renderDetail();
            }''',plan)
            photo=page.locator('.timeline-card .place-photo img').first
            photo.scroll_into_view_if_needed()
            playwright.expect(photo).to_be_visible(timeout=15000)
            assert photo.evaluate('img=>img.naturalWidth>0')
            menu=page.locator('.timeline-card .restaurant-menu').first
            menu.scroll_into_view_if_needed()
            playwright.expect(menu.locator('.menu-price-row')).to_have_count(1)
            playwright.expect(menu.locator('.menu-image-preview img')).to_have_count(1)
            assert menu.locator('.menu-image-preview img').evaluate('img=>img.complete && img.naturalWidth>0')
            playwright.expect(page.locator('.fallback-plan-map .leaflet-tile-loaded').first).to_be_visible()
            # Authentication failure and repeated redraw must preserve fallback,
            # and a reconnect must dispose the previous Leaflet instance.
            page.evaluate("document.querySelector('.plan-map').showMapFallback()")
            playwright.expect(page.locator('.fallback-plan-map')).to_have_count(1)
            page.evaluate('renderDetail()')
            playwright.expect(page.locator('.fallback-plan-map')).to_have_count(1)
            for width in (390,768,1440):
                page.set_viewport_size({'width':width,'height':900})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
            assert not errors,errors
            browser.close()
    finally:
        server.should_exit=True;thread.join(10);sock.close()
