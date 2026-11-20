"""장소 사진을 한국관광공사 자료에서 찾는 규칙(app/tour_places.py, 2026-11-20 사진 보강).

- 이름 맞추기: 같은 이름 → 느슨한 이름(지역 앞말·뜻이 같은 꼬리말) 두 단계, 단계마다 '반경 안에 하나뿐일 때만'. 다른 업종·편의점·다른 지역 가게는 붙지 않는다.
- 거리: 해변·공원처럼 넓은 곳 1km, 그 밖 400m.
- 대표 사진(firstimage)이 없으면 detailImage2 의 공공누리 제1·제3유형 사진을 쓴다. 관광공사 항목 번호가 있는 후보는 이름으로 다시 찾지 않는다.
- 공공 API 오류(HTTP 403, HTTP 200 + 오류 본문)는 '없음'으로 저장하지 않고 짧게만 둔다. '사진 다시 불러오기'는 그때만 뜻이 있다.
이름 규칙의 표본은 2026-11-20 실제 응답(searchKeyword2 keyword=한담, detailImage2 contentId=2723542)에서 필요한 값만 옮긴 것이다.
외부 호출은 모두 가짜 응답이다(tests/public_fakes.py, httpx.MockTransport).
"""
import time

import httpx
import pytest

from app import media, place_identity, public_places, store, tour_places
from public_fakes import calls, fake_public_api, image_item, tour_item

AEWOL = '제주특별자치도 제주시 애월읍 '


def row(content_id, type_id, title, address, lon, lat, lcls, kind, image=True):
    return dict(contentid=content_id, contenttypeid=type_id, title=title, addr1=address, mapx=str(lon), mapy=str(lat), lclsSystm3=lcls,
                cpyrhtDivCd=kind, firstimage=f'https://tong.visitkorea.or.kr/cms/resource/{content_id}.jpg' if image else '')


# 실제 응답 5건: 한담해변은 대표 사진이 없고(cpyrhtDivCd 도 빈 값), 321m 옆 공원·396m 옆 산책로·편의점·인천의 식당이 함께 나온다.
HANDAM = [
    row('3056625', '12', '애월한담공원', AEWOL + '애월로 11', 126.31126447797632, 33.46002879059966, 'NA020800', 'Type3'),
    row('2853930', '39', '한담민물장어', '인천광역시 연수구 인권로 26 (옥련동)', 126.6533958229, 37.4191070735, 'FD010100', 'Type3'),
    row('2723542', '12', '한담해변', AEWOL + '애월로1길 26-4', 126.3100950683, 33.4627528206, 'NA020900', '', image=False),
    row('2930935', '12', '한담해안산책로', AEWOL + '곽지리', 126.3105978795, 33.4591976873, 'NA050100', 'Type1'),
    row('4009600', '38', 'CU 제주애월한담점', AEWOL + '애월로 37', 126.312270179629, 33.4621761546953, 'SH040300', 'Type3'),
]
BEACH = (33.4627528206, 126.3100950683)


def place(name, at=BEACH, category='산책·풍경', **more):
    return dict(dict(id='catalog-' + name, name=name, region='제주', address=AEWOL + '애월로1길 26-4', lat=at[0], lon=at[1], category=category), **more)


def north(metres, at=BEACH):
    return at[0] + metres / 111_320, at[1]


def linked(target, rows=HANDAM):
    found = tour_places.same_place(target, rows)
    return found and found['contentid']


# ---------------------------------------------------------------- 이름


def test_same_name_wins_and_spacing_or_symbols_do_not_matter():
    for name in ('한담해변', '한담 해변', '한담-해변', '[제주] 한담해변', '한담해변(漢潭海邊)'):
        assert linked(place(name)) == '2723542', name
    assert linked(place('한담해안산책로')) == '2930935'
    assert linked(place('애월한담공원')) == '3056625'


