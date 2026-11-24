"""추천 후보는 우리 카탈로그와 공공 자료에서만 나온다(2026-11-20 2단계, docs/naver-terms-stage2-design.ko.md 3.8(b)).

- app/public_places.py: 한국관광공사 TourAPI·소상공인 상가정보를 우리 장소 모양으로 바꾸는 규칙, 사용자 공용 캐시, 실패·하루 상한.
- app/intent_discovery.py: 관광공사 항목을 먼저 쓰고 상가정보는 모자란 종류만 채운다. 네이버 지역 검색은 부르지 않는다.
- 주변 식당(app/restaurants.py)·레저(app/leisure.py)·장소 상세(app/catalog.get_place)도 같은 자료만 쓴다.
외부 호출은 모두 가짜 응답이다(tests/public_fakes.py).
"""
import json
import time
from datetime import date

import pytest

from app import intent_discovery, naver_cache, public_places, store
from app.models import Conditions

from public_fakes import calls, fake_public_api, store_item, tour_item

BUJEON = dict(lat=35.1578, lon=129.0600)


def conditions(**update):
    base = dict(mode='real', allow_estimates=True, include_meal=True, visit_date='2026-11-12', region='부산',
                origin={'name': '부산광역시 부산진구 부전동', **BUJEON}, count=3)
    return Conditions(**(base | update))


def near(dlat=0.0, dlon=0.0):
    return BUJEON['lat'] + dlat, BUJEON['lon'] + dlon


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr('app.restaurants.restaurants', lambda: [])
    box = fake_public_api(monkeypatch)
    # 네이버 지역 검색은 어떤 추천 경로에서도 부르면 안 된다.
    monkeypatch.setattr('app.naver_local.lookup', lambda *a, **k: pytest.fail('네이버 지역 검색 호출'))
    return box


def busan(box):
    box['tour'] += [
        tour_item(101, '서면 돼지국밥', *near(.001), cat3='A05020100'),
        tour_item(102, '서면 로스터리', *near(.0015), cat3='A05020900'),
        tour_item(103, '서면 미술관', *near(.002), cat3='A02060500', type_id='14'),
        tour_item(104, '부산시민공원', *near(.003), cat3='A02020700', type_id='12'),
        tour_item(105, '서면 컨벤션센터', *near(.001), cat3='A02060400', type_id='14'),
        tour_item(106, '다른 시 식당', *near(.001), address='경상남도 김해시 가야로 1'),
    ]
    box['stores'] += [
        store_item('S1', '서면 스시', *near(.0012), code='I20301', label='일식 회/초밥'),
        store_item('S2', '서면 곱창', *near(.0018), code='I20109', label='곱창 전골/구이'),
        store_item('S3', '서면 구내식당', *near(.0005), code='I20701', label='구내식당'),
        store_item('S4', '별다방', *near(.0006), code='I21201', label='카페', branch='서면역점'),
        store_item('S5', '서면 도자기 공방', *near(.002), code='P10613', label='기타 예술/스포츠 교육기관'),
        store_item('S6', '서면 미술교습소', *near(.002), code='P10611', label='미술학원'),
        store_item('S7', '서면푸드', *near(.0004), code='I20101', label='백반/한정식'),
    ]


# ---------------------------------------------------------------- 자료 → 장소


