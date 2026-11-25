"""조건 화면 간소화: 지역 칩·현재 위치(B), 날짜·시간·예산 칸과 칩(A·C), 지난번처럼 추천(D).

2026-11-25 시안: '기본 조건' 요약 줄·'바꾸기'·날짜/시간대/전체 예산 칩은 없어졌다. 날짜·시작·종료 칸이 항상 보이고,
예산은 '1인 예상 예산' 칩(3·6·10·15만원 × 인원)과 '예산 무관' 체크, 정확한 합계는 상세 조건 > 더 많은 조건의 '전체 예산' 칸이다.

외부 API는 부르지 않는다. 추천 요청(/api/plan-jobs)과 시·도 확인(/api/locations/region)은 가로채 응답한다.
시계는 브라우저 안에서만 2026-11-13(금) 서울 시각으로 고정한다."""
import json
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
STORE_KEY = 'datemate-last-conditions'


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
def opened(base, clock='09:00', **context):
    playwright = pytest.importorskip('playwright.sync_api')
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(channel=os.getenv('DATEMATE_BROWSER_CHANNEL', 'msedge'), headless=True)
        try:
            # Playwright wait_for_function evaluates text with eval, which CSP blocks.
            ctx = browser.new_context(viewport={'width': 390, 'height': 900}, timezone_id='Asia/Seoul',
                                      bypass_csp=True, **context)
            page = ctx.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.route('**/*', lambda route: route.continue_() if route.request.url.startswith(base) else route.abort())
            page.clock.set_fixed_time(f'{DAY}T{clock}:00+09:00')
            load(page, base)
            yield page, errors
            assert not errors, errors
        finally:
            browser.close()


def load(page, base):
    page.goto(base, wait_until='networkidle')
    page.wait_for_function("typeof statusData!=='undefined'&&!!statusData&&document.querySelector('.simple-plan-form')")


def intercept_jobs(page):
    bodies = []

    def create(route):
        if route.request.method != 'POST':
            return route.continue_()
        bodies.append(route.request.post_data_json)
        return route.fulfill(json={'id': 'quick-job'})

    page.route('**/api/plan-jobs', create)
    page.route('**/api/plan-jobs/quick-job', lambda route: route.fulfill(json={'status': 'failed', 'message': '점검용 검색 중단'}))
    return bodies


def wait_job(page, bodies, count):
    deadline = time.monotonic() + 20
    while len(bodies) < count and time.monotonic() < deadline:
        page.wait_for_timeout(100)
    assert len(bodies) == count
    page.wait_for_function('!document.querySelector("#submit-plan").disabled&&document.querySelector("#progress").textContent.includes("점검용 검색 중단")')
    return bodies[-1]


def area_chip(page, name):
    return page.get_by_role('group', name='인기 동네').get_by_role('button', name=name, exact=True)


def form_chip(page, group, name):
    # 2026-11-25 시안: 칩 묶음이 폼 카드에 바로 있다(예전 #condition-details 패널은 없어짐).
    return page.get_by_role('group', name=group).get_by_role('button', name=name, exact=True)


def open_details(page, more=False):
    """'상세 조건 더보기'(more=True 면 안의 '더 많은 조건'까지)를 요약을 눌러 펼친다."""
    extra = page.locator('details.simple-extra-options')
    if extra.evaluate('d=>!d.open'):
        extra.locator(':scope>summary').click()
    if more:
        detail_more = extra.locator('details.detail-more')
        if detail_more.evaluate('d=>!d.open'):
            detail_more.locator(':scope>summary').click()


def open_dream(page):
    """카드 맨 위 접힘 '한 줄로 적어서 조건 채우기 (선택)'을 펼친다."""
    dream = page.locator('#conditions .simple-dream')
    if dream.evaluate('d=>!d.open'):
        dream.locator(':scope>summary').click()


def set_budget_total(page, value):
    """'더 많은 조건'의 전체 예산(원, 일행 합계) 칸에 직접 넣는다(예전 '전체 예산 > 직접' 칩 대신)."""
    open_details(page, more=True)
    page.locator('[name=budget]').fill(str(value))


def back_to_conditions(page):
    page.locator('#edit-conditions').click()
    page.wait_for_function('!document.querySelector(".conditions").hidden')


def region_reply(page, reply):
    seen = []

    def handle(route):
        seen.append(route.request.post_data_json)
        return route.fulfill(json=reply)

    page.unroute('**/api/locations/region')
    page.route('**/api/locations/region', handle)
    return seen