def test_region_prefix_and_same_meaning_suffix_are_ignored_in_the_second_step():
    # 지역 앞말(주소의 시·도·시·군·구·읍·면 이름)과 뜻이 같은 꼬리말(해수욕장=해변=비치)만 느슨하게 본다.
    for name in ('애월 한담해변', '제주 한담해변', '제주시 애월읍 한담해변', '한담해수욕장', '애월한담비치'):
        target = place(name)
        assert linked(target) == '2723542', name
        assert tour_places.match_rows(target, HANDAM)[0] == [], name + ': 같은 이름은 아니다(느슨한 이름으로 연결)'
    assert linked(place('한담공원')) == '3056625', "관광공사 제목에만 지역 앞말이 붙은 경우('애월한담공원')"
    # 관광공사 쪽에 지역 앞말이 없는 경우: 우리 '제주카약올레' ↔ 관광공사 '카약올레'
    kayak = [row('1', '28', '카약올레', AEWOL + '애월해안로 1', BEACH[1], BEACH[0], 'LS020200', 'Type1')]
    assert linked(place('제주카약올레', category='레저·활동'), kayak) == '1'
    market = [row('2', '38', '애월전통시장', AEWOL + '애월로 1', BEACH[1], BEACH[0], 'SH060200', 'Type1')]
    assert linked(place('애월시장', category='오락·놀이'), market) == '2', '전통시장=재래시장=시장'


def test_partial_names_other_kinds_and_other_regions_are_not_linked():
    # 부분 일치는 쓰지 않는다: '한담'만 같은 공원·산책로·편의점·식당 어느 것도 아니다.
    for name, category in (('한담', '카페·미식'), ('한담', '오락·놀이'), ('카페 한담', '카페·미식'), ('한담산책로', '산책·풍경'),
                           ('한담해변 산책로', '산책·풍경'), ('한담점', '오락·놀이'), ('제주애월한담', '오락·놀이')):
        assert linked(place(name, category=category)) is None, name
    # 다른 지역: 이름이 같아도 인천의 식당은 제주 좌표와 멀다.
    assert linked(place('한담민물장어', category='카페·미식', meal=True)) is None
    # 다른 업종: 느슨한 이름이 같아도 음식점·카페(우리 분류)는 관광공사 음식점(39)과만, 그 밖은 음식점이 아닌 항목과만.
    assert linked(place('카페 한담공원', category='카페·미식')) is None, '카페 ↔ 관광지'
    eel_here = [dict(HANDAM[1], mapx=str(BEACH[1]), mapy=str(BEACH[0]), addr1=AEWOL + '애월로 1')]
    assert linked(place('애월 한담민물장어', category='문화·예술'), eel_here) is None, '식당이 아닌 우리 장소 ↔ 관광공사 음식점'
    assert linked(place('애월 한담민물장어', category='카페·미식', meal=True), eel_here) == '2853930'
    # 숙박(32)은 느슨한 이름으로 연결하지 않고, 여행코스(25)·축제(15)는 같은 이름이어도 장소가 아니다.
    assert linked(place('애월 한담해변'), [dict(HANDAM[2], contenttypeid='32')]) is None
    for type_id in ('25', '15'):
        assert linked(place('한담해변'), [dict(HANDAM[2], contenttypeid=type_id)]) is None
    # 지역 앞말을 떼고 흔한 낱말만 남는 이름은 느슨하게 보지 않는다.
    deck = [row('3', '12', '전망대', AEWOL + '애월로 1', BEACH[1], BEACH[0], 'VE010200', 'Type1')]
    assert linked(place('제주 애월 전망대'), deck) is None


def test_only_one_match_in_the_radius_is_linked():
    twin = dict(HANDAM[2], contentid='99', mapy=str(north(150)[0]))
    assert linked(place('한담해변'), HANDAM + [twin]) is None, '같은 이름이 둘'
    assert linked(place('애월 한담해변'), HANDAM + [twin]) is None, '느슨한 이름이 둘'
    resort = row('98', '12', '애월한담해수욕장', AEWOL + '애월로 1', BEACH[1], north(100)[0], 'NA020900', 'Type1')
    assert linked(place('한담해변'), HANDAM + [resort]) == '2723542', '같은 이름이 하나 있으면 느슨한 이름은 보지 않는다'
    assert linked(place('한담비치'), HANDAM + [resort]) is None, '느슨한 이름이 둘이면 연결하지 않는다'


