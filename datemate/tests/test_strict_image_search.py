"""엄격한 가게 사진 검색(2026-11-19 사용자 결정, app/image_search.strict_title_match·strict_place_images).

공식 이미지 검색 API 는 사진이 실린 글의 제목만 준다. 제목에 가게 이름(지점 포함)과 동네·주소 낱말이 함께 나온 사진만 쓰고,
이름이 비슷한 다른 지점·다른 가게, 동네가 없는 제목, 여러 가게를 모은 글, 다른 시·도 제목은 뺀다. 외부 호출은 하지 않는다(가짜 응답).
제목 예시는 2026-11-19 실제 API 표본(금돼지식당·어니언 성수)에서 본 모양을 따랐다.
"""
import httpx
import pytest

from app import store
from app.image_search import locality_words, split_branch, strict_place_images, strict_title_match

PIG = dict(id='strict-pig', name='금돼지식당', address='서울 중구 다산로 149', region='서울', category='카페·미식')
MINARI = dict(id='strict-minari', name='능동미나리 용산점', address='서울 용산구 한강대로40길 28', region='서울', category='카페·미식')
KYOJA = dict(id='strict-kyoja', name='명동교자 본점', address='서울 중구 명동10길 29', region='서울', category='카페·미식')


def test_locality_words_come_from_district_dong_and_road_names():
    assert locality_words(dict(address='서울 마포구 독막로8길 16')) == {'마포구', '마포', '독막로', '독막'}
    assert locality_words(PIG) == {'중구', '다산로', '다산'}
    # 지번 주소(식당 검색 결과의 lot_address)가 있으면 동 이름도 쓴다.
    words = locality_words(dict(address='서울 성동구 아차산로9길 8', lot_address='서울특별시 성동구 성수동2가 280-10'))
    assert {'성수동', '성수', '성동구', '아차산로'} <= words and '서울특별시' not in words
    assert split_branch('오레노라멘 합정본점') == ('오레노라멘', '합정본점') and split_branch('어니언') == ('어니언', '')


@pytest.mark.parametrize('place,title', [
    (PIG, '금돼지식당 - 중구 - 방문자 557명의 팁 22개에서의 사진'),
    (PIG, '#금돼지식당웨이팅 #다산로'),
    (PIG, '금돼지식당에서 중구 약수 점심'),
    (MINARI, '능동미나리 용산점 다녀옴'),
    (MINARI, '능동미나리 용산 한강대로 맛집'),
    (KYOJA, '명동교자 본점 명동 칼국수'),
    (KYOJA, '명동교자 명동 본점 웨이팅'),
])
def test_name_branch_and_neighbourhood_together_are_accepted(place, title):
    assert strict_title_match(place, title)


@pytest.mark.parametrize('place,title,why', [
    (PIG, '#오늘여기클립 약수 서울3대 고깃집 #금돼지식당 쏘쏘함', '동네·주소 낱말 없음'),
    (PIG, '‘TBJ X 금돼지식당’ 콜라보레이션 컬렉션', '동네 없음(뉴스·협업 사진)'),
    (PIG, '금돼지식당 강남점 중구', '다른 지점'),
    (PIG, '왕금돼지식당 중구', '앞에 글자가 붙은 다른 가게'),
    (PIG, '금돼지식당이야기 중구', '뒤에 글자가 붙은 다른 가게'),
    (PIG, '서울 중구 고깃집 BEST 5 금돼지식당', '여러 가게를 모은 글'),
    (PIG, '중구 맛집 3곳 금돼지식당', '여러 가게를 모은 글'),
    (PIG, '금돼지식당 부산 중구 맛집', '다른 시·도'),
    (MINARI, '능동미나리 강남점 후기', '다른 지점'),
    (MINARI, '능동미나리 맛집 추천', '지점·동네 없음'),
    (KYOJA, '명동교자 본점 칼국수', "이름 속 '명동'은 동네로 세지 않음"),
    (KYOJA, '명동교자 분점 명동', '다른 지점'),
    (dict(name='정면', address='서울 광진구 능동로13길 88'), '정면 능동 맛집', '두 글자 이름은 찾지 않음'),
])
def test_other_branches_other_shops_and_vague_titles_are_rejected(place, title, why):
    assert strict_title_match(place, title) is None, why


def fake_api(monkeypatch, titles_by_query):
    calls = []

    def get(self, url, **kwargs):
        query = kwargs['params']['query']
        calls.append(query)
        assert url == 'https://naverapihub.apigw.ntruss.com/search/v1/image'
        items = [dict(title=t, thumbnail=f'https://search.pstatic.net/{abs(hash(t))}.jpg', link=link)
                 for t, link in titles_by_query.get(query, [])]
        return httpx.Response(200, request=httpx.Request('GET', url), json={'items': items})

    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID', 'test')
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET', 'test')
    monkeypatch.setattr(httpx.Client, 'get', get)
    return calls