def test_area_chip_is_one_tap_and_map_choice_clears_it(server):
    with opened(server) as (page, errors):
        bodies = intercept_jobs(page)
        # 꼭 정할 것은 지역뿐: '필수'는 하나. 날짜·시간 칸은 바로 보이고 예산은 1인 칩(기본 6만원), 인원·장소 수·전체 예산 칸은 상세 조건 안에 접혀 있다.
        assert page.locator('.field-requirement').count() == 1
        for name in ('visit_date', 'start', 'end'):
            assert page.locator(f'[name={name}]').is_visible(), name
        for name in ('budget', 'people', 'count'):
            assert not page.locator(f'[name={name}]').is_visible(), name
        assert [page.locator(f'[name={n}]').input_value() for n in ('visit_date', 'start', 'end')] == [DAY, '11:00', '19:00']
        assert form_chip(page, '1인 예상 예산', '6만원').get_attribute('aria-pressed') == 'true'
        assert page.locator('.budget-note').inner_text() == '1인 6만 원까지 · 2명 합계 12만 원으로 찾아요.'
        chips = page.get_by_role('group', name='인기 동네').get_by_role('button')
        assert chips.all_inner_texts() == ['서울 성수', '서울 연남·홍대', '서울 서촌·안국', '부산 해운대', '강릉 안목', '경주 황리단길', '제주 애월', '현재 위치']
        for chip in chips.all():
            box = chip.bounding_box()
            assert box['height'] >= 44
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        category = page.evaluate('[form.elements.date_category.value,form.elements.date_subcategory.value]')
        chip = area_chip(page, '부산 해운대')
        assert chip.get_attribute('aria-pressed') == 'false'
        chip.click()
        page.wait_for_function('document.querySelector("[data-area=\'부산 해운대\']").getAttribute("aria-pressed")==="true"')
        assert page.locator('[name=region]').input_value() == '부산'
        assert page.locator('[name=origin_name]').input_value() == '부산 해운대역 지역 중심'
        # 홈 카드와 달리 분위기·분류는 건드리지 않는다.
        assert page.evaluate('[form.elements.date_category.value,form.elements.date_subcategory.value]') == category
        assert area_chip(page, '서울 성수').get_attribute('aria-pressed') == 'false'
        page.locator('#submit-plan').click()
        body = wait_job(page, bodies, 1)
        assert body['region'] == '부산' and body['origin'] == {'name': '부산 해운대역 지역 중심', 'lat': 35.1631, 'lon': 129.1636}
        assert body['visit_date'] == DAY and (body['start'], body['end'], body['budget']) == ('11:00', '19:00', 120000)
        assert Conditions.model_validate(body).region == '부산'
        # 지도 창(다른 곳 찾기)으로 다른 곳을 고르면 칩 선택 표시가 풀린다.
        back_to_conditions(page)
        region_reply(page, {'status': 'ok', 'region': '부산', 'label': '부산광역시 수영구 광안동', 'message': ''})
        page.locator('#origin-location').get_by_role('button', name='지도에서 고르기', exact=True).click()
        page.wait_for_function('!!locationMap', timeout=25000)
        page.evaluate('locationMap.setView([35.153,129.118],15,{animate:false})')
        page.locator('#dialog').get_by_role('button', name='지도 중심을 선택', exact=True).click()
        confirm = page.locator('#dialog').get_by_role('button', name='이 지역에서 데이트하기', exact=True)
        page.wait_for_function('document.querySelector(".location-picked").textContent.includes("부산광역시 수영구")')
        confirm.click()
        page.wait_for_function('!document.querySelector("[data-area][aria-pressed=true]")')
        assert page.locator('[name=origin_name]').input_value() == '부산광역시 수영구 광안동 · 지도에서 선택'


def test_current_location_allowed(server):
    with opened(server, permissions=['geolocation'], geolocation={'latitude': 37.5446, 'longitude': 127.0559}) as (page, errors):
        seen = region_reply(page, {'status': 'ok', 'region': '서울', 'label': '서울특별시 성동구 성수동1가', 'message': ''})
        bodies = intercept_jobs(page)
        here = page.get_by_role('group', name='인기 동네').get_by_role('button', name='현재 위치', exact=True)
        here.click()
        page.wait_for_function('form.elements.origin_name.value.endsWith("· 현재 위치")')
        assert seen == [{'lat': 37.5446, 'lon': 127.0559}]
        assert page.locator('[name=origin_name]').input_value() == '서울특별시 성동구 성수동1가 · 현재 위치'
        assert page.locator('[name=region]').input_value() == '서울'
        assert not page.locator('#dialog').evaluate('dialog=>dialog.open')
        assert '현재 위치' in page.locator('.area-status').inner_text()
        page.locator('#submit-plan').click()
        body = wait_job(page, bodies, 1)
        assert Conditions.model_validate(body).origin.name.startswith('서울특별시')
        # 위치는 얻었지만 시·도를 확인하지 못하면 안내하고 지역 검색 칸으로 이어 준다(지도 창을 갑자기 열지 않음).
        back_to_conditions(page)
        region_reply(page, {'status': 'key_missing', 'region': None, 'label': '', 'message': '키 없음'})
        here.click()
        page.wait_for_function('document.querySelector(".area-status").textContent.includes("시·도를 확인하지 못했어요")')
        assert not page.locator('#dialog').evaluate('dialog=>dialog.open')
        assert page.evaluate('document.activeElement===form.elements.origin_name')


