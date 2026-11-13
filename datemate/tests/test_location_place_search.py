"""데이트할 지역 검색: 주소 검색에 결과가 없을 때만 역·가게·명소 이름(네이버 지역 검색)으로 한 번 더 찾는다.

외부 API는 부르지 않는다. httpx.Client.get 을 가짜 응답으로 바꾼다."""
import uuid

import httpx
from fastapi.testclient import TestClient

from app.geocoding import search_places, with_place_fallback
from app.main import app
from app.regions import region_from_address

GEOCODE = 'map-geocode'
LOCAL = 'search/v1/local'
GANGNAM = {'title': '<b>강남역</b> 2호선', 'category': '교통,수송&gt;지하철,전철',
           'address': '서울특별시 강남구 역삼동 858', 'roadAddress': '서울특별시 강남구 강남대로 지하 396',
           'mapx': '1270276023', 'mapy': '374979502'}
NOWHERE = {'title': '<b>어딘가</b> 가게', 'category': '음식점>한식', 'address': '', 'roadAddress': '',
           'mapx': '1270276023', 'mapy': '374979502'}
ABROAD = {'title': '해외 매장', 'category': '쇼핑', 'address': 'New York', 'roadAddress': '',
          'mapx': '-740060000', 'mapy': '407128000'}


def keys(monkeypatch, maps=True, search=True):
    for name in ('NAVER_MAPS_KEY_ID', 'NAVER_MAPS_KEY'):
        monkeypatch.setenv(name, 'test' if maps else '')
    for name in ('NAVER_SEARCH_CLIENT_ID', 'NAVER_SEARCH_CLIENT_SECRET'):
        monkeypatch.setenv(name, 'test' if search else '')


def provider(monkeypatch, addresses=(), items=()):
    """주소 검색·지역 검색 가짜 응답. 부른 서비스를 순서대로 기록한다."""
    calls = []

    def get(self, url, **kwargs):
        if GEOCODE in url:
            calls.append('geocode')
            return httpx.Response(200, json={'status': 'OK', 'addresses': list(addresses)}, request=httpx.Request('GET', url))
        if LOCAL in url:
            calls.append('local')
            return httpx.Response(200, json={'items': list(items)}, request=httpx.Request('GET', url))
        raise AssertionError('unexpected provider call: ' + url)

    monkeypatch.setattr(httpx.Client, 'get', get)
    return calls


def unique(name):
    # 지역 검색 결과는 검색어별로 캐시되므로 테스트마다 다른 검색어를 쓴다.
    return name + ' ' + uuid.uuid4().hex[:8]


def post(query):
    n = uuid.uuid4().int
    with TestClient(app, client=(f'198.19.{n % 250}.{(n >> 8) % 250 + 1}', 1)) as client:
        response = client.post('/api/locations/search', json={'query': query})
    assert response.status_code == 200
    return response.json()


def test_station_name_falls_back_to_place_search(monkeypatch):
    keys(monkeypatch)
    calls = provider(monkeypatch, items=[GANGNAM, ABROAD])
    data = post(unique('강남역'))
    assert calls == ['geocode', 'local']
    assert data['status'] == 'ok' and data['message'] == '' and data['provider'] == 'NAVER 지역 검색'
    # 해외 좌표는 뺀다.
    assert len(data['results']) == 1
    point = data['results'][0]
    # <b> 태그와 HTML 엔티티는 정리한다.
    assert point['place_name'] == '강남역 2호선' and point['category'] == '교통,수송>지하철,전철'
    # 이름은 주소(도로명 우선)여서 기존 화면과 같은 방식으로 시·도를 판정한다.
    assert point['name'] == GANGNAM['roadAddress'] and point['road_address'] == GANGNAM['roadAddress']
    assert point['jibun_address'] == GANGNAM['address']
    assert region_from_address(point['name']) == '서울'
    assert abs(point['lat'] - 37.4979502) < 1e-9 and abs(point['lon'] - 127.0276023) < 1e-9


def test_address_results_skip_place_search(monkeypatch):
    keys(monkeypatch)
    calls = provider(monkeypatch, addresses=[{'roadAddress': '대전광역시 중구 대종로480번길 15', 'jibunAddress': '대전광역시 중구 은행동 145',
                                              'x': '127.4273', 'y': '36.3276'}], items=[GANGNAM])
    data = post(unique('대전 중구 대종로480번길 15'))
    assert calls == ['geocode']
    assert data['provider'] == 'NAVER Maps' and data['results'][0]['name'] == '대전광역시 중구 대종로480번길 15'
    assert 'place_name' not in data['results'][0]


def test_without_search_key_keeps_address_message(monkeypatch):
    keys(monkeypatch, search=False)
    calls = provider(monkeypatch, items=[GANGNAM])
    data = post(unique('강남역'))
    assert calls == ['geocode']
    assert data['status'] == 'ok' and data['results'] == []
    assert data['message'].startswith('주소를 찾지 못했습니다.')


def test_place_search_without_maps_key_and_empty_place_results(monkeypatch):
    # 지도 키가 없어도 검색 키가 있으면 장소 이름으로는 찾는다.
    keys(monkeypatch, maps=False)
    calls = provider(monkeypatch, items=[GANGNAM])
    data = post(unique('강남역'))
    assert calls == ['local'] and data['status'] == 'ok' and data['results'][0]['place_name'] == '강남역 2호선'
    # 장소도 없으면 주소 검색의 안내를 그대로 돌려준다.
    keys(monkeypatch, maps=False)
    provider(monkeypatch, items=[])
    data = post(unique('없는곳'))
    assert data['status'] == 'key_missing' and data['results'] == []


def test_place_search_failure_falls_back_to_address_message(monkeypatch):
    keys(monkeypatch)

    def get(self, url, **kwargs):
        if GEOCODE in url:
            return httpx.Response(200, json={'status': 'OK', 'addresses': []}, request=httpx.Request('GET', url))
        raise httpx.ConnectError('secret')

    monkeypatch.setattr(httpx.Client, 'get', get)
    data = post(unique('대전 성심당'))
    assert data['results'] == [] and data['message'].startswith('주소를 찾지 못했습니다.') and 'secret' not in str(data)


def test_place_without_province_is_kept_for_screen_to_disable(monkeypatch):
    keys(monkeypatch)
    provider(monkeypatch, items=[NOWHERE])
    results = search_places(unique('어딘가'))
    assert len(results) == 1
    point = results[0]
    # 주소가 없으면 이름만 남고, 시·도를 판정할 수 없다(화면은 이 결과를 고를 수 없게 한다).
    assert point['place_name'] == '어딘가 가게' and point['road_address'] is None and point['jibun_address'] is None
    assert not region_from_address(point['name'])


def test_with_place_fallback_returns_address_results_untouched(monkeypatch):
    keys(monkeypatch)
    calls = provider(monkeypatch, items=[GANGNAM])
    found = {'status': 'ok', 'results': [{'name': '서울특별시 마포구 연남동', 'lat': 37.56, 'lon': 126.92}], 'message': ''}
    assert with_place_fallback('연남동', found) is found
    assert calls == []
