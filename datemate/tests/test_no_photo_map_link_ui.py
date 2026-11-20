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


# ---------------------------------------------------------------- 사진 칸 정렬(2026-11-20 사용자 스크린샷)

FAILED = '한국관광공사 사진 자료에 지금 연결하지 못했어요. 잠시 뒤 다시 불러오거나 네이버 지도에서 사진을 확인해 주세요.'
TOUR_PHOTO = {'kind': 'tourapi', 'title': '장소 사진', 'author': '한국관광공사', 'license': '공공누리 제3유형(변경 금지)',
              'license_url': 'https://www.kogl.or.kr/info/licenseType3.do', 'source': 'https://korean.visitkorea.or.kr/detail/ms_detail.do?cotid=1',
              'image_url': 'https://photos.example.test/ok.png', 'url': 'https://photos.example.test/ok.png', 'checked_at': '2026-11-20'}
LEFTS = """root=>{const box=root.querySelector('.photo-empty-body'),left=e=>e?Math.round(e.getBoundingClientRect().left*10)/10:null;
  const retry=box.querySelector('.photo-retry'),panel=root.querySelector('.place-photo-panel').getBoundingClientRect();
  return {text:left(box.querySelector('.photo-status')),map:left(box.querySelector('.photo-map-link')),retry:left(retry),name:left(root.querySelector('.photo-empty-card strong')),
    panel:Math.round(panel.left*10)/10,panelWidth:panel.width,retryWidth:retry?retry.getBoundingClientRect().width:null};}"""


def results_with(page, base, kinds):
    """결과 화면을 실제 장소 코스처럼 다시 그리고, 장소 순서대로 kinds('photo'·'none'·'failed'·'error')의 /media 응답을 준다."""
    from test_functional_audit import generate, wait_for_selected_detail

    png = wide_png(800, 600)
    page.route('https://photos.example.test/**', lambda route: route.fulfill(body=png, content_type='image/png'))
    page.route('**/api/places/*/blogs?*', lambda route: route.fulfill(json={'posts': [], 'message': '없음'}))
    generate(page)
    ids = page.evaluate('selected.places.map(p=>p.id)')
    answers = {'photo': {'status': 'available', 'photos': [TOUR_PHOTO], 'map_url': MAP_URL, 'photo_retry': False},
               'none': {'status': 'not_found', 'photos': [], 'map_url': MAP_URL, 'message': MESSAGE, 'photo_retry': False},
               'failed': {'status': 'not_found', 'photos': [], 'map_url': MAP_URL, 'message': FAILED, 'photo_retry': True}}

    def media(route):
        pid = route.request.url.split('/api/places/')[1].split('/media')[0]
        kind = dict(zip(ids, kinds)).get(pid, 'photo')
        if 'fallback=reviews' in route.request.url:
            return route.fulfill(json={'photos': [], 'status': 'not_found', 'map_url': MAP_URL})
        return route.fulfill(status=500, json={'detail': 'x'}) if kind == 'error' else route.fulfill(json=answers[kind])

    page.route('**/api/places/*/media?*', media)
    page.evaluate("selected.conditions.mode='real';plans.forEach(p=>{p.conditions.mode='real';p.places.forEach(x=>x.demo=false)});renderResults();renderDetail()")
    wait_for_selected_detail(page)
    page.evaluate("document.querySelectorAll('details.plan-photo-details').forEach(d=>d.open=true)")
    return ids


def test_retry_button_only_when_trying_again_can_help(audit_page):
    """자료에 사진이 없다고 확정되면(photo_retry 없음·false) '사진 다시 불러오기'를 숨기고, 관광공사 호출 실패(photo_retry)·요청 실패에만 둔다."""
    page, base, errors = audit_page
    page.set_viewport_size({'width': 1280, 'height': 900})
    results_with(page, base, ['none', 'failed', 'error'])
    items = page.locator('.plan-card.selected .plan-photo-item')
    page.wait_for_function("document.querySelectorAll('.plan-card.selected .plan-photo-item .photo-empty-body').length===3")
    retry = lambda index: items.nth(index).get_by_role('button', name='사진 다시 불러오기', exact=True)
    assert retry(0).count() == 0 and items.nth(0).locator('.photo-map-link').count() == 1
    assert retry(1).count() == 1 and '지금 연결하지 못했어요' in items.nth(1).inner_text()
    assert retry(2).count() == 1 and '사진 정보를 불러오지 못했습니다' in items.nth(2).inner_text()


