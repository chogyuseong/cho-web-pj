"""브라우저 저장소의 네이버 검색 결과 보관(특약 2.4 기기: 24시간 또는 새 질의 시까지 중 짧은 기간, static/form-state.js).

'지난번처럼 추천'(localStorage datemate-last-conditions)이 유일하게 남기는 곳이다. 지역 검색(장소 이름으로 찾기)·팝업 거점에서 온
출발지에는 받은 시각(naver_at)과 검색 종류(naver_query)를 붙이고, 24시간이 지나거나 같은 종류의 새 검색을 하면 출발지만 지운다.
동네 칩·현재 위치·지도·주소 검색(지오코딩) 출발지와 시간·예산 같은 조건은 그대로 둔다.
"""

import json

from test_functional_audit import audit_page  # noqa: F401 (fixture)

LOCAL_ORIGIN = '서울 마포구 양화로 160'  # 지역 검색 결과의 도로명 주소로 만든 출발지 이름


def test_device_keeps_a_search_origin_for_a_day_or_until_a_new_search(audit_page):
    page, _, errors = audit_page
    key = 'datemate-last-conditions'
    page.evaluate("localStorage.removeItem('datemate-last-conditions')")
    base = dict(region='서울', start='11:00', end='19:00', budget=100000, people=2, count=3, transport='walk')
    # 네이버 결과가 아닌 출발지(동네 칩)는 시각을 붙이지 않고 기한 없이 둔다.
    chip = dict(base, origin=dict(name='서울 성수역 지역 중심', lat=37.5446, lon=127.0559))
    page.evaluate('v=>localStorage.setItem("datemate-last-conditions",JSON.stringify(v))', chip)
    assert page.evaluate('LastConditions.load()')['origin'] == chip['origin']
    # 받은 지 25시간 된 지역 검색 출발지: 출발지만 지우고 나머지 조건은 남긴다.
    old = dict(base, origin=dict(name=LOCAL_ORIGIN, lat=37.556, lon=126.923, naver_query='local'))
    page.evaluate('v=>{v.origin.naver_at=Date.now()-25*3600000;localStorage.setItem("datemate-last-conditions",JSON.stringify(v))}', old)
    assert page.evaluate('LastConditions.load()') is None
    kept = json.loads(page.evaluate(f'localStorage.getItem("{key}")'))
    assert 'origin' not in kept and kept['budget'] == 100000 and kept['transport'] == 'walk'
    # 1시간 된 것은 남고, 받은 시각은 다시 저장해도 늘지 않는다.
    page.evaluate('v=>{v.origin.naver_at=Date.now()-3600000;localStorage.setItem("datemate-last-conditions",JSON.stringify(v))}', old)
    loaded = page.evaluate('LastConditions.load()')
    assert loaded['origin']['name'] == LOCAL_ORIGIN and loaded['origin']['naver_query'] == 'local'
    first_at = loaded['origin']['naver_at']
    page.evaluate("s=>LastConditions.save({...s,mode:'real',festival:null})", loaded)
    assert json.loads(page.evaluate(f'localStorage.getItem("{key}")'))['origin']['naver_at'] == first_at
    # 다른 종류의 새 검색(팝업)은 지우지 않고, 같은 종류(출발지 검색)의 새 검색은 지운다.
    page.evaluate("LastConditions.newQuery('popups')")
    assert page.evaluate('LastConditions.load()')['origin']['name'] == LOCAL_ORIGIN
    page.evaluate("LastConditions.newQuery('local')")
    assert page.evaluate('LastConditions.load()') is None
    assert 'origin' not in json.loads(page.evaluate(f'localStorage.getItem("{key}")'))
    assert not errors, errors


def test_place_name_search_marks_the_origin_and_a_new_search_forgets_it(audit_page):
    page, _, errors = audit_page
    key = 'datemate-last-conditions'
    found = {'status': 'ok', 'provider': 'NAVER 지역 검색', 'message': '', 'results': [
        {'name': LOCAL_ORIGIN, 'lat': 37.556, 'lon': 126.923, 'road_address': LOCAL_ORIGIN, 'jibun_address': None,
         'place_name': '홍대입구역 2호선', 'category': '지하철'}]}  # fmt: skip
    page.route('**/api/locations/search', lambda route: route.fulfill(json=found))
    origin = page.locator('[name=origin_name]')
    origin.fill('홍대입구역')
    origin.press('Enter')
    page.wait_for_selector('#origin-search-option-0')
    page.locator('#origin-search-option-0').click()
    picked = page.evaluate('locationState.origin')
    assert picked['name'] == LOCAL_ORIGIN and picked['naver_query'] == 'local'
    assert abs(picked['naver_at'] - page.evaluate('Date.now()')) < 60000
    page.evaluate("LastConditions.save({...values(),mode:'real',festival:null})")
    saved = json.loads(page.evaluate(f'localStorage.getItem("{key}")'))
    assert saved['origin']['naver_at'] == picked['naver_at']
    # 새 출발지 검색을 시작하면 앞 검색에서 고른 출발지를 이 브라우저에서 지운다.
    origin.fill('합정역')
    origin.press('Enter')
    page.wait_for_selector('#origin-search-option-0')
    assert 'origin' not in json.loads(page.evaluate(f'localStorage.getItem("{key}")'))
    assert not errors, errors
