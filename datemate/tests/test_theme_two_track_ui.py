"""'테마로 고르는 하루' 2트랙(2026-11-24): 상황 테마(지역 자유)·계절 카드·동네 테마, 잔여 조건 정리, [테마 해제].

상황 테마 값은 static/theme-cards.js SITUATION_THEMES·SEASON_THEMES, 동네는 static/index.html 의 data-preset 버튼.
추천 요청은 가로채 본문만 본다(외부 API 를 부르지 않는다)."""
import pytest

from test_functional_audit import audit_page  # noqa: F401  (pytest fixture)
from test_nationwide_home import intercept_plan_jobs, wait_for_job

FIELDS = "Object.fromEntries(['budget','setting','max_walk','max_leg','start','end','count','stay_minutes','theme_mode','transport','meeting_type','priority'].map(n=>[n,form.elements[n]?.value]))"
CHECKS = "({reservation:form.elements.reservation.checked,include_meal:form.elements.include_meal?.checked,themes:[...document.querySelectorAll('[name=themes]:checked')].map(i=>i.value)})"


def ready(page):
    page.wait_for_function("!!statusData&&!!document.querySelector('[name=themes]')&&!!form.elements.meeting_type")


def situation(page, key):
    # 테마를 고르면 조건 화면으로 넘어가 홈 카드가 숨는다(home.css body.show-date-plan). 다음 카드를 누르려고 홈으로 되돌린다.
    page.evaluate("document.body.classList.remove('show-date-plan')")
    page.locator(f'[data-situation="{key}"]').click()


def test_season_card_matches_the_month(audit_page):
    page, _, _ = audit_page
    assert page.evaluate('[1,2,3,5,6,8,9,11,12].map(seasonFor)') == [
        'winter', 'winter', 'spring', 'spring', 'summer', 'summer', 'autumn', 'winter', 'winter']
    # 2026-11-25 시안: 11~2월 겨울('11월 겨울 시즌'), 9~10월 가을. 배지는 달과 계절.
    assert page.evaluate('[seasonBadge(10),seasonBadge(11),seasonBadge(2)]') == ['10월 가을 시즌', '11월 겨울 시즌', '2월 겨울 시즌']
    first = page.locator('#curation-situation .curation-card').first
    expected = page.evaluate('SEASON_THEMES[seasonFor(new Date().getMonth()+1)].key')
    assert first.get_attribute('data-situation') == expected
    assert first.locator('.curation-badge').inner_text() == page.evaluate('seasonBadge(new Date().getMonth()+1)')
    assert 'is-feature' in first.get_attribute('class')


@pytest.mark.parametrize('width', [375, 1280])
def test_situation_theme_keeps_area_fills_conditions_and_sends_them(audit_page, width):
    page, _, _ = audit_page
    page.set_viewport_size({'width': width, 'height': 900})
    ready(page)
    bodies = intercept_plan_jobs(page)
    # 지역을 먼저 고른 사람: 상황 테마는 지역을 바꾸지 않는다.
    page.evaluate("applyArea('부산',{name:'부산 해운대역 지역 중심',lat:35.1631,lon:129.1636})")
    situation(page, 'indoor')
    page.wait_for_function("location.hash==='#planner-section'")
    assert page.evaluate('[form.elements.region.value, locationState.origin.name]') == ['부산', '부산 해운대역 지역 중심']
    fields = page.evaluate(FIELDS)
    assert (fields['setting'], fields['max_walk'], fields['max_leg']) == ('indoor', '15', '15')
    assert page.evaluate(CHECKS)['themes'] == ['카페·미식', '문화·예술', '체험·제작']
    banner = page.locator('#preset-tags')
    assert '‘비·추위 피하는 올-실내’ 조건을 채웠어요. 데이트할 지역과 날짜만 골라 주세요.' in banner.inner_text()
    assert '실내만' in banner.inner_text() and '전체 도보 15분 이하' in banner.inner_text()
    # 지역이 이미 있으니 바로 추천받기 단추에 포커스.
    page.wait_for_function("document.activeElement?.classList.contains('preset-go')")
    # 상세 조건 배지에도 반영.
    badge = page.evaluate("[...document.querySelectorAll('#conditions *')].find(e=>e.textContent.startsWith('상세 조건 설정됨'))?.textContent||''")
    assert '도보 15분 제한' in badge and '실내만' in badge, badge
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    banner.get_by_role('button', name='이 조건으로 바로 추천받기').click()
    body = wait_for_job(page, bodies)
    assert (body['setting'], body['max_walk'], body['max_leg'], body['region']) == ('indoor', 15, 15, '부산')
    assert sorted(body['themes']) == sorted(['문화·예술', '체험·제작', '카페·미식'])


