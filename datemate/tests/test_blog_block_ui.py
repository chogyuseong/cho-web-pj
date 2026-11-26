"""결과 화면의 네이버 블로그 글 블록과 비용 안내(네이버 검색 API 특약 2단계, docs/naver-terms-stage2-design.ko.md 3.1(a)·3.2(a)).

- 코스 조사 패널: 블로그 글을 받은 순서·건수·글자 그대로의 독립 블록으로만 보여 준다. 우리 문구는 블록 밖. 예전 형식(고른 5건)은 그리지 않는다.
- 비용: 합계가 계획용 가정 범위라는 한 줄, 등록 단가가 없는 장소의 '네이버 지도에서 가격 확인' 링크. '단가 다시 검색' 단추는 없다.
"""
import pytest

from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401 (fixture)

POSTS = [dict(title=f'종로 데이트 코스 {i}번째 글 <b>굵게</b> & 협찬...', description=f'요약 {i}  원문 그대로...', url=f'https://blog.naver.com/a/{i}',
              blogger=f'작성자{i}', posted_at='2026-11-0' + str(i + 1)) for i in range(7)]
POSTS[2].update(url=None, description='')


def show(page, course_search):
    page.evaluate("""search=>{
      selected.conditions.mode='real';
      selected.places.forEach(p=>p.demo=false);
      selected.course_search=search;
      const row=selected.costs[0];
      Object.assign(row,{unit:[6000,15000],amount:[12000,30000],status:'estimated',price_kind:'planning_assumption',source:'서비스 예산 계획용 가정',
        price_basis:'계획용 1인 범위 · 등록된 단가가 없어 넣은 가정 (실제 단가 아님)',checked_at:null});
      Object.assign(selected.costs[1],{unit:null,amount:null,status:'unknown',price_basis:'등록된 단가가 없어요. 가격은 방문 전에 확인해 주세요.'});
      delete selected.costs[1].price_kind;
      renderDetail();
    }""", course_search)


@pytest.mark.parametrize('width', [390, 1280])
def test_course_panel_shows_blog_posts_as_an_untouched_block(audit_page, width):
    page, _, _ = audit_page
    page.set_viewport_size({'width': width, 'height': 900})
    generate(page)
    wait_for_selected_detail(page)
    show(page, dict(format=2, query='종로 데이트 코스', requested_query='종로 데이트 코스', posts=POSTS, status='available', search_relaxed=False))
    research = page.locator('details.course-evidence')
    assert research.count() == 1
    assert research.locator('summary').inner_text() == '코스 구성 메모 · 네이버 블로그 글 7건'
    research.locator('summary').click()
    panel = research.locator('.course-search-panel')
    # 2026-11-26 네이버 답(특약 1.2, 2-1·2-2): 우리 메모 상자와 블로그 칸을 나누고, 블로그 칸에는 블록 하나만. 블록 앞 안내 문구는 없다.
    assert panel.locator('.course-search-note').count() == 0 and '광고·협찬 글이 섞여' not in panel.inner_text()
    # 메모 상자는 내용이 있을 때만(이 체험 코스는 메모가 없다), 블로그 칸은 하나.
    assert panel.locator(':scope > .course-search-memo').count() == 0 and panel.locator(':scope > .course-search-blogs').count() == 1
    assert panel.locator('.course-search-memo .naver-result-block').count() == 0
    assert panel.locator('.course-search-blogs').evaluate('e=>[...e.children].map(c=>c.className)') == ['naver-result-block']
    block = panel.locator('.naver-result-block')
    assert block.count() == 1
    assert block.locator('.naver-result-head h3').inner_text() == '‘종로 데이트 코스’ 블로그 검색 결과 7건'
    assert '네이버 검색결과 · 블로그 검색' in block.locator('.naver-attribution').inner_text()
    # BI 로고는 블록 바닥 오른쪽, NAVER API HUB 로 새 창.
    logo = block.locator('.naver-result-foot > a.naver-powered')
    assert logo.count() == 1 and logo.get_attribute('target') == '_blank' and 'naverApiHub' in logo.get_attribute('href')
    assert logo.locator('img').get_attribute('alt') == 'Powered by NAVER OpenAPI'
    assert logo.locator('img').evaluate('i=>i.complete&&i.naturalWidth>0')
    titles = block.locator('.blog-post-title')
    # 처음 5건을 받은 순서·제목 그대로(태그 글자도 글자로만). 링크가 없는 글은 글자로만 보인다.
    assert titles.all_inner_texts() == [post['title'] for post in POSTS[:5]]
    assert block.locator('b').count() == 0
    assert [titles.nth(i).get_attribute('href') for i in (0, 1, 3)] == [POSTS[i]['url'] for i in (0, 1, 3)]
    assert titles.nth(2).evaluate('e=>e.tagName') == 'SPAN'
    assert block.locator('.blog-summary').all_text_contents() == [post['description'] for post in POSTS[:5] if post['description']]
    assert block.locator('.blog-meta').first.inner_text() == '작성자0 · 2026-11-01'
    for gone in ('선정', '확인한 장소', '상위 글', '검색 순위', '광고·협찬 표시'):
        assert gone not in block.inner_text(), gone
    # 「더 보기」는 블록 바닥(같은 결과의 뒤쪽을 펴는 쪽 넘김) — 블록 밖에 우리 단추를 두지 않는다.
    more = block.locator('.naver-result-pager').get_by_role('button', name='나머지 2건 더 보기', exact=True)
    assert more.count() == 1 and panel.get_by_role('button').count() == 1
    more.click()
    assert block.locator('.blog-post-title').all_inner_texts() == [post['title'] for post in POSTS]
    assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth')
    # 장소 카드의 추천 이유 칸에 '블로그 언급' 줄이 없다.
    assert '블로그 언급' not in page.locator('#plan-detail').inner_text()


