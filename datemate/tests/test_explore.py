"""장소 둘러보기(app/explore.py, 2026-11-20 2단계 3.5(b)).

- 기본 목록은 공공 자료(한국관광공사 시·도 목록 + 동네를 알 때 소상공인 상가정보)를 우리 기준으로 정리한 것이다.
- '네이버에서 더 찾기'는 검색어 하나당 네이버 지역 검색 결과를 받은 순서 그대로 한 블록씩이다. 합치지 않고, 거르지 않고,
  다시 줄 세우지 않으며, 우리 목록·장소 상세에 넣지 않는다.
외부 호출은 모두 가짜 응답이다.
"""
import pytest
from fastapi.testclient import TestClient

from app import explore, naver_local
from app.main import app

from public_fakes import calls, fake_public_api, store_item, tour_item

HAEUNDAE = (35.1631, 129.1636)


@pytest.fixture
def api(monkeypatch):
    box = fake_public_api(monkeypatch)
    box['tour'] += [
        tour_item(1, '해운대 해수욕장', 35.1587, 129.1604, cat3='A01011200', type_id='12', address='부산광역시 해운대구 우동 1', photo=False),
        tour_item(2, '부산시립미술관', 35.1667, 129.1370, cat3='A02060500', type_id='14', address='부산광역시 해운대구 APEC로 58'),
        tour_item(3, '해운대 전통찻집', 35.1630, 129.1630, cat3='A05020900', address='부산광역시 해운대구 구남로 1'),
        tour_item(4, '해운대 컨벤션', 35.1690, 129.1360, cat3='A02060400', type_id='14', address='부산광역시 해운대구 APEC로 55'),
        tour_item(5, '서울 미술관', 37.57, 126.98, cat3='A02060500', type_id='14', address='서울특별시 종로구 삼청로 1'),
    ]
    box['stores'] += [
        store_item('C1', '동네 카페', 35.1635, 129.1640, code='I21201', label='카페', address='부산광역시 해운대구 구남로 2'),
        store_item('C2', '체인 카페', 35.1632, 129.1637, code='I21201', label='카페', branch='해운대점', address='부산광역시 해운대구 구남로 3'),
        store_item('M1', '해운대 국밥', 35.1640, 129.1645, code='I20102', label='국/탕/찌개류', address='부산광역시 해운대구 구남로 4'),
    ]
    return box


def test_default_list_is_public_data_with_photos_first(api):
    client = TestClient(app)
    data = client.get('/api/explore', params=dict(region='부산')).json()
    assert data['status'] == 'ready' and data['region'] == '부산' and data['activity'] == '전체'
    names = [p['name'] for p in data['places']]
    # 관광지·문화시설만(검색어가 없으면 동네를 몰라 상가정보는 없다). 사진 있는 곳이 먼저, 후보가 아닌 분류·다른 시·도는 빠진다.
    assert names == ['부산시립미술관', '해운대 해수욕장']
    assert all(p['id'].startswith('public:tour-') and p['region'] == '부산' for p in data['places'])
    assert [c['contentTypeId'] for c in calls(api, 'tour_area')] == ['12', '14'] and not calls(api, 'store')
    assert data['center'] is None and '동네 이름' in data['center_hint']
    assert '인기·별점 순위가 아니에요' in data['ranking_method'] and '공공 자료' in data['data_note']
    assert not api['naver'], '기본 목록은 네이버 검색을 부르지 않는다'
    # 다른 사용자가 같은 조건으로 열어도 공공 API 를 다시 부르지 않는다(공공 자료라 나눠 쓴다).
    used = len(api['calls'])
    again = TestClient(app).get('/api/explore', params=dict(region='부산')).json()
    assert [p['id'] for p in again['places']] == [p['id'] for p in data['places']] and len(api['calls']) == used
    # 목록의 장소는 장소 상세에서 열린다.
    assert client.get('/api/places/' + data['places'][0]['id'], params={'mode': 'real'}).json()['name'] == '부산시립미술관'


