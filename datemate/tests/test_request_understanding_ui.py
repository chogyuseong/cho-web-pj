"""‘이렇게 이해했어요’ 칩·반영하지 못한 표현·자주 쓰는 조건 칩(390px·320px, 키보드).

외부 API는 부르지 않는다. 추천 요청(/api/plan-jobs)은 가로채 본문만 확인한다."""
import os
import socket
import threading
import time
from contextlib import contextmanager

import pytest
import uvicorn

from app.main import app
from app.models import Conditions
from app.request_intent import normalize


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
def opened(base, width=390):
    playwright = pytest.importorskip('playwright.sync_api')
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(channel=os.getenv('DATEMATE_BROWSER_CHANNEL', 'msedge'), headless=True)
        try:
            ctx = browser.new_context(viewport={'width': width, 'height': 900}, timezone_id='Asia/Seoul', bypass_csp=True)
            page = ctx.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.route('**/*', lambda route: route.continue_() if route.request.url.startswith(base) else route.abort())
            page.clock.set_fixed_time('2026-11-13T09:00:00+09:00')
            page.goto(base, wait_until='networkidle')
            page.wait_for_function("typeof statusData!=='undefined'&&!!statusData&&document.querySelector('.simple-plan-form')")
            yield page, errors
            assert not errors, errors
        finally:
            browser.close()


def understood(page):
    return page.get_by_role('group', name='이해한 조건 · 누르면 빼거나 다시 넣어요')


def chip(page, label):
    return understood(page).locator(f'[data-request-item="{label}"]')


def no_overflow(page):
    return page.evaluate('document.documentElement.scrollWidth<=innerWidth')


def test_understanding_chips_show_evidence_estimates_and_gaps(server):
    with opened(server) as (page, errors):
        box = page.locator('#request-understanding')
        assert box.is_hidden()
        page.locator('[name=request]').fill('조용하고 비 와도 괜찮은 곳, 분위기 좋은 데')
        page.locator('#parse').click()
        page.wait_for_function('!document.querySelector("#request-understanding").hidden')
        assert box.locator('h3').inner_text() == '이렇게 이해했어요'
        buttons = understood(page).get_by_role('button')
        assert buttons.evaluate_all('bs=>bs.map(b=>b.dataset.requestItem)') == ['setting:indoor', 'date:비 오는 날', 'priority:talk']
        assert buttons.evaluate_all('bs=>bs.map(b=>b.firstChild.textContent)') == ['실내만', '데이트 분류: 비 오는 날', '조용한 곳·대화 우선']
        assert buttons.evaluate_all('bs=>bs.map(b=>!!b.querySelector(".understood-estimated"))') == [False, False, True]
        talk = chip(page, 'priority:talk')
        assert talk.get_attribute('aria-pressed') == 'true'
        assert talk.get_attribute('aria-label').startswith('조용한 곳·대화 우선 (추정), 근거 ‘조용하고’')
        assert '추정 · 조용한 곳·대화 우선' in box.locator('.understood-notes').inner_text()
        assert box.locator('.request-gaps').inner_text() == '‘분위기 좋은’은 아직 반영하지 못했어요.'
        # 해석이 폼을 채웠다.
        assert page.evaluate('[form.elements.priority.value,form.elements.setting.value,form.elements.date_subcategory.value]') == ['talk', 'indoor', '비 오는 날']
        # 자주 쓰는 조건 칩은 켜진 조건을 눌린 상태로 보인다.
        quick = page.get_by_role('group', name='자주 쓰는 조건')
        assert quick.get_by_role('button', name='조용한 곳', exact=True).get_attribute('aria-pressed') == 'true'
        assert quick.get_by_role('button', name='비 와도 OK', exact=True).get_attribute('aria-pressed') == 'true'
        assert quick.get_by_role('button', name='걷기 적게', exact=True).get_attribute('aria-pressed') == 'false'
        # 글자 14px 이상, 누를 곳 44px 이상.
        sizes = box.evaluate("el=>[...el.querySelectorAll('*')].filter(n=>n.childNodes.length&&[...n.childNodes].some(c=>c.nodeType===3&&c.textContent.trim())).map(n=>parseFloat(getComputedStyle(n).fontSize))")
        assert min(sizes) >= 14
        for target in understood(page).get_by_role('button').all() + quick.get_by_role('button').all():
            assert target.bounding_box()['height'] >= 44
        assert no_overflow(page)
        page.set_viewport_size({'width': 320, 'height': 900})
        assert no_overflow(page)
        assert box.evaluate('el=>el.scrollWidth<=el.clientWidth+1')


