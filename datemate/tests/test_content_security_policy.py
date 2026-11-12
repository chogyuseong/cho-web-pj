"""Content-Security-Policy strings and an offline browser run that must cause no violation."""
import base64
import os
import socket
import threading
import time
from urllib.parse import urlsplit

import pytest
import uvicorn
from fastapi.testclient import TestClient

from app import web_security
from app.main import app

HTTPS_POLICY = (
    "default-src 'self'; "
    "script-src 'self' https://oapi.map.naver.com https://*.naver.com https://*.naver.net "
    "https://*.navercorp.com https://*.pstatic.net; "
    "script-src-attr 'none'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' data: https://fonts.gstatic.com; "
    "img-src 'self' data: blob: https:; "
    "connect-src 'self' https://www.wikidata.org https://commons.wikimedia.org https://*.naver.com "
    "https://*.naver.net https://*.navercorp.com https://*.pstatic.net; "
    "media-src 'self'; worker-src 'self' blob:; child-src 'self' blob:; frame-src 'none'; "
    "manifest-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; "
    "form-action 'self'; upgrade-insecure-requests"
)


def directives(policy):
    return dict((part.split(' ', 1) + [''])[:2] for part in policy.split('; '))


def test_https_policy_is_fixed():
    with TestClient(app, base_url='https://testserver') as client:
        assert client.get('/').headers['content-security-policy'] == HTTPS_POLICY
        assert client.get('/shared').headers['content-security-policy'] == HTTPS_POLICY


def test_production_uses_the_https_policy_even_behind_an_http_hop(monkeypatch):
    monkeypatch.setenv('DATEMATE_ENV', 'production')
    monkeypatch.setenv('DATEMATE_ALLOWED_HOSTS', 'testserver')
    # No lifespan: production start-up checks need a database URL, the header does not.
    client = TestClient(app)
    assert client.get('/healthz').headers['content-security-policy'] == HTTPS_POLICY


def test_local_http_differs_only_in_http_sources_and_upgrade():
    with TestClient(app) as client:
        local = directives(client.get('/').headers['content-security-policy'])
    deployed = directives(HTTPS_POLICY)
    assert set(deployed) - set(local) == {'upgrade-insecure-requests'}
    changed = {name for name in local if local[name] != deployed[name]}
    assert changed == {'script-src', 'img-src'}
    assert local['script-src'] == deployed['script-src'] + ' ' + web_security.NAVER_LOCAL_HTTP
    assert local['img-src'] == deployed['img-src'] + ' http:'


def test_required_directives_are_present():
    policy = directives(HTTPS_POLICY)
    for name in ('default-src', 'script-src', 'style-src', 'img-src', 'connect-src', 'font-src',
                 'frame-src', 'child-src', 'worker-src', 'manifest-src', 'object-src', 'base-uri',
                 'frame-ancestors', 'form-action', 'script-src-attr'):
        assert name in policy, name
    assert policy['object-src'] == "'none'" and policy['frame-ancestors'] == "'none'"
    assert policy['script-src-attr'] == "'none'" and policy['base-uri'] == "'self'"
    assert "'unsafe-eval'" not in HTTPS_POLICY and "'unsafe-inline'" not in policy['script-src']


# --- browser -------------------------------------------------------------------

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
PHOTO_URLS = ('https://blogthumb.pstatic.net/csp/photo.jpg', 'https://csp-blog.example.com/photo.jpg',
              'https://upload.wikimedia.org/wikipedia/commons/a/a0/csp.jpg')
FESTIVAL_IMAGE = 'https://tong.visitkorea.or.kr/cms/resource/00/0000000_image2_1.jpg'
INIT = """document.addEventListener('securitypolicyviolation', e => {
  (window.__csp = window.__csp || []).push(e.violatedDirective + ' ' + e.blockedURI);
});"""


def poll(page, expression, timeout=30):
    # wait_for_function evaluates strings with eval, which this policy forbids.
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if page.evaluate(f'() => Boolean({expression})'):
            return
        time.sleep(.1)
    raise AssertionError('timed out: ' + expression)