def test_no_photo_text_link_and_button_share_one_left_edge_and_one_width_rule(audit_page):
    """안내 글·'네이버 지도에서 사진 보기'·'사진 다시 불러오기'가 같은 왼쪽 선에 서고(전에는 링크·단추만 테두리에 붙음),
    단추는 3칸 목록에서도 일정 카드에서도 글자 폭이다(전에는 일정 카드에서 전체 폭)."""
    page, base, errors = audit_page
    for width in (390, 1280):
        page.set_viewport_size({'width': width, 'height': 900})
        page.goto(base, wait_until='networkidle')
        page.wait_for_function("typeof statusData!=='undefined'&&!!statusData&&document.querySelector('.simple-plan-form')")
        results_with(page, base, ['failed', 'failed', 'failed'])
        for selector in ('.plan-card.selected .plan-photo-item', '#plan-detail .timeline-card'):
            root = page.locator(selector).first
            root.locator('.place-photo-panel').scroll_into_view_if_needed()
            root.locator('.photo-retry').wait_for()
            seen = root.evaluate(LEFTS)
            assert seen['text'] == seen['map'] == seen['retry'], (width, selector, seen)
            assert seen['retryWidth'] < seen['panelWidth'] * 0.8 and seen['retryWidth'] < 220, (width, selector, seen)
            if 'plan-photo-item' in selector:
                # 사진이 테두리에 붙는 칸: 테두리에서 12px 안쪽, 회색 이름표의 이름과도 같은 선.
                assert seen['text'] - seen['panel'] >= 12 and seen['name'] == seen['text'], (width, seen)
        assert no_overflow(page), width
    assert not errors, errors


def test_credit_line_has_padding_and_breaks_only_between_its_parts(audit_page):
    """출처 줄('사진: 한국관광공사 · 공공누리 제3유형(변경 금지) · 사진 원문')과 '사진 정보'가 카드 테두리에 붙지 않고, '(변경 금지)'만 떨어지지 않는다."""
    page, base, errors = audit_page
    for width in (390, 1280):
        page.set_viewport_size({'width': width, 'height': 900})
        page.goto(base, wait_until='networkidle')
        page.wait_for_function("typeof statusData!=='undefined'&&!!statusData&&document.querySelector('.simple-plan-form')")
        results_with(page, base, ['photo', 'photo', 'photo'])
        item = page.locator('.plan-card.selected .plan-photo-item').first
        item.locator('figcaption .photo-credit-part').first.wait_for()
        assert item.locator('figcaption').inner_text().replace('\n', ' ') == '사진: 한국관광공사 · 공공누리 제3유형(변경 금지) · 사진 원문'
        seen = item.evaluate("""root=>{const panel=root.querySelector('.place-photo-panel').getBoundingClientRect(),left=e=>e.getBoundingClientRect().left-panel.left;
          return {parts:[...root.querySelectorAll('.photo-credit-part')].map(p=>({left:left(p),lines:Math.round(p.getBoundingClientRect().height/parseFloat(getComputedStyle(p).lineHeight))})),
            fold:left(root.querySelector('.photo-copy-fold>summary'))};}""")
        # 뜻 단위마다 한 줄(가운데에서 끊기지 않음), 어느 단위도 테두리에 붙지 않는다.
        assert all(part['lines'] == 1 and part['left'] >= 12 for part in seen['parts']) and len(seen['parts']) == 3, (width, seen)
        assert seen['fold'] >= 12, (width, seen)
        assert no_overflow(page), width
    assert not errors, errors


def test_blog_boxes_line_up_across_the_three_photo_columns(audit_page):
    """결과 화면 '장소 사진 3곳': 사진 있는 칸과 없는 칸의 높이가 달라도 '블로그 후기 보기' 상자가 같은 줄에 놓인다."""
    page, base, errors = audit_page
    page.set_viewport_size({'width': 1280, 'height': 900})
    results_with(page, base, ['photo', 'photo', 'failed'])
    page.wait_for_function("document.querySelectorAll('.plan-card.selected .plan-photo-item .photo-credit-part').length>=6&&document.querySelector('.plan-card.selected .plan-photo-item .photo-retry')")
    seen = page.evaluate("""()=>[...document.querySelectorAll('.plan-card.selected .plan-photo-item')].map(item=>{const y=e=>Math.round(e.getBoundingClientRect().top+scrollY);
      const panel=item.querySelector('.place-photo-panel').getBoundingClientRect();return {blog:y(item.querySelector('.place-blogs')),panelHeight:Math.round(panel.height)};})""")
    assert len(seen) == 3 and len({item['blog'] for item in seen}) == 1, seen
    assert len({item['panelHeight'] for item in seen}) == 1, seen
    assert not errors, errors
