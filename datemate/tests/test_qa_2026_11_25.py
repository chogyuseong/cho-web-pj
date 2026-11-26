"""2026-11-25 운영 QA 보고서(docs/QA_REPORT-2026-11-25.ko.md)의 '중간' 다섯 건 회귀 테스트.

QA-01 종료 시간이 시작보다 이르거나 같으면 보내기 전에 막는다(app.js timeRangeInvalid): 종료 칸 아래 안내·aria-invalid·포커스.
QA-01/02 422 검증 오류 목록은 개발자 원문(loc·영문 msg·'Value error, ')을 보이지 않는다(http-client.mjs validationMessage).
QA-02 '어떤 데이트를 꿈꾸나요?' 칸은 서버와 같은 4000자 상한(maxlength).
QA-03 네트워크 실패는 'Failed to fetch' 대신 한국어 안내 한 문구(http-client.mjs NETWORK_ERROR_TEXT), 오류에 network 표시.
      추천 요청(plan-jobs)의 '응답을 받지 못했어요' 분기는 그대로다(tests/test_search_resume_ui.py 도 본다).
QA-04 코스 탭(결과 목록·지도)을 눌러 다시 그린 뒤에도 포커스는 고른 코스의 탭에 있다(plan-results.js choose, maps.js).
QA-05 장소 둘러보기 '더 보기' 뒤 포커스는 새로 붙은 첫 장소 제목(explore.js page).
덧붙임: 이 브랜치 CI 에서 드러난 시각 의존 실패(여행 → 데이트가 오후에 맞춘 시간대를 11:00~19:00 으로 되돌림, header-mode.js).
"""
from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401 (fixture)

DEMO = ("form.elements.mode.value='demo';form.elements.mode.dispatchEvent(new Event('change',{bubbles:true}));"
        "form.elements.visit_date.value='2026-10-24';form.elements.max_leg.value=180;form.elements.budget.value=1000000;")
NETWORK_TEXT = '연결이 끊겨 서버에 닿지 못했어요. 인터넷 연결을 확인하고 다시 시도해 주세요.'
DEVELOPER_WORDS = ('body:', 'text:', 'Value error', 'String should', 'Failed to fetch', 'Field required')


def toast_text(page):
    page.wait_for_function("getComputedStyle(document.querySelector('#toast')).display!=='none'")
    return page.locator('#toast').inner_text()


def set_time(page, name, value):
    page.evaluate("([n,v])=>{const el=form.elements[n];el.value=v;el.dispatchEvent(new Event('input',{bubbles:true}));"
                  "el.dispatchEvent(new Event('change',{bubbles:true}));}", [name, value])


def test_end_time_not_after_start_is_stopped_in_the_browser(audit_page):
    page, _, _ = audit_page
    posts = []
    page.on('request', lambda request: posts.append(request.url) if request.method == 'POST' and '/api/plan-jobs' in request.url else None)
    page.evaluate(DEMO)
    for end in ('10:00', '11:00'):  # 이른 종료, 같은 시각
        set_time(page, 'start', '11:00')
        set_time(page, 'end', end)
        page.locator('#submit-plan').click()
        note = page.locator('#end-time-error')
        note.wait_for(state='visible')
        assert note.inner_text() == '종료 시간은 시작 시간보다 늦게 골라 주세요.'
        assert page.locator('[name=end]').get_attribute('aria-invalid') == 'true'
        assert page.locator('[name=end]').get_attribute('aria-describedby') == 'end-time-error'
        assert page.evaluate('document.activeElement===form.elements.end')
        assert toast_text(page) == '종료 시간은 시작 시간보다 늦게 골라 주세요.'
        # 안내는 종료 칸이 든 칸(label) 안, 입력 칸 바로 다음에 있다.
        assert page.evaluate("document.querySelector('#end-time-error').previousElementSibling===form.elements.end")
    page.wait_for_timeout(300)
    assert posts == [], '서버로 추천 요청을 보내지 않는다'
    assert not page.evaluate("document.querySelector('#progress').classList.contains('is-searching')")
    # 종료를 고치면 바로 안내와 표시가 사라지고, 그대로 추천을 받을 수 있다.
    set_time(page, 'end', '19:00')
    assert page.locator('#end-time-error').count() == 0
    assert page.locator('[name=end]').get_attribute('aria-invalid') is None
    assert page.locator('[name=end]').get_attribute('aria-describedby') is None
    page.locator('#submit-plan').click()
    page.wait_for_function('selected?.id&&!document.querySelector("#submit-plan").disabled', timeout=45000)
    assert len(posts) == 1