def test_tour_rows_become_places_with_our_categories_and_public_photos():
    row = public_places._tour_row(tour_item(7, '서면 미술관', 35.16, 129.06, cat3='A02060500', type_id='14'))
    place = public_places.tour_place(row, '부산')
    assert place['id'] == 'public:tour-7' and place['category'] == '문화·예술' and not place['meal']
    assert place['description'] == '문화관광>전시시설>미술관/화랑' and 'culture' in place['tags'] and place['setting'] == 'indoor'
    assert place['tour_photo'].startswith('https://tong.visitkorea.or.kr/') and place['tour_photo_license'] == '공공누리 제1유형'
    assert place['source'].endswith('cotid=7') and '네이버' not in place['source_type'] and place['hours'] is None
    cafe = public_places.tour_place(public_places._tour_row(tour_item(8, '바다 찻집', 35.16, 129.06, cat3='A05020900')), '부산')
    assert cafe['category'] == '카페·미식' and not cafe['meal'] and cafe['tags'][0] == 'cafe'
    meal = public_places.tour_place(public_places._tour_row(tour_item(9, '국밥집', 35.16, 129.06)), '부산')
    assert meal['meal'] and meal['tags'][0] == 'meal'
    # 분류는 TourAPI 새 분류(lclsSystm3)로 본다(예전 cat3 칸은 대부분 비어 있다). 후보로 쓰지 않는 분류(컨벤션센터·클럽), 다른 시·도,
    # 종목을 모르는 스포츠센터는 None.
    for item in (tour_item(1, '컨벤션', 35.16, 129.06, cat3='A02060400'), tour_item(2, '클럽', 35.16, 129.06, cat3='A05021000'),
                 tour_item(3, '서울 식당', 35.16, 129.06, address='서울특별시 중구 명동길 1'),
                 tour_item(4, '수련원', 35.16, 129.06, cat3='A03020200', type_id='28')):
        assert public_places.tour_place(public_places._tour_row(item), '부산') is None
    kart = public_places.tour_place(public_places._tour_row(tour_item(5, '해운대 카트장', 35.16, 129.06, cat3='A03020600', type_id='28')), '부산')
    assert kart['category'] == '레저·활동' and kart['tags'][0] == 'kart_luge'
    # 사진은 공공누리 제1·제3유형일 때만.
    plain = public_places._tour_row(dict(tour_item(6, '공원', 35.16, 129.06, cat3='A02020700', type_id='12'), cpyrhtDivCd=''))
    assert plain['photo'] is None


def test_store_rows_keep_only_date_venues_and_classify_sports_by_name():
    def place(item):
        row = public_places._store_row(item)
        return public_places.store_place(row, '부산', '202609') if row else None

    kind, meal = place(store_item('A', '서면 스시', 35.16, 129.06, code='I20301', label='일식 회/초밥'))
    assert kind == 'meal' and meal['meal'] and meal['id'] == 'public:store-A' and meal['description'] == '일식 회/초밥'
    assert '2026년 9월 자료' in meal['discovery_verification'] and '네이버' not in meal['source_type']
    kind, cafe = place(store_item('B', '별다방', 35.16, 129.06, code='I21201', label='카페', branch='서면역점'))
    assert kind == 'cafe' and cafe['name'] == '별다방 서면역점' and cafe['branch'] is True and not cafe['meal']
    kind, lane = place(store_item('C', '서면볼링센터', 35.16, 129.06, code='R10309', label='볼링장'))
    assert kind == 'sport' and lane['tags'][0] == 'bowling' and lane['category'] == '레저·활동'
    kind, gym = place(store_item('D', '더클라이밍', 35.16, 129.06, code='R10307', label='헬스장'))
    assert kind == 'sport' and gym['tags'][0] == 'climbing'
    kind, room = place(store_item('E', '서면 방탈출카페', 35.16, 129.06, code='R10405', label='기타 오락장'))
    assert kind == 'game' and room['category'] == '오락·놀이'
    kind, craft = place(store_item('F', '서면 도자기 공방', 35.16, 129.06, code='P10613', label='기타 예술/스포츠 교육기관'))
    assert kind == 'workshop'
    # 후보가 아닌 업종, 낱말 단서가 없는 상호, 회사 이름·강습소로 보이는 상호, 다른 시·도, 이름 없는 업소.
    for item in (store_item('G', '구내식당', 35.16, 129.06, code='I20701'), store_item('H', '파워짐', 35.16, 129.06, code='R10307'),
                 store_item('I', '칠성게임', 35.16, 129.06, code='R10404', label='전자 게임장'),
                 store_item('J', '오후의드로잉미술교습소', 35.16, 129.06, code='P10611', label='미술학원'),
                 store_item('K', '이탈리안푸드', 35.16, 129.06), store_item('L', '서울식당', 35.16, 129.06, address='서울특별시 중구 명동길 1'),
                 store_item('M', '업소명없음', 35.16, 129.06), store_item('N', '호프집', 35.16, 129.06, code='I21103', label='생맥주 전문')):
        assert place(item) is None, item['bizesNm']


