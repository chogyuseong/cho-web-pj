"""2026-11-26 사용자 시안(Gemini Canvas, Downloads\\datemate-시안-2026-11-26)대로 바꾼 화면.

- 처음 화면: 안내 알약 · 한 줄 제목 · 아이콘 상황 칩 · '추천 동선 미리보기 예시' 카드. 예전 한 줄 입력 막대(#hero-command)·사진은 없다.
  한 줄 입력은 코스 만들기 카드 맨 위(펼쳐 둠), 예시 문구는 데이트/여행에 따라 바뀐다(header-mode.js COPY).
- 빠른 검색 ⌘K/Ctrl+K(static/quick-search.js): 걸러 고르고 Enter 로 화면의 동네 칩을 누른 것과 같이 적용, Esc 로 닫는다.
- 메뉴 미끄럼 표시(header-mode.js placeNavIndicator): 데스크톱에서 고른 메뉴 자리로 옮겨 간다.
- 장소 카드 분류 색(data-kind)과 체류 −15분/+15분(delay-check.js changeStay → GET delay-check stays): 뒤 장소가 밀리고 되돌리기로 지운다."""
import pytest

from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401  (pytest fixture)


def test_hero_follows_the_mockup(audit_page):
    page, _, _ = audit_page
    page.set_viewport_size({'width': 1440, 'height': 900})
    hero = page.locator('.romance-hero')
    assert hero.locator('.hero-eyebrow').inner_text() == '함께 보내는 시간에, 조금 더 다정한 계획'
    assert hero.locator('h1').inner_text() == '어디서 만날까요?'
    # 예전 히어로 입력 막대와 사진은 없다.
    assert page.locator('#hero-command, .hero-photo').count() == 0
    # 상황 칩: 글자는 예전과 같고, 칩마다 장식 아이콘(aria-hidden).
    chips = hero.locator('#hero-quick button')
    assert chips.all_inner_texts() == ['비 오는 날 성수 실내', '퇴근 후 한남 3시간', '강릉 바다 드라이브', '어색함 없는 서촌 소개팅']
    assert hero.locator('#hero-quick button svg[aria-hidden=true]').count() == 4
    # 예시 카드: 실제 추천이 아니라는 '예시', 장소 3곳과 도보 구간 2개.
    preview = hero.locator('.hero-preview')
    assert '예시' in preview.locator('.hero-preview-head').inner_text()
    assert preview.locator('.hero-preview-stop').count() == 3 and preview.locator('.hero-preview-leg').count() == 2
    # 넓은 화면에서는 두 칸(글 | 예시 카드)이 나란히.
    left, right = hero.locator('.hero-copy').bounding_box(), preview.bounding_box()
    assert right['x'] > left['x'] + left['width'] - 1
    # 휴대폰에서는 한 칸, 가로 넘침 없음.
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth')
    assert preview.bounding_box()['y'] > hero.locator('.hero-copy').bounding_box()['y']


def test_request_box_is_open_at_the_top_of_the_builder_and_follows_the_mode(audit_page):
    page, _, _ = audit_page
    page.evaluate("try{localStorage.removeItem('datemate-mode')}catch{}")
    dream = page.locator('details.simple-dream')
    assert dream.evaluate('d=>d.open')
    request = page.locator('#conditions [name=request]')
    assert request.get_attribute('placeholder') == '예: 비 오는 날 성수에서 덜 걷고 분위기 좋은 저녁 코스'
    page.locator('#mode-switch [data-mode=travel]').click()
    page.wait_for_function("document.querySelector('.hero-copy h1').textContent==='어디로 떠날까요?'")
    assert request.get_attribute('placeholder') == '예: 강릉에서 바다 보며 드라이브하고 저녁은 시장에서'
    page.locator('#mode-switch [data-mode=date]').click()
    page.wait_for_function("document.querySelector('.hero-copy h1').textContent==='어디서 만날까요?'")
    page.evaluate("try{localStorage.removeItem('datemate-mode')}catch{}")