def test_current_location_denied_points_to_search(server):
    # 권한을 주지 않은 브라우저: 위치 요청이 거부된다. 권한을 켜는 방법을 알리고 검색 칸으로 이어 준다.
    with opened(server) as (page, errors):
        seen = region_reply(page, {'status': 'ok', 'region': '서울', 'label': '서울특별시 중구', 'message': ''})
        page.get_by_role('group', name='인기 동네').get_by_role('button', name='현재 위치', exact=True).click()
        page.wait_for_function('document.querySelector(".area-status").textContent.includes("위치 권한이 허용되지 않았어요")', timeout=20000)
        assert '‘허용’' in page.locator('.area-status').inner_text()
        assert not page.locator('#dialog').evaluate('dialog=>dialog.open')
        assert page.evaluate('document.activeElement===form.elements.origin_name')
        assert seen == [] and page.locator('[name=origin_name]').input_value() == ''


def test_condition_inputs_and_budget_chips_update_values(server):
    # 2026-11-25 시안: 날짜·시작·종료 칸이 항상 보이고, 예산은 1인 칩 · 직접 입력은 '더 많은 조건'의 전체 예산 칸.
    with opened(server, clock='12:30') as (page, errors):
        # 오늘 11시는 이미 지나 기본 시간대가 아직 가능한 오후로 조용히 옮겨진다(알림 없이).
        assert [page.locator(f'[name={n}]').input_value() for n in ('visit_date', 'start', 'end')] == [DAY, '13:00', '19:00']
        assert page.locator('.date-note').inner_text() == ''
        assert page.locator('[name=budget]').input_value() == '120000'
        # 1인 예산 칩은 '1인 상한 × 인원'을 전체 예산 칸에 넣고 change 이벤트도 보낸다.
        form_chip(page, '1인 예상 예산', '3만원').click()
        assert page.locator('[name=budget]').input_value() == '60000'
        assert page.evaluate('FormState.edited.has("budget")')
        assert form_chip(page, '1인 예상 예산', '3만원').get_attribute('aria-pressed') == 'true'
        assert form_chip(page, '1인 예상 예산', '6만원').get_attribute('aria-pressed') == 'false'
        assert page.locator('.budget-note').inner_text() == '1인 3만 원까지 · 2명 합계 6만 원으로 찾아요.'
        # 시작·종료 칸을 바로 고친다.
        page.locator('[name=start]').fill('17:00')
        page.locator('[name=end]').fill('22:00')
        assert (page.locator('[name=start]').input_value(), page.locator('[name=end]').input_value()) == ('17:00', '22:00')
        open_details(page)
        # 날짜를 내일로 바꾸면 오늘 기준 보정 알림은 없다.
        page.locator('[name=visit_date]').fill('2026-11-14')
        assert page.locator('.date-note').inner_text() == ''
        # 직접 입력(전체 예산 칸): 어느 칩도 눌리지 않고 합계와 1인 금액을 보인다.
        set_budget_total(page, 85000)
        page.wait_for_function('document.querySelector(".budget-note").textContent.includes("85,000원")')
        assert page.locator('.budget-note').inner_text() == '전체 예산 85,000원(직접 입력) · 1인 약 43,000원'
        assert all(chip.get_attribute('aria-pressed') == 'false' for chip in page.get_by_role('group', name='1인 예상 예산').get_by_role('button').all())
        # 상세 조건 안의 칸이 잘못되면 상세 조건을 펼쳐 보여 준다.
        page.locator('details.simple-extra-options>summary').click()
        assert page.evaluate("document.querySelector('details.simple-extra-options').open") is False
        invalid = page.evaluate("form.elements.budget.value='-1';form.elements.budget.dispatchEvent(new Event('input',{bubbles:true}));form.reportValidity()")
        assert invalid is False
        assert page.evaluate("document.querySelector('details.simple-extra-options').open") is True
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')


def test_evening_visit_moves_default_to_tomorrow(server):
    with opened(server, clock='18:10') as (page, errors):
        # 처음 열 때 오늘 시간대가 모두 지났으면 알림 없이 내일로 맞춘다.
        assert page.locator('[name=visit_date]').input_value() == '2026-11-14'
        assert (page.locator('[name=start]').input_value(), page.locator('[name=end]').input_value()) == ('11:00', '19:00')
        assert page.locator('.date-note').inner_text() == ''


