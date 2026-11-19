"""통신이 끊겨도 시작한 검색을 이어 보기 (docs/product-priorities-deep-review.ko.md 2번, static/plan-progress.js).

실제 서버로 가상 장소(데모) 추천을 돌리고, 브라우저의 /api/plan-jobs 요청만 고정 응답으로 바꾼다.
- 생성 POST 는 세어서 그대로 서버에 보낸다(이어보기가 새 검색을 보내지 않는지 본다).
- 상태 조회 GET 은 state['mode'] 에 따라 끊거나(abort), 진행 중으로 붙잡거나(hold), 서버 응답을 그대로 준다(pass).
모바일 폭(390px)에서 단추를 직접 눌러 확인한다.
"""
from test_functional_audit import audit_page  # noqa: F401 (fixture)

HELD = dict(status='running', stage='가격 확인', message='코스 후보를 찾았어요. 가격과 필수 조건을 마지막으로 확인해요')


def stub(page, state):
    state.setdefault('posts', 0)
    state.setdefault('gets', 0)
    state.setdefault('held', [])

    def jobs(route):
        if route.request.method == 'POST':
            state['posts'] += 1
            if state.get('post') == 'abort':
                return route.abort('failed')
        return route.continue_()

    def status(route):
        if route.request.method != 'GET':
            return route.continue_()
        state['gets'] += 1
        mode = state.get('mode', 'pass')
        if mode == 'abort':
            return route.abort('failed')
        if mode == 'gone':
            return route.fulfill(status=404, json=dict(detail='검색 작업을 찾을 수 없습니다.'))
        if mode == 'park':
            # 응답을 보내지 않고 쥐고 있다가 테스트가 나중에 풀어 준다(취소 뒤 늦게 오는 응답).
            state['held'].append(route)
            return None
        response = route.fetch()
        data = response.json()
        if data.get('status') == 'complete' and mode == 'hold':
            data = dict(HELD, id=data['id'])
        if data.get('status') == 'complete' and mode == 'fail':
            data = dict(id=data['id'], status='failed', stage='가격 확인', message='가격 확인 단계에서 처리 오류가 발생했어요.')
        return route.fulfill(response=response, json=data)

    page.route('**/api/plan-jobs', jobs)
    page.route('**/api/plan-jobs/*', status)


def submit(page):
    page.set_viewport_size({'width': 390, 'height': 844})
    page.evaluate("form.elements.mode.value='demo';form.elements.mode.dispatchEvent(new Event('change',{bubbles:true}));form.elements.visit_date.value='2026-10-24';form.elements.max_leg.value=180;form.elements.budget.value=1000000;")
    page.locator('#submit-plan').click()


def failure_text(page):
    page.wait_for_function("document.querySelector('#progress')?.innerText.includes('검색을')&&!document.querySelector('#progress').classList.contains('is-searching')", timeout=45000)
    return page.locator('#progress').inner_text()


def test_lost_status_resumes_the_same_job_with_one_create_request(audit_page):
    page, _, _ = audit_page
    state = dict(mode='abort')
    stub(page, state)
    submit(page)
    text = failure_text(page)
    assert '연결이 끊겨 검색 상태를 받지 못했어요' in text
    resume = page.get_by_role('button', name='이 검색 이어보기')
    assert resume.is_visible() and page.get_by_role('button', name='같은 조건으로 다시 검색').count() == 0
    job = page.evaluate('PlanSearch.pending()')
    assert job, '작업 ID 가 남아 있어야 이어볼 수 있다'
    assert state['posts'] == 1 and state['gets'] == 3, '상태 조회 세 번 실패 뒤에 멈춘다'
    # 조회 루프(PlanSearch.wait) 수를 센다. 서버 검색은 그사이 끝났다. 이어보기를 두 번 빠르게 눌러도 루프는 하나다.
    page.evaluate("()=>{const w=PlanSearch.wait;window.__waits=0;PlanSearch.wait=function(...a){window.__waits++;return w.apply(this,a);};}")
    state['mode'] = 'pass'
    # 연속 탭. 두 번째 탭이 같은 자리에 새로 나타난 '검색 취소'를 눌러 검색을 취소하던 문제도 함께 본다.
    resume.dblclick()
    page.wait_for_function('selected?.id&&!document.querySelector("#submit-plan").disabled', timeout=45000)
    assert '검색 복원 완료' in page.locator('#progress').inner_text()
    assert page.locator('#results .plan-option-tabs button').count() >= 1
    assert state['posts'] == 1, '최초 제출부터 결과 표시까지 생성 POST 는 한 번'
    assert page.evaluate('window.__waits') == 1, '이어보기를 연달아 눌러도 조회 루프는 하나만 돈다'
    assert page.evaluate('PlanSearch.pending()') is None
    assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth')