def test_neighbourhood_query_adds_nearby_shops_from_store_info(api):
    data = TestClient(app).get('/api/explore', params=dict(region='부산', activity='카페', q='해운대')).json()
    assert data['center']['name'] == '해운대' and data['center']['basis'] == 'dictionary' and data['center_hint'] is None
    names = [p['name'] for p in data['places']]
    # 관광공사 카페가 먼저, 그다음 상가정보 카페(지점 표기 없는 곳 먼저). 식당은 카페가 아니라 빠진다.
    assert names == ['해운대 전통찻집', '동네 카페', '체인 카페 해운대점']
    assert [p['public_source'] for p in data['places']] == ['tour', 'store', 'store']
    assert calls(api, 'tour_keyword')[0]['keyword'] == '해운대' and calls(api, 'store')[0]['indsLclsCd'] == 'I2'
    meals = TestClient(app).get('/api/explore', params=dict(region='부산', activity='맛집', q='해운대')).json()
    assert [p['name'] for p in meals['places']] == ['해운대 국밥']


def test_center_comes_from_our_dictionary_or_tour_titles_never_from_naver():
    assert explore.center_for('서울', '성수 카페')['basis'] == 'dictionary'
    assert explore.center_for('서울', '더현대 서울')['name'] == '더현대 서울'
    assert explore.center_for('부산', '성수') is None, '다른 시·도의 동네 이름은 쓰지 않는다'
    rows = [dict(title='광안리해수욕장', lat=35.153, lon=129.118), dict(title='광안리 카페거리', lat=35.155, lon=129.120),
            dict(title='다른 곳', lat=35.3, lon=129.3)]
    center = explore.center_for('부산', '광안리', rows)
    assert center['basis'] == 'tour_keyword' and abs(center['lat'] - 35.155) < 1e-9
    assert explore.center_for('부산', '광', rows) is None and explore.center_for('부산', '없는동네', rows) is None


def test_invalid_conditions_missing_key_and_failures(api, monkeypatch):
    client = TestClient(app)
    assert client.get('/api/explore', params=dict(region='도쿄')).status_code == 422
    assert client.get('/api/explore', params=dict(region='부산', activity='골프')).status_code == 422
    assert client.get('/api/explore/naver', params=dict(region='부산', activity='골프')).status_code == 422
    api['fail'] |= {'tour_area'}
    failed = explore.results('대구', '박물관')
    assert failed['status'] == 'unavailable' and failed['places'] == []
    api['fail'].clear()
    api['tour'].append(tour_item(9, '대구 박물관', 35.87, 128.6, cat3='A02060100', type_id='14', address='대구광역시 중구 국채보상로 1'))
    # 실패는 목록으로 보관하지 않아, 실패 표시(60초)가 지나면 다음 요청이 다시 찾는다.
    from app import store
    with store.connect() as db:
        db.execute("DELETE FROM cache WHERE key LIKE 'public-tour-area-%'")
    assert [p['name'] for p in explore.results('대구', '박물관')['places']] == ['대구 박물관']
    monkeypatch.setenv('TOUR_API_KEY', '')
    data = client.get('/api/explore', params=dict(region='제주', activity='카페', q='키없음점검')).json()
    assert data['status'] == 'key_missing' and data['places'] == [] and data['total'] == 0


# ---------------------------------------------------------------- 네이버에서 더 찾기


def local(title, address, category='카페,디저트', x='1291636000', y='351631000', link=''):
    return dict(title=title, category=category, roadAddress=address, address='', mapx=x, mapy=y, telephone='', description='', link=link)


def test_naver_queries_are_few_and_each_is_one_block():
    for activity in ['', *explore.ACTIVITIES]:
        for q in ('', '해운대'):
            planned = explore.naver_queries('부산', activity, q)
            assert 0 < len(planned) <= explore.MAX_NAVER_QUERIES and all(p.startswith('부산 ') for p in planned)
            assert all(q in p for p in planned) and all(activity in p for p in planned)
    assert explore.naver_queries('부산')[0] == '부산 데이트 장소'


