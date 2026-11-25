"""결과 화면 고정 윗줄·휴대폰 아래 막대(2026-11-25 Gemini Canvas 시안, static/plan-results.js syncResultsBars · redesign.css 12)).

- 데스크톱: 윗줄(#results-bar)에 조건 수정하기·조건 칩·공유 티켓·일정 복사가 있고, 내려 읽어도 머리글 바로 아래에 붙어 있다.
- 휴대폰: 코스가 있으면 메뉴 바 대신 '지도 보기 / 일정 복사 / 공유 티켓'. 지도 보기 → 지도로 가고 '일정 보기'로 바뀐다. 처음 화면에서는 메뉴 바 그대로.
- 인쇄에는 두 막대의 단추가 나오지 않는다."""
import pytest

from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401  (pytest fixture)

SHOWN = "s=>[...document.querySelectorAll(s)].filter(e=>e.getClientRects().length>0).length"


def test_desktop_bar_sticks_under_the_header_with_share_and_copy(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 1440, 'height': 900})
    generate(page)
    wait_for_selected_detail(page)
    bar = page.locator('#results-bar')
    assert bar.locator('#edit-conditions').is_visible()
    assert bar.locator('#results-meta > *').count() >= 3
    assert [b.inner_text() for b in bar.locator('.results-bar-actions button').all()] == ['공유 티켓', '일정 복사']
    # 내려 읽어도 머리글 바로 아래(같은 자리)에 붙어 있다.
    page.locator('#plan-detail .stop').nth(2).evaluate("e=>e.scrollIntoView({block:'center'})")
    page.wait_for_timeout(300)
    top, header = page.evaluate("[document.querySelector('#results-bar').getBoundingClientRect().top,"
                                "document.querySelector('body>header').getBoundingClientRect().bottom]")
    assert abs(top - header) <= 2, (top, header)
    # 공유 티켓은 오른쪽 패널과 같은 대화상자를 연다.
    bar.get_by_role('button', name='공유 티켓').click()
    page.wait_for_function("document.querySelector('#dialog')?.open")
    # 휴대폰 아래 막대는 데스크톱에서 보이지 않는다.
    assert page.evaluate(SHOWN, '#results-actionbar') == 0


@pytest.mark.parametrize('width', [390, 320])
def test_phone_shows_map_copy_ticket_bar_instead_of_the_menu_on_results(audit_page, width):
    page, base, errors = audit_page
    page.set_viewport_size({'width': width, 'height': 800})
    # 처음 화면: 메뉴 바, 결과 막대 없음.
    assert page.evaluate("getComputedStyle(document.querySelector('body>header nav')).display") != 'none'
    assert page.evaluate(SHOWN, '#results-actionbar') == 0
    generate(page)
    wait_for_selected_detail(page)
    bar = page.locator('#results-actionbar')
    assert bar.is_visible()
    assert page.evaluate("getComputedStyle(document.querySelector('body>header nav')).display") == 'none'
    assert [b.inner_text() for b in bar.locator('button').all()] == ['지도 보기', '일정 복사', '공유 티켓']
    boxes = [b.bounding_box() for b in bar.locator('button').all()]
    assert len({round(b['y']) for b in boxes}) == 1 and all(b['height'] >= 44 for b in boxes)
    # 윗줄의 공유·복사는 휴대폰에서 숨긴다(아래 막대와 겹치지 않게).
    assert page.evaluate(SHOWN, '#results-bar .results-bar-actions button') == 0
    # 지도 보기 → 지도가 화면에 오고 단추가 '일정 보기'로 바뀐다. 다시 누르면 첫 장소로.
    page.emulate_media(reduced_motion='reduce')
    bar.locator('.results-actionbar-map').click()
    page.wait_for_function("document.querySelector('.results-actionbar-map').innerText.trim()==='일정 보기'")
    bar.locator('.results-actionbar-map').click()
    page.wait_for_function("(()=>{const r=document.querySelector('#plan-detail .stop').getBoundingClientRect();return r.top<innerHeight&&r.bottom>0})()")
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
    # 조건 수정하기로 돌아가면(결과가 숨으면) 메뉴 바가 다시 보인다.
    page.locator('#edit-conditions').click()
    page.wait_for_function("getComputedStyle(document.querySelector('body>header nav')).display!=='none'")


def test_print_hides_the_bar_buttons(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 800})
    generate(page)
    wait_for_selected_detail(page)
    page.emulate_media(media='print')
    assert page.evaluate(SHOWN, '#results-actionbar') == 0
    assert page.evaluate(SHOWN, '#results-bar button') == 0
