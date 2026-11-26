"""리디자인 1단계(2026-11-24, static/redesign.css·theme-cards.js 히어로): 머리글 알약 메뉴, 휴대폰 하단 바, 커맨드 바 히어로, 바로 시작 칩, 벤토 테마 카드."""
import pytest

from test_functional_audit import audit_page  # noqa: F401  (pytest fixture)


def ready(page):
    page.wait_for_function("!!statusData&&!!document.querySelector('[name=themes]')&&!!form.elements.meeting_type")


def test_tokens_and_font():
    from app.config import ROOT
    css = (ROOT / 'static' / 'style.css').read_text(encoding='utf-8')
    for token in ('--hong:#E0004D', '--accent-date:#FF385C', '--radius-card:20px', '"Pretendard"'):
        assert token in css, token


def test_desktop_header_is_a_centered_pill_menu(audit_page):
    page, _, _ = audit_page
    page.set_viewport_size({'width': 1280, 'height': 900})
    nav = page.locator('body > header nav')
    box = nav.bounding_box()
    # 가운데 정렬(브랜드 쪽으로 치우치지 않는다), 고른 메뉴는 진한 알약.
    center = box['x'] + box['width'] / 2
    assert abs(center - 640) < 120, box
    # 2026-11-25 시안: 데스크톱 메뉴는 코스 만들기·테마 추천·장소 둘러보기·피드백(코스 결과 칸은 휴대폰 하단 바에서만 보인다).
    # 첫 화면은 '테마 추천'(#nav-home)이 고른 메뉴이고, 고른 메뉴 뒤에 흰 알약 표시(.nav-indicator)가 미끄러져 온다(2026-11-26, redesign.css 17).
    assert page.locator('body > header nav > :is(a,button)').evaluate_all("l=>l.filter(e=>e.getClientRects().length).map(e=>e.textContent.trim())") == ['코스 만들기', '테마 추천', '장소 둘러보기', '피드백']
    active = page.locator('#nav-home')
    assert active.get_attribute('aria-current') == 'true'
    mark = page.locator('body > header > .nav-indicator')
    assert mark.evaluate("e=>getComputedStyle(e).backgroundColor") == 'rgb(255, 255, 255)'
    assert float(mark.evaluate("e=>parseFloat(getComputedStyle(e).borderTopLeftRadius)")) >= 20
    page.wait_for_timeout(400)
    assert page.evaluate("""()=>{const m=document.querySelector('body > header > .nav-indicator').getBoundingClientRect(),
      a=document.getElementById('nav-home').getBoundingClientRect();return Math.abs(m.left-a.left)<2&&Math.abs(m.width-a.width)<2;}""")
    assert page.locator('body > header').evaluate("e=>getComputedStyle(e).position") == 'sticky'


@pytest.mark.parametrize('width', [320, 375])
def test_phone_menu_is_a_bottom_bar(audit_page, width):
    page, _, _ = audit_page
    page.set_viewport_size({'width': width, 'height': 740})
    ready(page)
    # 2026-11-25 시안: 하단 바 네 칸은 코스 만들기·테마 추천·코스 결과·장소 둘러보기(DOM 순서는 결과가 마지막이고 CSS order 로 셋째 칸). 피드백은 바닥글.
    all_items = page.locator('body > header nav > :is(a,button)')
    visible = [item for item in all_items.all() if item.is_visible()]
    assert len(visible) == 4
    visible.sort(key=lambda item: item.bounding_box()['x'])
    assert [item.inner_text().strip() for item in visible] == ['코스 만들기', '테마 추천', '추천 결과', '장소 둘러보기']
    items = page.locator('body > header nav > :is(a,button):visible')
    boxes = [item.bounding_box() for item in visible]
    # 네 칸이 한 줄로 화면 아래에, 터치 높이 44px 이상.
    assert len({round(b['y']) for b in boxes}) == 1
    assert all(b['height'] >= 44 for b in boxes)
    assert boxes[0]['y'] + boxes[0]['height'] > 740 - 40
    # 스크롤해도 같은 자리.
    page.mouse.wheel(0, 1500)
    page.wait_for_timeout(300)
    assert abs(visible[0].bounding_box()['y'] - boxes[0]['y']) < 2
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    # 메뉴가 바에서도 동작한다.
    page.get_by_role('button', name='장소 둘러보기', exact=True).click()
    page.wait_for_function("document.body.classList.contains('show-explore')")