# ---------------------------------------------------------------- 거리


def test_wide_places_link_within_1km_and_others_within_400m():
    beach = [HANDAM[2]]
    assert linked(place('한담해변', at=north(900)), beach) == '2723542'
    assert linked(place('한담해변', at=north(1100)), beach) is None
    museum = [row('5', '14', '애월미술관', AEWOL + '애월로 1', BEACH[1], BEACH[0], 'VE070600', 'Type1')]
    assert linked(place('애월미술관', at=north(350), category='문화·예술'), museum) == '5'
    assert linked(place('애월미술관', at=north(600), category='문화·예술'), museum) is None
    cafe = [row('6', '39', '한담카페', AEWOL + '애월로 1', BEACH[1], BEACH[0], 'FD050100', 'Type1')]
    assert linked(place('한담카페', at=north(600), category='카페·미식'), cafe) is None, '음식점·카페는 넓은 곳이 아니다'
    assert tour_places.link_radius_m(place('한담해변')) == 1000 and tour_places.link_radius_m(place('애월미술관', category='문화·예술')) == 400
    # 우리 분류를 몰라도 이름 끝(공원·숲·산·호수 등)이나 관광공사 분류(자연관광 NA, 도시공원 VE03)로 넓은 곳을 안다.
    assert tour_places.is_wide(place('서울숲공원', category='오락·놀이'))
    assert tour_places.is_wide(place('어떤 곳', category='오락·놀이'), dict(lclsSystm3='VE030100'))
    assert not tour_places.is_wide(place('해변식당', category='카페·미식'), dict(lclsSystm3='NA020900'))


def test_search_keyword_drops_region_words_and_keeps_generic_names_whole():
    assert tour_places.search_keyword(place('한담해변')) == '한담해변'
    assert tour_places.search_keyword(place('애월 한담해변')) == '한담해변'
    assert tour_places.search_keyword(place('제주카약올레')) == '카약올레'
    assert tour_places.search_keyword(place('카페 놀맨', category='카페·미식')) == '놀맨'
    seoul = dict(region='서울', address='서울 성동구 뚝섬로 273')
    assert tour_places.search_keyword(dict(name='서울숲', **seoul)) == '서울숲', '남는 이름이 한 글자면 떼지 않는다'
    assert tour_places.search_keyword(dict(name='대구미술관', region='대구', address='대구광역시 수성구 미술관로 40')) == '대구미술관'


# ---------------------------------------------------------------- 사진 조회(가짜 응답)


def tour_json(items, total=None):
    return dict(response=dict(header=dict(resultCode='0000', resultMsg='OK'),
                              body=dict(items=dict(item=items) if items else '', totalCount=len(items) if total is None else total)))


# 2026-11-20 실제 오류 응답 두 가지.
KEY_ERROR = httpx.Response(403, json=dict(OpenAPI_ServiceResponse=dict(cmmMsgHeader=dict(
    errMsg='SERVICE_KEY_IS_NOT_REGISTERED_ERROR', returnAuthMsg='등록되지 않은 서비스키', returnReasonCode='30'))))
FLAT_ERROR = dict(responseTime='2026-11-20T22:34:08.379', resultCode='11', resultMsg='NO_MANDATORY_REQUEST_PARAMETERS_ERROR1(contentId)')