def test_old_format_course_search_is_not_drawn(audit_page):
    page, _, _ = audit_page
    generate(page)
    wait_for_selected_detail(page)
    old = dict(query='종로 데이트 코스', provider='네이버 검색 후보에서 지역·최근성·작성자 중복을 고려한 후기 최대 5개', matches={},
               posts=[dict(rank=1, title='고른 글', url='https://blog.naver.com/a/1', selection_reason='검색 순위 4', content_scope='검색 요약만 확인')])
    show(page, old)
    assert page.locator('details.course-evidence').count() == 0
    assert '고른 글' not in page.locator('body').inner_text()


@pytest.mark.parametrize('width', [390, 1280])
def test_cost_table_says_the_total_is_a_planning_range_and_links_to_the_map(audit_page, width):
    page, _, _ = audit_page
    page.set_viewport_size({'width': width, 'height': 900})
    generate(page)
    wait_for_selected_detail(page)
    show(page, None)
    detail = page.locator('#plan-detail')
    note = detail.locator('.cost-basis-note')
    assert note.count() == 1
    text = note.inner_text()
    assert '실제 가격이 아니라 계획용 가정 범위예요' in text and '1곳이 가정 금액' in text and '1곳이 미확인(합계에서 빠짐)' in text
    assert '블로그 글에 적힌 가격은 읽지 않아요' in text
    detail.locator('.cost-table-details > summary').click()
    rows = detail.locator('.cost-table tbody tr')
    places = page.evaluate('selected.places.length')
    links = detail.locator('.cost-table a.price-map-check')
    # 가정 금액·미확인 장소 줄에만 지도 링크가 있다(이동 줄에는 없음). 검색 API 를 부르지 않는 네이버 지도 링크다.
    assert links.count() == 2 and rows.nth(0).locator('a.price-map-check').count() == 1 and rows.nth(1).locator('a.price-map-check').count() == 1
    assert rows.nth(places).locator('a.price-map-check').count() == 0
    assert links.first.inner_text() == '네이버 지도에서 가격 확인 ↗' and links.first.get_attribute('href').startswith('https://map.naver.com/p/')
    assert detail.locator('.price-refresh-control').count() == 0
    assert page.get_by_role('button', name='현재 단가 다시 검색').count() == 0
    assert detail.locator('.cost-table .naver-attribution').count() == 0
    assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth')
