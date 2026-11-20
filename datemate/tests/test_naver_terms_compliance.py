"""네이버 약관 준수(2026-11-19): 화면 자동 조회를 끄고 공식 API·공공데이터로 대신한다.

- app/naver_pages.py 가 꺼져 있으면 search.naver.com·m.place.naver.com·m.blog.naver.com 에 요청이 나가지 않는다.
- 메뉴 가격은 읽어 오지 않고 네이버 지도 링크로 안내한다(app/menus.py map_menu_link. 블로그 요약의 가격은 2단계에서 없앰).
- 같은 업체 확인은 공공 자료로(app/place_identity.py, tests/test_public_identity.py), 사진·영업 안내는 한국관광공사 TourAPI 로(app/tour_places.py).
"""
import httpx
import pytest

from app import naver_pages, tour_places

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
    from app.public_place_photos import public_place_photos
    from app.review_facts import BlogText, public_body

    monkeypatch.setattr('app.store.cached', lambda key: None)
    assert public_body('https://blog.naver.com/a/1') == ''
    assert public_body('https://example.com/private') == ''
    # 남겨 둔 본문 읽기 규칙: 본문 칸의 글자만, 스크립트·메뉴는 뺀다.
    parser = BlogText()
    parser.feed('<div>navigation</div><div class="se-main-container"><div>서울숲</div><script>fake</script>산책</div><div>footer</div>')
    assert ' '.join(parser.parts) == '서울숲 산책'
    assert read_post(dict(url='https://blog.naver.com/a/1'), PLACE) == []
    assert public_place_photos(PLACE)['photos'] == []
    assert no_naver_pages == []


def test_menu_reads_no_price_and_points_to_naver_map(no_naver_pages, monkeypatch):
    """모아 둔 메뉴가 없는 식당: 블로그 검색 요약에서 가격을 읽지 않고(검색 API 호출 없음) 네이버 지도 링크만 준다."""
    from app import menus

    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID', 'test')
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET', 'secret')
    monkeypatch.setattr('app.store.cached', lambda key: None)
    monkeypatch.setattr(httpx.Client, 'request', lambda self, *a, **k: pytest.fail('외부 호출'))
    menu = menus.restaurant_menu(PLACE, force=True)
    assert menu['status'] == 'not_found' and menu['items'] == [] and menu['reason'] == 'not_collected'
    assert menu['source_kind'] == 'map_link' and menu['source_url'].startswith('https://map.naver.com/p/search/')
    assert '네이버 지도에서 확인' in menu['message'] and '블로그' not in menu['message']
    assert menus.cost_menu_options(menu) == []
    assert not hasattr(menus, 'blog_menu')
    assert no_naver_pages == []


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
