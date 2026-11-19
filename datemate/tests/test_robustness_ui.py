"""견고성 재현(개선안 55·59). 이미 막혀 있으면 그 근거를 테스트로 남긴다.

55: 코스 탭을 A→B→A 로 빠르게 바꾸는 동안 A 의 응답이 늦게 도착해도 화면은 지금 고른 코스를 보인다.
    근거: plan-actions.js commitPlanChange 는 응답의 코스가 지금 고른 코스일 때만 화면을 다시 그리고(아니면 목록만 갱신),
    사진은 요청한 그 화면 요소에만 쓴다(다시 그린 상세에서는 떨어져 나간 요소).
59: 장소 하나의 사진 요청만 실패하면 그 사진 칸에만 '사진 다시 불러오기'가 붙고, 다른 장소와 코스 조작은 그대로 된다.
"""
from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401 (fixture)


def test_late_answers_after_fast_tab_switch_do_not_replace_the_selected_course(audit_page):
    page, _, _ = audit_page
    generate(page)
    wait_for_selected_detail(page)
    if page.evaluate('plans.length') < 2:
        return
    a, b = page.evaluate('[plans[0].id, plans[1].id]')
    held = []
    page.route('**/api/plans/' + a + '/transport', lambda route: held.append(route))
    # A 에서 이동 수단 변경을 보내고(응답은 쥐고 있다), 그사이 B → A → B 로 탭을 바꾼다.
    page.evaluate("()=>changePlanTransport({mode:'transit'},'all',document.createElement('div'),document.createElement('span'))")
    page.wait_for_timeout(500)
    tabs = page.locator('#results .plan-option-tabs > button')
    tabs.nth(1).click()
    tabs.nth(0).click()
    tabs.nth(1).click()
    page.wait_for_function(f"selected?.id==='{b}'")
    assert held, 'A 의 변경 요청이 쥐어져 있어야 한다'
    for route in held:
        route.continue_()
    page.wait_for_timeout(2000)
    assert page.evaluate('selected.id') == b, '늦게 온 A 의 응답이 지금 고른 B 를 바꾸지 않는다'


def test_one_failed_photo_request_keeps_the_rest_usable(audit_page):
    page, base, _ = audit_page
    from test_results_extras_ui import mount_photo_routes, real_results
    mount_photo_routes(page, base, count=2)
    page.route('**/api/places/*/blogs?*', lambda route: route.fulfill(json={'posts': [], 'message': '없음'}))
    failed = {}

    def media(route):
        # 첫 장소의 사진 목록 요청만 끊는다(나중에 건 route 가 먼저 받는다). 다시 불러오기는 통과시킨다.
        if not failed:
            failed['url'] = route.request.url
            return route.abort('failed')
        return route.fallback()
    page.route('**/api/places/*/media?*', media)
    real_results(page, base)
    wait_for_selected_detail(page)
    for photo in page.locator('#plan-detail .timeline-card .place-photo-panel').all():
        photo.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
    page.wait_for_function("document.querySelectorAll('#plan-detail .photo-open').length>0", timeout=20000)
    assert failed, '사진 요청 하나를 실패시켰다'
    retry = page.locator('#plan-detail').get_by_role('button', name='사진 다시 불러오기')
    assert retry.count() == 1, '실패한 사진 칸에만 다시 불러오기가 붙는다'
    assert page.locator('#plan-detail .photo-open').count() >= 1, '다른 장소 사진은 그대로 보인다'
    # 코스 조작(지각 확인)은 그대로 된다.
    box = page.locator('#plan-detail details.delay-check')
    box.locator('summary').click()
    box.get_by_role('button', name='확인').click()
    page.wait_for_function("document.querySelector('#plan-detail .delay-check-basis')", timeout=20000)
    # 다시 불러오기를 누르면 그 칸만 다시 받는다.
    opened = page.locator('#plan-detail .photo-open').count()
    retry.click()
    page.wait_for_function(f"document.querySelectorAll('#plan-detail .photo-open').length>{opened}", timeout=20000)
    assert page.locator('#plan-detail').get_by_role('button', name='사진 다시 불러오기').count() == 0
