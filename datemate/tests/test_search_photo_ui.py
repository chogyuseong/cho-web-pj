"""장소 사진 칸의 '검색 사진'과 사진이 없을 때의 네이버 지도 링크(2026-11-19 사용자 결정, static/place-photos.js).

- 엄격한 이미지 검색 사진(kind image_search, app/image_search.strict_place_images)은 출처 줄이 '네이버 검색결과 · 검색 사진 · 원본 · 검색'이다.
- 사진이 하나도 없거나 모든 후보가 깨지면 빈 사진 칸·깨진 그림 대신 '네이버 지도에서 사진 보기' 링크(app.js placeMapLink 와 같은 주소)를 둔다.
외부 API 는 부르지 않는다. /media 응답과 사진 서버는 page.route 로 흉내 낸다.
"""
from test_functional_audit import audit_page  # noqa: F401  (audit_page 는 fixture)
from test_results_extras_ui import no_overflow, wide_png

PLACE = {'id': 'search-photo-test', 'name': '엄격 검색 식당', 'category': '카페·미식', 'address': '서울 중구 다산로 149'}
MAP_URL = 'https://map.naver.com/p/search/%EC%97%84%EA%B2%A9'


def mount(page, media):
    png = wide_png(800, 600)
    page.route('https://photos.example.test/**', lambda route: route.fulfill(body=png, content_type='image/png')
               if route.request.url.endswith('/ok.png') else route.fulfill(status=404, body=b''))

    def handle(route):
        reviews = 'fallback=reviews' in route.request.url
        route.fulfill(json={'photos': [], 'status': 'not_found', 'map_url': MAP_URL} if reviews else media)

    page.route('**/api/places/*/media?*', handle)
    page.route('**/api/places/*/blogs?*', lambda route: route.fulfill(json={'posts': [], 'message': '없음'}))
    page.evaluate("""p=>{const holder=document.createElement('section');holder.id='search-photo-holder';
      holder.append(placePhotoPanel(p,'real',false,true));document.querySelector('main').prepend(holder);
      holder.scrollIntoView({block:'start',behavior:'instant'});}""", PLACE)


def search_photo(name):
    url = f'https://photos.example.test/{name}.png'
    return {'id': 'image-search-' + name, 'kind': 'image_search', 'source_label': '검색 사진', 'title': '엄격 검색 식당 중구 다산로',
            'image_url': url, 'url': url, 'source': url, 'search_url': 'https://search.naver.com/search.naver?where=image&query=x',
            'checked_at': '2026-11-19T00:00:00+00:00'}


def test_search_photo_is_labelled_with_its_source(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 900})
    mount(page, {'status': 'available', 'photos': [search_photo('ok')], 'map_url': MAP_URL})
    page.wait_for_function("document.querySelector('#search-photo-holder .place-photo img')?.naturalWidth>0")
    caption = page.locator('#search-photo-holder .place-photo figcaption')
    # 2026-11-20: 네이버 검색 API 특약 2.1 — 네이버 검색결과임을 앞에 밝힌다.
    assert caption.inner_text() == '네이버 검색결과 · 검색 사진 · 원본 · 검색'
    original = caption.locator('a').first
    assert original.get_attribute('href') == 'https://photos.example.test/ok.png'
    assert original.get_attribute('aria-label') == '사진 원본 (검색 사진)'
    kind = page.locator('#search-photo-holder .photo-kind')
    assert kind.text_content() == '사진 구분: 검색 사진'
    assert no_overflow(page)


def test_no_photo_shows_the_naver_map_link_instead_of_an_empty_box(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 320, 'height': 900})
    mount(page, {'status': 'not_found', 'photos': [], 'map_url': MAP_URL, 'message': '가게 이름과 동네가 함께 확인되는 사진을 찾지 못했어요.'})
    link = page.locator('#search-photo-holder .photo-map-link')
    link.wait_for()
    # 다른 지도 링크와 같은 주소(app.js placeMapLink: 가게 이름 + 도로명 주소 검색).
    assert link.inner_text() == '네이버 지도에서 사진 보기 ↗'
    assert link.get_attribute('href') == page.evaluate('p=>placeMapUrl(p)', PLACE)
    assert link.get_attribute('href').startswith('https://map.naver.com/p/search/')
    assert page.locator('#search-photo-holder img').count() == 0
    assert no_overflow(page)


def test_all_broken_candidates_leave_a_map_link_not_a_broken_image(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 900})
    mount(page, {'status': 'available', 'photos': [search_photo('broken')], 'map_url': MAP_URL})
    link = page.locator('#search-photo-holder .photo-map-link')
    link.wait_for(timeout=30000)
    assert link.get_attribute('href') == page.evaluate('p=>placeMapUrl(p)', PLACE)
    # 깨진 그림은 남기지 않는다(사진 칸의 img 가 사라지고 안내 글 + 지도 링크).
    assert page.locator('#search-photo-holder .place-photo img').count() == 0
    assert '현재 표시할 수 있는 장소 사진이 없어요.' in page.locator('#search-photo-holder').inner_text()