def test_removed_chip_is_left_out_of_the_form_and_the_plan_request(server):
    with opened(server) as (page, errors):
        bodies = []

        def create(route):
            if route.request.method != 'POST':
                return route.continue_()
            bodies.append(route.request.post_data_json)
            return route.fulfill(json={'id': 'understanding-job'})

        page.route('**/api/plan-jobs', create)
        page.route('**/api/plan-jobs/understanding-job', lambda route: route.fulfill(json={'status': 'failed', 'message': '점검용 검색 중단'}))
        page.get_by_role('group', name='인기 동네').get_by_role('button', name='서울 성수', exact=True).click()
        page.locator('[name=request]').fill('조용한 카페 투어, 매운 건 빼고')
        # '피할 활동' 칸은 간단한 조건 화면에서 숨겨져 있다(예전 연동용). 직접 적은 값으로 넣어 둔다.
        page.evaluate("form.elements.avoid.value='클라이밍'")
        page.locator('#parse').click()
        page.wait_for_function('!!document.querySelector("[data-request-item=\'priority:talk\']")')
        assert page.evaluate('form.elements.priority.value') == 'talk'
        assert page.locator('[name=avoid]').input_value().startswith('클라이밍, 매운')
        # 키보드로 칩을 뺀다(Enter). 포커스는 같은 칩에 남는다.
        talk = chip(page, 'priority:talk')
        talk.focus()
        page.keyboard.press('Enter')
        page.wait_for_function('document.querySelector("[data-request-item=\'priority:talk\']").getAttribute("aria-pressed")==="false"')
        assert page.evaluate('document.activeElement.dataset.requestItem') == 'priority:talk'
        assert page.evaluate('form.elements.priority.value') == 'balanced'
        assert '뺐어요' in page.locator('.request-understanding-status').inner_text()
        # 스페이스로 음식 제외도 뺀다. 직접 적은 '클라이밍'은 남는다.
        spicy = chip(page, 'avoid:매운 음식')
        spicy.focus()
        page.keyboard.press('Space')
        page.wait_for_function('document.querySelector("[data-request-item=\'avoid:매운 음식\']").getAttribute("aria-pressed")==="false"')
        assert page.locator('[name=avoid]').input_value() == '클라이밍'
        page.locator('#submit-plan').click()
        deadline = time.monotonic() + 20
        while not bodies and time.monotonic() < deadline:
            page.wait_for_timeout(100)
        body = bodies[-1]
        assert sorted(body['request_ignore']) == ['avoid:매운 음식', 'priority:talk']
        assert body['priority'] == 'balanced' and body['avoid'] == ['클라이밍']
        c = normalize(Conditions.model_validate(body))
        assert c.priority == 'balanced' and c.avoid == ['클라이밍'] and c.themes == ['카페·미식']
        # 다시 넣으면(+) 조건이 돌아온다.
        page.locator('#edit-conditions').click()
        page.wait_for_function('!document.querySelector(".conditions").hidden')
        chip(page, 'priority:talk').click()
        page.wait_for_function('document.querySelector("[data-request-item=\'priority:talk\']").getAttribute("aria-pressed")==="true"')
        assert page.evaluate('form.elements.priority.value') == 'talk'


def test_quick_chips_add_supported_phrases_and_can_be_turned_off(server):
    with opened(server) as (page, errors):
        quick = page.get_by_role('group', name='자주 쓰는 조건')
        assert quick.get_by_role('button').all_inner_texts() == ['조용한 곳', '비 와도 OK', '걷기 적게', '사진 잘 나오는 곳', '가성비', '기념일']
        page.locator('[name=request]').fill('전시 보고 싶어')
        walk = quick.get_by_role('button', name='걷기 적게', exact=True)
        walk.click()
        page.wait_for_function('document.querySelector(".request-quick-chips [aria-pressed=true]")')
        assert page.locator('[name=request]').input_value() == '전시 보고 싶어, 걷기 적게'
        assert walk.get_attribute('aria-pressed') == 'true'
        assert page.evaluate('form.elements.transport.value') == 'transit'
        assert chip(page, 'exclude:walk').get_attribute('aria-pressed') == 'true'
        # 다시 누르면 그 조건을 빼고(글은 그대로), 이동 수단도 원래대로 돌아간다.
        walk.click()
        page.wait_for_function('document.querySelector("[data-request-item=\'transport:transit\']").getAttribute("aria-pressed")==="false"')
        assert walk.get_attribute('aria-pressed') == 'false'
        assert page.evaluate('form.elements.transport.value') == 'walk'
        assert page.locator('[name=request]').input_value() == '전시 보고 싶어, 걷기 적게'
        # 우선순위는 하나라 사진을 켜면 조용함은 반영하지 못했다고 알린다.
        quick.get_by_role('button', name='조용한 곳', exact=True).click()
        page.wait_for_function('form.elements.priority.value==="talk"')
        quick.get_by_role('button', name='사진 잘 나오는 곳', exact=True).click()
        page.wait_for_function('form.elements.priority.value==="photo"')
        assert quick.get_by_role('button', name='조용한 곳', exact=True).get_attribute('aria-pressed') == 'false'
        assert '하나만 정해요' in page.locator('.request-gaps').inner_text()
        # 글을 지우면 해석이 넣은 값을 되돌리고 칸을 닫는다.
        page.locator('[name=request]').fill('')
        page.locator('[name=request]').dispatch_event('change')
        page.wait_for_function('document.querySelector("#request-understanding").hidden')
        assert page.evaluate('[form.elements.priority.value,form.elements.transport.value]') == ['balanced', 'walk']
        assert no_overflow(page)
