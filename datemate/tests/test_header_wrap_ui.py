"""머리글의 같은 이름 중복, 메뉴 이동, 한글 낱말 단위 줄바꿈: 실제 브라우저, 가상 장소 데모."""
from test_feedback_ui import route_festivals
from test_functional_audit import audit_page, generate  # noqa: F401

VISIBLE_HEADER_LABELS = """[...document.querySelectorAll('body > header a, body > header button')]
  .filter(el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden')
  .map(el => el.textContent.trim()).filter(Boolean)"""


def no_overflow(page):
    return page.evaluate('document.documentElement.scrollWidth<=innerWidth')


def test_header_shows_each_menu_once_and_plan_tab_moves_to_conditions(audit_page):
    page, base, errors = audit_page
    for width in (1440, 1100, 801, 390):
        page.set_viewport_size({'width': width, 'height': 900})
        labels = page.evaluate(VISIBLE_HEADER_LABELS)
        assert labels.count('코스 만들기') == 1, (width, labels)
        assert len(labels) == len(set(labels)), (width, labels)
    page.set_viewport_size({'width': 1440, 'height': 900})
    page.evaluate('scrollTo(0, document.body.scrollHeight)')
    page.locator('#nav-plan').click()
    page.wait_for_function("location.hash==='#planner-section'")
    page.wait_for_function("Math.abs(document.querySelector('#planner-section').getBoundingClientRect().top)<120")
    assert not page.locator('#planner-section').evaluate('el=>el.hidden')


def test_korean_text_breaks_between_words_without_overflow(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 844})
    style = page.evaluate("['body','h1','h2','.hero-description','#curation p'].map(s=>{const c=getComputedStyle(document.querySelector(s));return [c.wordBreak,c.overflowWrap]})")
    assert all(row == ['keep-all', 'anywhere'] for row in style), style
    assert no_overflow(page)
    route_festivals(page)
    generate(page)
    page.wait_for_function('document.querySelectorAll("#festival-results .festival-card").length===3')
    assert no_overflow(page)
    cards = page.locator('#festival-results .festival-card')
    assert all(box['x'] >= 0 and box['x'] + box['width'] <= 390 for box in (cards.nth(i).bounding_box() for i in range(3)))
    if not page.locator('.comparison-details').evaluate('d=>d.open'):
        page.locator('.comparison-details summary').click()
    assert no_overflow(page)
    # 비교 표 칸은 전처럼 낱말을 쪼개지 않는다(editorial.css 의 keep-all + normal 유지).
    assert page.locator('.option-comparison td').first.evaluate('el=>getComputedStyle(el).overflowWrap') == 'normal'