def offline_routes(context, base, explore_rows):
    def handle(route):
        url = route.request.url
        path = urlsplit(url).path
        if url in PHOTO_URLS or url.startswith(('https://tong.visitkorea.or.kr/', 'https://tile.openstreetmap.org/')):
            return route.fulfill(body=PNG, content_type='image/png')
        if url.startswith(('https://www.wikidata.org/', 'https://commons.wikimedia.org/')):
            return route.fulfill(json={'claims': {}, 'query': {}}, headers={'Access-Control-Allow-Origin': '*'})
        if not url.startswith(base):
            return route.abort()
        if path == '/api/festivals':
            return route.fulfill(json={'status': 'available', 'message': '테스트', 'festivals': [dict(
                id='123456', title='테스트 축제', start='2026-10-01', end='2026-12-31', region='서울',
                address='서울 중구 세종대로 110', lat=37.5663, lon=126.9779, image_url=FESTIVAL_IMAGE,
                source_url='https://korean.visitkorea.or.kr/')]})
        if path.startswith('/api/festivals/'):
            return route.fulfill(json={'status': 'available', 'fee': '무료', 'hours': ''})
        if path == '/api/explore':
            return route.fulfill(json={'places': explore_rows, 'total': len(explore_rows), 'region': '서울',
                                       'activity': '전체', 'has_more': False, 'message': ''})
        if path.endswith('/media'):
            # The last card has no photos but a Wikidata item, so the browser asks Wikimedia.
            if explore_rows and path.split('/')[-2] == explore_rows[-1]['id']:
                return route.fulfill(json={'photos': [], 'videos': [], 'wikidata_id': 'Q1'})
            photos = [dict(kind='search_result', source=url, image_url=url, url=url, title='사진',
                           checked_at='2026-11-01', source_label='검색') for url in PHOTO_URLS]
            return route.fulfill(json={'photos': photos, 'videos': []})
        if path.endswith(('/blogs', '/menu')):
            return route.fulfill(json={'items': [], 'blogs': [], 'status': 'unavailable'})
        return route.continue_()
    context.route('**/*', handle)


def test_main_flows_cause_no_csp_violation():
    playwright = pytest.importorskip('playwright.sync_api')
    sock = socket.socket(); sock.bind(('127.0.0.1', 0)); sock.listen(128)
    base = f'http://127.0.0.1:{sock.getsockname()[1]}'
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True); thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(.05)
        with TestClient(app) as client:
            rows = [dict(row, demo=False) for row in client.get('/api/places?mode=demo').json()['places'][:3]]
        with playwright.sync_playwright() as pw:
            browser = pw.chromium.launch(channel=os.getenv('DATEMATE_BROWSER_CHANNEL', 'msedge'), headless=True)
            context = browser.new_context(viewport={'width': 1440, 'height': 1000}, accept_downloads=True)
            context.add_init_script(INIT)
            offline_routes(context, base, rows)
            page = context.new_page()
            errors, console = [], []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.on('console', lambda m: console.append(m.text) if 'Content Security Policy' in m.text else None)
            response = page.goto(base, wait_until='networkidle')
            assert "default-src 'self'" in response.headers['content-security-policy']
            poll(page, "typeof statusData !== 'undefined' && statusData && document.querySelector('.simple-plan-form')")
            # Theme card, then the location picker (no Naver key in tests: Leaflet).
            page.evaluate("() => document.querySelector('[data-preset]').click()")
            page.evaluate("() => openLocationPicker('origin')")
            poll(page, "document.querySelector('#location-map .leaflet-tile')", 15)
            page.get_by_role('button', name='지도 중심을 선택').click()
            page.evaluate("() => document.getElementById('dialog').close()")
            # Demo course: results, plan map and the festival section with its photo.
            page.evaluate("() => {form.elements.mode.value='demo';form.elements.mode.dispatchEvent(new Event('change',{bubbles:true}));"
                          "form.elements.visit_date.value='2026-11-20';form.elements.max_leg.value=180;}")
            page.locator('#submit-plan').click()
            poll(page, 'selected && selected.id', 60)
            poll(page, "document.querySelector('.plan-map .leaflet-tile')", 20)
            poll(page, "document.querySelector('.festival-photo img') && document.querySelector('.festival-photo img').naturalWidth > 0", 20)
            page.evaluate("() => showPlace(selected.places[0].id, 'demo')")
            poll(page, "document.getElementById('dialog').open")
            page.evaluate("() => document.getElementById('dialog').close()")
            # Course card PNG save and print.
            page.get_by_role('button', name='코스 카드 저장').first.click()
            poll(page, "document.querySelector('.share-canvas')", 15)
            with page.expect_download() as download:
                page.get_by_role('button', name='PNG 이미지 저장').click()
            assert download.value.suggested_filename.endswith('.png')
            page.evaluate("() => { document.getElementById('dialog').close(); window.print = () => { window.__printed = true; }; }")
            page.get_by_role('button', name='인쇄 / PDF').first.click()
            assert page.evaluate('() => window.__printed === true')
            share = page.evaluate("(id) => api('/plans/'+id+'/shares', {})", page.evaluate('() => selected.id'))
            # Explore with photos from several https hosts and a Wikimedia lookup.
            page.locator('#nav-explore').click()
            page.evaluate('() => ExploreView.search()')
            poll(page, "[...document.querySelectorAll('#catalog img')].some(i => !i.hidden && i.naturalWidth > 0)", 20)
            page.wait_for_timeout(1500)
            main_violations = page.evaluate('() => window.__csp || []')
            shared = context.new_page()
            shared.goto(base + share['url'], wait_until='networkidle')
            poll(shared, "document.getElementById('shared-status').textContent.length > 0", 15)
            shared_violations = shared.evaluate('() => window.__csp || []')
            browser.close()
        assert main_violations == [] and shared_violations == [] and console == []
        assert errors == []
    finally:
        server.should_exit = True
        thread.join(5)
