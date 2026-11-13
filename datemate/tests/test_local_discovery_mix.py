"""Default local discovery outside Seoul must mix meals, cafes, exhibitions and walks."""

import pytest

from app import intent_discovery
from app.explore import classify_local
from app.models import Conditions


@pytest.mark.parametrize('category,name,expected', [
    ('음식점>한식', '돼지국밥집', ('카페·미식', True)),
    ('한식>곱창,막창,양', '곱창골목', ('카페·미식', True)),
    ('음식점>일식>초밥,롤', '스시집', ('카페·미식', True)),
    ('카페,디저트', '바다카페', ('카페·미식', False)),
    ('음식점>카페,디저트', '디저트가게', ('카페·미식', False)),
    ('카페,디저트>베이커리', '빵집', ('카페·미식', False)),
    ('지원,대행>전시,행사대행', '행사기획사', None),
    ('광고,마케팅>옥외,전시광고', '간판광고', None),
    ('문화,예술>갤러리,화랑', '바다 갤러리카페', ('카페·미식', False)),
    ('갤러리카페', '바다 갤러리', ('카페·미식', False)),
    ('문화,예술>미술관', '시립미술관', ('문화·예술', False)),
    ('여행,명소>공원', '시민공원', ('산책·풍경', False)),
    ('자동차>전시장', '자동차 갤러리', None),
    ('주차장', '공영주차장', None),
    ('부동산>중개업', '공원부동산', None),
    ('병원,의원>피부과', '갤러리의원', None),
    ('숙박>호텔', '전망호텔', None),
    ('', '이름만', None),
])
def test_classify_local_table(category, name, expected):
    assert classify_local(category, name) == expected


def _conditions(**update):
    base = dict(mode='real', allow_estimates=True, include_meal=True, visit_date='2026-11-12', region='부산',
                origin={'name': '부산광역시 부산진구 부전동', 'lat': 35.1578, 'lon': 129.0600}, count=3)
    return Conditions(**(base | update))


def _place(pid, category, meal=False, dlat=0.0):
    return dict(id=pid, name=pid, region='부산', lat=35.1578 + dlat, lon=129.0600, category=category, meal=meal, tags=[])


@pytest.fixture
def isolated(monkeypatch):
    cache = {}
    monkeypatch.setattr(intent_discovery.store, 'cached', lambda key: cache.get(key))
    monkeypatch.setattr(intent_discovery.store, 'cache', lambda key, value, ttl: cache.__setitem__(key, value))
    # 한 번에 읽고 쓰는 저장 함수(store.cached_many·cache_many)도 같은 임시 저장소를 쓰게 한다.
    monkeypatch.setattr(intent_discovery.store, 'cached_many', lambda keys: {k: cache[k] for k in keys if k in cache})
    monkeypatch.setattr(intent_discovery.store, 'cache_many', lambda entries: [cache.__setitem__(k, v) for k, v, _ in entries])
    monkeypatch.setattr(intent_discovery, 'search_enabled', lambda: True)
    monkeypatch.setattr('app.restaurants.restaurants', lambda: [])
    calls = []
    monkeypatch.setattr(intent_discovery, 'local_lookup',
                        lambda term, area, **kw: (calls.append((term, kw.get('sort'))), ([], 'available'))[1])
    return calls