@pytest.mark.parametrize('width', [375, 1280])
def test_hero_quick_start_fills_theme_and_area(audit_page, width):
    page, _, _ = audit_page
    page.set_viewport_size({'width': width, 'height': 900})
    ready(page)
    chips = page.get_by_role('group', name='바로 시작하기').get_by_role('button')
    assert chips.all_inner_texts() == ['비 오는 날 성수 실내', '퇴근 후 한남 3시간', '강릉 바다 드라이브', '어색함 없는 서촌 소개팅']
    assert all(chip.bounding_box()['height'] >= 44 for chip in chips.all())
    # 첫 화면의 시작 시각은 지금 시각에 따라 11:00·13:00·17:00 중 하나다(simple-form.js startPassed — 브라우저 시계, CI 는 UTC).
    # 그래서 되돌릴 값은 적어 두지 않고 칩을 누르기 전 값을 쓴다.
    start_before = page.evaluate('form.elements.start.value')
    chips.nth(1).click()
    page.wait_for_function("location.hash==='#planner-section'")
    assert page.evaluate('[form.elements.region.value, locationState.origin.name, form.elements.start.value, form.elements.end.value]') == [
        '서울', '서울 한남 한강진역 지역 중심', '18:30', '21:30']
    banner = page.locator('#preset-tags')
    assert '서울 한남 지역을 채웠어요' in banner.inner_text()
    page.wait_for_function("document.activeElement?.classList.contains('preset-go')")
    # [테마 해제]는 칩이 넣은 동네까지 되돌린다.
    banner.get_by_role('button', name='테마 해제').click()
    assert page.evaluate('[locationState.origin, form.elements.start.value]') == [None, start_before]
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')


def test_hero_quick_start_area_only_uses_the_area_card(audit_page):
    page, _, _ = audit_page
    ready(page)
    page.get_by_role('button', name='강릉 바다 드라이브', exact=True).click()
    assert page.evaluate('[locationState.origin.name, form.elements.transport.value]') == ['강원 강릉 안목해변 지역 중심', 'car']


# 예전 test_hero_command_sends_the_sentence_to_the_request_parser: 2026-11-26 시안에서 히어로 한 줄 입력 막대가 없어졌다.
# 한 줄 입력은 코스 만들기 카드 맨 위(test_ux_p0_form_ui.py·test_redesign_1126_ui.py 가 본다).


def test_theme_cards_are_rounded_cards(audit_page):
    page, _, _ = audit_page
    page.set_viewport_size({'width': 1280, 'height': 900})
    card = page.locator('#curation-situation .curation-card').first
    # 2026-11-25 시안: 진한 그라데이션 카드(흰 글자). ::before 는 글자 대비용 어두운 막(예전 노선 동그라미 크기·테두리는 지움).
    style = card.evaluate("e=>{const s=getComputedStyle(e),b=getComputedStyle(e,'::before');return [s.borderTopLeftRadius,s.color,s.backgroundImage.includes('gradient'),b.borderTopWidth,b.width===s.width]}")
    assert style == ['20px', 'rgb(255, 255, 255)', True, '0px', True], style


@pytest.mark.parametrize('width', [375, 1280])
def test_activity_chips_toggle_the_category_filter(audit_page, width):
    # 리디자인 2단계: 숨긴 분류 체크박스(themes)를 '원하는 활동' 칩으로. 상황 테마가 바꾼 분류도 칩 눌림에 맞춰진다.
    page, _, _ = audit_page
    page.set_viewport_size({'width': width, 'height': 900})
    ready(page)
    page.locator('#nav-plan').click()
    group = page.get_by_role('group', name='원하는 활동')
    chips = group.get_by_role('button')
    assert chips.all_inner_texts() == ['카페·맛집', '산책·풍경', '전시·문화', '공방·체험', '놀거리', '레저·스포츠', '휴식·힐링']
    assert all(c.bounding_box()['height'] >= 44 for c in chips.all())
    group.get_by_role('button', name='전시·문화').click()
    group.get_by_role('button', name='카페·맛집').click()
    assert page.evaluate("[...document.querySelectorAll('[name=themes]:checked')].map(i=>i.value)") == ['카페·미식', '문화·예술']
    assert group.get_by_role('button', name='전시·문화').get_attribute('aria-pressed') == 'true'
    assert page.evaluate("FormState.edited.has('themes')")
    group.get_by_role('button', name='카페·맛집').click()
    assert page.evaluate("[...document.querySelectorAll('[name=themes]:checked')].map(i=>i.value)") == ['문화·예술']
    # 상황 테마(최소 도보 힐링)가 분류를 채우면 칩도 눌린 상태로.
    page.evaluate("document.body.classList.remove('show-date-plan')")
    page.locator('[data-situation="rest"]').click()
    page.wait_for_function("document.querySelector('[data-theme=\"휴식·힐링\"]').getAttribute('aria-pressed')==='true'")
    assert group.get_by_role('button', name='전시·문화').get_attribute('aria-pressed') == 'true'
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