def test_pick_stores_prefers_unbranched_then_nearest_and_skips_known_venues():
    center = dict(BUJEON)

    def pair(biz, name, d, branch=''):
        row = public_places._store_row(store_item(biz, name, *near(d), code='I21201', label='카페', branch=branch))
        return public_places.store_place(row, '부산', '202609')

    rows = [pair('1', '프랜차이즈', .0001, '서면점'), pair('2', '먼 동네 카페', .004), pair('3', '가까운 동네 카페', .001),
            pair('4', '이미 있는 카페', .0005)]
    known = [dict(name='이미있는카페', lat=near(.0005)[0], lon=near(.0005)[1])]
    picked = public_places.pick_stores(rows, center, dict(cafe=2), taken=known)
    assert [p['name'] for _, p in picked] == ['가까운 동네 카페', '먼 동네 카페']
    assert [p['name'] for _, p in public_places.pick_stores(rows, center, dict(cafe=5), taken=known)][-1] == '프랜차이즈 서면점'


# ---------------------------------------------------------------- 캐시·실패·상한


def test_public_lists_are_shared_between_users_and_failures_wait_a_minute(api):
    api['tour'].append(tour_item(1, '서면 식당', *near(.001)))
    api['tour'].append(tour_item(2, '먼 식당', *near(.05)))
    api['stores'].append(store_item('S', '서면 스시', *near(.001), code='I20301'))
    first = public_places.tour_near(BUJEON['lat'], BUJEON['lon'], 2.5)
    # 반경에 걸친 시·군·구(부산진구 26230)의 목록을 관광 타입마다 받아 거리로 거른다.
    assert first['status'] == 'available' and first['districts'] == ['26230'] and [r['title'] for r in first['rows']] == ['서면 식당']
    assert sorted(p['contentTypeId'] for p in calls(api, 'tour_district')) == sorted(public_places.TOUR_TYPES)
    params = calls(api, 'tour_district')[0]
    assert (params['lDongRegnCd'], params['lDongSignguCd']) == ('26', '230') and 'areaCode' not in params and 'mapX' not in params
    assert calls(api, 'probe')[0]['radius'] == 2650 and calls(api, 'probe')[0]['indsSclsCd'] == 'G21501'
    # 다른 사용자, 150m 옆 좌표(같은 격자), 같은 구의 다른 동네: 같은 캐시를 쓴다.
    with naver_cache.scope(store.owner_of('another-user')):
        again = public_places.tour_near(BUJEON['lat'] + .0005, BUJEON['lon'] + .0005, 2.5)
        public_places.tour_near(BUJEON['lat'] + .01, BUJEON['lon'], 2.5)
        public_places.store_sheet('food', BUJEON['lat'], BUJEON['lon'], 600)
        public_places.store_sheet('food', BUJEON['lat'] + .0005, BUJEON['lon'], 600)
    assert [r['id'] for r in again['rows']] == [r['id'] for r in first['rows']]
    assert len(calls(api, 'tour_district')) == 5 and len(calls(api, 'probe')) == 2 and len(calls(api, 'store')) == 1
    assert calls(api, 'store')[0]['radius'] == 750 and calls(api, 'store')[0]['indsLclsCd'] == 'I2'
    # 캐시에는 키가 들어가지 않는다.
    with store.connect() as db:
        payloads = ' '.join(row[0] + row[1] for row in db.execute("SELECT key,payload FROM cache WHERE key LIKE 'public-%'"))
    assert 'test-public-key' not in payloads and 'serviceKey' not in payloads
    # 실패는 후보 없음으로 답하고 60초 동안 다시 부르지 않는다.
    api['fail'] |= {'probe', 'store'}
    assert public_places.tour_near(35.9, 128.6, 2.5) == dict(status='unavailable', rows=[], districts=[])
    assert public_places.tour_near(35.9, 128.6, 2.5)['status'] == 'unavailable'
    assert public_places.store_sheet('food', 35.9, 128.6, 600)['status'] == 'unavailable'
    public_places.store_sheet('food', 35.9, 128.6, 600)
    assert len(calls(api, 'probe')) == 3 and len(calls(api, 'store')) == 2