def test_cafe_only_area_searches_missing_kinds(monkeypatch, isolated):
    cafes = [_place(f'cafe{i}', '카페·미식', dlat=i * .001) for i in range(3)]
    monkeypatch.setattr('app.catalog.places', lambda *a, **k: cafes)
    result = intent_discovery.discover_requested_places(_conditions())
    terms = [t for t, _ in isolated]
    assert sorted(terms[:7]) == sorted(['맛집', '음식점', '전시', '미술관', '공원', '산책', '공방'])
    assert '카페' not in terms and dict(isolated)['맛집'] == 'comment' and dict(isolated)['음식점'] is None
    assert result['searched_kinds'] == ['meal', 'culture', 'walk', 'workshop'] and result['lookups'] == 8 == len(isolated)
    assert result['supply'] == {'카페·미식': 3}
    # 동네 검색이 0건이면 남은 1건으로 식사를 구 단위('부산진구')에서 한 번 더 찾는다.
    assert result['query_area'] == '부산진구 부전동' and result['fallback_queries'] == [
        dict(kind='meal', term='맛집', area='부산 부산진구')]
    assert result['meal_supply'] == dict(before=0, found_reachable=0, after=0, enough=False)

    # 식사 조건이 꺼져 있으면 식당은 찾지 않는다.
    isolated.clear()
    result = intent_discovery.discover_requested_places(_conditions(include_meal=False, origin={'name': '부산광역시 부산진구 전포동', 'lat': 35.1578, 'lon': 129.0600}))
    assert '맛집' not in [t for t, _ in isolated] and len(isolated) == result['lookups'] == 8
    assert [q['kind'] for q in result['fallback_queries']] == ['culture', 'walk', 'workshop']


def test_enough_kinds_skip_search(monkeypatch, isolated):
    rows = [_place('m1', '카페·미식', True), _place('m2', '카페·미식', True, .001),
            _place('c1', '카페·미식', dlat=.002), _place('c2', '카페·미식', dlat=.003),
            _place('w1', '산책·풍경', dlat=.004), _place('w2', '산책·풍경', dlat=.005)]
    monkeypatch.setattr('app.catalog.places', lambda *a, **k: rows)
    result = intent_discovery.discover_requested_places(_conditions())
    assert result['status'] == 'not_needed' and not isolated
    # 식사 장소가 1곳뿐이면 식사만 찾는다(다른 종류는 이미 충분).
    monkeypatch.setattr('app.catalog.places', lambda *a, **k: rows[1:])
    result = intent_discovery.discover_requested_places(_conditions())
    assert sorted(t for t, _ in isolated) == ['맛집', '맛집', '음식점'] and result['searched_kinds'] == ['meal']


def _item(title, category, dlat, dlon=0.0):
    return dict(title=title, category=category, roadAddress=f'부산광역시 부산진구 부전동 {title}',
                mapx=129.0600 + dlon, mapy=35.1578 + dlat)


BUSAN = {
    '맛집': [_item('서면 돼지국밥', '음식점>한식', .001), _item('서면 디저트', '음식점>카페,디저트', .0015)],
    '음식점': [_item('서면 스시', '음식점>일식>초밥,롤', .002), _item('서면 곱창', '한식>곱창,막창,양', .0025)],
    '카페': [_item('서면 로스터리', '카페,디저트', .003)],
    '전시': [_item('서면 갤러리', '문화,예술>갤러리,화랑', .0035), _item('서면 행사대행', '지원,대행>전시,행사대행', .004)],
    '미술관': [_item('서면 미술관', '문화,예술>미술관', .0045)],
    '공원': [_item('부산시민공원', '여행,명소>공원', .005)],
    '산책': [_item('전포 산책길', '여행,명소>산책로', .0055)],
    '공방': [_item('서면 도자기 공방', '공예,공방>도자기', .006)],
}


