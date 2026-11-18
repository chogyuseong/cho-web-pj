"""카드 사진은 줄인 사진(thumb_url)을 먼저, 크게 보기는 원본(static/place-photos.js loadSafePhoto thumb 옵션, 2026-11-18).

가짜 /media 가 사진마다 thumb_url 을 준다(서버에서는 app/photo_thumb.with_thumbs). 원본과 줄인 사진 요청을 따로 센다.
확인: 카드는 줄인 사진만 받고 원본은 받지 않는다 / 크게 보기에서 원본을 받는다 / 줄인 사진이 404 면 원본으로 대체돼 사진이 보인다."""
from test_functional_audit import audit_page  # noqa: F401
from test_results_extras_ui import wide_png

CARD_IMG = "#catalog .place-card .place-photo img"


def mount(page, base, thumb_status=200):
    png = wide_png()
    requests = dict(original=[], thumb=[])
    photos = [{'kind': 'place_public', 'source_label': '업체 등록 사진', 'title': f'사진 {i + 1}', 'source': base,
               'image_url': f'{base}/original-{i}.png', 'url': f'{base}/original-{i}.png', 'search_url': base,
               'thumb_url': f'/photo-thumb?u=original-{i}&w=960', 'checked_at': '2026-11-18'} for i in range(2)]

    def original(route):
        requests['original'].append(route.request.url)
        route.fulfill(body=png, content_type='image/png')

    def thumb(route):
        requests['thumb'].append(route.request.url)
        if thumb_status == 200:
            route.fulfill(body=png, content_type='image/webp')
        else:
            route.fulfill(status=thumb_status, body='Not Found')

    page.route('**/original-*.png', original)
    page.route('**/photo-thumb?*', thumb)
    page.route('**/api/places/*/media?*', lambda route: route.fulfill(json={'status': 'available', 'photos': photos}))
    page.route('**/api/explore?*', lambda route: route.fulfill(json={
        'places': [{'id': 'thumb-1', 'name': '줄인 사진 카페', 'category': '카페·미식', 'address': '서울 성동구 성수동', 'region': '서울'}],
        'total': 1, 'has_more': False, 'region': '서울', 'activity': '', 'message': ''}))
    page.get_by_role('button', name='장소 둘러보기', exact=True).click()
    return requests


def test_card_uses_the_small_photo_and_the_viewer_the_original(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 900})
    requests = mount(page, base)
    page.wait_for_function(f"[...document.querySelectorAll('{CARD_IMG}')].some(i=>!i.hidden&&i.naturalWidth>0)")
    assert '/photo-thumb?u=original-0&w=960' in page.locator(CARD_IMG).first.get_attribute('src')
    page.wait_for_timeout(500)
    assert requests['original'] == [] and len(requests['thumb']) >= 1, requests
    # 크게 보기는 원본.
    page.locator('#catalog .place-card .photo-open').first.click()
    page.wait_for_function("(()=>{const i=document.querySelector('#photo-viewer img');return i&&!i.hidden&&i.naturalWidth>0})()")
    assert page.locator('#photo-viewer img').get_attribute('src').endswith('/original-0.png')
    assert any(url.endswith('/original-0.png') for url in requests['original'])
    assert not errors, errors


def test_card_falls_back_to_the_original_when_the_small_photo_fails(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 900})
    requests = mount(page, base, thumb_status=404)
    page.wait_for_function(f"[...document.querySelectorAll('{CARD_IMG}')].some(i=>!i.hidden&&i.naturalWidth>0)")
    assert page.locator(CARD_IMG).first.get_attribute('src').endswith('/original-0.png')
    assert requests['thumb'] and requests['original']
    # 줄인 사진 404 는 화면 오류가 아니다(원본으로 대체).
    assert not [e for e in errors if 'photo-thumb' not in e], errors