def test_naver_blocks_keep_what_naver_returned_in_its_order(api, monkeypatch):
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID', 'test')
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET', 'secret')
    asked = []

    def lookup(client, query):
        asked.append(query)
        rows = [local(f'<b>바다</b>카페 {query[-2:]}', '부산광역시 해운대구 구남로 1', link='https://example.com/cafe'),
                local('같은 가게', '부산광역시 해운대구 구남로 9'),
                local('서울 가게 &amp; 병원', '서울특별시 중구 명동길 1', category='병원,의원'),
                local('같은 가게', '부산광역시 해운대구 구남로 9')]
        return query, rows, 'available'

    monkeypatch.setattr(explore, 'lookup', lookup)
    client = TestClient(app)
    data = client.get('/api/explore/naver', params=dict(region='부산', activity='카페', q='해운대')).json()
    planned = ['부산 해운대 카페', '부산 해운대 데이트 카페']
    assert data['status'] == 'ready' and sorted(asked) == sorted(planned)
    assert [b['query'] for b in data['blocks']] == planned, '검색어 하나가 블록 하나'
    block = data['blocks'][0]
    # 받은 순서·건수 그대로: 다른 시·도, 우리가 쓰지 않는 업종, 같은 가게가 두 번 나와도 빼거나 합치지 않는다.
    assert [i['title'] for i in block['items']] == ['바다카페 카페', '같은 가게', '서울 가게 & 병원', '같은 가게']
    first = block['items'][0]
    assert set(first) == {'title', 'category', 'road_address', 'address', 'description', 'telephone', 'link', 'map_url'}
    assert first['category'] == '카페,디저트' and first['link'] == 'https://example.com/cafe'
    assert first['map_url'].startswith('https://map.naver.com/p/search/') and block['search_url'].startswith('https://map.naver.com/p/search/')
    # 좌표·우리 분류·우리 id 를 만들지 않고, 장소 상세·추천 후보에 넣지 않는다.
    text = str(data)
    assert 'mapx' not in text and 'discovered:' not in text and 'public:' not in text and '카페·미식' not in text
    from app import public_places
    from app.catalog import places
    assert public_places.candidates() == [] and not [p for p in places('real') if p['name'] == '같은 가게']
    # 같은 사용자의 같은 조건은 다시 부르지 않는다. 공공 API 도 부르지 않는다.
    client.get('/api/explore/naver', params=dict(region='부산', activity='카페', q='해운대'))
    assert len(asked) == 2 and not api['calls']


def test_naver_blocks_without_key_or_permission(monkeypatch):
    assert explore.naver_blocks('부산')['status'] == 'key_missing'
    monkeypatch.setattr(explore, 'search_enabled', lambda: True)
    monkeypatch.setattr(explore, 'lookup', lambda client, query: (query, [], 'permission_required'))
    data = explore.naver_blocks('대구', '서점', '권한점검')
    assert data['status'] == 'permission_required' and all(b['items'] == [] for b in data['blocks'])
    calls_ = []
    monkeypatch.setattr(explore, 'lookup', lambda client, query: (calls_.append(query), (query, [], 'available'))[1])
    assert explore.naver_blocks('대구', '서점', '권한점검')['status'] == 'empty' and calls_, '실패는 보관하지 않는다'


def test_original_items_only_strip_highlight_tags():
    rows = naver_local.original_items([local('<b>성수</b> 카페 &lt;본점&gt;', '서울특별시 성동구 연무장길 1', link='javascript:alert(1)'), 'bad'])
    assert rows == [dict(title='성수 카페 <본점>', category='카페,디저트', road_address='서울특별시 성동구 연무장길 1', address='', description='',
                         telephone='', link=None, map_url='https://map.naver.com/p/search/' + __import__('urllib.parse').parse.quote('성수 카페 <본점> 서울특별시 성동구 연무장길 1'))]