def test_busan_default_conditions_build_strict_plan_with_meal(monkeypatch):
    from app import store
    from app.planner import recommend
    from app.request_usage import measure

    monkeypatch.setattr(intent_discovery, 'search_enabled', lambda: True)
    requested = []

    def fake_get(url, params=None, **kwargs):
        import httpx
        term = params['query'].split()[-1]
        requested.append((term, params['sort']))
        return httpx.Response(200, json=dict(items=BUSAN.get(term, [])), request=httpx.Request('GET', url))

    monkeypatch.setattr('app.discovery.httpx.get', fake_get)
    c = _conditions()
    try:
        with measure() as usage:
            found = intent_discovery.discover_requested_places(c)
            # 추천 서비스의 조건 완화 재검색처럼 다시 불려도 방금 찾은 종류는 다시 검색하지 않는다.
            again = intent_discovery.discover_requested_places(c.model_copy(update={'course_query': ''}))
        assert found['status'] == 'available' and found['lookups'] == len(requested) <= 8
        assert again['lookups'] == 0 and again['status'] in ('not_needed', 'recently_searched')
        assert len(requested) <= 8 and usage.snapshot()['total_calls'] == len(requested)
        assert ('맛집', 'comment') in requested and ('음식점', 'random') in requested
        assert not any(term == '카페' and sort == 'comment' for term, sort in requested)

        result = recommend(c)
        assert result['status'] == 'ok' and 'strict_failure' not in result, result.get('reasons')
        plan = result['plans'][0]
        meal = {r['condition']: r for r in plan['condition_checks']}['meal']
        assert meal['state'] == 'met'
        meals = [p for p in plan['places'] if p.get('meal')]
        assert meals and all(p['name'] in ('서면 돼지국밥', '서면 스시', '서면 곱창') for p in meals)
        assert all(p['hours'] is None and p['price'] is None for p in meals)
        meal_costs = [row for p, row in zip(plan['places'], plan['costs']) if p.get('meal')]
        assert meal_costs and all(row['amount'] is None and row['status'] == 'unknown' for row in meal_costs), meal_costs
        assert all({p['name'] + ' 영업시간', p['name'] + ' 가격'} <= set(plan['unknown']) for p in meals), plan['unknown']
        assert all(p['region'] == '부산' for p in plan['places'])
        names = {p['name'] for p in intent_discovery_places()}
        assert '서면 디저트' in names and '서면 행사대행' not in names
        dessert = next(p for p in intent_discovery_places() if p['name'] == '서면 디저트')
        assert not dessert['meal'] and dessert['category'] == '카페·미식'
    finally:
        with store.connect() as db:
            for p in intent_discovery_places():
                db.execute('DELETE FROM cache WHERE key=?', ('discovered-place:' + p['id'],))


def intent_discovery_places():
    from app.catalog import places
    titles = {item['title'] for items in BUSAN.values() for item in items}
    return [p for p in places('real') if p['id'].startswith('discovered:') and p['name'] in titles
            and (p.get('address') or '').startswith('부산광역시 부산진구 부전동')]


# 강릉 안목해변처럼 카페만 많고 식사 장소가 적은 동네(2026-11-13 실측: 최종 1안).
ANMOK = dict(lat=37.7716, lon=128.9477)


def _anmok_conditions(**update):
    center = dict(name='강원 강릉 안목해변 지역 중심', **ANMOK)
    base = dict(mode='real', allow_estimates=True, include_meal=True, visit_date='2026-11-13', region='강원',
                origin=center, area_center=center, start='13:00', end='19:00', count=3)
    return Conditions(**(base | update))


def _anmok_item(title, category, dlat, dlon=0.0):
    return dict(title=title, category=category, roadAddress=f'강원특별자치도 강릉시 창해로 {title}',
                mapx=ANMOK['lon'] + dlon, mapy=ANMOK['lat'] + dlat)