def test_validation_errors_never_show_developer_text(audit_page):
    page, _, _ = audit_page
    # 목록 변환: 한국어 서버 문구는 접두어만 떼고, 영문 검증 오류는 칸 이름 없이 한국어로.
    cases = page.evaluate("""async()=>{const m=await import('/static/http-client.mjs');return [
      m.validationMessage([{type:'value_error',loc:['body'],msg:'Value error, 종료 시간은 같은 날 시작 시간 이후여야 합니다.'}]),
      m.validationMessage([{type:'string_too_long',loc:['body','text'],msg:'String should have at most 4000 characters',ctx:{max_length:4000}}]),
      m.validationMessage([{type:'greater_than_equal',loc:['body','people'],msg:'Input should be greater than or equal to 1'}]),
      m.validationMessage([{type:'missing',loc:['body','x'],msg:'Field required'},{type:'value_error',loc:['body'],msg:'Value error, 고정 장소의 순서나 중복을 확인하세요.'}]),
      m.validationMessage([])];}""")
    assert cases == [
        '종료 시간은 같은 날 시작 시간 이후여야 합니다.',
        '입력한 글이 너무 길어요. 4,000자 이하로 줄여 주세요.',
        '입력값을 확인해 주세요. 허용 범위를 벗어난 값이 있어요.',
        '고정 장소의 순서나 중복을 확인하세요.',
        '입력값을 확인해 주세요. 허용 범위를 벗어난 값이 있어요.',
    ]
    # 실제 서버의 422: 화면 검사를 건너뛰고 종료 시각이 이른 조건을 바로 보낸다.
    page.evaluate(DEMO)
    plan = page.evaluate("""async()=>{const d=values();d.end=d.start;const m=await import('/static/http-client.mjs');
      try{await m.apiRequest('/plan-jobs',d);return null;}catch(e){return {message:e.message,status:e.status,validation:!!e.validation};}}""")
    assert plan == {'message': '종료 시간은 같은 날 시작 시간 이후여야 합니다.', 'status': 422, 'validation': True}


def test_request_box_has_the_server_limit_and_long_text_reads_in_korean(audit_page):
    from app.main import ParseInput
    from app.models import Conditions

    def limit(model, name):
        return next(m.max_length for m in model.model_fields[name].metadata if getattr(m, 'max_length', None))
    page, _, _ = audit_page
    assert limit(ParseInput, 'text') == limit(Conditions, 'request') == 4000
    assert page.evaluate('form.elements.request.maxLength') == 4000
    # 상한을 넘는 글이 스크립트로 들어와도(붙여넣기 도구 등) 서버의 422 는 한국어 한 줄로 보인다.
    page.evaluate("form.elements.request.value='가'.repeat(4200)")
    page.evaluate("document.getElementById('parse').click()")
    text = toast_text(page)
    assert text == '입력한 글이 너무 길어요. 4,000자 이하로 줄여 주세요.'
    assert not any(word in text for word in DEVELOPER_WORDS), text


def test_network_failure_reads_in_korean_on_every_screen(audit_page):
    page, _, _ = audit_page
    page.route('**/api/conditions/parse', lambda route: route.abort('failed'))
    # 한 줄 입력 '이 마음으로 조건 채우기'(QA-03 재현 경로 — 2026-11-26 시안부터 한 줄 입력은 코스 만들기 카드 맨 위에 있다).
    page.locator('#conditions [name=request]').fill('성수에서 전시 보고 저녁 먹기')
    page.locator('#parse').click()
    text = toast_text(page)
    assert text == NETWORK_TEXT
    assert not any(word in text for word in DEVELOPER_WORDS), text
    # 오류에는 status 없이 network 표시가 붙는다(추천 요청·서버 깨우기는 status 가 없는 오류를 '응답을 받지 못함'으로 본다).
    error = page.evaluate("""async()=>{const m=await import('/static/http-client.mjs');
      try{await m.apiRequest('/conditions/parse',{text:'가'});return null;}catch(e){return {message:e.message,network:e.network===true,status:e.status??null};}}""")
    assert error == {'message': NETWORK_TEXT, 'network': True, 'status': None}
    assert page.evaluate("ServerWake.preparing({network:true})"), '연결 실패는 여전히 서버 준비 중으로 다시 묻는다'
    # 추천 요청의 생성 POST 가 끊기면 예전처럼 '요청이 서버에 닿았는지 알 수 없어' 안내(no_job)로 간다.
    page.unroute('**/api/conditions/parse')
    page.evaluate("form.elements.request.value=''")
    page.route('**/api/plan-jobs', lambda route: route.abort('failed') if route.request.method == 'POST' else route.continue_())
    page.evaluate(DEMO)
    page.locator('#submit-plan').click()
    page.wait_for_function("document.querySelector('#progress')?.innerText.includes('요청이 서버에 닿았는지 알 수 없어')", timeout=30000)
    assert page.get_by_role('button', name='같은 조건으로 다시 검색').is_visible()


def focused_tab(page):
    return page.evaluate("""()=>{const a=document.activeElement;return {
      plan:a.closest('#results .plan-option-tabs')?a.dataset.option:null,
      map:a.closest('.plan-map-card .map-option-tabs')?a.dataset.mapOption:null,
      pressed:a.getAttribute('aria-pressed'),tag:a.tagName};}""")


