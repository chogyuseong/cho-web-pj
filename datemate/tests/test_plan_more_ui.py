"""2026-11-25 상세 결과 시안: 일정 위를 비우고, 시안에 없는 기능은 접힌 칸 두 개(static/plan-detail.js planMoreFold)에 모은다.

- 처음에는 접혀 있고, 펼치면 이 브라우저에서 다음 코스에도 펼친 채로 그린다(localStorage).
- 접힌 칸 안에 예전 기능이 그대로 있다(지우지 않음): 수단 한 번에 바꾸기·지각 확인·순서 제안·당일 도구·비용표·결정·공유 / 레저·질문·후기.
- 순서: 일정 → 비교 표 → 체크리스트 → '더 할 수 있는 것' → (축제) → '더 둘러보기 · 질문 · 후기'.
다른 화면 테스트는 conftest.py PLAN_FOLDS_OPEN 이 두 칸을 미리 펼친다. 여기서는 sessionStorage 표시로 그 값을 넣지 않는다."""
from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401  (pytest fixture)


def default_folds(page, base):
    """conftest 의 '미리 펼침'을 끄고 저장된 펼침 기억을 지운 뒤 다시 연다(첫 방문과 같은 상태)."""
    page.evaluate("sessionStorage.setItem('datemate-test-folds','default');localStorage.removeItem('datemate:plan-more');"
                  "localStorage.removeItem('datemate:plan-extras-more')")
    page.goto(base, wait_until='networkidle')
    page.wait_for_function("typeof statusData!=='undefined'&&!!statusData&&document.querySelector('.simple-plan-form')")


def test_folds_start_closed_keep_old_tools_and_remember_opening(audit_page):
    page, base, errors = audit_page
    default_folds(page, base)
    generate(page)
    wait_for_selected_detail(page)
    folds = page.locator('#plan-detail .plan-more, #plan-extras .plan-more')
    assert folds.count() == 2
    assert folds.evaluate_all('f=>f.map(x=>x.open)') == [False, False]
    # 일정 위에는 도구 상자가 없다(지각 미리 보기 줄만).
    above = page.evaluate("""()=>{const d=document.querySelector('#plan-detail .detail'),first=d.querySelector(':scope>.stop');
      return [...d.children].slice(0,[...d.children].indexOf(first)).map(e=>e.className)}""")
    assert not any(name for name in above if any(k in name for k in ('delay-check', 'order-suggestion', 'day-of', 'transport-overview', 'map-link-list'))), above
    # 접힌 칸 안에 예전 기능이 그대로 있다.
    more = page.locator('#plan-detail .plan-more')
    for selector in ('.delay-check', '.day-of-tools', '.cost-table', '.plan-share'):
        assert more.locator(selector).count() >= 1, selector
    extras = page.locator('#plan-extras .plan-more')
    assert extras.get_by_text('이 일정에 대해 물어보세요').count() == 1
    # 순서: 마지막 장소 → 비교 표 → 체크리스트 → 접힌 칸.
    order = page.evaluate("""()=>{const d=document.querySelector('#plan-detail .detail'),kids=[...d.children],at=s=>kids.findIndex(e=>e.matches(s));
      const stops=kids.filter(e=>e.matches('.stop'));return [kids.indexOf(stops.at(-1)),at('.comparison-details'),at('.action-card'),at('.plan-more')]}""")
    assert order == sorted(order) and -1 not in order, order
    # 펼치면 기억하고, 다른 코스를 골라 다시 그려도 펼친 채다.
    more.locator('>summary').click()
    page.wait_for_function("localStorage.getItem('datemate:plan-more')==='open'")
    page.locator('#results .plan-option-tabs > button').nth(1).click()
    wait_for_selected_detail(page)
    assert page.locator('#plan-detail .plan-more').evaluate('f=>f.open')
    assert not page.locator('#plan-extras .plan-more').evaluate('f=>f.open')
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')


def test_print_opens_the_fold_without_remembering_it(audit_page):
    # 비용표·합계·네 가지 확인이 접힌 칸 안에 있어도 인쇄에 나온다(beforeprint 에 펼침, afterprint 에 되돌림, 기억은 그대로).
    page, base, errors = audit_page
    default_folds(page, base)
    generate(page)
    wait_for_selected_detail(page)
    fold = page.locator('#plan-detail .plan-more')
    assert not fold.evaluate('f=>f.open')
    page.evaluate("dispatchEvent(new Event('beforeprint'))")
    assert fold.evaluate('f=>f.open')
    page.emulate_media(media='print')
    assert page.locator('#plan-detail .total-row').first.is_visible()
    assert not page.locator('#plan-detail .plan-more>summary').is_visible()
    assert not page.locator('#plan-detail .comparison-details').is_visible()
    page.emulate_media(media='screen')
    page.evaluate("dispatchEvent(new Event('afterprint'))")
    page.wait_for_function("!document.querySelector('#plan-detail .plan-more').open")
    page.wait_for_timeout(100)
    assert page.evaluate("localStorage.getItem('datemate:plan-more')") is None
