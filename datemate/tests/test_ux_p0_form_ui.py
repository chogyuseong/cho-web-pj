"""P0-2 코스 만들기 폼 다듬기 (2026-11-24 사용자 요구 'UX 개선 P0').

- 맨 위: '어떤 데이트를 꿈꾸나요?' 자연어 입력 + 상황 예시 칩(누르면 그 문장으로 채움) + '이 마음으로 조건 채우기'.
- 그 아래 지역(필수) → 날짜·시간·예산·교통(칸이 바로 보임, 2026-11-25 시안) → '상세 조건 더보기'(접힘).
- 상세 조건에는 예전에 화면에서 숨어 있던 것까지 모두: 테마 구성, 실내·실외, 피할 활동, 예약, 귀가 포함, MBTI, 체류 시간, 구간당 최대 이동, 전체 도보 제한.
- 상세 조건을 하나라도 바꾸면 머리글에 '상세 조건 설정됨 · …' 요약이 붙는다.
"""
import pytest

from test_functional_audit import audit_page, generate  # noqa: F401  (fixture)

# 2026-11-25 시안: 실내·실외(setting)는 숨은 select 를 세 칸 칩 막대로 꺼내 보이므로 아래에서 칩 묶음으로 따로 확인한다.
DETAIL_FIELDS = ('theme_mode', 'avoid', 'reservation', 'return_home', 'mbti', 'use_mbti', 'stay_minutes', 'max_leg', 'max_walk')


def test_dream_box_comes_first_with_scenario_chips(audit_page):  # noqa: F811
    page, _, _ = audit_page
    page.locator('#nav-plan').click()
    order = page.evaluate("""()=>{
      const dream=document.querySelector('#conditions .simple-dream'),area=[...document.querySelectorAll('#conditions .simple-form-group')].find(g=>g.textContent.includes('지역 선택'));
      return [!!dream,!!area,!!(dream&&area&&(dream.compareDocumentPosition(area)&Node.DOCUMENT_POSITION_FOLLOWING))];
    }""")
    assert order == [True, True, True], order
    dream = page.locator('#conditions .simple-dream')
    # 2026-11-26 시안: 한 줄 요청은 카드 맨 위에 처음부터 펼쳐져 있다(접기 틀과 요약 글은 남김).
    assert dream.evaluate('d=>d.open') and '한 줄로 적어서 조건 채우기' in dream.locator(':scope>summary').inner_text()
    assert '어떤 데이트를 꿈꾸나요?' in dream.inner_text()
    assert page.locator('#parse').inner_text() == '이 마음으로 조건 채우기'
    dream.get_by_role('button', name='비 오는 날 성수 실내 데이트', exact=True).click()
    assert page.evaluate('form.elements.request.value') == '비 오는 날 성수 실내 데이트'
    dream.get_by_role('button', name='덜 걷고 분위기 좋은 저녁 코스', exact=True).click()
    assert page.evaluate('form.elements.request.value') == '덜 걷고 분위기 좋은 저녁 코스', '예시 칩은 덧붙이지 않고 그 문장으로 바꾼다'


def test_details_hold_every_advanced_filter_and_summarise_changes(audit_page):  # noqa: F811
    page, _, _ = audit_page
    page.locator('#nav-plan').click()
    details = page.locator('details.simple-extra-options')
    summary = details.locator(':scope>summary')
    assert summary.inner_text().startswith('상세 조건 더보기')
    assert '설정됨' not in summary.inner_text()
    assert details.evaluate('d=>!d.open')
    summary.click()
    inside = page.evaluate(f"""()=>{list(DETAIL_FIELDS)}.map(n=>{{const el=form.elements[n];const d=el&&el.closest('details.simple-extra-options');
      return [n,!!d,!!el&&el.getClientRects().length>0||(el&&el.closest('details:not([open])')!==null)];}})""")
    assert all(row[1] for row in inside), inside
    assert details.get_by_role('group', name='실내 · 실외 비중').get_by_role('button', name='실내만', exact=True).is_visible()
    page.evaluate("""()=>{
      const set=(n,v)=>{const el=form.elements[n];if(el.type==='checkbox')el.checked=v;else el.value=v;el.dispatchEvent(new Event('change',{bubbles:true}));};
      set('max_walk','30');set('setting','indoor');set('avoid','클라이밍');
    }""")
    page.wait_for_function("document.querySelector('details.simple-extra-options>summary').textContent.includes('설정됨')")
    text = summary.inner_text()
    assert '상세 조건 설정됨' in text and '도보 30분 제한' in text and '실내만' in text and '외 1건' in text, text
    # 되돌리면 요약도 사라진다.
    page.evaluate("()=>{for(const [n,v] of [['max_walk',''],['setting','any'],['avoid','']]){form.elements[n].value=v;form.elements[n].dispatchEvent(new Event('change',{bubbles:true}));}}")
    page.wait_for_function("!document.querySelector('details.simple-extra-options>summary').textContent.includes('설정됨')")


def test_mbti_and_return_home_are_sent(audit_page):  # noqa: F811
    page, _, _ = audit_page
    page.locator('#nav-plan').click()
    page.locator('details.simple-extra-options>summary').click()
    page.evaluate("()=>{form.elements.mbti.value='INFP';form.elements.use_mbti.checked=true;}")
    sent = page.evaluate("()=>{const f=new FormData(form);return [f.get('mbti'),f.has('use_mbti')];}")
    assert sent == ['INFP', True], 'MBTI 는 더 이상 자동으로 비우지 않는다(사용자가 고른 값을 보낸다)'


@pytest.mark.parametrize('width', [375, 1280])
def test_form_fits_the_screen(audit_page, width):  # noqa: F811
    page, _, _ = audit_page
    page.set_viewport_size({'width': width, 'height': 900})
    page.locator('#nav-plan').click()
    page.locator('details.simple-extra-options>summary').click()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')


def test_area_then_submit_is_enough(audit_page):  # noqa: F811
    # 지역 칩 하나 + 추천받기 = 두 번 눌러 코스가 나온다(기본 조건은 채워져 있다).
    page, _, _ = audit_page
    generate(page)
    assert page.locator('#plan-detail').count() == 1


@pytest.mark.parametrize('width', [375, 1280])
def test_theme_card_fills_tags_and_focuses_the_quick_submit(audit_page, width):  # noqa: F811
    """테마 카드 → 채운 조건 태그 + '이 조건으로 바로 추천받기'에 포커스. 토스트는 하나(예전에는 두 핸들러가 겹쳤다)."""
    page, _, _ = audit_page
    page.set_viewport_size({'width': width, 'height': 900})
    page.wait_for_function('!!statusData')
    page.get_by_role('tab', name='주말 떠나기 좋은 동네').click()
    page.locator('[data-preset="서울 성수"]').click()
    tags = page.locator('#preset-tags')
    tags.wait_for()
    assert tags.is_visible() and '서울 성수' in tags.inner_text()
    go = tags.get_by_role('button', name='이 조건으로 바로 추천받기', exact=True)
    page.wait_for_function("document.activeElement?.classList.contains('preset-go')")
    toast_text = page.locator('#toast').text_content()
    assert '에서 시작하는 테마를 골랐어요' in toast_text and '날짜와 예산을 확인하고' not in toast_text, toast_text
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    go.click()
    page.wait_for_selector('#plan-detail .stop', timeout=60000)
    # 다른 지역을 고르면 태그를 지운다.
    page.locator('#edit-conditions').click()
    page.get_by_role('group', name='인기 동네').get_by_role('button', name='부산 해운대', exact=True).click()
    page.wait_for_function("document.getElementById('preset-tags').hidden")