def test_last_conditions_repeat_and_privacy_delete(server):
    with opened(server) as (page, errors):
        bodies = intercept_jobs(page)
        assert page.locator('.last-conditions').is_hidden()
        area_chip(page, '제주 애월').click()
        page.locator('[name=start]').fill('13:00')
        open_details(page)
        page.locator('[name=people]').fill('3')
        page.locator('[name=people]').dispatch_event('change')
        form_chip(page, '1인 예상 예산', '15만원').click()
        form_chip(page, '이동 수단', '대중교통').click()
        open_dream(page)
        page.locator('[name=request]').fill('바다 보면서 쉬고 싶어요')
        page.locator('#submit-plan').click()
        wait_job(page, bodies, 1)
        saved = json.loads(page.evaluate(f'localStorage.getItem("{STORE_KEY}")'))
        # 자유 입력 문장과 날짜는 저장하지 않는다.
        assert saved == {'region': '제주', 'origin': {'name': '제주 애월 한담해변 지역 중심', 'lat': 33.4621, 'lon': 126.3104},
                         'start': '13:00', 'end': '19:00', 'budget': 450000, 'people': 3, 'count': 3, 'transport': 'transit'}
        # 축제를 골라 바뀐 출발지(축제 장소)는 지난 지역으로 남기지 않는다.
        back_to_conditions(page)
        page.evaluate("""()=>{
          const origin={name:'부산 해운대구 · 점검 축제 행사장 주변',lat:35.1,lon:129.1};
          applyArea('부산',origin);
          FestivalPanel.chosen={festival:{id:'f1',title:'점검 축제',lat:origin.lat,lon:origin.lon},originName:origin.name};
        }""")
        page.locator('#submit-plan').click()
        body = wait_job(page, bodies, 2)
        assert body['festival']['id'] == 'f1'
        saved = json.loads(page.evaluate(f'localStorage.getItem("{STORE_KEY}")'))
        assert saved['region'] == '제주' and saved['origin']['name'] == '제주 애월 한담해변 지역 중심'
        # 다시 방문하면 맨 위에 '지난번처럼 추천'이 보이고, 한 번 누르면 같은 조건(날짜는 오늘)으로 추천한다.
        page.evaluate('sessionStorage.clear()')
        load(page, server)
        again = page.locator('.last-conditions .again-button')
        assert again.is_visible()
        assert again.inner_text().replace('\n', ' ') == '지난번처럼 추천 제주 애월 한담해변 · 13:00–19:00 · 3명 · 45만 원 · 3곳 · 대중교통'
        first = page.evaluate('document.querySelector("#conditions").firstElementChild.nextElementSibling.className')
        assert first == 'last-conditions'
        again.click()
        body = wait_job(page, bodies, 3)
        assert body['region'] == '제주' and body['origin']['name'] == '제주 애월 한담해변 지역 중심'
        assert (body['visit_date'], body['start'], body['end'], body['budget'], body['people'], body['transport']) == (DAY, '13:00', '19:00', 450000, 3, 'transit')
        assert body['request'] == '' and body['festival'] is None
        Conditions.model_validate(body)
        # 브라우저 데이터 삭제는 이 저장값도 지운다.
        page.once('dialog', lambda dialog: dialog.accept())
        page.get_by_role('button', name='이 브라우저의 저장 데이터 삭제', exact=True).click()
        page.wait_for_url(server + '/')
        page.wait_for_function("typeof statusData!=='undefined'&&!!statusData&&document.querySelector('.simple-plan-form')")
        assert page.evaluate(f'localStorage.getItem("{STORE_KEY}")') is None
        assert page.locator('.last-conditions').is_hidden()


def test_area_chip_pressed_before_status_loads_is_applied_when_ready(server):
    with opened(server) as (page, _):
        # 서버 상태 요청을 붙잡아 두어, 화면은 떴지만 아직 준비되지 않은 구간을 만든다.
        held = []
        page.route('**/api/status', lambda route: held.append(route))
        page.goto(server)
        page.wait_for_selector('.simple-plan-form')
        assert page.evaluate('!statusData')
        area_chip(page, '서울 성수').click()
        area_chip(page, '부산 해운대').click()
        assert page.evaluate('locationState.origin') is None
        assert '준비' in page.locator('.area-status').inner_text()
        assert len(held) == 1
        held[0].continue_()
        page.wait_for_function("!!statusData&&!!locationState.origin")
        # 마지막으로 누른 동네가 적용되고, 상태 응답의 기본 시·도가 덮어쓰지 않는다.
        assert page.evaluate('form.elements.region.value') == '부산'
        assert page.evaluate('form.elements.origin_name.value').startswith('부산')
        assert area_chip(page, '부산 해운대').get_attribute('aria-pressed') == 'true'
        assert area_chip(page, '서울 성수').get_attribute('aria-pressed') == 'false'