@pytest.fixture
def tour(monkeypatch):
    """httpx.get(목록·영업 안내·추가 사진)은 public_fakes, httpx.Client(이름 검색 searchKeyword2·detailIntro2)는 여기서 답한다.
    box['search'] 에 응답(httpx.Response·dict, 또는 검색 조건을 받아 응답을 주는 함수)을 넣으면 이름 검색이 그대로 돌려준다. box['searches'] 는 이름 검색 조건 기록."""
    box = fake_public_api(monkeypatch)
    box.update(rows=list(HANDAM), search=None, searches=[], intro={})

    def handler(request):
        params = dict(request.url.params)
        if request.url.path.endswith('searchKeyword2'):
            box['searches'].append(params)
            if box['search'] is not None:
                answer = box['search'](params) if callable(box['search']) else box['search']
                return answer if isinstance(answer, httpx.Response) else httpx.Response(200, json=answer)
            found = [item for item in box['rows'] if params['keyword'] in item['title']
                     and (not params.get('lDongRegnCd') or item['addr1'].startswith('제주') == (params['lDongRegnCd'] == '50'))]
            return httpx.Response(200, json=tour_json(found))
        box['calls'].append(('tour_detail', params))
        return httpx.Response(200, json=tour_json([box['intro']] if box['intro'] else []))

    real = httpx.Client.__init__
    monkeypatch.setattr(httpx.Client, '__init__', lambda self, *a, **k: real(self, *a, **dict(k, transport=httpx.MockTransport(handler))))
    box['images']['2723542'] = [image_item('2723542', 3413987 + i, name=f'제주_한담해변 ({i + 1})') for i in range(8)]
    return box


def cache_seconds(prefix):
    """그 머리로 시작하는 공용 캐시 행들의 남은 시간(초)."""
    with store.connect() as db:
        rows = db.execute('SELECT expires FROM cache WHERE key LIKE ?', (prefix + '%',)).fetchall()
    return [round(float(item[0]) - time.time()) for item in rows]


def test_place_without_a_main_photo_gets_the_detail_images(tour):
    beach = place('한담해변')
    result = tour_places.tour_photo_result(beach)
    assert result['status'] == 'available' and len(result['photos']) == tour_places.MAX_PHOTOS == 5
    first = result['photos'][0]
    assert first['image_url'] == 'https://tong.visitkorea.or.kr/cms/resource/3413987_image2_1.jpg' and first['kind'] == 'tourapi'
    assert first['license'] == '공공누리 제3유형(변경 금지)' and first['license_url'].endswith('licenseType3.do') and first['author'] == '한국관광공사'
    assert first['source'].endswith('cotid=2723542') and '1000m' in first['caption'] and '같은 이름' in first['caption']
    assert len({photo['id'] for photo in result['photos']}) == 5 and len({photo['image_url'] for photo in result['photos']}) == 5
    # 호출: 이름 검색 1건(시·도로 좁힘) + 추가 사진 1건. 영업 안내(detailIntro2)는 전과 같다.
    assert tour['searches'] == [dict(tour['searches'][0], keyword='한담해변', lDongRegnCd='50', numOfRows='100')]
    assert [name for name, _ in tour['calls']] == ['tour_detail', 'tour_image'] and calls(tour, 'tour_image')[0]['contentId'] == '2723542'
    # 두 번째부터는 공용 캐시(7일)에서: 호출이 늘지 않는다.
    assert tour_places.tour_photo_result(beach)['photos'] == result['photos'] and len(tour['searches']) == 1 and len(tour['calls']) == 2
    assert all(604700 < left <= 604800 for left in cache_seconds('tour-images-v1:') + cache_seconds('tour-place-v3:'))
    # 사진 칸 응답: 사진이 있으면 다시 불러오기는 뜻이 없다.
    data = media.media_info(beach)
    assert len(data['photos']) == 5 and data['photo_retry'] is False


def test_cut_off_name_search_is_not_linked(tour):
    """이름 검색 결과가 100건을 넘어 잘리면 받지 못한 항목에 같은 이름이 또 있을 수 있다. 이름 전체로 한 번 더 찾고, 그래도 잘리면 연결하지 않는다."""
    tour['search'] = tour_json([HANDAM[2]], total=150)
    assert tour_places.tour_info(place('애월 한담해변')) == dict(status='not_found')
    assert [search['keyword'] for search in tour['searches']] == ['한담해변', '애월 한담해변'], '낱말 → 이름 전체, 두 번'
    assert not calls(tour, 'tour_detail')
    # 이름 전체로 찾은 결과가 다 왔으면 그것으로 맞춘다.
    tour['searches'].clear()
    tour['search'] = lambda params: tour_json([HANDAM[2]], total=150 if params['keyword'] == '한담해변' else 1)
    assert tour_places.tour_info(place('제주 한담해변'))['content_id'] == '2723542'
    assert [search['keyword'] for search in tour['searches']] == ['한담해변', '제주 한담해변']


