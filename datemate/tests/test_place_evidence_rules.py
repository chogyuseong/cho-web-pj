"""장소 정보 확인 규칙(2026-11-19 사용자 스크린샷: 한 장소에 위치·영업 정보·가격 '확인 필요'와 블로그 언급 없음).

- 위치(2026-11-20): 공공 자료(상가정보·인허가) 판정만 보여 준다. 판정이 없으면 '네이버 지도에서 확인' 링크만(app/place_identity.py, tests/test_public_identity.py).
- 영업 정보: 영업 자료 파일로 확인한 영업시간이 있으면 그 확인일이 카드의 '최근 영업 자료'가 된다. 예전에는 날짜가 이어지지 않았다.
- 지점 이름('OO카페 성수점')에서 지점 낱말을 떼는 규칙(without_branch). 업종 낱말('서점')은 떼지 않는다.
  (블로그 글에서 장소·가격을 읽던 규칙은 2026-11-20 2단계에서 없앴다: 네이버 검색 API 특약 2.2, tests/test_blog_independent_block.py.)
"""
from datetime import timedelta

from app import operating_evidence
from app.course_search import without_branch
from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401 (fixture)


def test_branch_suffix_is_removed_only_for_branch_words():
    assert without_branch('OO카페 성수점') == 'OO카페'
    assert without_branch('교보문고 광화문점') == '교보문고'
    assert without_branch('블루보틀 삼청 한옥점') == '블루보틀 삼청'
    for keep in ('책읽는 서점', '서울 백화점', '카페점', '어니언 성수'):
        assert without_branch(keep) == keep


def test_evidence_file_hours_set_the_operating_check_date():
    checked = (operating_evidence.today() - timedelta(days=10)).isoformat()
    records = {'p1': dict(hours=dict(value=[600, 1260], source='https://example.org/hours', checked_at=checked, valid_days=90))}
    result = operating_evidence.apply_evidence(dict(id='p1', name='요가', hours=None, closed_days=None), records)
    assert result['hours'] == [600, 1260]
    assert result['operations_checked_at'] == checked
    # 이미 더 최근 확인일이 있으면 그대로 둔다.
    newer = (operating_evidence.today() - timedelta(days=1)).isoformat()
    kept = operating_evidence.apply_evidence(dict(id='p1', name='요가', hours=None, operations_checked_at=newer), records)
    assert kept['operations_checked_at'] == newer
    # 기한이 지난 자료는 날짜를 넣지 않는다.
    old = (operating_evidence.today() - timedelta(days=200)).isoformat()
    stale = {'p1': dict(hours=dict(value=[600, 1260], source='https://example.org/hours', checked_at=old, valid_days=90))}
    assert operating_evidence.apply_evidence(dict(id='p1', name='요가', hours=None), stale).get('operations_checked_at') is None


def detail_with_real_places(page):
    # 사진 요청(/media)의 실제 응답(identity 포함)이 늦게 와서 테스트가 넣은 판정을 덮지 않게, 판정 없는 응답으로 고정한다.
    page.route('**/api/places/*/media?*', lambda route: route.fulfill(json=dict(photos=[], status='not_found')))
    generate(page)
    wait_for_selected_detail(page)
    page.evaluate("selected.conditions.mode='real';selected.places.forEach(p=>p.demo=false);renderDetail()")
    first = page.evaluate('selected.places[0].id')
    return first, lambda: page.locator(f'#plan-detail li[data-identity-place-id="{first}"]').first


def test_location_line_without_a_verdict_is_only_the_naver_map_link(audit_page):
    """공공 자료 판정이 없으면(자료에 없음·키 없음·실패) 판정 문구 없이 '네이버 지도에서 확인' 링크만 나온다."""
    page, _, _ = audit_page
    first, item = detail_with_real_places(page)
    assert item().locator('.evidence-text').text_content().strip() == '네이버 지도에서 확인 ↗'
    assert item().get_attribute('data-identity-status') == 'unknown' and 'evidence-check' in item().get_attribute('class')
    link = item().locator('a.evidence-map-link')
    assert link.get_attribute('href').startswith('https://map.naver.com/p/search/') and link.get_attribute('target') == '_blank'
    for answer in ("{status:'unknown',pending:false,source:null,reason:'not_found'}", "{status:'unknown',pending:false,source:null,reason:'key_missing'}"):
        page.evaluate(f"rememberVerifiedMapTarget(selected.places[0],{{identity:{answer}}})")
        assert item().locator('.evidence-text').text_content().strip() == '네이버 지도에서 확인 ↗'
    # 네이버 화면에서 얻은 업체 번호(지금은 꺼진 경로)는 지도 링크만 바꾸고 '위치' 판정은 만들지 않는다.
    page.evaluate("rememberVerifiedMapTarget(selected.places[0],{naver_place_id:'123456',naver_place_id_verified:true})")
    assert item().get_attribute('data-identity-status') == 'unknown'
    assert page.locator(f'#plan-detail a[data-map-place-id="{first}"]').first.get_attribute('href').endswith('/place/123456')