def test_cancel_then_late_status_does_not_bring_back_results(audit_page):
    page, _, _ = audit_page
    state = dict(mode='hold')
    stub(page, state)
    submit(page)
    page.wait_for_function("document.querySelector('#progress')?.classList.contains('is-searching')", timeout=45000)
    page.wait_for_timeout(1500)
    state['mode'] = 'park'
    page.wait_for_timeout(1500)
    page.get_by_role('button', name='검색 취소').click()
    page.wait_for_function("!document.querySelector('#progress').classList.contains('is-searching')", timeout=15000)
    # 취소 뒤에 쥐고 있던 조회 응답을 '완료'로 풀어 준다. 화면은 그 결과를 되살리지 않는다.
    state['mode'] = 'pass'
    for route in state['held']:
        try:
            route.fulfill(json=dict(id='late', status='complete', stage='완료', message='', result=dict(plans=[])))
        except Exception:
            pass  # 취소로 요청이 이미 끊긴 경우
    page.wait_for_timeout(1500)
    assert page.evaluate('selected===null&&plans.length===0')
    assert page.locator('#results .plan-option-tabs').count() == 0
    assert page.evaluate('PlanSearch.pending()') is None
    assert state['posts'] == 1


def test_expired_job_offers_a_new_search_not_resume(audit_page):
    page, _, _ = audit_page
    state = dict(mode='gone')
    stub(page, state)
    submit(page)
    text = failure_text(page)
    assert '서버에서 찾을 수 없어요' in text
    assert page.get_by_role('button', name='이 검색 이어보기').count() == 0
    assert page.get_by_role('button', name='같은 조건으로 다시 검색').is_visible()
    assert page.evaluate('PlanSearch.pending()') is None
    # 같은 조건으로 다시 검색하면 새 생성 요청을 한 번 보낸다.
    state['mode'] = 'pass'
    page.get_by_role('button', name='같은 조건으로 다시 검색').click()
    page.wait_for_function('selected?.id&&!document.querySelector("#submit-plan").disabled', timeout=45000)
    assert state['posts'] == 2


def test_server_failure_and_missing_job_id_show_their_own_next_step(audit_page):
    page, _, _ = audit_page
    state = dict(mode='fail')
    stub(page, state)
    submit(page)
    text = failure_text(page)
    assert '가격 확인 단계에서 처리 오류' in text
    assert page.get_by_role('button', name='이 검색 이어보기').count() == 0
    assert page.get_by_role('button', name='조건 확인하고 다시 검색').is_visible()
    # 생성 요청의 응답부터 받지 못하면 ID 가 없어 이어볼 수 없다고 밝히고 새 검색을 제안한다.
    page.get_by_role('button', name='조건 확인하고 다시 검색').click()
    state.update(mode='pass', post='abort')
    page.locator('#submit-plan').click()
    text = failure_text(page)
    assert '요청이 서버에 닿았는지 알 수 없어' in text
    assert page.get_by_role('button', name='이 검색 이어보기').count() == 0
    assert page.get_by_role('button', name='같은 조건으로 다시 검색').is_visible()
    assert page.evaluate('PlanSearch.pending()') is None