def test_loose_name_caption_says_how_it_was_linked(tour):
    photo = tour_places.tour_photos(place('한담공원'))[0]
    assert photo['image_url'].endswith('/3056625.jpg') and '이름이 맞는 한 곳' in photo['caption'] and '지역 이름 차이는 무시' in photo['caption']
    assert tour['searches'][0]['keyword'] == '한담공원' and not calls(tour, 'tour_image'), '대표 사진이 있으면 추가 사진을 묻지 않는다(기본값)'


def test_detail_images_keep_only_kogl_type1_and_type3_on_the_tour_host(tour):
    tour['images']['2723542'] = [
        image_item('2723542', 1, kind='Type2'), image_item('2723542', 2, kind=''),
        image_item('2723542', 3, kind='Type1', url='http://tong.visitkorea.or.kr/cms/resource/3_image2_1.jpg'),
        image_item('2723542', 4, url='https://example.com/a.jpg'), image_item('2723542', 5, url='https://tong.visitkorea.or.kr.evil.test/a.jpg'),
        image_item('2723542', 6), image_item('2723542', 7, url='https://tong.visitkorea.or.kr/cms/resource/6_image2_1.jpg'),
    ]
    photos = tour_places.tour_photos(place('한담해변'))
    assert [(photo['image_url'], photo['license']) for photo in photos] == [
        ('https://tong.visitkorea.or.kr/cms/resource/3_image2_1.jpg', '공공누리 제1유형'),
        ('https://tong.visitkorea.or.kr/cms/resource/6_image2_1.jpg', '공공누리 제3유형(변경 금지)')]


def listed(content_id, title, photo):
    item = tour_item(content_id, title, *BEACH, cat3='NA020900', type_id='12', address=AEWOL + '애월로1길 26-4', photo=photo)
    return public_places.tour_place(public_places._tour_row(item), '제주')


def test_listed_public_place_asks_by_its_content_id_without_a_name_search(tour, monkeypatch):
    bare = listed(2723542, '한담해변', photo=False)
    assert bare['tour_content_id'] == '2723542' and not bare.get('tour_photo')
    result = tour_places.tour_photo_result(bare)
    assert result['status'] == 'available' and len(result['photos']) == 5 and '관광정보 항목의 사진' in result['photos'][0]['caption']
    assert tour['searches'] == [] and [name for name, _ in tour['calls']] == ['tour_detail', 'tour_image']
    tour_places.tour_photo_result(bare)
    assert len(tour['calls']) == 2, '추가 사진도 공용 캐시'
    # 대표 사진이 있는 항목은 추가 사진을 묻지 않는다(기본값). DATEMATE_TOUR_EXTRA_PHOTOS=1 이면 대표 사진 뒤에 붙인다.
    shown = listed(555, '곽지해변', photo=True)
    tour['images']['555'] = [image_item('555', 9), image_item('555', 10, url=shown['tour_photo'])]
    assert [photo['image_url'] for photo in tour_places.tour_photos(shown)] == [shown['tour_photo']] and len(calls(tour, 'tour_image')) == 1
    monkeypatch.setenv('DATEMATE_TOUR_EXTRA_PHOTOS', '1')
    more = tour_places.tour_photos(shown)
    assert [photo['image_url'] for photo in more] == [shown['tour_photo'], 'https://tong.visitkorea.or.kr/cms/resource/9_image2_1.jpg']
    assert len(calls(tour, 'tour_image')) == 2 and len({photo['id'] for photo in more}) == 2
    # 상가정보 후보는 관광공사에 묻지 않는다.
    shop = dict(id='public:store-1', name='애월 식당', lat=BEACH[0], lon=BEACH[1], category='카페·미식', meal=True)
    assert tour_places.tour_photo_result(shop) == dict(status='not_found', photos=[]) and len(calls(tour, 'tour_image')) == 2


