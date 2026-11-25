"""2026-11-25 사용자 시안(Downloads/screencapture-gemini-*.png) 반영: 머리글 메뉴 표시·데이트/여행 스위치·테마 카드 글자 대비.

화면 규칙은 static/header-mode.js, static/theme-cards.js, static/redesign.css 2)·5)·8)."""
import pytest

from test_functional_audit import audit_page  # noqa: F401  (pytest fixture)


def lum(rgb):
    out = []
    for value in rgb:
        c = value / 255
        out.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]


def contrast(a, b):
    x, y = sorted((lum(a), lum(b)), reverse=True)
    return (x + 0.05) / (y + 0.05)


def hex_rgb(text):
    text = text.strip().lstrip('#')
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))


def blend(rgb, alpha):
    """흰색을 alpha 만큼 덮은 색(배지 rgba(255,255,255,.18))."""
    return tuple(v * (1 - alpha) + 255 * alpha for v in rgb)


def test_white_text_stays_readable_on_every_card_tone(audit_page):
    # 카드 글자는 흰색. 그라데이션의 세 색(--tone·--tone-from·--tone-to) 모두에서 4.5:1, 배지(흰 18%)는 시작 색 위에서 4.5:1.
    page, _, _ = audit_page
    tones = page.evaluate("""()=>[...document.querySelectorAll('#curation .curation-card')].map(c=>{const s=getComputedStyle(c);
      return {tone:c.dataset.tone,colors:['--tone','--tone-from','--tone-to'].map(n=>s.getPropertyValue(n))}})""")
    assert len(tones) == 12 and all(t['tone'] for t in tones), tones
    for item in tones:
        for color in item['colors']:
            assert contrast((255, 255, 255), hex_rgb(color)) >= 4.5, item
        assert contrast((255, 255, 255), blend(hex_rgb(item['colors'][1]), .18)) >= 4.5, item


def test_season_card_text_and_tags_match_the_filled_conditions(audit_page):
    page, _, _ = audit_page
    # 태그가 약속한 조건을 실제로 채우는지: 이색 체험 '#예약 가능', 휴식 '#도보 10분 제한', 기념일 '#10만원대'(1인).
    values = page.evaluate("Object.fromEntries(SITUATION_THEMES.map(t=>[t.key,[t.tags,t.values]]))")
    assert values['activity'][1]['reservation'] is True and '#예약 가능' in values['activity'][0]
    assert values['rest'][1]['max_walk'] == 10 and '#도보 10분 제한' in values['rest'][0]
    assert values['anniversary'][1]['budget_per_person'] == 200000 and '#10만원대' in values['anniversary'][0]
    assert values['after-work'][1]['start'] == '18:30' and values['after-work'][1]['end'] == '21:30'


@pytest.mark.parametrize('width', [390, 1440])
def test_mode_switch_changes_color_copy_chips_and_tab_and_is_remembered(audit_page, width):
    page, base, _ = audit_page
    page.set_viewport_size({'width': width, 'height': 900})
    page.evaluate("try{localStorage.removeItem('datemate-mode')}catch{}")
    page.goto(base + '/', wait_until='networkidle')
    switch = page.get_by_role('group', name='추천 모드')
    date, travel = switch.get_by_role('button', name='데이트'), switch.get_by_role('button', name='여행')
    assert date.get_attribute('aria-pressed') == 'true' and travel.get_attribute('aria-pressed') == 'false'
    assert all(b.bounding_box()['height'] >= 44 for b in (date, travel))
    accent = "getComputedStyle(document.body).getPropertyValue('--hong').trim()"
    assert page.evaluate(accent).upper() == '#E0004D'
    travel.click()
    assert travel.get_attribute('aria-pressed') == 'true' and page.evaluate("document.body.classList.contains('mode-travel')")
    assert page.evaluate(accent).upper() == '#1D4ED8'
    assert page.locator('.hero-copy h1').inner_text().replace('\n', ' ') == '어디로 떠날까요?'
    chips = page.locator('#hero-quick button')
    assert chips.all_inner_texts() == ['강릉 바다 드라이브', '부산 광안리 밤바다', '경주 황리단길 한옥 산책', '제주 애월 오션뷰']
    assert page.get_by_role('tab', name='주말 떠나기 좋은 동네').get_attribute('aria-selected') == 'true'
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    # 다시 열어도 여행(이 브라우저에 기억).
    page.reload(wait_until='networkidle')
    assert page.evaluate("document.body.classList.contains('mode-travel')")
    assert page.get_by_role('group', name='추천 모드').get_by_role('button', name='여행').get_attribute('aria-pressed') == 'true'
    # 여행 칩은 동네 카드를 그대로 고른다(조건 화면으로 넘어가 지역이 채워진다).
    page.wait_for_function("!!statusData&&!!document.querySelector('[name=themes]')")
    page.locator('#hero-quick button', has_text='제주 애월 오션뷰').click()
    page.wait_for_function('form.elements.origin_name.value==="제주 애월 한담해변 지역 중심"')
    page.evaluate("document.body.classList.remove('show-date-plan')")
    page.get_by_role('group', name='추천 모드').get_by_role('button', name='데이트').click()
    assert page.locator('.hero-copy h1').inner_text().replace('\n', ' ') == '어디서 만날까요?'
    assert page.get_by_role('tab', name='오늘의 상황으로 고르기').get_attribute('aria-selected') == 'true'
    assert page.evaluate("localStorage.getItem('datemate-mode')") == 'date'


def test_menu_follows_the_section_on_screen(audit_page):
    page, _, _ = audit_page
    page.set_viewport_size({'width': 1440, 'height': 900})
    state = "[document.querySelector('#nav-home').classList.contains('active'),document.querySelector('#nav-plan').getAttribute('aria-pressed')]"
    assert page.evaluate(state) == [True, 'false']
    # 사용자가 조건 화면까지 스크롤하면 '코스 만들기'로, 다시 위로 가면 '홈 · 테마'로.
    page.evaluate("document.getElementById('planner-section').scrollIntoView()")
    page.mouse.wheel(0, 10)
    page.wait_for_function(f"{state}[1]==='true'")
    page.evaluate("scrollTo(0,0)")
    page.mouse.wheel(0, -10)
    page.wait_for_function(f"{state}[0]===true")
    # 장소 둘러보기는 그 화면에 있는 동안.
    page.click('#nav-explore')
    assert page.evaluate("[document.querySelector('#nav-explore').getAttribute('aria-pressed'),document.querySelector('#nav-home').classList.contains('active')]") == ['true', False]