def test_public_data_verdicts_show_their_source_and_date(audit_page):
    """인허가 → '영업 중 · 행안부 인허가 자료 기준 · n일 전 조회', 상가정보 → '위치 확인 · 소상공인 상가정보(연월 자료) 기준', 폐업은 확인 필요."""
    page, _, _ = audit_page
    first, item = detail_with_real_places(page)
    count = lambda: page.evaluate("document.querySelector('#plan-detail li[data-identity-place-id]').closest('details').querySelector('.evidence-summary-count')?.textContent||''")
    before = count()
    page.evaluate("rememberVerifiedMapTarget(selected.places[0],{identity:{status:'open',pending:false,source:'license',license_kind:'일반음식점',age_days:2,modified_on:'2026-06-02'}})")
    text = item().text_content()
    assert 'evidence-ok' in item().get_attribute('class') and '영업 중 · 행안부 인허가 자료(일반음식점) 기준 · 2일 전 조회' in text
    assert '네이버 지도에서 확인 ↗' in text
    # '방문 전 확인 n개'도 함께 줄어든다.
    assert count() != before and int(''.join(filter(str.isdigit, before))) - 1 == int(''.join(filter(str.isdigit, count())) or 0)
    page.evaluate("rememberVerifiedMapTarget(selected.places[0],{identity:{status:'located',pending:false,source:'store_info',data_month:'202609',age_days:0}})")
    assert '위치 확인 · 소상공인 상가정보(2026년 9월 자료) 기준 · 오늘 조회' in item().text_content() and '200m 안' in item().text_content()
    page.evaluate("rememberVerifiedMapTarget(selected.places[0],{identity:{status:'closed',pending:false,source:'license',license_kind:'휴게음식점',closed_on:'2026-03-02',age_days:5}})")
    assert 'evidence-check' in item().get_attribute('class') and '폐업으로 등록됨(2026.03.02) · 행안부 인허가 자료(휴게음식점) 기준 · 5일 전 조회' in item().text_content()
    assert count() == before


def test_pending_verdict_is_asked_again_and_falls_back_to_the_link(audit_page):
    """공공 API 가 느려 서버가 '확인 중'으로 답하면 화면은 링크를 먼저 그리고 /identity 를 다시 묻는다. 끝까지 없으면 링크만 남는다."""
    page, _, _ = audit_page
    first, item = detail_with_real_places(page)
    answers = [dict(status='unknown', pending=True, source=None, reason='checking'),
               dict(status='located', pending=True, source='store_info', data_month='202609', age_days=0),
               dict(status='open', pending=False, source='license', license_kind='일반음식점', age_days=0)]
    asked = []

    def identity(route):
        asked.append(route.request.url)
        route.fulfill(json=dict(place_id=first, identity=answers[min(len(asked), len(answers)) - 1]))

    page.route('**/api/places/*/identity?*', identity)
    page.evaluate("IDENTITY_RECHECK_MS=[50,50,50,50]")
    page.evaluate("rememberVerifiedMapTarget(selected.places[0],{identity:{status:'unknown',pending:true,source:null,reason:'checking'}})")
    assert '공공 자료를 확인하고 있어요.' in item().text_content() and '네이버 지도에서 확인 ↗' in item().text_content()
    page.wait_for_function("document.querySelector('#plan-detail li[data-identity-place-id]').dataset.identityStatus==='open'")
    assert len(asked) == 3 and all('mode=real' in url for url in asked)
    page.wait_for_timeout(300)
    assert len(asked) == 3, '판정이 정해지면 더 묻지 않는다'
    # 실패만 돌아오면 정해진 횟수 뒤에 멈추고 링크만 남긴다.
    page.unroute('**/api/places/*/identity?*')
    failed = []
    page.route('**/api/places/*/identity?*', lambda route: (failed.append(1), route.fulfill(status=503, json=dict(detail='x')))[1])
    page.evaluate("identityViews.clear();IDENTITY_RECHECK_MS=[30,30];rememberVerifiedMapTarget(selected.places[0],{identity:{status:'unknown',pending:true,source:null,reason:'checking'}})")
    page.wait_for_function("!document.querySelector('#plan-detail li[data-identity-place-id]').textContent.includes('확인하고 있어요')")
    assert len(failed) == 2 and item().locator('.evidence-text').text_content().strip() == '네이버 지도에서 확인 ↗'


def test_tour_hours_reach_the_card(audit_page):
    """관광공사 영업 안내는 '영업 정보' 줄에 글로 덧붙는다."""
    page, _, _ = audit_page
    first, _ = detail_with_real_places(page)
    page.evaluate("rememberVerifiedMapTarget(selected.places[0],{tour_hours:{hours:'10:00~22:00',rest:'연중무휴',source_url:'https://korean.visitkorea.or.kr/detail/ms_detail.do?cotid=1'}})")
    hours = page.locator(f'#plan-detail li[data-operating-place-id="{first}"] .tour-hours').first
    assert '한국관광공사 안내: 10:00~22:00 · 쉬는 날 연중무휴' in hours.text_content()
    assert hours.locator('a').get_attribute('href').startswith('https://korean.visitkorea.or.kr/')
    # 같은 응답이 두 번 와도 한 번만 붙는다.
    page.evaluate("markTourHours(selected.places[0].id,{hours:'10:00~22:00'})")
    assert page.locator(f'#plan-detail li[data-operating-place-id="{first}"] .tour-hours').count() == 1
    # 2026-11-24 사용자 스크린샷: 안내 글이 줄(3칸 격자)의 넷째 칸으로 붙어 첫 칸이 넓어지고, '확인 필요' 배지가 가로로 늘어나고
    # 본문이 한 글자씩 세로로 쌓였다. 안내 글은 본문 칸 안에 들어가야 한다(줄의 자식은 배지·이름·본문 셋).
    shape = page.evaluate(f"""()=>{{
      const li=document.querySelector('#plan-detail li[data-operating-place-id="{first}"]');
      li.closest('details').open=true;
      const badge=li.querySelector('.evidence-badge').getBoundingClientRect(),text=li.querySelector(':scope>.evidence-text').getBoundingClientRect();
      return [li.children.length,Math.round(badge.width),Math.round(text.width)];
    }}""")
    assert shape[0] == 3, shape
    assert shape[1] < 120 and shape[2] > 200, shape