def test_no_photo_in_the_data_is_final_and_hides_the_retry(tour):
    tour['images']['2723542'] = []
    beach = place('한담해변')
    assert tour_places.tour_photo_result(beach) == dict(status='not_found', photos=[])
    data = media.media_info(beach)
    assert data['photos'] == [] and data['photo_retry'] is False and '한국관광공사 사진이 없는 곳' in data['message']
    assert len(calls(tour, 'tour_image')) == 1 and cache_seconds('tour-images-v1:')[0] > 600000, "자료에 사진이 없는 것은 '없음'으로 7일"
    # 관광공사에 없는 장소도 확정된 '없음'(6시간).
    unknown = place('어디에도 없는 곳')
    assert media.media_info(unknown)['photo_retry'] is False and tour_places.tour_info(unknown) == dict(status='not_found')


# ---------------------------------------------------------------- 오류는 '없음'이 아니다


@pytest.mark.parametrize('answer', [KEY_ERROR, FLAT_ERROR, httpx.Response(200, text='<OpenAPI_ServiceResponse/>'), httpx.Response(500, text='error'),
                                    dict(response=dict(body=dict(items='', totalCount=0)))])
def test_name_search_errors_are_not_stored_as_not_found(tour, answer):
    beach = place('한담해변')
    tour['search'] = answer
    assert tour_places.tour_info(beach) == dict(status='unavailable')
    assert all(0 < left <= tour_places.FAIL_SECONDS for left in cache_seconds('tour-place-v3:')) and len(cache_seconds('tour-place-v3:')) == 1
    data = media.media_info(beach)
    assert data['photos'] == [] and data['photo_retry'] is True and '지금 연결하지 못했어요' in data['message']
    assert len(tour['searches']) == 1, '실패 직후 1분은 다시 부르지 않는다'
    # 다시 불러오기(force)는 실패 표시만 건너뛴다. 고쳐지면 바로 사진이 나온다.
    tour['search'] = None
    assert media.media_info(beach)['photos'] == []
    assert len(media.media_info(beach, force=True)['photos']) == 5 and len(tour['searches']) == 2
    # 찾은 결과는 force 로도 다시 부르지 않는다(하루 호출 한도 보호).
    media.media_info(beach, force=True)
    assert len(tour['searches']) == 2 and len(calls(tour, 'tour_image')) == 1


@pytest.mark.parametrize('answer', [KEY_ERROR, FLAT_ERROR])
def test_detail_image_errors_are_retried_and_not_stored_as_no_photo(tour, answer):
    bare = listed(2723542, '한담해변', photo=False)
    tour['answer']['tour_image'] = answer
    assert tour_places.tour_photo_result(bare) == dict(status='unavailable', photos=[])
    assert media.media_info(bare)['photo_retry'] is True and len(calls(tour, 'tour_image')) == 1
    assert all(left <= tour_places.FAIL_SECONDS for left in cache_seconds('tour-images-v1:'))
    del tour['answer']['tour_image']
    assert len(media.media_info(bare, force=True)['photos']) == 5


def test_daily_limit_is_neither_stored_nor_called_no_photo(tour, monkeypatch):
    bare = listed(2723542, '한담해변', photo=False)
    monkeypatch.setattr(public_places, '_reserve', lambda api: False)
    assert tour_places.tour_photo_result(bare) == dict(status='limited', photos=[])
    data = media.media_info(bare)
    assert data['photo_retry'] is False and '오늘은 한국관광공사 사진을 더 확인하지 못했어요' in data['message'] and '없는 곳' not in data['message']
    assert not calls(tour, 'tour_image') and cache_seconds('tour-images-v1:') == []
    monkeypatch.undo()


