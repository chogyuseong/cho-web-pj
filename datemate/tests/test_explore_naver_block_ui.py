"""둘러보기 화면: 공공 자료 기본 목록과 그 아래의 '네이버에서 더 찾기' 블록(2026-11-20 2단계 3.5(b)·3.7(a)). 실제 브라우저, 응답은 가짜.

- 기본 목록의 카드는 공공 자료 출처 한 줄을 달고, 네이버 출처 표시가 없다.
- '네이버에서 더 찾기'는 펼쳤을 때만 부른다. 검색어 하나가 블록 하나이고, 블록은 공통 부품(naverResultBlock)이다:
  테두리 상자 + 머리글(검색어·건수, '네이버 검색결과' 표시, 원본 링크) + 본문(받은 순서 그대로의 API 필드).
- 블록 안에는 우리 정보(사진·단추·분류 태그·안내 문장)가 없다. 우리 안내는 블록 밖에 있다.
"""
import pytest

from test_functional_audit import audit_page  # noqa: F401

PLACES = [
    dict(id='public:tour-1', name='부산시립미술관', category='문화·예술', address='부산광역시 해운대구 APEC로 58', region='부산', demo=False,
         public_source='tour', source='https://korean.visitkorea.or.kr/detail/ms_detail.do?cotid=1', tags=['culture'], photos=[], lat=35.1667, lon=129.137),
    dict(id='public:store-C1', name='동네 카페', category='카페·미식', address='부산광역시 해운대구 구남로 2', region='부산', demo=False,
         public_source='store', source='https://www.data.go.kr/data/15012005/openapi.do', tags=['cafe'], photos=[], lat=35.1635, lon=129.164),
]
EXPLORE = dict(status='ready', places=PLACES, total=2, offset=0, has_more=False, region='부산', activity='전체', message=None, naver_more=True,
               ranking_method='공공 자료(한국관광공사 관광정보·소상공인 상가정보)를 사진이 있는 곳 먼저 정리했어요. 인기·별점 순위가 아니에요.',
               data_note='공공 자료에는 사진·영업시간·후기가 없는 곳이 많아요. 장소를 열면 네이버 지도에서 확인하는 링크가 있어요.',
               center_hint='동네 이름(예: 성수, 해운대)으로 검색하면 그 주변 가게(소상공인 상가정보)도 함께 보여 드려요.')


def item(title, category='카페,디저트', road='부산광역시 해운대구 구남로 1', link=None, description=''):
    return dict(title=title, category=category, road_address=road, address='', description=description, telephone='',
                link=link, map_url='https://map.naver.com/p/search/' + title)


BLOCKS = dict(status='ready', message=None, queries_used=2, region='부산', activity='전체', blocks=[
    dict(query='부산 데이트 장소', status='available', search_url='https://map.naver.com/p/search/부산 데이트 장소',
         items=[item('<b>글자</b>로만 카페', link='https://example.com/cafe', description='받은 설명'), item('같은 가게'),
                item('서울 병원', category='병원,의원', road='서울특별시 중구 명동길 1'), item('같은 가게')]),
    dict(query='부산 데이트 카페', status='available', search_url='https://map.naver.com/p/search/부산 데이트 카페', items=[]),
])


def open_explore(page, width):
    requests = []
    page.set_viewport_size({'width': width, 'height': 900})
    page.route('**/api/explore?*', lambda route: route.fulfill(json=EXPLORE))
    page.route('**/api/places/*/media*', lambda route: route.fulfill(json=dict(photos=[], videos=[], status='not_found', map_url='https://map.naver.com/p/search/x')))

    def naver(route):
        requests.append(route.request.url)
        return route.fulfill(json=BLOCKS)

    page.route('**/api/explore/naver?*', naver)
    page.evaluate("document.getElementById('nav-explore').click()")
    page.wait_for_function('document.querySelectorAll("#catalog .place-card").length===2')
    return requests