def test_course_tabs_keep_focus_on_the_chosen_course_after_redraw(audit_page):
    page, _, _ = audit_page
    generate(page)
    wait_for_selected_detail(page)
    if page.evaluate('plans.length') < 3:
        return
    tabs = page.locator('#results .plan-option-tabs > button')
    # 1) 마우스 클릭.
    tabs.nth(1).click()
    wait_for_selected_detail(page)
    page.wait_for_timeout(300)
    assert focused_tab(page) == {'plan': '2', 'map': None, 'pressed': 'true', 'tag': 'BUTTON'}
    # 2) 키보드(Enter).
    tabs.nth(2).focus()
    page.keyboard.press('Enter')
    wait_for_selected_detail(page)
    page.wait_for_timeout(300)
    assert focused_tab(page)['plan'] == '3'
    # 3) 누른 단추가 포커스를 받지 않는 클릭(Safari·자동화 도구): 다시 그린 뒤 BODY 로 빠지지 않고 고른 탭에 온다.
    page.evaluate("document.activeElement?.blur();document.querySelectorAll('#results .plan-option-tabs > button')[0].click()")
    wait_for_selected_detail(page)
    page.wait_for_timeout(300)
    assert focused_tab(page) == {'plan': '1', 'map': None, 'pressed': 'true', 'tag': 'BUTTON'}
    # 4) 지도 탭: 다시 그린 바로 그 순간(단추 동작은 마이크로태스크, app.js button)부터 고른 탭에 포커스가 있고, 스크롤 위치는 그대로다.
    page.locator('.plan-map-card').scroll_into_view_if_needed()
    before = page.evaluate('scrollY')
    now = page.evaluate("""()=>{document.activeElement?.blur();document.querySelectorAll('.plan-map-card .map-option-tabs > button')[1].click();
      return new Promise(resolve=>queueMicrotask(()=>queueMicrotask(()=>resolve(document.activeElement.dataset.mapOption||document.activeElement.tagName))));}""")
    assert now == '2'
    page.wait_for_timeout(400)
    assert focused_tab(page) == {'plan': None, 'map': '2', 'pressed': 'true', 'tag': 'BUTTON'}
    assert abs(page.evaluate('scrollY') - before) < 2, '지도 탭은 스크롤을 옮기지 않는다'
    page.locator('.plan-map-card .map-option-tabs > button').nth(2).click()
    page.wait_for_timeout(400)
    assert focused_tab(page)['map'] == '3'
    assert page.evaluate('selected.id') == page.evaluate('plans[2].id')


def test_travel_back_to_date_restores_the_afternoon_time_window(audit_page):
    """브랜치 CI 에서 발견(QA 항목 밖): 오후에 연 화면은 오늘 지난 11:00 시작을 17:00~22:00 으로 맞춘다(simple-form.js).
    여행 → 데이트로 돌아오면 그 값으로 돌아와야 한다(header-mode.js dateDefaults). 전에는 맞추기 전 11:00~19:00 으로 돌아가
    test_travel_mode_ui 가 브라우저 시각 11~17시에만 실패했다. 시계를 오후 2시 30분으로 고정해 언제 돌려도 같게 본다."""
    import datetime
    page, base, _ = audit_page
    page.clock.install(time=datetime.datetime.now().replace(hour=14, minute=30, second=0, microsecond=0))
    page.evaluate("try{localStorage.removeItem('datemate-mode')}catch{}")
    page.goto(base + '/', wait_until='networkidle')
    page.wait_for_function("typeof statusData!=='undefined'&&!!statusData&&document.querySelector('.simple-plan-form')")
    times = "[form.elements.start.value,form.elements.end.value]"
    assert page.evaluate(times) == ['17:00', '22:00']
    for mode in ('travel', 'date'):
        page.locator(f'#mode-switch [data-mode={mode}]').click()
        page.wait_for_function(f"document.querySelector('#mode-switch [data-mode={mode}]').getAttribute('aria-pressed')==='true'")
    assert page.evaluate(times) == ['17:00', '22:00']
    page.evaluate("try{localStorage.removeItem('datemate-mode')}catch{}")


def test_explore_more_moves_focus_to_the_first_new_place(audit_page, monkeypatch):
    from public_fakes import fake_public_api, tour_item
    page, _, _ = audit_page
    api = fake_public_api(monkeypatch)
    for i in range(30):
        api['tour'].append(tour_item(3000 + i, f'서울 포커스 장소 {i}', 37.56 + i * .0005, 126.98, cat3='A02020700',
                                     type_id='12', address=f'서울특별시 중구 포커스로 {i}'))
    page.get_by_role('button', name='장소 둘러보기', exact=True).click()
    page.wait_for_function('document.querySelectorAll("#catalog .place-card").length===24')
    page.get_by_role('button', name='장소 더 보기 · 24 / 30', exact=True).click()
    page.wait_for_function('document.querySelectorAll("#catalog .place-card").length===30')
    focus = page.evaluate("""()=>{const a=document.activeElement,cards=[...document.querySelectorAll('#catalog .place-card')];
      return {index:cards.indexOf(a.closest('.place-card')),tag:a.tagName,tabindex:a.getAttribute('tabindex')};}""")
    assert focus == {'index': 24, 'tag': 'H3', 'tabindex': '-1'}
    # 처음 24곳의 제목은 Tab 순서·포커스 대상이 바뀌지 않는다.
    assert page.locator('#catalog .place-card').first.locator('h3').get_attribute('tabindex') is None