@pytest.mark.parametrize('answer', [KEY_ERROR, FLAT_ERROR, dict(response=dict(body=dict(items='', totalCount=0)))])
def test_tour_lists_do_not_store_an_error_as_an_empty_list(tour, answer):
    """예전: HTTP 200 으로 온 오류(머리 없는 본문)를 '항목 0개'로 읽어 시·군·구 목록을 7일, 시·도 목록을 하루 비워 두었다."""
    tour['tour'].append(tour_item(1, '한담해변', *BEACH, cat3='NA020900', type_id='12', address=AEWOL + '애월로1길 26-4'))
    for kind in ('tour_district', 'tour_area', 'tour_keyword'):
        tour['answer'][kind] = answer
    failed = [public_places.tour_district('50110', '12'), public_places.tour_area('제주'), public_places.tour_keyword('제주', '한담')]
    assert [data['status'] for data in failed] == ['unavailable'] * 3 and all(not data['rows'] for data in failed)
    assert all(0 < left <= public_places.FAIL_SECONDS for left in cache_seconds('public-tour-')) and len(cache_seconds('public-tour-')) == 3
    tour['answer'].clear()
    with store.connect() as db:  # 1분이 지난 뒤
        db.execute('DELETE FROM cache')
    assert public_places.tour_district('50110', '12')['rows'][0]['title'] == '한담해변'
    assert max(cache_seconds('public-tour-district')) > 600000, '진짜 목록만 7일'


@pytest.mark.parametrize('answer', [KEY_ERROR, FLAT_ERROR])
def test_festival_list_error_is_unavailable_and_not_cached(monkeypatch, answer):
    from datetime import date

    from app import festivals

    monkeypatch.setenv('TOUR_API_KEY', 'test-key')
    real = httpx.Client.__init__
    monkeypatch.setattr(httpx.Client, '__init__', lambda self, *a, **k: real(self, *a, **dict(k, transport=httpx.MockTransport(
        lambda request: answer if isinstance(answer, httpx.Response) else httpx.Response(200, json=answer)))))
    result = festivals.fetch_festivals(date(2026, 11, 20), date(2026, 11, 30), '제주')
    assert result['status'] == 'unavailable' and result['festivals'] == [] and cache_seconds('festivals:') == []
    assert festivals.fetch_festival_detail('123')['status'] == 'unavailable' and cache_seconds('festival-detail:') == []


def test_identity_lookup_failure_is_reported_as_unavailable_not_not_found(monkeypatch):
    """2026-11-20 운영 키가 어긋났던 동안 /identity 가 미술관에 not_found 로 답했다. 조회 실패는 저장하지 않고(30분 뒤 재시도) unavailable 로 답한다."""
    monkeypatch.setenv('TOUR_API_KEY', "'test-public-key'")
    museum = dict(id='identity-museum', name='금호미술관', category='문화·예술', lat=37.5797, lon=126.9801, address='서울 종로구 삼청로 18', region='서울')
    box = dict(answer=KEY_ERROR, calls=0)

    def handler(request):
        box['calls'] += 1
        answer = box['answer']
        return answer if isinstance(answer, httpx.Response) else httpx.Response(200, json=answer)

    real = httpx.Client.__init__
    monkeypatch.setattr(httpx.Client, '__init__', lambda self, *a, **k: real(self, *a, **dict(k, transport=httpx.MockTransport(handler))))
    for answer in (KEY_ERROR, FLAT_ERROR, dict(OpenAPI_ServiceResponse=dict(cmmMsgHeader=dict(errMsg='SERVICE_KEY_IS_NOT_REGISTERED_ERROR')))):
        with store.connect() as db:
            db.execute('DELETE FROM cache')
        box['answer'] = answer
        place_identity.lookup(museum)
        seen = place_identity.verify_identity(museum)
        assert seen == dict(status='unknown', pending=False, source=None, reason='unavailable'), answer
        assert store.cached(place_identity.cache_key(museum, 'store')) is None, "실패는 '없음'으로 저장되지 않는다"
        assert all(left <= place_identity.RETRY_SECONDS for left in cache_seconds(place_identity.CACHE_PREFIX + 'store-retry'))
    # 재시도 시간이 지나 자료가 정상으로 답하면 그때 '없음'(미술관은 상가정보에 없다)이 저장된다.
    with store.connect() as db:
        db.execute("DELETE FROM cache WHERE key LIKE ?", (place_identity.CACHE_PREFIX + 'store-retry%',))
    box['answer'] = dict(header=dict(resultCode='03', resultMsg='NODATA_ERROR'), body={})
    place_identity.lookup(museum)
    assert place_identity.verify_identity(museum)['reason'] == 'not_found'
    assert store.cached(place_identity.cache_key(museum, 'store'))['status'] == 'not_found'
