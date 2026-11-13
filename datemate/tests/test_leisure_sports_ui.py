"""레저 패널: 실내·실외 구분, 종목 이름·거리, 종목 필터, 실외 안내, 그 자리만 교체(실제 브라우저)."""
import re
import pytest
from test_functional_audit import audit_page, generate


def leisure_rows(page, monkeypatch):
    from app.catalog import places as catalog_places
    anchor = page.evaluate('selected.places[0]')

    def row(pid, name, key, category, km):
        return dict(anchor, id=pid, name=name, category='레저·활동', themes=['레저·활동'], tags=[key, category],
                    description=category, lat=anchor['lat'] + km / 111.0)
    rows = [row('ui-bowling', '동선 볼링센터', 'bowling', '스포츠,오락>볼링장', .3),
            row('ui-billiards', '동선 당구클럽', 'billiards', '스포츠,오락>당구장', .4),
            row('ui-tennis', '동선 테니스장', 'tennis', '스포츠,오락>테니스장', 1.2)]
    monkeypatch.setattr('app.catalog.places', lambda *args, **kwargs: [*catalog_places(*args, **kwargs), *rows])
    return rows


@pytest.mark.parametrize('width', [360, 430])
def test_leisure_panel_splits_indoor_outdoor_filters_and_replaces_only_that_stop(audit_page, monkeypatch, width):
    page, base, errors = audit_page
    page.set_viewport_size({'width': width, 'height': 900})
    generate(page)
    leisure_rows(page, monkeypatch)
    other = page.evaluate('selected.places[1].id')
    panel = page.locator('.leisure-results').first
    panel.locator('summary').click()
    indoor = panel.locator('.leisure-setting[data-setting=indoor]')
    outdoor = panel.locator('.leisure-setting[data-setting=outdoor]')
    outdoor.locator('.leisure-result-card').filter(has_text='동선 테니스장').wait_for()
    assert indoor.locator('.leisure-result-card').filter(has_text='동선 볼링센터').count() == 1
    assert indoor.locator('.leisure-result-card').filter(has_text='동선 테니스장').count() == 0
    tennis = outdoor.locator('.leisure-result-card').filter(has_text='동선 테니스장')
    assert '테니스 · 실외 (시설에 따라 다름)' in tennis.locator('.leisure-sport-tag').inner_text()
    assert '현재 장소에서 직선 1.2km' in tennis.inner_text()
    bowling = indoor.locator('.leisure-result-card').filter(has_text='동선 볼링센터')
    assert bowling.locator('.leisure-sport-tag').inner_text() == '볼링 · 실내'
    assert re.search(r'현재 장소에서 직선 \d{3}m', bowling.inner_text())
    assert '날씨와 계절에 따라 운영이 달라요. 방문 전 확인해 주세요.' in outdoor.inner_text()
    assert '실외 레저는 반경 5km' in panel.inner_text()
    # 종목 필터: 테니스만 보기 → 실내 구분은 '없어요' 안내, 전체로 되돌리기.
    chips = panel.locator('.leisure-filter button')
    assert chips.count() >= 4
    panel.locator('.leisure-filter button', has_text='테니스').click()
    assert tennis.is_visible()
    assert not indoor.locator('.leisure-result-card').filter(has_text='동선 볼링센터').is_visible()
    assert indoor.locator('.leisure-filter-empty').is_visible()
    assert panel.locator('.leisure-filter button', has_text='테니스').get_attribute('aria-pressed') == 'true'
    panel.locator('.leisure-filter button', has_text='전체').click()
    assert indoor.locator('.leisure-result-card').filter(has_text='동선 볼링센터').is_visible()
    heights = panel.locator('.leisure-filter button, .leisure-result-card button').evaluate_all(
        'els=>els.filter(e=>e.offsetParent).map(e=>e.getBoundingClientRect().height)')
    assert heights and min(heights) >= 44
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    original = page.evaluate('selected.id')
    tennis.get_by_role('button', name='이 레저로 교체', exact=True).click()
    page.wait_for_function('(id)=>selected.id!==id', arg=original)
    assert page.evaluate('selected.places[0].id') == 'ui-tennis'
    assert page.evaluate('selected.places[1].id') == other


def test_leisure_panel_says_how_many_far_outdoor_venues_were_excluded(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 360, 'height': 900})
    generate(page)
    sport = dict(page.evaluate('selected.places[0]'), id='ui-route-bowling', name='응답 볼링장')
    body = {'message': '주변 레저', 'options': [{'place': sport, 'distance_m': 300, 'delta': {'minutes': 5, 'cost': [0, 0]},
            'sport': {'key': 'bowling', 'label': '볼링', 'setting': 'indoor', 'setting_basis': 'default', 'varies': False, 'radius_km': 1.5}}],
            'diagnostics': {'rejected': {'구간 이동 시간 초과': 16},
                            'rejected_by_setting': {'indoor': {'count': 0, 'reasons': {}},
                                                    'outdoor': {'count': 16, 'reasons': {'구간 이동 시간 초과': 16}}}}}
    page.route('**/leisure-options', lambda route: route.fulfill(json=body))
    panel = page.locator('.leisure-results').first
    panel.locator('summary').click()
    outdoor = panel.locator('.leisure-setting[data-setting=outdoor]')
    outdoor.locator('.leisure-rejected').wait_for()
    assert '주변에서 찾지 못했어요.' in outdoor.inner_text()
    assert outdoor.locator('.leisure-rejected').inner_text() == (
        '실외 레저 16곳은 현재 일정 조건 때문에 제외했어요 (구간 이동 시간 초과 16곳). 이동 시간이나 예산을 늘리면 더 볼 수 있어요.')
    assert panel.locator('.leisure-setting[data-setting=indoor] .leisure-rejected').count() == 0
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