def test_district_codes_follow_store_info_and_sejong_is_special():
    assert public_places.district_parts('11200') == ('11', '200') and public_places.district_parts('52111') == ('52', '111')
    assert public_places.district_parts('36110') == ('36110', '36110')
    assert public_places.district_parts('1120') is None and public_places.district_parts(None) is None
    assert set(public_places.REGION_CODES) == set(__import__('app.regions').regions.REGIONS)


def test_place_without_pharmacies_nearby_has_no_tour_list(api):
    # 약국이 반경 안에도 5km 안에도 없으면 시·군·구를 알 수 없다: 관광공사 목록 없이 상가정보·카탈로그만 쓴다.
    found = public_places.tour_near(33.3, 126.2, 2.5)
    assert found == dict(status='not_found', rows=[], districts=[])
    assert [p['radius'] for p in calls(api, 'probe')] == [2650, 5000] and not calls(api, 'tour_district')


def test_daily_cap_stops_tour_calls_but_not_the_recommendation(api, monkeypatch):
    monkeypatch.setenv('DATEMATE_TOUR_CANDIDATE_CALLS_PER_DAY', '1')
    with store.connect() as db:
        db.execute("DELETE FROM request_budgets WHERE scope LIKE 'public-api:%'")
    assert public_places.tour_area('부산', '12')['status'] == 'available'
    assert public_places.tour_area('부산', '14') == dict(status='limited', rows=[])
    assert len(calls(api, 'tour_area')) == 1 and public_places.daily_calls()['tour'] == 1
    with store.connect() as db:
        db.execute("DELETE FROM request_budgets WHERE scope LIKE 'public-api:%'")


def test_sparse_area_widens_the_store_radius_once(api):
    api['stores'].append(store_item('S', '외딴 식당', *near(.012), code='I20101'))
    data, radius = public_places.stores_near('food', BUJEON['lat'], BUJEON['lon'])
    assert radius == 2000 and [r['name'] for r in data['rows']] == ['외딴 식당']
    assert [p['radius'] for p in calls(api, 'store')] == [750, 2150]


def test_provider_name_separates_public_apis():
    from app.telemetry import provider_of
    assert provider_of(public_places.TOUR_AREA_URL) == 'apis.data.go.kr/B551011'
    assert provider_of(public_places.STORE_URL) == 'apis.data.go.kr/B553077'
    assert provider_of('https://apis.data.go.kr/1741000/rest_cafes/info') == 'apis.data.go.kr/1741000'
    assert provider_of('https://naverapihub.apigw.ntruss.com/search/v1/blog') == 'naverapihub.apigw.ntruss.com'


# ---------------------------------------------------------------- 후보 찾기


def test_default_search_uses_tour_rows_first_and_stores_only_for_short_kinds(api, monkeypatch):
    busan(api)
    monkeypatch.setattr('app.catalog._places', lambda *a, **k: public_places.candidates())
    c = conditions()
    result = intent_discovery.discover_requested_places(c)
    found = {p['name']: p for p in public_places.candidates()}
    assert result['status'] == 'available' and result['coverage_supplement'] and result['resolved'] == len(found)
    # 관광공사 항목: 후보가 아닌 분류(컨벤션센터)와 다른 시·도는 빠진다.
    assert {'서면 돼지국밥', '서면 로스터리', '서면 미술관', '부산시민공원'} <= set(found)
    assert '서면 컨벤션센터' not in found and '다른 시 식당' not in found
    # 식사는 관광공사 1곳뿐이라 상가정보로 채운다(구내식당·회사 이름은 빠짐). 공방도 상가정보에서.
    assert {'서면 스시', '서면 곱창', '서면 도자기 공방'} <= set(found)
    assert not {'서면 구내식당', '서면푸드', '서면 미술교습소'} & set(found)
    # 카페는 모자란 종류였어도 상가정보 묶음이 같아(음식) 함께 받는다. 지점 표기 있는 곳도 다른 후보가 없으면 쓴다.
    assert result['store_kinds'] == ['meal', 'cafe', 'culture', 'walk', 'workshop']
    assert [s['source'] for s in result['sources']] == ['tour', 'store:food', 'store:craft']
    assert result['meal_supply'] == dict(before=0, found_reachable=3, after=3, enough=True)
    assert all(p['id'].startswith('public:') and '네이버' not in json.dumps(p, ensure_ascii=False) for p in found.values())
    assert not api['naver']
    # 같은 추천 안에서 다시 불려도 공공 API 를 또 부르지 않는다.
    used = len(api['calls'])
    again = intent_discovery.discover_requested_places(c.model_copy(update={'course_query': ''}))
    assert again['resolved'] == 0 and again['lookups'] == 0 and len(api['calls']) == used
    assert {p['name'] for p in public_places.candidates()} == set(found)


