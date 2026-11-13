"""결과·홈 화면 개선: 테마 카드(3), 예산 무관 결과 표시(4), 사진 크게 보기(5), 블로그 후기 패널(7), 식사·카페 이름(8).

외부 API는 부르지 않는다. 사진·블로그·둘러보기 응답은 가로채 흉내 낸다."""
import struct
import zlib

import pytest

from test_functional_audit import audit_page, generate  # noqa: F401  (audit_page 는 fixture)


def wide_png(width=400, height=100):
    """가로로 긴 회색 PNG. 큰 보기에서 자르지 않고 보이는지(비율 유지) 확인한다."""
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    raw = b''.join(b'\x00' + b'\x88' * width for _ in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


def no_overflow(page):
    return page.evaluate('document.documentElement.scrollWidth<=innerWidth')


@pytest.mark.parametrize('width', [390, 1440])
def test_theme_cards_show_theme_first(audit_page, width):
    page, base, errors = audit_page
    page.set_viewport_size({'width': width, 'height': 900})
    section = page.locator('#curation')
    assert section.locator('#curation-title').inner_text() == '테마로 고르는 하루'
    assert '테마를 고르면' in section.locator('.curation-heading p').inner_text()
    cards = section.locator('.curation-card')
    assert cards.count() == 6
    first = cards.first
    # 테마가 먼저, 더 크게. 동네 이름은 보조 정보.
    assert first.evaluate('c=>c.firstElementChild.className') == 'curation-mood'
    sizes = first.evaluate("c=>['.curation-mood','.curation-area'].map(s=>parseFloat(getComputedStyle(c.querySelector(s)).fontSize))")
    assert sizes == [19, 14]
    mood, area = first.locator('.curation-mood').bounding_box(), first.locator('.curation-area').bounding_box()
    assert mood['y'] + mood['height'] <= area['y'] + 1
    lefts = {round(card.bounding_box()['x']) for card in cards.all()}
    assert len(lefts) == (3 if width == 1440 else 1)
    for card in cards.all():
        assert card.evaluate('c=>[...c.children].every(s=>s.scrollWidth<=s.clientWidth+1)')
    assert no_overflow(page)
    # 조건 화면 동네 칩은 그대로 동네 이름(data-preset)을 쓴다.
    assert page.get_by_role('group', name='인기 동네').get_by_role('button').all_inner_texts()[:2] == ['서울 성수', '부산 해운대']
    first.click()
    page.wait_for_function('form.elements.origin_name.value==="서울 성수역 지역 중심"')


def test_budget_unlimited_results_and_place_kinds(audit_page):
    page, base, errors = audit_page
    generate(page)
    detail = page.locator('#plan-detail')
    # 서버가 budget_unlimited 를 싣지 않은 코스는 전처럼 예산 대비 차액을 보여 준다.
    assert '예산 대비 차액' in detail.inner_text()
    page.evaluate("""()=>{
      selected.conditions.budget_unlimited=true;selected.remaining=null;
      selected.condition_checks=[...(selected.condition_checks||[]).filter(c=>c.condition!=='budget'),
        {condition:'budget',label:'예산 무관',state:'info',message:'예산 무관으로 골랐어요. 계산한 비용은 30,000~52,000원이에요.'}];
      selected.places[0].meal=true;selected.places[0].category='카페·미식';
      selected.places[1].meal=false;selected.places[1].category='카페·미식';
      renderResults();renderDetail();
    }""")
    rows = detail.locator('.total-row').all_inner_texts()
    assert any('예산 무관' in row for row in rows) and not any('예산 대비 차액' in row for row in rows)
    assert '미확인' not in ' '.join(row for row in rows if '예산' in row)
    assert '예산 무관' in detail.locator('.execution-grid').inner_text()
    compact = page.evaluate('compactConditionSummary(selected).textContent')
    assert '참고 예산 무관' in compact and '초과' not in compact
    # 참고(info)는 경고 모양이 아니다.
    assert page.evaluate("[...compactConditionSummary(selected).children].find(p=>p.textContent.startsWith('참고')).className") == ''
    # 가격 미리보기도 예산과 비교하지 않는다.
    page.evaluate("form.elements.budget_unlimited.checked=true;updatePricePreview(selected)")
    preview = page.locator('.price-input-preview').text_content()
    assert '예산 무관' in preview and '상한 대비' not in preview
    # 식당은 '식사', 그 밖의 카페·미식은 '카페'.
    activity = page.locator('.option-comparison tbody tr').first.locator('td').nth(2).inner_text()
    assert '식사' in activity and '카페' in activity and '카페·미식' not in activity
    tags = detail.locator('.step-category').all_inner_texts()
    assert tags[0] == '식사' and tags[1] == '카페'


def mount_photo_routes(page, base, count=3):
    png = wide_png()
    photos = [{'kind': 'search_result', 'source_label': '업체 등록 사진', 'title': f'사진 {i + 1}', 'source': f'{base}/wide-{i}.png',
               'image_url': f'{base}/wide-{i}.png', 'search_url': base, 'checked_at': '2026-11-13'} for i in range(count)]
    page.route('**/wide-*.png', lambda route: route.fulfill(body=png, content_type='image/png'))
    page.route('**/api/places/*/media?*', lambda route: route.fulfill(json={'status': 'available', 'photos': photos}))
    page.route('**/api/explore?*', lambda route: route.fulfill(json={
        'places': [{'id': 'viewer-1', 'name': '사진 큰보기 카페', 'category': '카페·미식', 'address': '서울 성동구 성수동', 'region': '서울'}],
        'total': 1, 'has_more': False, 'region': '서울', 'activity': '', 'message': ''}))


@pytest.mark.parametrize('width', [390, 1440])
def test_explore_photo_opens_large_viewer(audit_page, width):
    page, base, errors = audit_page
    page.set_viewport_size({'width': width, 'height': 900})
    mount_photo_routes(page, base)
    page.get_by_role('button', name='장소 둘러보기', exact=True).click()
    card = page.locator('#catalog .place-card').first
    opener = card.get_by_role('button', name='사진 1 사진 크게 보기', exact=True)
    opener.wait_for()
    page.wait_for_function("[...document.querySelectorAll('#catalog .place-photo img')].some(i=>!i.hidden&&i.complete&&i.naturalWidth>0)")
    thumb = card.locator('.place-photo img').first.bounding_box()
    opener.click()
    viewer = page.locator('#photo-viewer')
    page.wait_for_function("document.querySelector('#photo-viewer').open")
    page.wait_for_function("(()=>{const i=document.querySelector('#photo-viewer img');return !i.hidden&&i.complete&&i.naturalWidth===400})()")
    image = viewer.locator('img')
    assert image.evaluate('i=>getComputedStyle(i).objectFit') == 'contain'
    box = image.bounding_box()
    # 자르지 않음: 그려진 상자의 비율이 원본(4:1)과 같고, 카드 사진보다 크다.
    assert abs(box['width'] / box['height'] - 4) < 0.1
    assert box['width'] > thumb['width']
    assert '사진 큰보기 카페 사진' == viewer.locator('h2').inner_text()
    assert viewer.locator('.photo-counter').inner_text() == '1 / 3'
    # 출처 줄이 그대로 보인다.
    credit = viewer.locator('figcaption')
    assert credit.is_visible() and '네이버 사진 자료' in credit.inner_text()
    assert credit.get_by_role('link', name='업체 등록 사진', exact=True).count() == 1
    # 이전·다음(단추와 화살표 키)
    viewer.get_by_role('button', name='다음 사진', exact=True).click()
    assert viewer.locator('.photo-counter').inner_text() == '2 / 3'
    page.keyboard.press('ArrowLeft')
    assert viewer.locator('.photo-counter').inner_text() == '1 / 3'
    page.keyboard.press('ArrowLeft')
    assert viewer.locator('.photo-counter').inner_text() == '3 / 3'
    assert viewer.get_by_role('button', name='닫기', exact=True).bounding_box()['height'] >= 44
    assert no_overflow(page)
    # Esc 로 닫히고 포커스는 누른 사진으로 돌아간다.
    page.keyboard.press('Escape')
    page.wait_for_function("!document.querySelector('#photo-viewer').open")
    assert page.evaluate("document.activeElement.classList.contains('photo-open')")
    # 닫기 단추, 바깥 누르기
    opener.click()
    page.wait_for_function("document.querySelector('#photo-viewer').open")
    viewer.get_by_role('button', name='닫기', exact=True).click()
    page.wait_for_function("!document.querySelector('#photo-viewer').open")
    opener.click()
    page.wait_for_function("document.querySelector('#photo-viewer').open")
    page.mouse.click(3, 3)
    page.wait_for_function("!document.querySelector('#photo-viewer').open")


def real_results(page, base):
    """데모 코스를 실제 장소 코스처럼 다시 그려 사진·블로그 패널이 나오게 한다."""
    generate(page)
    page.evaluate("selected.conditions.mode='real';plans.forEach(p=>{p.conditions.mode='real';p.places.forEach(x=>x.demo=false)});renderResults();renderDetail()")


def test_result_photo_opens_same_viewer(audit_page):
    page, base, errors = audit_page
    mount_photo_routes(page, base, count=2)
    page.route('**/api/places/*/blogs?*', lambda route: route.fulfill(json={'posts': [], 'message': '없음'}))
    real_results(page, base)
    opener = page.locator('.timeline-card .photo-open').first
    opener.wait_for()
    opener.click()
    page.wait_for_function("document.querySelector('#photo-viewer').open")
    assert page.locator('#photo-viewer .photo-counter').inner_text() == '1 / 2'
    page.keyboard.press('Escape')


CUT_CASES = [
    # (원문 제목, 다듬은 제목)
    ('성수 데이트 코스 추천 | 성수 놀....', '성수 데이트 코스 추천 | 성수…'),
    ('반지 공방 데이트 로벤타 성수 반지 ....', '반지 공방 데이트 로벤타 성수 반지…'),
    ('성수 카페 위치 주소 서울 성동구...', '성수 카페 위치 주소 서울…'),
    ('성수 데이트로 추천할게요!!...', '성수 데이트로 추천할게요!!…'),
    ('성수 카페 [분위기 좋은…', '성수 카페…'),
    ('잘리지 않은 제목 그대로', '잘리지 않은 제목 그대로'),
]


def test_blog_text_trimming_functions(audit_page):
    page, base, errors = audit_page
    for raw, expected in CUT_CASES:
        result = page.evaluate('t=>blogTitleText(t)', raw)
        assert result == {'text': expected, 'cut': raw != expected}, raw
    excerpt = page.evaluate('t=>blogExcerptText(t)', '주말에 다녀왔는데 정말 좋았어요. 분위기도 좋고 사장님도 친절하세요! 다음에도 꼭 다시 오고 싶은 곳이에요 주차는 어려워서 대중교통을 추천할...')
    assert excerpt == {'text': '주말에 다녀왔는데 정말 좋았어요. 분위기도 좋고 사장님도 친절하세요! 다음에도 꼭 다시 오고 싶은 곳이에요', 'cut': True}
    # 끝난 문장까지 남기면 너무 짧으면 낱말 경계에서 끊고 …
    short = page.evaluate('t=>blogExcerptText(t)', '좋아요. 성수동 골목 안쪽에 있는 작은 카페인데 창가 자리가 넓고 조용해서 오래 머물기 좋은 주소 서울 성동구...')
    assert short == {'text': '좋아요. 성수동 골목 안쪽에 있는 작은 카페인데 창가 자리가 넓고 조용해서 오래 머물기 좋은 주소 서울…', 'cut': True}
    whole = '잘리지 않은   요약은 공백만 정리해요'
    assert page.evaluate('t=>blogExcerptText(t)', whole) == {'text': '잘리지 않은 요약은 공백만 정리해요', 'cut': False}


POSTS = [{'title': '성수 데이트 코스 추천 | 성수 놀....', 'url': 'https://blog.naver.com/a/1', 'blogger': '하루', 'posted_at': '2026-11-01',
          'description': '주말에 다녀왔는데 정말 좋았어요. 분위기도 좋고 사장님도 친절하세요! 다음에도 꼭 다시 오고 싶은 곳이에요 주차는 어려워서...'},
         {'title': '반지 공방 데이트 로벤타 성수 반지 ....', 'url': 'https://blog.naver.com/b/2', 'blogger': '이틀', 'posted_at': '2026-10-20',
          'description': '반지 만들기 체험 후기 주소 서울 성동구...'},
         {'title': '성수 데이트로 추천할게요!!...', 'url': 'https://blog.naver.com/c/3', 'blogger': '사흘', 'posted_at': None,
          'description': '세 번째 글 요약입니다.'}]


@pytest.mark.parametrize('width', [390, 1440])
def test_blog_panel_loading_and_results(audit_page, width):
    page, base, errors = audit_page
    page.set_viewport_size({'width': width, 'height': 1000})
    mount_photo_routes(page, base, count=1)
    held = []
    page.route('**/api/places/*/blogs?*', lambda route: held.append(route))
    real_results(page, base)
    # 일정 카드의 첫 번째 블로그 패널
    panel = page.locator('.timeline-card .place-blogs').first
    panel.locator('summary').click()
    content = panel.locator('.place-blog-content')
    page.wait_for_function('document.querySelector(".timeline-card .place-blog-content")?.getAttribute("aria-busy")==="true"')
    assert '네이버 블로그 후기를 찾고 있어요…' in content.inner_text()
    assert content.locator('.blog-skeleton').count() == 3
    assert content.locator('.blog-skeleton-list').get_attribute('aria-hidden') == 'true'
    animation = content.locator('.blog-skeleton span').first.evaluate('s=>getComputedStyle(s).animationName')
    assert animation == 'blog-skeleton-pulse'
    loading_height = content.bounding_box()['height']
    page.wait_for_function('n=>document.querySelectorAll("#plan-detail .place-blog-content .blog-skeleton").length>0', arg=0)
    for _ in range(50):
        if held:
            break
        page.wait_for_timeout(100)
    for route in held:
        route.fulfill(json={'posts': POSTS, 'search_url': 'https://search.naver.com/search.naver?query=x', 'message': ''})
    page.wait_for_function('document.querySelector(".timeline-card .place-blog-content").getAttribute("aria-busy")==="false"')
    loaded_height = content.bounding_box()['height']
    # 뼈대 높이가 결과의 절반 이상이라 크게 튀지 않는다.
    assert loading_height >= loaded_height * 0.4, (loading_height, loaded_height)
    text = content.inner_text()
    assert text.count('검색 요약 발췌 · 본문 전체나 실제 방문 여부는 확인하지 않았어요.') == 1
    titles = content.locator('a.blog-post-title')
    assert titles.count() == 3
    assert titles.first.inner_text() == '1. 성수 데이트 코스 추천 | 성수… ↗'
    assert titles.first.get_attribute('title') == '성수 데이트 코스 추천 | 성수 놀....'
    assert titles.first.evaluate('a=>getComputedStyle(a).webkitLineClamp') == '2'
    assert content.locator('.blog-preview-label').count() == 3
    excerpt = content.locator('.blog-excerpt').first.inner_text()
    assert '주차는 어려워서' not in excerpt and excerpt.startswith('미리보기')
    more = content.get_by_role('link', name='원문에서 이어 읽기 ↗', exact=True)
    assert more.count() == 3 and more.first.get_attribute('href') == 'https://blog.naver.com/a/1'
    # 패널 안 모든 글자는 14px 이상(일정 카드와 코스 카드 사진 미리보기 모두).
    page.evaluate("document.querySelectorAll('.plan-photo-details').forEach(d=>d.open=true)")
    preview = page.locator('.plan-photo-preview .place-blogs')
    if preview.count() and preview.first.is_visible():
        preview.first.locator('summary').click()
        page.wait_for_function('document.querySelector(".plan-photo-preview .place-blog-content")?.getAttribute("aria-busy")==="false"')
    sizes = page.evaluate("""[...document.querySelectorAll('.place-blogs')].filter(p=>p.offsetParent).flatMap(p=>[p,...p.querySelectorAll('*')])
      .filter(el=>[...el.childNodes].some(n=>n.nodeType===3&&n.textContent.trim())).map(el=>parseFloat(getComputedStyle(el).fontSize))""")
    assert sizes and min(sizes) >= 14, sorted(set(sizes))
    assert no_overflow(page)


def test_blog_panel_empty_and_error_states(audit_page):
    page, base, errors = audit_page
    mount_photo_routes(page, base, count=1)
    calls = []

    def blogs(route):
        calls.append(route.request.url)
        if len(calls) == 1:
            return route.fulfill(status=500, json={'detail': '오류'})
        return route.fulfill(json={'posts': [], 'message': '관련 후기를 찾지 못했어요.'})
    page.route('**/api/places/*/blogs?*', blogs)
    real_results(page, base)
    panel = page.locator('.timeline-card .place-blogs').first
    panel.locator('summary').click()
    content = panel.locator('.place-blog-content')
    page.wait_for_function('document.querySelector(".timeline-card .place-blog-content .blog-state")')
    assert '블로그 검색을 불러오지 못했어요.' in content.inner_text()
    content.get_by_role('button', name='후기 다시 검색', exact=True).click()
    page.wait_for_function('document.querySelector(".timeline-card .place-blog-content").textContent.includes("관련 후기를 찾지 못했어요")')
    assert content.locator('.blog-state').count() == 1 and content.get_attribute('aria-busy') == 'false'
    assert '블로그 후기를 찾지 못했어요.' in content.inner_text()
