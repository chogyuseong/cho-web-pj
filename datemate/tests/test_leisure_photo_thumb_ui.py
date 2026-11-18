"""레저 사진 격자도 줄인 사진(thumb_url, /photo-thumb)을 먼저, 크게 보기 링크는 원본(static/leisure.js, 2026-11-18).

가짜 /media 가 사진마다 thumb_url 을 준다(서버에서는 app/photo_thumb.with_thumbs). 원본과 줄인 사진 요청을 따로 센다.
확인: 격자는 줄인 사진만 받고 원본은 받지 않는다 / 사진을 감싼 '크게 보기' 링크는 원본 / 출처 줄은 그대로 /
줄인 사진이 404 면 원본으로 대체돼 사진 두 장이 보인다."""
import pytest

from test_functional_audit import audit_page, generate  # noqa: F401
from test_results_extras_ui import wide_png

GRID_IMG = '.leisure-photo-grid img'
SHOWN = f"[...document.querySelectorAll('{GRID_IMG}')].filter(i=>!i.hidden&&i.complete&&i.naturalWidth>0).length===2"


def mount(page, base, thumb_status=200):
    png = wide_png()
    requests = dict(original=[], thumb=[])
    generate(page)
    sport = dict(page.evaluate('selected.places[0]'), id='thumb-sport', name='줄인 사진 클라이밍', demo=False, category='레저·활동')
    page.route('**/leisure-options', lambda route: route.fulfill(json={
        'message': '주변 레저', 'options': [{'place': sport, 'distance_m': 100, 'delta': {'minutes': 10, 'cost': [0, 10000]}}]}))
    photos = [{'kind': 'place_public', 'source_label': '업체 등록 사진', 'title': f'사진 {i}', 'source': base,
               'image_url': f'{base}/leisure-original-{i}.png', 'url': f'{base}/leisure-original-{i}.png', 'search_url': base,
               'thumb_url': f'/photo-thumb?u=leisure-original-{i}&w=960', 'checked_at': '2026-11-18'} for i in range(2)]
    page.route('**/api/places/thumb-sport/media?*', lambda route: route.fulfill(json={'status': 'available', 'photos': photos}))

    def original(route):
        requests['original'].append(route.request.url)
        route.fulfill(body=png, content_type='image/png')

    def thumb(route):
        requests['thumb'].append(route.request.url)
        if thumb_status == 200:
            route.fulfill(body=png, content_type='image/webp')
        else:
            route.fulfill(status=thumb_status, body='Not Found')

    page.route('**/leisure-original-*.png', original)
    page.route('**/photo-thumb?*', thumb)
    page.evaluate("selected.conditions.mode='real';renderResults()")
    panel = page.locator('.leisure-results').first
    panel.locator('summary').click()
    panel.locator('.leisure-photo-panel').scroll_into_view_if_needed()
    page.wait_for_function(SHOWN)
    return panel, requests


@pytest.mark.parametrize('width', [1440, 390])
def test_leisure_grid_uses_small_photos_and_links_the_originals(audit_page, width):
    page, base, errors = audit_page
    page.set_viewport_size({'width': width, 'height': 1000})
    panel, requests = mount(page, base)
    grid = panel.locator('.leisure-photo-grid')
    sources = grid.locator('img').evaluate_all('els=>els.map(el=>el.src)')
    assert sorted(sources) == [f'{base}/photo-thumb?u=leisure-original-{i}&w=960' for i in range(2)], sources
    page.wait_for_timeout(500)
    assert requests['original'] == [] and len(requests['thumb']) >= 2, requests
    # 사진을 감싼 '크게 보기' 링크는 원본(새 창). 출처 줄은 전과 같다.
    links = grid.locator('figure>a')
    assert sorted(links.evaluate_all('els=>els.map(el=>el.href)')) == [f'{base}/leisure-original-{i}.png' for i in range(2)]
    assert links.first.get_attribute('target') == '_blank'
    assert '크게 보기' in links.first.get_attribute('aria-label')
    assert grid.get_by_role('link', name='업체 등록 사진 ↗', exact=True).count() == 2
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
    assert not errors, errors


def test_leisure_grid_falls_back_to_the_originals_when_small_photos_fail(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 1000})
    panel, requests = mount(page, base, thumb_status=404)
    grid = panel.locator('.leisure-photo-grid')
    sources = grid.locator('img').evaluate_all('els=>els.map(el=>el.src)')
    assert sorted(sources) == [f'{base}/leisure-original-{i}.png' for i in range(2)], sources
    assert len(requests['thumb']) >= 2 and len(requests['original']) >= 2, requests
    assert sorted(grid.locator('figure>a').evaluate_all('els=>els.map(el=>el.href)')) == sources
    assert panel.locator('.leisure-photo-empty').count() == 0
    # 줄인 사진 404 는 화면 오류가 아니다(원본으로 대체).
    assert not [e for e in errors if 'photo-thumb' not in e], errors