def test_enough_catalog_supply_still_adds_tour_rows_but_no_store_rows(api, monkeypatch):
    busan(api)

    def row(pid, category, meal=False, dlat=0.0):
        return dict(id=pid, name=pid, region='부산', lat=BUJEON['lat'] + dlat, lon=BUJEON['lon'], category=category, meal=meal, tags=[])

    rows = [row('m1', '카페·미식', True), row('m2', '카페·미식', True, .001), row('c1', '카페·미식', dlat=.002),
            row('c2', '카페·미식', dlat=.003), row('w1', '산책·풍경', dlat=.004), row('w2', '산책·풍경', dlat=.005)]
    monkeypatch.setattr('app.catalog._places', lambda *a, **k: rows + public_places.candidates())
    result = intent_discovery.discover_requested_places(conditions())
    assert result['searched_kinds'] == [] and result['store_kinds'] == []
    assert [s['source'] for s in result['sources']] == ['tour'] and not calls(api, 'store')
    assert {p['name'] for p in public_places.candidates()} == {'서면 돼지국밥', '서면 로스터리', '서면 미술관', '부산시민공원'}


def test_requested_activity_fills_from_stores_when_tour_has_none(api, monkeypatch):
    busan(api)
    api['stores'] += [store_item('B1', '서면볼링센터', *near(.002), code='R10309', label='볼링장'),
                      store_item('B2', '전포당구클럽', *near(.002, .001), code='R10310', label='당구장')]
    monkeypatch.setattr('app.catalog._places', lambda *a, **k: public_places.candidates())
    result = intent_discovery.discover_requested_places(conditions(request='볼링 치고 싶어', include_meal=False))
    names = {p['name'] for p in public_places.candidates()}
    assert '서면볼링센터' in names and '전포당구클럽' not in names
    assert result['store_kinds'] == ['bowling'] and result['kind_stats']['bowling']['adopted'] == 1
    # 스포츠 시설이 드문 동네라 좁은 반경(1.5km) 다음에 넓은 반경(3km)으로 한 번 더 받는다.
    assert [(p['indsLclsCd'], p['radius']) for p in calls(api, 'store')] == [('R1', 1650), ('R1', 3150)]


def test_missing_key_and_failed_sources_leave_candidates_empty(api, monkeypatch):
    monkeypatch.setattr('app.catalog._places', lambda *a, **k: public_places.candidates())
    api['fail'] |= {'tour_district', 'store'}
    result = intent_discovery.discover_requested_places(conditions())
    assert result['status'] == 'not_found' and result['search_unavailable'] and public_places.candidates() == []
    monkeypatch.setenv('TOUR_API_KEY', '')
    assert intent_discovery.discover_requested_places(conditions(region='대구', origin={'name': '대구 중구', 'lat': 35.869, 'lon': 128.594})) == dict(status='not_available', resolved=0)


