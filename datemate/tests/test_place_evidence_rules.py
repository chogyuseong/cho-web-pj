"""장소 정보 확인 규칙(2026-11-19 사용자 스크린샷: 한 장소에 위치·영업 정보·가격 '확인 필요'와 블로그 언급 없음).

- 위치: 네이버 지도에서 같은 업체를 찾으면(사진 요청의 naver_place_id_verified) '확인됨'으로 바뀐다. 예전에는 늘 고정 문구였다.
- 영업 정보: 영업 자료 파일로 확인한 영업시간이 있으면 그 확인일이 카드의 '최근 영업 자료'가 된다. 예전에는 날짜가 이어지지 않았다.
- 블로그·가격: 지점 이름('OO카페 성수점')을 지점 없이 쓴 글도 같은 장소로 본다. 업종 낱말('서점')은 떼지 않는다.
- 가격: 카페 라떼·디저트, 체험·레저의 원데이 클래스·수강료 같은 흔한 표현도 읽는다.
"""
from datetime import date, timedelta

from app import operating_evidence, pricing
from app.course_search import match_places, without_branch
from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401 (fixture)


def test_branch_suffix_is_removed_only_for_branch_words():
    assert without_branch('OO카페 성수점') == 'OO카페'
    assert without_branch('교보문고 광화문점') == '교보문고'
    assert without_branch('블루보틀 삼청 한옥점') == '블루보틀 삼청'
    for keep in ('책읽는 서점', '서울 백화점', '카페점', '어니언 성수'):
        assert without_branch(keep) == keep


def test_blog_post_without_branch_name_matches_the_branch():
    post = dict(rank=1, title='성수 데이트', description='포인트오브뷰 다녀왔어요', _body='', author='a')
    rows = [dict(id='p1', name='포인트오브뷰 성수점'), dict(id='p2', name='책읽는 서점')]
    assert set(match_places([post], rows)) == {'p1'}


def test_more_price_phrases_are_read(monkeypatch):
    monkeypatch.setattr(pricing, 'today', lambda: date(2026, 11, 19))
    posted = (date(2026, 11, 19) - timedelta(days=30)).strftime('%Y%m%d')
    cafe = dict(name='어니언 성수점', category='카페·미식')
    yoga = dict(name='플래닛 요가 스트레치', category='레저·활동')
    item = lambda text: dict(title=text, description='', link='https://blog.naver.com/a/1', postdate=posted)
    assert pricing.extract_quote(cafe, item('어니언 다녀옴 카페라떼 6,500원'))['amount'] == 6500
    assert pricing.extract_quote(yoga, item('플래닛 요가 스트레치 원데이 클래스 25,000원'))['amount'] == 25000
    assert pricing.extract_quote(yoga, item('플래닛 요가 스트레치 수강료 1회 3만원'))['amount'] == 30000
    assert pricing.extract_quote(yoga, item('다른 요가원 원데이 클래스 25,000원')) is None, '다른 장소 글은 읽지 않는다'


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


def test_location_line_turns_verified_when_the_naver_place_matches(audit_page):
    page, _, _ = audit_page
    generate(page)
    wait_for_selected_detail(page)
    page.evaluate("selected.conditions.mode='real';selected.places.forEach(p=>p.demo=false);renderDetail()")
    first = page.evaluate('selected.places[0].id')
    item = page.locator(f'#plan-detail li[data-identity-place-id="{first}"]').first
    assert '같은 지점인지는 확인하지 못했' in item.text_content()
    page.evaluate("rememberVerifiedMapTarget(selected.places[0],{naver_place_id:'123456',naver_place_id_verified:true})")
    item = page.locator(f'#plan-detail li[data-identity-place-id="{first}"]').first
    assert 'evidence-ok' in item.get_attribute('class') and '400m 안' in item.text_content()
    assert page.locator(f'#plan-detail a[data-map-place-id="{first}"]').first.get_attribute('href').endswith('/place/123456')


def test_official_identity_and_tour_hours_reach_the_card(audit_page):
    """공식 지역 검색 API 로 같은 업체가 확인되면 '위치'가 확인됨, 관광공사 영업 안내는 '영업 정보' 줄에 글로 덧붙는다."""
    page, _, _ = audit_page
    generate(page)
    wait_for_selected_detail(page)
    page.evaluate("selected.conditions.mode='real';selected.places.forEach(p=>p.demo=false);renderDetail()")
    first = page.evaluate('selected.places[0].id')
    page.evaluate("rememberVerifiedMapTarget(selected.places[0],{identity:{verified:true},tour_hours:{hours:'10:00~22:00',rest:'연중무휴',source_url:'https://korean.visitkorea.or.kr/detail/ms_detail.do?cotid=1'}})")
    item = page.locator(f'#plan-detail li[data-identity-place-id="{first}"]').first
    assert 'evidence-ok' in item.get_attribute('class') and '공식 API' in item.text_content()
    hours = page.locator(f'#plan-detail li[data-operating-place-id="{first}"] .tour-hours').first
    assert '한국관광공사 안내: 10:00~22:00 · 쉬는 날 연중무휴' in hours.text_content()
    assert hours.locator('a').get_attribute('href').startswith('https://korean.visitkorea.or.kr/')
    # 같은 응답이 두 번 와도 한 번만 붙는다.
    page.evaluate("markTourHours(selected.places[0].id,{hours:'10:00~22:00'})")
    assert page.locator(f'#plan-detail li[data-operating-place-id="{first}"] .tour-hours').count() == 1
