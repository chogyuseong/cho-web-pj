"""잠든 서버의 첫 접속(server-wake.js): 화면은 먼저 뜨고, 서버 응답이 수십 초 늦거나 준비 중 오류(503·시간 초과)가 와도
'서버를 준비하고 있어요' 안내만 보이다가 준비되면 저절로 정상 상태가 된다. 그 사이 누른 [코스 만들기]는 실패하지 않고
준비된 뒤 진행된다. 운영에서는 Worker 가 화면을 엣지에서 주고(cloudflare/edge.mjs) API 는 컨테이너가 켜질 때까지 기다린다.
여기서는 /api/status 를 붙잡아 두거나 503 으로 답해 그 상태를 만든다. 외부 API 는 부르지 않는다."""
import os
import socket
import threading
import time
from contextlib import contextmanager

import pytest
import uvicorn

from app.main import app
from app.models import Conditions

DAY = '2026-11-13'
WAITING = '서버를 준비하고 있어요'


@pytest.fixture
def server():
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen(128)
    base = f'http://127.0.0.1:{sock.getsockname()[1]}'
    srv = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=srv.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not srv.started and time.monotonic() < deadline:
        time.sleep(.05)
    assert srv.started
    try:
        yield base
    finally:
        srv.should_exit = True
        thread.join(10)
        sock.close()


@contextmanager
def browser_page(base):
    playwright = pytest.importorskip('playwright.sync_api')
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(channel=os.getenv('DATEMATE_BROWSER_CHANNEL', 'msedge'), headless=True)
        try:
            # Playwright wait_for_function evaluates text with eval, which CSP blocks.
            ctx = browser.new_context(viewport={'width': 390, 'height': 900}, timezone_id='Asia/Seoul', bypass_csp=True)
            page = ctx.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.route('**/*', lambda route: route.continue_() if route.request.url.startswith(base) else route.abort())
            page.clock.set_fixed_time(f'{DAY}T09:00:00+09:00')
            yield page, errors
            assert not errors, errors
        finally:
            browser.close()


def hold(page, pattern):
    held = []
    page.route(pattern, lambda route: held.append(route))
    return held


def wait_until(page, check, seconds=15):
    deadline = time.monotonic() + seconds
    while not check() and time.monotonic() < deadline:
        page.wait_for_timeout(100)
    assert check()


def banner(page):
    return page.locator('#server-wake')


def test_home_shows_a_calm_notice_and_runs_an_early_course_request_when_ready(server):
    with browser_page(server) as (page, _):
        jobs = []

        def create(route):
            if route.request.method != 'POST':
                return route.continue_()
            jobs.append(route.request.post_data_json)
            return route.fulfill(json={'id': 'wake-job'})

        page.route('**/api/plan-jobs', create)
        page.route('**/api/plan-jobs/wake-job', lambda route: route.fulfill(json={'status': 'failed', 'message': '점검용 검색 중단'}))
        statuses = hold(page, '**/api/status')
        page.goto(server)
        # 화면(폼·테마 카드)은 서버 응답 없이 먼저 쓸 수 있다.
        page.wait_for_selector('.simple-plan-form')
        assert page.evaluate('!statusData')
        assert banner(page).count() == 0 or banner(page).is_hidden()
        # 늦어지면(1.5초 뒤) 오류가 아닌 준비 안내가 뜬다.
        page.wait_for_selector('#server-wake:not([hidden])')
        assert WAITING in banner(page).inner_text()
        assert page.locator('#server-wake').get_attribute('role') == 'status'
        # 준비 전에 동네를 고르고 [데이트 코스 추천받기]를 눌러도 실패로 끝나지 않는다.
        page.get_by_role('group', name='인기 동네').get_by_role('button', name='부산 해운대', exact=True).click()
        page.locator('#submit-plan').click()
        page.wait_for_function('document.querySelector("#toast").textContent.includes("서버를 준비하고 있어요")')
        assert page.locator('#submit-plan').is_disabled()
        # 첫 응답이 준비 중 오류(Cloudflare 503 같은 HTML)로 와도 다시 묻고, 안내는 그대로다.
        wait_until(page, lambda: len(statuses) == 1)
        statuses[0].fulfill(status=503, content_type='text/html', body='<html>starting</html>')
        wait_until(page, lambda: len(statuses) == 2)
        assert WAITING in banner(page).inner_text()
        assert page.locator('#status').text_content() == '서비스 상태를 확인하고 있어요.'
        assert jobs == []
        # 서버가 준비되면 안내가 사라지고, 미뤄 둔 동네 선택과 추천 요청이 그대로 이어진다.
        statuses[1].continue_()
        page.wait_for_function('!!statusData')
        page.wait_for_selector('#server-wake', state='hidden')
        wait_until(page, lambda: len(jobs) == 1)
        body = jobs[0]
        assert body['region'] == '부산' and body['origin']['name'] == '부산 해운대역 지역 중심'
        Conditions.model_validate(body)
        page.wait_for_function('document.querySelector("#progress").textContent.includes("점검용 검색 중단")')
        assert '전국 실제 장소 검색' in page.locator('#status').text_content()
        assert page.locator('#date-category-tabs button').count() > 0


def test_home_on_a_ready_server_shows_no_notice(server):
    with browser_page(server) as (page, _):
        page.goto(server, wait_until='networkidle')
        page.wait_for_function('!!statusData')
        page.wait_for_timeout(1800)
        assert banner(page).count() == 0 or banner(page).is_hidden()


def test_real_errors_are_not_retried_as_a_sleeping_server(server):
    with browser_page(server) as (page, _):
        calls = []

        def busy(route):
            calls.append(route)
            route.fulfill(status=429, json={'detail': '요청이 많아요. 잠시 후 다시 시도해 주세요.'})

        page.route('**/api/status', busy)
        page.goto(server)
        page.wait_for_function('document.querySelector("#status").textContent.includes("요청이 많아요")')
        page.wait_for_timeout(1800)
        assert len(calls) == 1
        assert banner(page).count() == 0 or banner(page).is_hidden()


def test_shared_page_waits_for_a_sleeping_server(server):
    with browser_page(server) as (page, _):
        plans = hold(page, '**/api/shared-plan')
        page.goto(server + '/shared#token-for-test')
        wait_until(page, lambda: len(plans) == 1)
        # 연결이 끊겨도(시간 초과와 같은 갈래) 오류 대신 준비 안내를 띄우고 다시 묻는다.
        plans[0].abort('timedout')
        page.wait_for_selector('#server-wake:not([hidden])')
        assert WAITING in banner(page).inner_text()
        assert page.locator('#shared-status').inner_text() == '코스를 불러오고 있어요.'
        wait_until(page, lambda: len(plans) == 2)
        plans[1].fulfill(json={'notice': '두 사람의 의견을 모아요.', 'my_choices': {}, 'festival_search': None,
                               'places': [{'id': 'p1', 'name': '작은 전시실', 'arrival': '11:00', 'departure': '12:00',
                                           'address': '서울 성동구'}]})
        page.wait_for_selector('#shared-form:not([hidden])')
        page.wait_for_selector('#server-wake', state='hidden')
        assert page.locator('#shared-status').inner_text() == '두 사람의 의견을 모아요.'
        assert '작은 전시실' in page.locator('#shared-places').inner_text()