def test_recommendation_builds_strict_plans_from_public_candidates_only(api):
    from app.recommendation_service import generate
    busan(api)
    owner = naver_cache.current_owner()
    result = generate(conditions(), owner)
    assert result['status'] == 'ok' and len(result['plans']) >= 1, result.get('reasons')
    plan = result['plans'][0]
    assert all(p['id'].startswith('public:') and p['region'] == '부산' for p in plan['places'])
    meals = [p for p in plan['places'] if p.get('meal')]
    assert meals and {r['condition']: r for r in plan['condition_checks']}['meal']['state'] == 'met'
    # 공공 자료에는 영업시간·가격이 없다: 지어내지 않고 '확인 필요'로 남는다.
    assert all(p['hours'] is None and p['price'] is None for p in plan['places'])
    assert all(p['name'] + ' 영업시간' in plan['unknown'] for p in plan['places'])
    # 이유 문장·근거에 네이버 지역 검색이 없다.
    assert '네이버' not in json.dumps(plan['reasons'], ensure_ascii=False)
    assert result['diagnostics']['intent_discovery']['sources'][0]['source'] == 'tour'
    assert not api['naver']
    # 저장 코스의 장소는 보관이 끝난 뒤에도 그 사용자의 코스에서 찾는다.
    from app.catalog import get_place
    target = plan['places'][0]
    naver_cache.new_query('plan', owner)
    assert get_place(target['id'], 'real')['name'] == target['name']
    with naver_cache.scope(store.owner_of('someone-else')):
        assert get_place(target['id'], 'real') is None


def test_public_places_are_not_naver_places_and_get_identity_checks():
    from app import place_identity
    from app.naver_terms import is_naver_place, strip_plan
    row = public_places._store_row(store_item('Z', '서면 스시', 35.16, 129.06, code='I20301'))
    _, place = public_places.store_place(row, '부산', '202609')
    assert not is_naver_place(place) and place_identity.applies(place)
    assert place_identity.license_kinds(place) == ['일반음식점', '휴게음식점']
    # 21일 정리는 공공 자료 장소를 지우지 않는다.
    plan = dict(conditions=dict(mode='real', region='부산'), places=[place], reasons=[], costs=[], legs=[])
    assert strip_plan(plan)['places'][0]['name'] == '서면 스시'


# ---------------------------------------------------------------- 관광공사 사진·영업 안내


def test_listed_tour_place_asks_only_for_its_detail_and_store_places_ask_nothing(api):
    from app.tour_places import tour_hours, tour_info, tour_photos
    row = public_places._tour_row(tour_item(55, '서면 돼지국밥', 35.16, 129.06))
    place = public_places.tour_place(row, '부산')
    api['detail']['55'] = dict(opentimefood='11:00~21:00', restdatefood='매주 월요일')
    info = tour_info(place)
    assert info['status'] == 'available' and info['photo'] == place['tour_photo'] and info['hours'] == '11:00~21:00'
    assert tour_hours(place)['rest'] == '매주 월요일' and tour_photos(place)[0]['license'] == '공공누리 제1유형'
    assert [name for name, _ in api['calls']] == ['tour_detail'], '이름으로 다시 찾지 않는다'
    tour_info(place)
    assert len(api['calls']) == 1
    _, shop = public_places.store_place(public_places._store_row(store_item('Q', '서면 스시', 35.16, 129.06, code='I20301')), '부산', '202609')
    assert tour_info(shop) == dict(status='not_found') and tour_photos(shop) == [] and len(api['calls']) == 1


# ---------------------------------------------------------------- 주변 식당·레저


def plan_near(places_rows, **update):
    from app.condition_audit import audit_plan
    from app.planner import evaluate
    c = conditions(count=len(places_rows), **update)
    plan, error = evaluate(places_rows, c, soft=True)
    assert not error, error
    return audit_plan(plan, c)


def stop(pid, name, dlat, category='문화·예술'):
    lat, lon = near(dlat)
    return dict(id=pid, name=name, region='부산', address='부산광역시 부산진구 부전동 9', lat=lat, lon=lon, category=category, themes=[category],
                tags=[], meal=False, demo=False, description='', source='https://example.org', source_type='fixture', checked_at='2026-11-01',
                license='test', price=None, price_unit='person', hours=None, closed_days=None, breaks=None, last_entry=None, reservation=None,
                stay=None, stay_basis=None, rating=None, setting='indoor', photos=[], videos=[])