def test_strict_search_shapes_photos_caches_and_stops_after_two_queries(monkeypatch):
    place = dict(PIG, id='strict-pig-search')
    calls = fake_api(monkeypatch, {
        '금돼지식당 서울 중구 다산로 149': [
            ('금돼지식당 강남점 중구', 'https://postfiles.pstatic.net/other.jpg'),
            ('<b>금돼지식당</b> 중구 다산로 본점 웨이팅', 'https://postfiles.pstatic.net/ok.jpg'),
            ('금돼지식당 중구 같은 사진', 'https://postfiles.pstatic.net/ok.jpg'),
            ('금돼지식당 중구 위험 주소', 'javascript:alert(1)'),
        ],
    })
    result = strict_place_images(place)
    assert result['status'] == 'available' and len(result['photos']) == 1
    photo = result['photos'][0]
    assert photo['kind'] == 'image_search' and photo['source_label'] == '검색 사진'
    assert photo['image_url'] == photo['source'] == 'https://postfiles.pstatic.net/ok.jpg'
    assert photo['url'].startswith('https://search.pstatic.net/') and '<b>' not in photo['title']
    assert photo['search_url'].startswith('https://search.naver.com/search.naver?where=image')
    assert photo['license'] is None and 'test' not in str(photo)
    # 맞는 사진이 3장이 안 돼 두 번째 검색어(이름 + 동네 낱말)까지 부르고 멈춘다.
    assert calls == ['금돼지식당 서울 중구 다산로 149', '금돼지식당 다산로']
    # 같은 장소는 캐시로 답한다(외부 호출 없음).
    assert strict_place_images(place) == result and len(calls) == 2


def test_strict_search_failure_is_not_cached_and_short_names_are_not_searched(monkeypatch):
    calls = fake_api(monkeypatch, {})
    place = dict(PIG, id='strict-pig-fail')

    def boom(self, url, **kwargs):
        calls.append('boom')
        raise httpx.ConnectError('down')

    monkeypatch.setattr(httpx.Client, 'get', boom)
    assert strict_place_images(place) == {'status': 'unavailable', 'photos': []}
    assert strict_place_images(place)['status'] == 'unavailable' and calls == ['boom', 'boom']
    short = dict(id='strict-short', name='정면', address='서울 광진구 능동로13길 88', category='카페·미식')
    assert strict_place_images(short) == {'status': 'not_applicable', 'photos': []} and len(calls) == 2
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID', '')
    assert strict_place_images(dict(PIG, id='strict-no-key'))['status'] == 'key_missing'
    assert strict_place_images(dict(PIG, demo=True))['status'] == 'demo'


def test_media_route_does_not_resize_or_cache_search_photos(monkeypatch):
    # 2026-11-20 네이버 검색 API 특약 2.2·2.3: 검색 결과 사진은 줄이지(가공) 않고 서버에 담아 두지(캐싱) 않는다. 브라우저가 원본을 받는다.
    """카드에는 기존 /photo-thumb 축소를 쓴다: 검색 사진 원본(허용 호스트)도 thumb_url 을 받고 허용 목록에 오른다."""
    from fastapi.testclient import TestClient
    from app import photo_thumb
    from app.main import app

    original = 'https://imgnews.naver.net/strict/news.jpg'
    photo = dict(id='image-search-x', kind='image_search', title='검색 사진', image_url=original, url='https://search.pstatic.net/x.jpg', source=original)
    monkeypatch.setattr('app.main.media_info', lambda *a, **k: dict(photos=[photo, dict(photo, id='y', image_url='https://example.com/a.jpg')]))
    monkeypatch.setattr('app.place_identity.verify_identity', lambda p: dict(verified=False))
    monkeypatch.setattr('app.tour_places.tour_hours', lambda p: None)
    with TestClient(app) as client:
        body = client.get('/api/places/Q482485/media', params={'mode': 'real'}).json()
    first, second = body['photos']
    assert 'thumb_url' not in first
    assert store.cached(photo_thumb.allow_key(original)) is None
    # 허용 호스트가 아닌 원본은 줄이지 않는다(브라우저가 원본을 직접 받음). 열린 중계가 되지 않는다.
    assert 'thumb_url' not in second
    assert not photo_thumb.allowed_source('https://imgnews.naver.net.evil.example/a.jpg')
    assert not photo_thumb.allowed_source('http://imgnews.naver.net/a.jpg')
