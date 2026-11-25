"""모바일 다듬기(2026-11-19)와 그때 찾은 입력 경쟁 상태.

- 휴대폰에서 아래로 읽는 동안 머리말 소개 문구를 숨겨 머리말을 낮춘다(shell.css header.is-compact, romance.js).
- 장소마다 붙는 단추 줄과 당일 도구 단추를 같은 폭 2열로(results.css).
- 구간 한 줄에 분·근거가 두 번 붙지 않는다(day-of.js dayLegText).
- 예산을 입력하고 칸을 벗어나기 전에 자연어 해석이 도착해도 입력한 값을 덮지 않는다(form-state.js 가 input 에서도 기록).
"""
from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401 (fixture)


def test_typed_budget_survives_a_parse_that_arrives_before_leaving_the_field(audit_page):
    page, _, _ = audit_page
    budget = page.locator('[name=budget]')
    page.evaluate("form.elements.budget.value='';FormState.edited.delete('budget')")
    # 사용자가 입력 중(input 만, 아직 change 없음)일 때 해석 결과가 도착한 상황.
    page.evaluate("const b=form.elements.budget;b.value='80000';b.dispatchEvent(new Event('input',{bubbles:true}));applyRequestPatch({budget:50000})")
    assert budget.input_value() == '80000'


def test_phone_header_compacts_and_buttons_line_up(audit_page):
    page, _, _ = audit_page
    page.set_viewport_size({'width': 390, 'height': 844})
    generate(page)
    wait_for_selected_detail(page)
    page.evaluate('scrollTo(0,0)')
    page.wait_for_timeout(200)
    tall = page.evaluate("document.querySelector('body>header').getBoundingClientRect().height")
    page.locator('#plan-detail .day-of-tools').scroll_into_view_if_needed()
    page.wait_for_function("document.querySelector('body>header').classList.contains('is-compact')")
    page.wait_for_timeout(200)
    short = page.evaluate("document.querySelector('body>header').getBoundingClientRect().height")
    # 2026-11-25 시안 머리글: 휴대폰에서는 메뉴가 하단 바로 빠져 머리글이 처음부터 한 줄(71px)이라 더 낮아지지 않는다.
    # 낮아지지 않아도 되지만 커지면 안 되고, 높이 변수는 실제 높이와 맞아야 한다.
    assert short <= tall <= 80, (short, tall)
    assert page.evaluate("parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--site-header-height'))") == round(short + .49)
    # 같은 폭 2열: 장소 단추 줄의 첫 두 단추와 당일 도구 두 단추.
    for selector in ('#plan-detail .stop .actions', '#plan-detail .day-of-actions'):
        widths = page.evaluate(f"[...document.querySelector('{selector}').children].slice(0,2).map(e=>Math.round(e.getBoundingClientRect().width))")
        assert abs(widths[0] - widths[1]) <= 1, (selector, widths)
    assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth')
    page.evaluate('scrollTo(0,0)')
    page.wait_for_function("!document.querySelector('body>header').classList.contains('is-compact')")
    # 데스크톱 폭에서는 낮추지 않는다.
    page.set_viewport_size({'width': 1440, 'height': 900})
    page.evaluate('scrollTo(0,2000)')
    page.wait_for_timeout(300)
    assert not page.evaluate("document.querySelector('body>header').classList.contains('is-compact')")


def test_leg_line_does_not_repeat_minutes(audit_page):
    page, _, _ = audit_page
    generate(page)
    wait_for_selected_detail(page)
    text = page.evaluate('fieldItineraryText(selected)')
    leg = page.evaluate('dayLegText(selected, selected.legs[0])')
    assert leg.count('분') == 1 and '(추정)' not in leg
    assert leg in text