def test_nearby_restaurants_come_from_public_data_without_a_popularity_list(api):
    from app.catalog import get_place
    from app.restaurants import meal_rescue, restaurant_matches, search_nearby
    busan(api)
    plan = plan_near([stop('p1', '서면 전시관', .001), stop('p2', '서면 책방', .002)])
    data = restaurant_matches(plan)
    assert 'popular' not in data and len(data['groups']) == 2
    first = data['groups'][0]
    names = [food['name'] for food in first['restaurants']]
    # 관광공사 음식점이 먼저, 그다음 상가정보(지점 표기 없는 곳·가까운 순). 카페·구내식당·회사 이름은 없다.
    assert names[0] == '서면 돼지국밥' and set(names[1:]) == {'서면 스시', '서면 곱창'}
    assert all(food['search_radius_m'] == 500 and food['meal'] and food['id'].startswith('public:') for food in first['restaurants'])
    assert first['restaurants'][0]['recognition'] == '한국관광공사 관광정보에 실린 음식점'
    assert '후기·별점 순위가 아니에요' in first['ranking_basis'] and '네이버' not in first['ranking_basis']
    # 보여 준 식당은 '일정에 넣기'·장소 상세에서 다시 찾을 수 있다.
    assert get_place(first['restaurants'][1]['id'], 'real')['name'] == first['restaurants'][1]['name']
    assert search_nearby(plan, 0)['restaurants'][0]['name'] == '서면 돼지국밥'
    # 식사 조건이 미충족인 코스의 대안도 같은 자료에서.
    plan['deviations'] = [dict(condition='meal', state='unmet')]
    rescue = meal_rescue(plan)
    assert rescue['status'] == 'available' and rescue['restaurants'][0]['name'] == '서면 돼지국밥' and len(rescue['restaurants']) <= 3
    assert not api['naver']


def test_nearby_restaurants_without_key_or_data_point_to_the_map(api, monkeypatch):
    from app.restaurants import restaurant_matches
    plan = plan_near([stop('p1', '서면 전시관', .001), stop('p2', '서면 책방', .002)])
    empty = restaurant_matches(plan)['groups'][0]
    assert empty['restaurants'] == [] and empty['status'] == 'not_found' and '네이버 지도' in empty['message']
    monkeypatch.setenv('TOUR_API_KEY', '')
    assert restaurant_matches(plan)['groups'][0]['status'] == 'key_missing'


def test_leisure_options_come_from_public_data_and_stay_out_of_default_pools(api, monkeypatch):
    from app import leisure
    from app.quality import pool
    api['tour'].append(tour_item(301, '부산 카트장', *near(.02), cat3='A03020600', type_id='28'))
    api['stores'] += [store_item('L1', '서면볼링센터', *near(.002), code='R10309', label='볼링장'),
                      store_item('L2', '전포당구클럽', *near(.003), code='R10310', label='당구장'),
                      store_item('L3', '파워짐', *near(.001), code='R10307', label='헬스장'),
                      *[store_item(f'L{i}', f'당구장{i}', *near(.001 * i, .002), code='R10310', label='당구장') for i in range(4, 10)]]
    c = conditions(include_meal=False)
    anchor = stop('p1', '서면 전시관', .001)
    result = leisure.discover_leisure(c, anchor)
    assert result['search_status'] == 'complete' and [s['source'] for s in result['sources']] == ['tour', 'store:play']
    assert {p['contentTypeId'] for p in calls(api, 'tour_district')} == {'28'} and calls(api, 'store')[0]['indsLclsCd'] == 'R1'
    found = {p['name']: p for p in public_places.candidates()}
    assert {'부산 카트장', '서면볼링센터'} <= set(found) and '파워짐' not in found
    assert result['adopted_by_sport']['billiards'] == leisure.MAX_PER_SPORT, '한 종목은 가까운 순으로 몇 곳만'
    assert all(p['leisure_search'] for p in found.values())
    # 운동을 원하지 않은 기본 추천의 후보에는 섞이지 않고, 운동을 요청하면 들어간다.
    assert not [p for p in pool(c) if p.get('leisure_search')]
    assert '서면볼링센터' in {p['name'] for p in pool(conditions(include_meal=False, request='볼링 치고 싶어'))}
    used = len(api['calls'])
    assert leisure.discover_leisure(c, anchor)['cache_hit'] and len(api['calls']) == used
    assert not api['naver']


# ---------------------------------------------------------------- 동네 반경 밖의 가장 가까운 곳(요청 활동 미충족 안내)


