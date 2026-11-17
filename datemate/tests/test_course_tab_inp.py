"""코스 탭(INP): 누르면 탭 표시만 바로 바꾸고 결과·상세·지도는 다음 화면 갱신 뒤에 그린다(plan-results choose)."""
from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401


def test_tab_marks_itself_at_once_and_draws_the_detail_after_the_next_paint(audit_page):
    page, base, errors = audit_page
    generate(page)
    first = page.evaluate('plans[0].id')
    assert page.evaluate("document.querySelector('#plan-detail').dataset.planId") == first
    # 같은 작업(task) 안에서 누르고 바로 읽는다: 탭 표시는 바뀌었고 상세는 아직 전 코스다.
    state = page.evaluate("""()=>{const tab=document.querySelectorAll('#results .plan-option-tabs > button')[1];
      tab.focus();tab.click();
      return new Promise(resolve=>queueMicrotask(()=>resolve({
        pressed:[...document.querySelectorAll('#results .plan-option-tabs > button')].map(b=>b.getAttribute('aria-pressed')),
        indicator:!!tab.querySelector('.selection-indicator'),
        detail:document.querySelector('#plan-detail').dataset.planId,
        busy:document.querySelector('#results').getAttribute('aria-busy'),
        selected:selected.id})));}""")
    second = page.evaluate('plans[1].id')
    assert state['pressed'][:2] == ['false', 'true'], state
    assert state['indicator'] and state['selected'] == second and state['busy'] == 'true', state
    assert state['detail'] == first, state
    wait_for_selected_detail(page)
    assert page.evaluate("document.querySelector('#plan-detail').dataset.planId") == second
    # 다시 그려 탭 단추가 새로 만들어져도 키보드 포커스는 누른 탭에 남는다.
    assert page.evaluate("document.activeElement.closest('.plan-option-tabs')&&document.activeElement.dataset.option") == '2'
    assert page.locator('.map-option-tabs [aria-pressed=true]').get_attribute('data-map-option') == '2'
    assert errors == []


def test_quick_taps_draw_only_the_last_course(audit_page):
    page, base, errors = audit_page
    generate(page)
    if page.evaluate('plans.length') < 3:
        return
    page.evaluate("""()=>{window.detailDraws=0;const draw=renderDetail;renderDetail=function(){window.detailDraws++;return draw.apply(this,arguments);};
      const tabs=()=>document.querySelectorAll('#results .plan-option-tabs > button');tabs()[1].click();tabs()[2].click();}""")
    wait_for_selected_detail(page)
    assert page.evaluate('selected.id') == page.evaluate('plans[2].id')
    assert page.evaluate('window.detailDraws') == 1
