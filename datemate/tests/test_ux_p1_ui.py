"""P1 코스 이후 동선 (2026-11-24 사용자 요구 'UX 개선 P1').

- 장소마다 「↻ 다른 장소로 바꾸기」·「○ 장소 고정」·「네이버 지도 보기 ↗」(실제 장소만).
- 구간마다 「길찾기 ▾」 → 네이버 지도·카카오맵 길찾기(우리 좌표 그대로, 새 탭).
- 결과 머리에 '방문 전 … 오늘 영업시간을 확인해 주세요.' 한 줄.
- 공유 줄 맨 앞 「카톡용 일정·링크 복사」: 날짜·시간별 장소·이동·예상 비용·24시간 공유 링크.
"""
import pytest

from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401  (fixture)


def real_detail(page):
    generate(page)
    wait_for_selected_detail(page)
    # 데모 코스를 실제 코스처럼 다시 그린다(좌표는 그대로).
    page.evaluate("selected.conditions.mode='real';selected.places.forEach(p=>p.demo=false);renderDetail()")


def test_stop_buttons_and_map_link(audit_page):  # noqa: F811
    page, _, _ = audit_page
    real_detail(page)
    stop = page.locator('#plan-detail .stop').first
    assert stop.get_by_role('button', name='↻ 다른 장소로 바꾸기', exact=True).count() == 1
    assert stop.get_by_role('button', name='○ 장소 고정', exact=True).count() == 1
    link = stop.get_by_role('link', name='네이버 지도 보기 ↗', exact=True)
    assert link.count() == 1 and link.get_attribute('href').startswith('https://map.naver.com/')
    assert link.get_attribute('target') == '_blank' and 'noopener' in link.get_attribute('rel')
    assert stop.get_by_role('link', name='도착지 지도·길찾기 확인').count() == 0
    # 체험 코스(가상 장소)에는 지도 링크가 없다.
    page.evaluate("selected.conditions.mode='demo';renderDetail()")
    assert page.locator('#plan-detail .stop').first.get_by_role('link', name='네이버 지도 보기 ↗').count() == 0


def test_directions_menu_offers_naver_and_kakao(audit_page):  # noqa: F811
    page, _, _ = audit_page
    real_detail(page)
    menu = page.locator('#plan-detail .route-directions').first
    assert menu.locator('summary').inner_text() == '길찾기 ▾'
    menu.locator('summary').click()
    naver, kakao = menu.locator('.route-directions-link'), menu.locator('.route-directions-kakao')
    assert naver.is_visible() and kakao.is_visible()
    assert naver.get_attribute('href').startswith('https://map.naver.com/p/directions/')
    href = kakao.get_attribute('href')
    leg = page.evaluate("new URL(selected.legs[0].link).searchParams.toString()")
    assert href.startswith('https://map.kakao.com/link/from/') and '/to/' in href, href
    lat = page.evaluate("new URL(selected.legs[0].link).searchParams.get('dlat')")
    assert lat and lat in href, (href, leg)
    assert kakao.get_attribute('target') == '_blank' and 'noopener' in kakao.get_attribute('rel')
    assert page.locator('#plan-detail .route-directions').count() == page.evaluate('selected.legs.filter(l=>l.link).length')


def test_results_head_has_one_short_visit_note(audit_page):  # noqa: F811
    page, _, _ = audit_page
    real_detail(page)
    note = page.locator('.results-area .visit-check-note')
    assert note.is_visible() and note.inner_text() == '방문 전 각 장소의 「네이버 지도 보기」에서 오늘 영업시간을 확인해 주세요.'


def test_kakao_itinerary_copy(audit_page):  # noqa: F811
    page, _, _ = audit_page
    real_detail(page)
    text = page.evaluate("kakaoItineraryText(selected,'https://example.test/shared#tok')")
    lines = text.split('\n')
    assert lines[0].startswith('[데이트메이트] ') and lines[0].endswith('데이트 코스')
    names = page.evaluate('selected.places.map(p=>p.name)')
    arrivals = page.evaluate('selected.timeline.map(t=>t.arrival)')
    for name, arrival in zip(names, arrivals):
        assert f'{arrival} {name}' in lines
    assert any(line.startswith('  ↓ ') for line in lines)
    assert any(line.startswith('예상 비용 ') for line in lines)
    assert 'https://example.test/shared#tok' in text and lines[-1] == '영업시간은 방문 전 네이버 지도에서 확인해 주세요.'
    # 단추: 공유 줄 맨 앞, 누르면 링크를 만들어 함께 복사한다.
    page.evaluate("Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async t=>{window.copied=t;}}})")
    actions = page.locator('#plan-detail .share-actions')
    assert actions.locator('button').first.inner_text() == '카톡용 일정·링크 복사'
    actions.get_by_role('button', name='카톡용 일정·링크 복사').click()
    page.wait_for_function('!!window.copied')
    copied = page.evaluate('window.copied')
    assert '/shared#' in copied and names[0] in copied


@pytest.mark.parametrize('width', [375, 1280])
def test_result_layout_fits(audit_page, width):  # noqa: F811
    page, _, _ = audit_page
    page.set_viewport_size({'width': width, 'height': 900})
    real_detail(page)
    page.locator('#plan-detail .route-directions summary').first.click()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