def test_nearest_outside_reads_only_lists_already_fetched(api):
    busan(api)
    api['tour'].append(tour_item(110, '전포 도자기 공방', *near(.036), cat3='A04010700', type_id='38'))  # 약 4km
    public_places.tour_near(BUJEON['lat'], BUJEON['lon'], 2.5)  # 추천이 받아 두는 것과 같은 목록
    before = len(api['calls'])
    from app.request_intent import matches
    found = public_places.nearest_outside(BUJEON['lat'], BUJEON['lon'], 2.5, '부산', lambda p: matches(p, 'workshop'))
    assert found == dict(name='전포 도자기 공방', km=4.0)
    assert len(api['calls']) == before  # 새로 부르지 않는다
    # 받아 둔 목록이 없는 곳(다른 동네)은 모른다고 답한다(호출하지 않음).
    assert public_places.nearest_outside(37.0, 127.0, 2.5, '경기', lambda p: True) is None
    assert len(api['calls']) == before


def test_unmet_requested_activity_names_the_nearest_place_outside_the_neighborhood(api):
    from app.condition_audit import audit_plan
    from app.recommendation_service import generate
    busan(api)
    api['stores'] = [s for s in api['stores'] if '공방' not in s['bizesNm']]
    api['tour'].append(tour_item(110, '전포 도자기 공방', *near(.036), cat3='A04010700', type_id='38'))
    # 이름에 '공방'이 든 빵집(카페·미식)은 더 가까워도 공방 체험 안내로 쓰지 않는다(요청 활동의 종류만).
    api['tour'].append(tour_item(111, '전포 식빵공방', *near(.030), cat3='A05020900'))
    center = {'name': '서면 지역 중심', **BUJEON}
    result = generate(conditions(origin=center, area_center=center, request='공방 체험 하고 싶어'), naver_cache.current_owner())
    assert result['plans'], result.get('reasons')
    plan = result['plans'][0]
    check = next(r for r in plan['condition_checks'] if r['condition'] == 'request_activity')
    assert check['state'] == 'unmet'
    assert '가장 가까운 곳은 전포 도자기 공방' in check['message'] and '4km' in check['message'] and '반경 2.5km 밖' in check['message']
    assert plan['nearest_outside'] == [dict(intent='공방', name='전포 도자기 공방', km=4.0)]
    # 저장한 코스를 다시 열어 조건을 다시 대조해도 안내가 남는다(다시 찾지 않음).
    again = audit_plan(json.loads(json.dumps(plan)))
    assert '가장 가까운 곳은 전포 도자기 공방' in next(r for r in again['condition_checks'] if r['condition'] == 'request_activity')['message']


def test_listed_tour_restaurant_shows_its_menu_text(api):
    """관광공사 음식점 안내의 대표·취급 메뉴를 메뉴 칸에 글 그대로 싣는다(2026-11-24). 가격은 만들지 않고 지도 링크는 그대로다."""
    from app.menus import restaurant_menu
    from app.tour_places import tour_menu
    row = public_places._tour_row(tour_item(56, '서면 국밥집', 35.16, 129.06))
    place = public_places.tour_place(row, '부산')
    api['detail']['56'] = dict(opentimefood='11:00~21:00', restdatefood='연중무휴', firstmenu='돼지국밥', treatmenu='돼지국밥, 수육 백반')
    assert tour_menu(place) == dict(first='돼지국밥', treat='돼지국밥, 수육 백반', source_url=place['source'],
                                    source_label='한국관광공사 음식점 안내', checked_at=tour_menu(place)['checked_at'])
    menu = restaurant_menu(place)
    assert menu['tour_menu']['first'] == '돼지국밥' and menu['items'] == [] and menu['source_label'] == '네이버 지도에서 메뉴 보기'
    # 메뉴 글이 없는 음식점·음식점이 아닌 곳은 싣지 않는다.
    other = public_places.tour_place(public_places._tour_row(tour_item(57, '서면 빵집', 35.16, 129.06)), '부산')
    api['detail']['57'] = dict(opentimefood='08:00~20:00', restdatefood='')
    assert 'tour_menu' not in restaurant_menu(other)