def test_switching_themes_leaves_nothing_behind_and_clear_restores(audit_page):
    page, _, _ = audit_page
    ready(page)
    # 테마 전에 사용자가 바꿔 둔 값: 장소 4곳.
    page.evaluate("form.elements.count.value='4'")
    before = page.evaluate(FIELDS)
    before_checks = page.evaluate(CHECKS)
    situation(page, 'anniversary')
    assert page.evaluate(CHECKS)['reservation'] is True
    assert page.evaluate('form.elements.meeting_type.value') == 'anniversary'
    # '#10만원대'(1인): 예산 칸은 일행 합계라 인원(2명)을 곱해 넣는다.
    assert page.evaluate('[form.elements.budget.value, form.elements.budget_unlimited.checked]') == ['400000', False]
    # 다른 상황 테마로: 기념일의 예약·만남 종류가 남지 않는다.
    situation(page, 'rest')
    fields, checks = page.evaluate(FIELDS), page.evaluate(CHECKS)
    assert checks['reservation'] is False and fields['meeting_type'] == 'regular'
    assert (fields['max_walk'], fields['stay_minutes'], fields['count']) == ('10', '120', '2')
    assert fields['budget'] == before['budget']
    situation(page, 'after-work')
    fields = page.evaluate(FIELDS)
    assert (fields['max_walk'], fields['stay_minutes'], fields['start'], fields['end'], fields['count']) == ('', '60', '18:30', '21:30', '2')
    assert page.evaluate(CHECKS)['themes'] == ['카페·미식', '산책·풍경']
    # 동네 테마로 바꿔도 상황 테마 값이 남지 않고, 동네의 이동 수단이 들어간다.
    page.evaluate("document.body.classList.remove('show-date-plan')")
    page.get_by_role('tab', name='주말 떠나기 좋은 동네').click()
    page.locator('[data-preset="강릉 안목해변"]').click()
    fields = page.evaluate(FIELDS)
    # 시각은 동네 테마가 정하지 않아 테마 전 값 그대로다. 첫 화면은 지금 시각이 11:00 을 넘으면 다음 시간대(13:00·17:00)로 시작하므로
    # (simple-form.js startPassed — 브라우저 시계 기준, CI 는 UTC) '11:00' 을 적어 두면 하루 중 몇 시간 동안 실패했다.
    assert (fields['start'], fields['end'], fields['transport'], fields['count']) == (before['start'], before['end'], 'car', '4')
    assert page.evaluate(CHECKS)['themes'] == []
    banner = page.locator('#preset-tags')
    assert '‘강릉 안목해변’ 추천 조건을 채웠어요. 날짜와 시간만 확인하고 바로 추천받아 보세요.' in banner.inner_text()
    # [테마 해제]: 테마를 고르기 전 값으로(지역도 고르기 전처럼 비움).
    banner.get_by_role('button', name='테마 해제').click()
    assert banner.is_hidden()
    assert page.evaluate(FIELDS) == before
    assert page.evaluate(CHECKS) == before_checks
    assert page.evaluate('locationState.origin') is None
    assert page.evaluate("document.querySelectorAll('#curation [aria-pressed=true]').length") == 0


@pytest.mark.parametrize('width', [375, 1280])
def test_situation_theme_without_area_points_to_the_area_step(audit_page, width):
    page, _, _ = audit_page
    page.set_viewport_size({'width': width, 'height': 900})
    ready(page)
    assert page.evaluate('locationState.origin') is None
    situation(page, 'first-date')
    group = page.locator('.simple-form-group.needs-area')
    group.wait_for()
    page.wait_for_function("document.activeElement?.classList.contains('needs-area')")
    assert '어디에서 만날까요' in group.inner_text()
    banner = page.locator('#preset-tags')
    assert not banner.get_by_role('button', name='이 조건으로 바로 추천받기').is_visible()
    fields = page.evaluate(FIELDS)
    assert (fields['start'], fields['end'], fields['count'], fields['max_walk'], fields['meeting_type'], fields['priority']) == (
        '14:00', '17:00', '2', '15', 'first', 'talk')
    # 지역을 고르면 강조가 꺼지고 바로 추천받기가 보인다. 상황 테마 안내는 그대로.
    page.get_by_role('group', name='인기 동네').get_by_role('button', name='서울 성수', exact=True).click()
    page.wait_for_function("!document.querySelector('.needs-area')")
    banner.get_by_role('button', name='이 조건으로 바로 추천받기').wait_for()
    assert '썸 & 소개팅' in banner.inner_text()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')


def test_tabs_move_with_arrow_keys(audit_page):
    page, _, _ = audit_page
    first = page.get_by_role('tab', name='오늘의 상황으로 고르기')
    second = page.get_by_role('tab', name='주말 떠나기 좋은 동네')
    assert first.get_attribute('aria-selected') == 'true' and page.locator('#curation-areas').is_hidden()
    first.focus()
    page.keyboard.press('ArrowRight')
    assert second.get_attribute('aria-selected') == 'true' and page.evaluate('document.activeElement.id') == 'curation-tab-areas'
    assert page.locator('#curation-situation').is_hidden() and page.locator('#curation-areas').is_visible()
    page.keyboard.press('ArrowRight')
    assert first.get_attribute('aria-selected') == 'true'
