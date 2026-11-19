"""네이버 약관 준수(2026-11-19): 화면 자동 조회를 끄고 공식 API·공공데이터로 대신한다.

- app/naver_pages.py 가 꺼져 있으면 search.naver.com·m.place.naver.com·m.blog.naver.com 에 요청이 나가지 않는다.
- 메뉴 가격은 공식 블로그 검색 API 요약문의 가격으로(app/menus.py blog_menu), 없으면 네이버 지도 링크로 안내한다.
- 같은 업체 확인은 공식 지역 검색 API 로(app/place_identity.py), 사진·영업 안내는 한국관광공사 TourAPI 로(app/tour_places.py).
"""
import httpx
import pytest

from app import naver_pages, place_identity, tour_places

PLACE = dict(id='p1', name='어니언 성수점', category='카페·미식', lat=37.5446, lon=127.0557, address='서울 성동구 아차산로9길 8', region='서울')


@pytest.fixture
def no_naver_pages(monkeypatch):
    """네이버 화면 주소로 나가는 요청이 있으면 실패시킨다."""
    seen = []
    real_get, real_stream = httpx.Client.get, httpx.Client.stream

    def guard(url):
        host = httpx.URL(str(url)).host
        if host in ('search.naver.com', 'm.place.naver.com', 'm.blog.naver.com', 'blog.naver.com', 'pcmap.place.naver.com'):
            seen.append(str(url))
            raise AssertionError('네이버 화면 자동 조회: ' + str(url))

    monkeypatch.setattr(httpx.Client, 'get', lambda self, url, *a, **k: (guard(url), real_get(self, url, *a, **k))[1])
    monkeypatch.setattr(httpx.Client, 'stream', lambda self, method, url, *a, **k: (guard(url), real_stream(self, method, url, *a, **k))[1])
    monkeypatch.setattr(httpx, 'get', lambda url, *a, **k: (guard(url), (_ for _ in ()).throw(httpx.ConnectError('offline')))[1])
    return seen


def test_gate_is_off_by_default():
    assert naver_pages.allowed() is False


def test_page_fetchers_do_not_touch_naver_pages(no_naver_pages, monkeypatch):
    from app.blog_photos import read_post
    from app.course_search import public_body
    from app.public_place_photos import public_place_photos

    monkeypatch.setattr('app.store.cached', lambda key: None)
    assert public_body('https://blog.naver.com/a/1') == ''
    assert read_post(dict(url='https://blog.naver.com/a/1'), PLACE) == []
    assert public_place_photos(PLACE)['photos'] == []
    assert no_naver_pages == []


def test_menu_uses_blog_api_quotes_and_points_to_naver_map(no_naver_pages, monkeypatch):
    from app import menus

    monkeypatch.setattr('app.store.cached', lambda key: None)
    quotes = [dict(item='카페라떼', amount=6500, source='https://blog.naver.com/a/1', posted_at='2026-10-01'),
              dict(item='카페라떼', amount=7000, source='https://blog.naver.com/b/2', posted_at='2026-10-02')]
    monkeypatch.setattr('app.pricing.lookup_price', lambda place, force=False: dict(status='available', quotes=quotes))
    menu = menus.restaurant_menu(PLACE)
    assert menu['status'] == 'available' and [i['name'] for i in menu['items']] == ['카페라떼']
    assert menu['items'][0]['amount'] == 6500 and menu['source_label'] == '블로그 글에 나온 가격'
    assert menu['source_url'].startswith('https://map.naver.com/p/search/')
    assert menus.cost_menu_options(menu)[0]['amount'] == 6500
    monkeypatch.setattr('app.pricing.lookup_price', lambda place, force=False: dict(status='not_found', quotes=[]))
    empty = menus.restaurant_menu(PLACE)
    assert empty['status'] == 'not_found' and '네이버 지도에서 확인' in empty['message']
    assert no_naver_pages == []


def local_item(title, lat, lon):
    return dict(title=f'<b>{title}</b>', mapx=str(int(lon * 1e7)), mapy=str(int(lat * 1e7)))


def test_identity_needs_same_name_within_400m_and_only_one():
    near = local_item('어니언', 37.5448, 127.0559)
    assert place_identity.matches(PLACE, [near]) == 1, '지점 낱말을 뗀 이름도 같은 업체로 본다'
    assert place_identity.matches(PLACE, [local_item('어니언 성수점', 37.5600, 127.0700)]) == 0, '400m 밖'
    assert place_identity.matches(PLACE, [local_item('다른 카페', 37.5447, 127.0558)]) == 0
    assert place_identity.matches(PLACE, [near, local_item('어니언 성수점', 37.5445, 127.0556)]) == 2


def test_identity_api_result(monkeypatch):
    monkeypatch.setattr('app.store.cached', lambda key: None)
    monkeypatch.setattr('app.store.cache', lambda *a: None)
    monkeypatch.setattr('app.image_search.search_enabled', lambda: True)
    monkeypatch.setattr('app.discovery.local_lookup', lambda name, area, sort='random': ([local_item('어니언', 37.5448, 127.0559)], 'available'))
    assert place_identity.verify_identity(PLACE) == dict(verified=True, method='naver_local_search_api')
    monkeypatch.setattr('app.discovery.local_lookup', lambda name, area, sort='random': ([], 'unavailable'))
    assert place_identity.verify_identity(PLACE)['verified'] is False