def test_quick_search_palette_finds_and_applies_a_neighborhood(audit_page):
    page, _, _ = audit_page
    page.set_viewport_size({'width': 1440, 'height': 900})
    opener = page.locator('#quick-search-open')
    assert opener.is_visible() and opener.get_attribute('aria-haspopup') == 'dialog'
    page.keyboard.press('Control+k')
    dialog = page.locator('#quick-search')
    page.wait_for_function("document.getElementById('quick-search').open")
    field = page.locator('#quick-search-input')
    assert page.evaluate('document.activeElement.id') == 'quick-search-input'
    # 처음에는 묶음별 전체 목록(페이지·상황 테마·인기 동네·시·도).
    groups = dialog.locator('.quick-search-group').all_inner_texts()
    assert groups == ['페이지', '상황 테마', '인기 동네', '시·도']
    field.fill('성수')
    options = dialog.locator('[role=option]')
    assert options.all_inner_texts() == ['서울 성수']
    assert options.first.get_attribute('aria-selected') == 'true' and field.get_attribute('aria-activedescendant') == options.first.get_attribute('id')
    field.press('Enter')
    page.wait_for_function("!document.getElementById('quick-search').open")
    page.wait_for_function("!!locationState.origin")
    assert page.evaluate('locationState.origin.name').startswith('서울 성수')
    # 맞는 항목이 없으면 안내 한 줄, Esc 로 닫으면 연 단추로 포커스가 돌아간다.
    opener.click()
    field.fill('없는동네이름')
    assert dialog.locator('[role=option]').count() == 0 and '맞는 항목이 없어요' in dialog.locator('.quick-search-empty').inner_text()
    field.press('Escape')
    page.wait_for_function("!document.getElementById('quick-search').open")
    assert page.evaluate('document.activeElement.id') == 'quick-search-open'
    # 휴대폰에서는 돋보기만(44px 정사각).
    page.set_viewport_size({'width': 390, 'height': 844})
    box = opener.bounding_box()
    assert box['width'] >= 44 and box['height'] >= 44 and not opener.locator('.quick-search-label').is_visible()


def test_nav_indicator_slides_to_the_chosen_menu(audit_page):
    page, _, _ = audit_page
    page.set_viewport_size({'width': 1440, 'height': 900})
    page.evaluate('window.syncHeaderNav()')
    mark = page.locator('body > header > .nav-indicator')
    assert mark.count() == 1 and mark.get_attribute('aria-hidden') == 'true'
    # 메뉴 안 항목 수는 그대로(표시는 메뉴 밖).
    assert page.locator('body > header nav > .nav-indicator').count() == 0

    def lined_up(selector):
        return page.evaluate(f"""()=>{{const m=document.querySelector('body > header > .nav-indicator').getBoundingClientRect(),
          a=document.querySelector('{selector}').getBoundingClientRect();return Math.abs(m.left-a.left)<2&&Math.abs(m.width-a.width)<2;}}""")
    page.locator('#nav-explore').click()
    page.wait_for_function("document.getElementById('nav-explore').classList.contains('active')")
    page.wait_for_timeout(400)  # 옮겨 가는 움직임(0.28초)이 끝나기를 기다린다
    assert lined_up('#nav-explore')


@pytest.mark.parametrize('width', [1280, 390])
def test_stay_stepper_recomputes_the_rest_of_the_day(audit_page, width):
    page, _, _ = audit_page
    page.set_viewport_size({'width': width, 'height': 900})
    generate(page)
    wait_for_selected_detail(page)
    cards = page.locator('#plan-detail .timeline-card')
    # 분류 색: 카드마다 data-kind 와 왼쪽 4px 띠.
    assert all(cards.nth(i).get_attribute('data-kind') for i in range(cards.count()))
    assert cards.first.evaluate('e=>getComputedStyle(e).borderLeftWidth') == '4px'
    stepper = page.locator('#plan-detail .stay-stepper').first
    base = int(stepper.get_attribute('data-base'))
    stepper.locator('.stay-plus').click()
    stepper.locator('.stay-plus').click()
    assert stepper.locator('.stay-value').inner_text() == f'{base + 30}분' and 'is-changed' in stepper.get_attribute('class')
    page.wait_for_function("(()=>{const t=document.querySelector('#plan-detail .delay-sim-status')?.textContent||'';return t&&!t.includes('계산하고')})()")
    status = page.locator('#plan-detail .delay-sim-status').inner_text()
    assert status.startswith('체류를 바꿔'), status
    # 두 번째 장소부터 30분 밀린다(개점 대기가 없으면). 첫 장소는 떠나는 시각과 바뀐 체류를 함께 보인다.
    shifts = page.locator('#plan-detail .delay-sim-shift').all_inner_texts()
    assert shifts[0] == '그대로' and shifts[1] == '+30분', shifts
    assert f'({base + 30}분)' in page.locator('#plan-detail .delay-sim-departure').first.inner_text()
    reset = page.locator('#plan-detail .delay-sim-reset')
    assert reset.is_visible()
    reset.click()
    page.wait_for_function("document.querySelectorAll('#plan-detail .delay-sim-time').length===0")
    assert stepper.locator('.stay-value').inner_text() == f'{base}분' and reset.is_hidden()
    assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth')
    # 단추는 누르기 쉬운 높이.
    assert stepper.locator('.stay-plus').bounding_box()['height'] >= 44


def test_parse_stays_and_delay_check_with_stays():
    from app.delay_check import STAY_RANGE, parse_stays
    assert parse_stays('', 3) == {} and parse_stays('0:90, 2:45', 3) == {0: 90, 2: 45}
    for bad in ('x', '5:60', f'0:{STAY_RANGE[0] - 1}', f'0:{STAY_RANGE[1] + 1}'):
        with pytest.raises(ValueError):
            parse_stays(bad, 3)
