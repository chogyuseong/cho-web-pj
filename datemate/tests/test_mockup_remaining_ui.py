"""2026-11-25 Gemini Canvas 시안(share.gemini.google/NMTZYFdUBrws)의 남은 기능.

- 비교 표 마지막 칸 '선택': 지금 코스는 '현재 보고 있는 코스', 다른 코스는 「이 코스 보기」(코스 탭과 같은 동작) — plan-evidence.js optionComparison.
- 축제 구역 필터 탭(전체 / 축제·행사 / 팝업스토어): 팝업 구역이 있을 때만 보이고 한쪽 구역을 숨긴다 — plan-results.js 끝, redesign.css 13).
- 일정 끝 '귀가 동선 포함' 카드: 스위치는 조건 화면의 귀가 칸을 바꾸고 다시 찾기를 안내한다(서버 재계산이라 그 자리에서 바꾸지 않음) — plan-detail.js returnHomeCard.
(늦어짐 → 「대신 갈 곳 찾기」는 tests/test_redesign_results_ui.py 의 지각 미리 보기 테스트에 있다.)"""
from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401  (pytest fixture)

SHOWN = "s=>[...document.querySelectorAll(s)].filter(e=>e.getClientRects().length>0).length"


def test_comparison_table_switches_course(audit_page):
    page, base, errors = audit_page
    generate(page)
    wait_for_selected_detail(page)
    table = page.locator('#plan-detail .option-comparison')
    assert table.locator('thead th').last.inner_text() == '선택'
    picks = table.locator('tbody tr')
    assert picks.nth(0).locator('.comparison-current').inner_text() == '현재 보고 있는 코스'
    second = page.evaluate('plans[1].id')
    picks.nth(1).get_by_role('button', name='코스 2 보기').click()
    page.wait_for_function(f"selected?.id==='{second}'")
    wait_for_selected_detail(page)
    # 다시 그린 표에서는 코스 2가 '현재 보고 있는 코스'.
    rows = page.locator('#plan-detail .option-comparison tbody tr')
    assert rows.nth(1).locator('.comparison-current').count() == 1 and rows.nth(0).get_by_role('button', name='코스 1 보기').count() == 1
    assert page.locator('#results .plan-option-tabs > button[data-option="2"]').get_attribute('aria-pressed') == 'true'


def test_event_filter_tabs_show_only_with_popups_and_hide_one_side(audit_page):
    page, base, errors = audit_page
    generate(page)
    wait_for_selected_detail(page)
    page.evaluate("document.getElementById('festival-section').hidden=false")
    popup = page.evaluate("!!document.getElementById('popup-course')")
    if popup:
        page.evaluate("document.getElementById('popup-course').hidden=true")
    # 팝업 구역이 없거나 숨어 있으면 탭이 없다.
    assert page.evaluate(SHOWN, '.event-filter') == 0
    if not popup:
        page.evaluate("""()=>{const s=document.createElement('section');s.id='popup-course';s.className='popup-course';s.textContent='팝업 블록';
          document.getElementById('festival-section').after(s)}""")
    page.evaluate("document.getElementById('popup-course').hidden=false;document.getElementById('festival-results').textContent='축제 카드'")
    tabs = page.locator('.event-filter')
    assert tabs.is_visible() and tabs.locator('button').all_inner_texts() == ['전체', '축제·행사', '팝업스토어']
    assert all(b['height'] >= 44 for b in tabs.locator('button').evaluate_all('l=>l.map(e=>e.getBoundingClientRect().toJSON())'))
    tabs.get_by_role('button', name='축제·행사').click()
    assert page.locator('#popup-course').is_hidden() and page.locator('#festival-results').is_visible()
    assert tabs.get_by_role('button', name='축제·행사').get_attribute('aria-pressed') == 'true'
    tabs.get_by_role('button', name='팝업스토어').click()
    assert page.locator('#popup-course').is_visible() and page.locator('#festival-results').is_hidden()
    assert page.locator('#festival-title').is_visible()
    tabs.get_by_role('button', name='전체').click()
    assert page.locator('#popup-course').is_visible() and page.locator('#festival-results').is_visible()


def test_return_home_card_switch_goes_to_the_condition(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 844})
    generate(page)
    wait_for_selected_detail(page)
    card = page.locator('#plan-detail .return-home-card')
    assert card.count() == 1
    switch = card.get_by_role('switch')
    assert switch.get_attribute('aria-checked') == 'false' and card.locator('.return-home-route').count() == 0
    assert switch.bounding_box()['height'] >= 44
    # 마지막 장소 뒤, 체크리스트 앞.
    assert page.evaluate("""()=>{const c=document.querySelector('#plan-detail .return-home-card'),s=[...document.querySelectorAll('#plan-detail .stop')].at(-1),
      a=document.querySelector('#plan-detail .action-card');return !!(s.compareDocumentPosition(c)&Node.DOCUMENT_POSITION_FOLLOWING)&&!!(c.compareDocumentPosition(a)&Node.DOCUMENT_POSITION_FOLLOWING)}""")
    switch.click()
    page.wait_for_function('form.elements.return_home.checked')
    page.wait_for_function("(()=>{const r=document.querySelector('[name=return_home]').getBoundingClientRect();return r.height>0&&r.top<innerHeight&&r.bottom>0})()")
    # 귀가가 들어간 코스면 켜진 스위치와 귀가 구간 한 줄.
    page.evaluate("""()=>{const p=selected;p.conditions.return_home=true;p.legs=[...p.legs,{...p.legs.at(-1),origin:p.places.at(-1).name,destination:'우리 집'}];
      showPlannerPage(true);renderResults();renderDetail();}""")
    card = page.locator('#plan-detail .return-home-card')
    assert card.get_by_role('switch').get_attribute('aria-checked') == 'true'
    route = card.locator('.return-home-route').inner_text()
    assert '우리 집' in route and '출발' in route, route
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