def tour_row(title, lat, lon, image='https://tong.visitkorea.or.kr/a.jpg', kind='Type1', content='123', type_id='39'):
    return dict(title=title, mapy=str(lat), mapx=str(lon), firstimage=image, cpyrhtDivCd=kind, contentid=content, contenttypeid=type_id)


def test_tour_same_place_rules():
    assert tour_places.same_place(PLACE, [tour_row('어니언 성수', 37.5447, 127.0558)]) is None, '이름이 다르면 연결하지 않는다'
    assert tour_places.same_place(PLACE, [tour_row('어니언', 37.5447, 127.0558)])['contentid'] == '123'
    assert tour_places.same_place(PLACE, [tour_row('어니언', 37.5447, 127.0558), tour_row('어니언', 37.5449, 127.0559, content='9')]) is None
    assert tour_places.same_place(PLACE, [tour_row('어니언', 37.5600, 127.0800)]) is None, '400m 밖'


def test_tour_info_photo_license_and_hours(monkeypatch):
    monkeypatch.setenv('TOUR_API_KEY', 'test-key')
    monkeypatch.setattr('app.store.cached', lambda key: None)
    monkeypatch.setattr('app.store.cache', lambda *a: None)
    pages = {}

    def handler(request):
        if request.url.path.endswith('searchKeyword2'):
            return httpx.Response(200, json=dict(response=dict(header=dict(resultCode='0000'), body=dict(items=dict(item=[pages['row']])))))
        return httpx.Response(200, json=dict(response=dict(header=dict(resultCode='0000'), body=dict(items=dict(item=[dict(opentimefood='10:00~22:00<br>(라스트오더 21:30)', restdatefood='연중무휴')])))))

    real = httpx.Client.__init__
    monkeypatch.setattr(httpx.Client, '__init__', lambda self, *a, **k: real(self, *a, **dict(k, transport=httpx.MockTransport(handler))))
    pages['row'] = tour_row('어니언', 37.5447, 127.0558)
    info = tour_places.tour_info(PLACE)
    assert info['hours'] == '10:00~22:00 / (라스트오더 21:30)' and info['rest'] == '연중무휴'
    assert tour_places.tour_photos(PLACE)[0]['license'].startswith('공공누리 제1유형')
    assert tour_places.tour_hours(PLACE)['source_url'].endswith('cotid=123')
    pages['row'] = tour_row('어니언', 37.5447, 127.0558, kind='Type3')
    assert '제3유형' in tour_places.tour_photos(PLACE)[0]['license'], '축제 사진과 같은 기준(원본 그대로 표시)'
    pages['row'] = tour_row('어니언', 37.5447, 127.0558, kind='Type4')
    assert tour_places.tour_photos(PLACE) == [], '그 밖의 유형·유형 없음은 쓰지 않는다'
    monkeypatch.setenv('TOUR_API_KEY', '')
    assert tour_places.tour_info(PLACE) == dict(status='key_missing')


def test_tour_title_tags_and_http_images_from_the_real_api(monkeypatch):
    """2026-11-19 실제 응답: 제목 앞 '[K드라마 촬영지]' 꼬리표, 사진 주소 http://tong.visitkorea.or.kr/..."""
    gallery = dict(PLACE, name='공근혜갤러리')
    row = tour_row('[K드라마 촬영지] 공근혜갤러리', 37.5447, 127.0558, image='http://tong.visitkorea.or.kr/cms/a.jpg', type_id='14')
    assert tour_places.same_place(gallery, [row]) is row
    assert tour_places.same_place(dict(PLACE, name='경복궁'), [tour_row('경복궁(景福宮)', 37.5447, 127.0558)]) is not None
    monkeypatch.setenv('TOUR_API_KEY', 'test-key')
    monkeypatch.setattr('app.store.cached', lambda key: None)
    monkeypatch.setattr('app.store.cache', lambda *a: None)

    def handler(request):
        item = row if request.url.path.endswith('searchKeyword2') else dict(usetimeculture='10:30 ~ 17:30', restdateculture='매주 일, 월 휴무')
        return httpx.Response(200, json=dict(response=dict(header=dict(resultCode='0000'), body=dict(items=dict(item=[item])))))

    real = httpx.Client.__init__
    monkeypatch.setattr(httpx.Client, '__init__', lambda self, *a, **k: real(self, *a, **dict(k, transport=httpx.MockTransport(handler))))
    photo = tour_places.tour_photos(gallery)[0]
    assert photo['image_url'] == 'https://tong.visitkorea.or.kr/cms/a.jpg'
    assert tour_places.tour_hours(gallery)['hours'] == '10:30 ~ 17:30'
    other = dict(row, firstimage='http://example.com/a.jpg', firstimage2='')
    monkeypatch.setattr(tour_places, 'same_place', lambda place, rows: other)
    assert tour_places.tour_photos(gallery) == [], '관광공사 사진 호스트가 아니면 쓰지 않는다'