@pytest.mark.parametrize('width', [390, 1280])
def test_public_list_then_untouched_naver_blocks(audit_page, width):
    page, _, _ = audit_page
    requests = open_explore(page, width)
    # 기본 목록: 공공 자료 출처 한 줄, 네이버 출처 표시 없음, 정렬 기준과 '확인 필요'가 많은 까닭 한 줄.
    cards = page.locator('#catalog .place-card')
    assert cards.nth(0).locator('.public-data-source').inner_text() == '공공 자료 · 한국관광공사 관광정보 ↗'
    assert cards.nth(1).locator('.public-data-source').inner_text() == '공공 자료 · 소상공인 상가정보 ↗'
    assert page.locator('#catalog .naver-attribution').count() == 0 and '네이버 검색결과' not in page.locator('#catalog').inner_text()
    assert '부산 · 전체 · 공공 자료 2곳' in page.locator('#search-info').inner_text()
    notes = page.locator('#explore-controls').inner_text()
    assert '인기·별점 순위가 아니에요' in notes and '사진·영업시간·후기가 없는 곳이 많아요' in notes and '동네 이름' in notes
    # '네이버에서 더 찾기'는 접혀 있고, 펼치기 전에는 부르지 않는다.
    more = page.locator('#explore-naver details.explore-naver-more')
    assert more.count() == 1 and not more.evaluate('e=>e.open') and requests == []
    assert page.evaluate("()=>{const a=document.getElementById('catalog'),b=document.getElementById('explore-naver');"
                         "return Boolean(a.compareDocumentPosition(b)&Node.DOCUMENT_POSITION_FOLLOWING)}"), '기본 목록 아래에 있다'
    more.locator('summary').click()
    page.wait_for_function('document.querySelectorAll("#explore-naver .naver-result-block").length===2')
    assert len(requests) == 1 and 'region=%EC%84%9C%EC%9A%B8' in requests[0], '화면에서 고른 시·도(서울)로 한 번 부른다'
    # 우리 안내는 블록 밖에 한 번.
    note = more.locator('.explore-naver-note')
    assert '네이버가 준 순서 그대로' in note.inner_text() and '코스 추천에도 쓰지 않아요' in note.inner_text()
    assert more.locator('.naver-result-block .explore-naver-note').count() == 0
    blocks = more.locator('.naver-result-block')
    first = blocks.nth(0)
    # 블록 = 머리글(검색어·건수 + 출처 표시 + 원본 링크) + 본문.
    assert first.evaluate('e=>[...e.children].map(c=>c.className)') == ['naver-result-head', 'naver-result-body']
    head = first.locator('.naver-result-head')
    assert head.locator('.naver-result-title').inner_text() == '‘부산 데이트 장소’ 검색 결과 4건'
    assert '네이버 검색결과 · 지역 검색' in head.locator('.naver-attribution').inner_text()
    assert head.locator('a').first.get_attribute('href').startswith('https://map.naver.com/p/search/')
    assert 'NAVER 오픈 API' in head.inner_text()
    # 본문: 받은 순서·건수 그대로(다른 시·도, 병원, 같은 가게 두 번도 그대로). 태그 글자는 글자로만.
    titles = first.locator('.naver-local-title').all_inner_texts()
    assert titles == ['<b>글자</b>로만 카페', '같은 가게', '서울 병원', '같은 가게']
    assert first.locator('.naver-result-body b').count() == 0
    row = first.locator('.naver-local-item').nth(0)
    assert row.locator('.naver-local-category').inner_text() == '카페,디저트'
    assert row.locator('.naver-local-address').inner_text() == '부산광역시 해운대구 구남로 1'
    assert row.locator('.naver-local-description').inner_text() == '받은 설명'
    links = row.locator('a')
    assert links.all_inner_texts() == ['네이버 지도에서 보기 ↗', '홈페이지 ↗']
    assert links.nth(0).get_attribute('rel') == 'noopener noreferrer' and links.nth(1).get_attribute('href') == 'https://example.com/cafe'
    # 블록 안에는 우리 정보가 없다: 사진, 단추, 우리 분류 태그, 장소 카드, 공공 자료 표시.
    for gone in ('img', 'button', '.tag', '.place-card', '.place-photo-panel', '.public-data-source', '.hint'):
        assert blocks.nth(0).locator(gone).count() == 0, gone
    assert '카페·미식' not in first.inner_text()
    # 결과가 없는 검색어도 블록 하나로 남는다.
    assert blocks.nth(1).locator('.naver-result-title').inner_text() == '‘부산 데이트 카페’ 검색 결과 0건'
    # 테두리로 구분된 상자다.
    style = first.evaluate('e=>{const s=getComputedStyle(e);return [s.borderTopWidth,s.borderTopStyle]}')
    assert style == ['1px', 'solid']
    assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth')
    # 항목의 링크(네이버 지도·홈페이지)는 누를 수 있는 높이를 가진다(머리글의 출처 줄은 글 속 링크라 따로 재지 않는다).
    short = more.locator('.naver-local-links a').evaluate_all('els=>els.filter(el=>el.getBoundingClientRect().height<24).map(el=>el.textContent)')
    assert not short, short
    # 다시 접었다 펴도 다시 부르지 않는다.
    more.locator('summary').click()
    more.locator('summary').click()
    assert len(requests) == 1


def test_naver_more_is_absent_without_the_search_key(audit_page):
    page, _, _ = audit_page
    page.route('**/api/explore?*', lambda route: route.fulfill(json=dict(EXPLORE, naver_more=False)))
    page.route('**/api/places/*/media*', lambda route: route.fulfill(json=dict(photos=[], videos=[], status='not_found')))
    page.evaluate("document.getElementById('nav-explore').click()")
    page.wait_for_function('document.querySelectorAll("#catalog .place-card").length===2')
    assert page.locator('#explore-naver details').count() == 0