def test_gangneung_neighborhood_search_reports_radius_losses_and_retries_meal(monkeypatch, isolated):
    cafes = [dict(id=f'anmok-cafe{i}', name=f'안목 카페 {i}', region='강원', lat=ANMOK['lat'] + i * .0005, lon=ANMOK['lon'],
                  category='카페·미식', meal=False, tags=[]) for i in range(7)]
    monkeypatch.setattr('app.catalog.places', lambda *a, **k: cafes)
    far = .05  # 약 5.5km: 시 단위 검색 결과처럼 반경 2.5km 밖
    answers = {
        '맛집': [_anmok_item('안목 칼국수', '한식>칼국수,만두', .003), _anmok_item('시내 짬뽕', '중식>중식당', far)],
        '음식점': [_anmok_item('안목 커피빵', '음식점>카페,디저트', .001)],
        '전시': [_anmok_item('시내 박물관', '문화,예술>박물관', far)],
        '미술관': [_anmok_item('시내 미술관', '문화,예술>미술관', far)],
        '공원': [_anmok_item('안목해변', '여행,명소>해수욕장,해변', .002)],
        '산책': [], '공방': [_anmok_item('시내 공방', '공예,공방>도자기', far)],
        '식당': [_anmok_item('안목 횟집', '음식점>생선회', .004)],
    }
    seen = []

    def lookup(term, area, **kw):
        seen.append((term, area))
        return answers.get(term, []), 'available'

    monkeypatch.setattr(intent_discovery, 'local_lookup', lookup)
    result = intent_discovery.discover_requested_places(_anmok_conditions())
    assert result['lookups'] == len(seen) <= 8
    assert result['query_area'] == '강릉 안목해변' and all(area == '강원 강릉 안목해변' for _, area in seen)
    # 식사가 반경 안에서 1곳뿐이라 남은 1건으로 같은 동네에서 다른 검색어('식당')를 쓴다.
    assert result['fallback_queries'] == [dict(kind='meal', term='식당', area='강원 강릉 안목해변')]
    assert result['meal_supply'] == dict(before=0, found_reachable=2, after=2, enough=True)
    stats = result['kind_stats']
    assert stats['culture'] == dict(received=2, out_of_radius=2)
    assert stats['meal']['out_of_radius'] == 1 and stats['meal']['other_kind'] == 1  # 음식점 검색의 카페
    assert stats['walk']['adopted'] == 1 and result['adopted']['walk'] == 1  # 해변은 산책·풍경
    assert result['adopted']['meal'] == 2 and result['adopted_reachable']['meal'] == 2


def test_gangneung_one_meal_place_still_fills_three_options(monkeypatch):
    """식사 장소가 1곳뿐이어도 식사 시간대를 지키는 안으로 3안을 채운다(고른 뒤 식사 미충족 안이 빠져 1안만 남던 문제)."""
    from app import store
    from app.planner import recommend
    from app.routes import distance
    monkeypatch.setenv('DATEMATE_OPTION_SELECTOR', 'shadow')
    rows = [dict(name='안목 칼국수', category='카페·미식', meal=True, tags=['meal', '한식>칼국수,만두'], dlat=.003)]
    rows += [dict(name=f'안목 카페 {i}', category='카페·미식', meal=False, tags=['cafe', '카페,디저트>카페'], dlat=-.0004 * i, dlon=.0004 * i)
             for i in range(1, 8)]
    ids = []
    try:
        for i, r in enumerate(rows):
            pid = f'discovered:anmoktest{i:011d}'
            ids.append(pid)
            store.cache('discovered-place:' + pid, dict(
                id=pid, name=r['name'], address=f'강원특별자치도 강릉시 창해로 {i + 1}', lat=ANMOK['lat'] + r['dlat'],
                lon=ANMOK['lon'] + r.get('dlon', 0), region='강원', demo=False, category=r['category'], themes=[r['category']],
                tags=r['tags'], meal=r['meal'], description=r['tags'][1], source='https://map.naver.com/p/search/test',
                source_type='네이버 지역 검색 · 요청 활동 유형 연결', checked_at='2026-11-13T00:00:00+00:00',
                discovery_verification='테스트', price=None, price_unit='person', hours=None, closed_days=None, breaks=None,
                last_entry=None, reservation=None, stay=None, stay_basis=None, rating=None, setting=None, photos=[], videos=[],
                license='검색 결과'), 600)
        result = recommend(_anmok_conditions())
        assert result['status'] == 'ok' and 'strict_failure' not in result
        assert len(result['plans']) == 3
        for plan in result['plans']:
            checks = {r['condition']: r['state'] for r in plan['condition_checks']}
            assert checks['meal'] == 'met' and plan['places'][0]['name'] == '안목 칼국수'
            assert all(distance(ANMOK, p) <= 2.5 for p in plan['places'])
        selection = result['diagnostics']['option_selection']
        assert selection['selector'] == 'shadow' and selection['returned'] == 3
    finally:
        with store.connect() as db:
            for pid in ids:
                db.execute('DELETE FROM cache WHERE key=?', ('discovered-place:' + pid,))
