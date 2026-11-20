"""사진이 없는 장소의 사진 칸(static/place-photos.js). 2026-11-20 부터 네이버 이미지 검색 사진('검색 사진')은 쓰지 않는다.

- 사진이 하나도 없거나 모든 후보가 깨지면 빈 사진 칸·깨진 그림 대신 '네이버 지도에서 사진 보기' 링크(app.js placeMapLink 와 같은 주소)를 둔다.
- 서버가 준 까닭 한 줄('네이버 검색 결과에서 사진을 골라 쓰지 않아요')이 함께 보인다.
- 화면 코드에 '검색 사진' 표기가 남아 있지 않다.
외부 API 는 부르지 않는다. /media 응답과 사진 서버는 page.route 로 흉내 낸다.
"""
from pathlib import Path

from test_functional_audit import audit_page  # noqa: F401  (audit_page 는 fixture)
from test_results_extras_ui import no_overflow, wide_png

PLACE = {'id': 'no-photo-test', 'name': '사진 없는 식당', 'category': '카페·미식', 'address': '서울 중구 다산로 149'}
MAP_URL = 'https://map.naver.com/p/search/%EC%82%AC%EC%A7%84'
MESSAGE = '등록 사진이나 한국관광공사 사진이 없는 곳이에요. 네이버 검색 결과에서 사진을 골라 쓰지 않아요. 네이버 지도에서 사진을 확인해 주세요.'
STATIC = Path(__file__).resolve().parents[1] / 'static'


def mount(page, media):
    png = wide_png(800, 600)
    page.route('https://photos.example.test/**', lambda route: route.fulfill(body=png, content_type='image/png')
               if route.request.url.endswith('/ok.png') else route.fulfill(status=404, body=b''))

    def handle(route):
        reviews = 'fallback=reviews' in route.request.url
        route.fulfill(json={'photos': [], 'status': 'not_found', 'map_url': MAP_URL} if reviews else media)

    page.route('**/api/places/*/media?*', handle)
    page.route('**/api/places/*/blogs?*', lambda route: route.fulfill(json={'posts': [], 'message': '없음'}))
    page.evaluate("""p=>{const holder=document.createElement('section');holder.id='no-photo-holder';
      holder.append(placePhotoPanel(p,'real',false,true));document.querySelector('main').prepend(holder);
      holder.scrollIntoView({block:'start',behavior:'instant'});}""", PLACE)


def test_search_photo_wording_is_gone_from_the_screens():
    for name in ('place-photos.js', 'leisure.js', 'popups.js', 'place-dialog.js', 'meal-suggestions.js'):
        text = (STATIC / name).read_text(encoding='utf-8')
        # 주석의 설명('검색 사진'은 없앴다)은 남아도 된다. 사진 종류 분기와 출처 줄 표기('검색 사진 · 원본')가 없어야 한다.
        assert 'image_search' not in text and 'search_result' not in text and '검색 사진 ·' not in text, name


def test_no_photo_shows_the_naver_map_link_and_the_reason(audit_page):
    page, base, errors = audit_page
    for width in (320, 390, 1280):
        page.set_viewport_size({'width': width, 'height': 900})
        page.evaluate("document.getElementById('no-photo-holder')?.remove()")
        mount(page, {'status': 'not_found', 'photos': [], 'map_url': MAP_URL, 'message': MESSAGE})
        link = page.locator('#no-photo-holder .photo-map-link')
        link.wait_for()
        # 다른 지도 링크와 같은 주소(app.js placeMapLink: 가게 이름 + 도로명 주소 검색).
        assert link.inner_text() == '네이버 지도에서 사진 보기 ↗'
        assert link.get_attribute('href') == page.evaluate('p=>placeMapUrl(p)', PLACE)
        assert link.get_attribute('href').startswith('https://map.naver.com/p/search/')
        assert page.locator('#no-photo-holder img').count() == 0
        assert '네이버 검색 결과에서 사진을 골라 쓰지 않아요' in page.locator('#no-photo-holder .photo-status').first.inner_text()
        assert no_overflow(page), width


def test_all_broken_candidates_leave_a_map_link_not_a_broken_image(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 900})
    url = 'https://photos.example.test/broken.png'
    photo = {'id': 'registered-broken', 'kind': 'tourapi', 'title': '사진 없는 식당 장소 사진', 'image_url': url, 'url': url, 'source': url,
             'author': '한국관광공사', 'license': '공공누리 제1유형', 'license_url': 'https://www.kogl.or.kr/info/licenseType1.do',
             'checked_at': '2026-11-20'}
    mount(page, {'status': 'available', 'photos': [photo], 'map_url': MAP_URL})
    link = page.locator('#no-photo-holder .photo-map-link')
    link.wait_for(timeout=30000)
    assert link.get_attribute('href') == page.evaluate('p=>placeMapUrl(p)', PLACE)
    # 깨진 그림은 남기지 않는다(사진 칸의 img 가 사라지고 안내 글 + 지도 링크).
    assert page.locator('#no-photo-holder .place-photo img').count() == 0
    assert '현재 표시할 수 있는 장소 사진이 없어요.' in page.locator('#no-photo-holder').inner_text()
