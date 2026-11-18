"""휴대폰 식당 카드 사진 배치(2026-11-18 사용자 신고: 가격표 옆 사진이 너무 좁게 나옴).

760px 이하에서는 식당 카드(meal-suggestions.js restaurantCard, .meal-card-with-photo)를 한 칸으로 쌓는다:
정보(이름·주소·메뉴 가격표) → 사진(카드 폭, 높이 200px) → 단추. 전에는 정보 옆 사진 칸이 100px 이었다.
761px 이상(데스크톱)은 전처럼 정보 옆에 사진 칸(minmax(165px,38%))을 둔다. 규칙은 static/selle.css.
외부 API 는 부르지 않는다. 사진·메뉴·블로그 응답은 가로채 흉내 낸다."""
import pytest

from test_functional_audit import audit_page  # noqa: F401  (audit_page 는 fixture)
from test_results_extras_ui import no_overflow, wide_png

FOOD = {'id': 'meal-photo-test', 'name': '사진 배치 시험 식당', 'cuisine': '한식', 'address': '서울 성동구 성수동 1',
        'lat': 37.5445, 'lon': 127.056}
# 실제 운영에서 사용자가 본 출처 줄과 같은 종류(place_public, 긴 출처 이름)로 둔다.
PHOTO = {'kind': 'place_public', 'source_label': '업체 연결 공개 사진 · 등록 주체 미확인', 'title': FOOD['name'] + ' 장소 사진',
         'checked_at': '2026-11-18T00:00:00+00:00'}
MENU = {'status': 'available', 'items': [{'name': '된장찌개 정식', 'display_price': '12,000원'},
                                         {'name': '제육볶음', 'display_price': '13,000원'},
                                         {'name': '고등어구이 정식', 'display_price': '14,000원'}],
        'checked_at': '2026-11-18', 'source_url': 'https://example.invalid/menu', 'source_label': '네이버 플레이스'}
# 카드 안 요소 위치(문서 기준 px)와 사진·출처 크기.
LAYOUT = """()=>{const card=document.querySelector('.meal-card-with-photo'),box=e=>{const r=e.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top+scrollY,bottom:r.bottom+scrollY,width:r.width,height:r.height};};
  const img=card.querySelector('.meal-photo .place-photo img');
  return {card:box(card),info:box(card.querySelector('.meal-info')),menu:box(card.querySelector('.restaurant-menu')),
    photo:box(card.querySelector('.meal-photo')),img:img&&box(img),loaded:!!img&&img.complete&&img.naturalWidth>0,
    caption:box(card.querySelector('.meal-photo figcaption')),actions:box(card.querySelector('.meal-actions'))};}"""


def mount(page, base):
    png = wide_png(800, 600)
    photo = dict(PHOTO, source=base + '/meal-wide.png', image_url=base + '/meal-wide.png', search_url=base)
    page.route('**/meal-wide.png', lambda route: route.fulfill(body=png, content_type='image/png'))
    page.route('**/api/places/*/media?*', lambda route: route.fulfill(json={'status': 'available', 'photos': [photo]}))
    page.route('**/api/places/*/menu?*', lambda route: route.fulfill(json=MENU))
    page.route('**/api/places/*/blogs?*', lambda route: route.fulfill(json={'posts': [], 'message': '없음'}))
    page.goto(base + '/')
    page.wait_for_function("typeof restaurantCard==='function'")
    # 결과 화면의 식당 카드와 같은 자리(main 안)에 넣어 결과 화면 CSS(readability.css 의 main … 규칙)도 받게 한다.
    page.evaluate("""food=>{const holder=document.createElement('section');holder.className='meal-suggestions';
      holder.append(restaurantCard(food,{badge:'우선 추천'}));document.querySelector('main').prepend(holder);
      holder.scrollIntoView({block:'start',behavior:'instant'});}""", FOOD)
    # 사진은 화면 근처에서 받는다(place-photos.js). src 가 아직 없는 <img> 도 complete=true 라서 naturalWidth 로 실제로 받았는지 본다.
    page.wait_for_function("document.querySelector('.meal-card-with-photo .menu-price-row')&&document.querySelector('.meal-card-with-photo .meal-photo img')?.naturalWidth>0")


@pytest.mark.parametrize('width', [390, 320])
def test_phone_meal_card_puts_a_full_width_photo_under_the_price_list(audit_page, width):
    page, base, errors = audit_page
    page.set_viewport_size({'width': width, 'height': 900})
    mount(page, base)
    layout = page.evaluate(LAYOUT)
    assert layout['loaded'], layout
    info, photo, img, card = layout['info'], layout['photo'], layout['img'], layout['card']
    # 한 칸: 사진은 정보(가격표 포함) 아래, 단추 위.
    assert photo['top'] >= info['bottom'] and layout['menu']['bottom'] <= photo['top'], layout
    assert layout['actions']['top'] >= layout['caption']['bottom'], layout
    # 사진은 정보 칸과 같은 폭(카드 안쪽 폭: 390px 화면에서 304px)이고, 높이 200px. 전에는 100×100 이었다.
    assert abs(photo['width'] - info['width']) <= 1 and abs(img['width'] - info['width']) <= 3, layout
    assert img['height'] == 200, layout
    # 출처 줄은 짧은 표기 한 줄(전에는 '네이버 사진 자료 · 업체 연결 공개 사진 · 등록 주체 미확인 · 검색 결과'가 100px 칸에 여러 줄로 쌓임).
    caption = page.locator('.meal-photo figcaption')
    assert caption.inner_text() == '네이버 공개 사진 · 원본 · 검색'
    caption_lines = page.evaluate("""()=>{const c=document.querySelector('.meal-photo figcaption'),line=parseFloat(getComputedStyle(c).lineHeight)||20;
      return c.getBoundingClientRect().height/line;}""")
    assert caption_lines <= 1.2, (caption_lines, layout)
    # 사진 구분은 '사진 정보' 접기 안 첫 줄로 옮겼다(접혀 있어 처음에는 보이지 않음).
    fold = page.locator('.meal-photo details.photo-copy-fold')
    kind = fold.locator('.photo-kind')
    assert not kind.is_visible() and kind.text_content() == '사진 구분: 업체 연결 공개 사진 · 등록 주체 미확인'
    fold.locator('summary').click()
    assert kind.is_visible()
    # 머리 글자에는 사진 구분을 되풀이하지 않는다.
    assert '등록 주체' not in fold.locator('.photo-eyebrow').text_content()
    assert card['right'] <= width and no_overflow(page), layout
    assert not errors, errors


def test_desktop_meal_card_keeps_the_photo_beside_the_info(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 1440, 'height': 900})
    mount(page, base)
    layout = page.evaluate(LAYOUT)
    info, photo = layout['info'], layout['photo']
    # 데스크톱은 그대로 두 칸: 사진이 정보 오른쪽, 위쪽이 나란하다(사진 높이 180px).
    assert photo['left'] >= info['right'] and abs(photo['top'] - info['top']) < 40, layout
    assert layout['img']['height'] == 180, layout
    assert not errors, errors
