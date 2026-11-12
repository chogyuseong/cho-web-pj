"""Regression tests for input bounds, session issuance and IP-range request limits."""
import hashlib
import logging
import threading
import time
import uuid
from datetime import timedelta

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import festivals, store, web_security
from app.catalog import places
from app.main import app
from app.models import Conditions, ReviewInput
from app.request_usage import bind_client, unbind_client, client_range
from app.service_time import today


def unique_ip():
    """A fresh TEST-NET-2 address so limit buckets never collide between tests."""
    n = uuid.uuid4().int
    return f'198.51.{n % 250}.{(n >> 8) % 250 + 1}'


def unique_v6_prefix():
    n = uuid.uuid4().int
    return f'2001:db8:{n % 65535:x}:{(n >> 16) % 65535:x}'


def session_count():
    with store.connect() as db:
        return db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]


# --- A. input bounds -------------------------------------------------------

def base_conditions(**fields):
    return dict(visit_date='2026-10-31', **fields)


@pytest.mark.parametrize('fields', [
    dict(avoid=['가' * 31]),
    dict(excluded_place_ids=['x' * 151]),
    dict(region='서' * 21),
    dict(themes=['카' * 21]),
    dict(count=5, locked={0: 'a', 1: 'b', 2: 'c', 3: 'd', 4: 'e', 5: 'f'}),
    dict(locked={0: 'x' * 151}),
])
def test_oversized_condition_fields_are_rejected(fields):
    with pytest.raises(ValidationError):
        Conditions(**base_conditions(**fields))
    with TestClient(app) as client:
        assert client.post('/api/plans', json=base_conditions(**fields)).status_code == 422


def test_condition_bounds_keep_normal_values():
    c = Conditions(**base_conditions(avoid=['클라이밍', '게임'], excluded_place_ids=['discovered:' + 'a' * 20],
                                     count=3, locked={0: 'discovered:' + 'b' * 20}, themes=['카페·미식']))
    assert c.avoid == ['클라이밍', '게임'] and c.locked == {0: 'discovered:' + 'b' * 20}


def test_review_body_is_limited_to_2000_characters():
    ReviewInput(rating=5, body='가' * 2000, nickname='별명', visited='2026-01-01')
    with pytest.raises(ValidationError):
        ReviewInput(rating=5, body='가' * 2001, nickname='별명', visited='2026-01-01')


def test_other_request_models_bound_strings():
    with TestClient(app) as client:
        long_id = 'x' * 151
        assert client.post('/api/plans/missing/replace',
                           json={'index': 0, 'replacement_id': long_id}).status_code in (404, 422)
        assert client.post('/api/shared-plan/vote', headers={'Authorization': 'Bearer t'},
                           json={'choices': {long_id: 'yes'}}).status_code == 422


def test_request_body_limit_is_64_kib():
    with TestClient(app) as client:
        # A normal maximal recommendation request still fits.
        big = base_conditions(request='가' * 4000, excluded_place_ids=['x' * 150] * 100,
                              avoid=['가' * 30] * 30)
        assert client.post('/api/conditions/parse', json={'text': '카페'}).status_code == 200
        assert len(str(big).encode()) < 64 * 1024
        response = client.post('/api/conditions/parse', content='x' * (64 * 1024 + 1))
        assert response.status_code == 413
        assert '64 KiB' in response.json()['detail']


def test_plan_payload_size_is_capped():
    huge = {'places': [{'id': 'p1', 'name': '장소'}], 'note': 'x' * (300 * 1024)}
    before = None
    with store.connect() as db:
        before = db.execute('SELECT COUNT(*) FROM plans').fetchone()[0]
    with pytest.raises(store.PlanTooLarge):
        store.save_plan(huge, 'payload-cap-owner')
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM plans').fetchone()[0] == before
    saved = store.save_plan({'places': [{'id': 'p1', 'name': '장소'}], 'note': 'x' * 1000}, 'payload-cap-owner')
    assert store.get_plan(saved['id'])


def test_oversized_recommendation_result_returns_safe_413(monkeypatch):
    import app.recommendation_service as service

    def too_big(data, owner):
        raise store.PlanTooLarge('코스 자료가 너무 커서 저장하지 않았어요.')

    monkeypatch.setattr(service, 'generate', too_big)
    with TestClient(app) as client:
        response = client.post('/api/plans', json=base_conditions())
    assert response.status_code == 413 and '너무 커서' in response.json()['detail']


# --- B. sessions -----------------------------------------------------------

def test_pages_and_404s_do_not_create_sessions():
    with TestClient(app, client=(unique_ip(), 1)) as client:
        before = session_count()
        for path in ('/', '/shared', '/no-such-page', '/static/style.css'):
            response = client.get(path)
            assert 'set-cookie' not in response.headers, path
        assert session_count() == before
        assert 'dm_session' not in client.cookies


def test_first_api_call_issues_lax_session_and_existing_cookie_is_kept():
    with TestClient(app, client=(unique_ip(), 1)) as client:
        first = client.get('/api/status')
        cookie = first.headers['set-cookie'].lower()
        assert 'samesite=lax' in cookie and 'httponly' in cookie
        token = client.cookies['dm_session']
        assert 'set-cookie' not in client.get('/').headers
        assert 'set-cookie' not in client.get('/api/status').headers
        assert client.cookies['dm_session'] == token
        # The owner is recognised: deleting my data works with the same cookie.
        assert client.delete('/api/me/data').status_code == 200


def test_new_sessions_are_limited_per_ip_range(monkeypatch):
    monkeypatch.setenv('DATEMATE_IP_SESSIONS_PER_MINUTE', '2')
    with TestClient(app, client=(unique_ip(), 1)) as client:
        assert client.get('/api/status').status_code == 200
        kept = client.cookies['dm_session']
        client.cookies.clear()
        assert client.get('/api/status').status_code == 200
        client.cookies.clear()
        response = client.get('/api/status')
        assert response.status_code == 429 and 'set-cookie' not in response.headers
        # An existing valid session is still recognised from the same range.
        client.cookies.set('dm_session', kept)
        assert client.get('/api/status').status_code == 200


# --- C. IP-range limits ----------------------------------------------------

def test_ipv6_is_grouped_by_64_and_ipv4_is_per_address():
    prefix = unique_v6_prefix()
    assert web_security.range_of(prefix + ':1::1') == web_security.range_of(prefix + ':ffff:1:2:3')
    assert web_security.range_of(prefix + ':1::1') != web_security.range_of('2001:db8:ffff:ffff::1')
    assert web_security.range_of('192.0.2.1') != web_security.range_of('192.0.2.2')
    assert web_security.range_of('::ffff:192.0.2.1') == '192.0.2.1'
    assert web_security.range_of('testclient') == 'testclient'


def geocode_stub(monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, 'search_address', lambda query: dict(status='ok', results=[], message=''))


def test_owner_limit_cannot_be_reset_by_dropping_cookie(monkeypatch):
    geocode_stub(monkeypatch)
    monkeypatch.setenv('DATEMATE_IP_GEOCODE_PER_MINUTE', '1')
    with TestClient(app, client=(unique_ip(), 1)) as client:
        assert client.post('/api/locations/search', json={'query': '서울 중구'}).status_code == 200
        client.cookies.clear()
        response = client.post('/api/locations/search', json={'query': '서울 중구'})
        assert response.status_code == 429


def test_ipv6_clients_in_one_64_share_limits(monkeypatch):
    geocode_stub(monkeypatch)
    monkeypatch.setenv('DATEMATE_IP_GEOCODE_PER_MINUTE', '1')
    prefix = unique_v6_prefix()
    with TestClient(app, client=(prefix + ':1::10', 1)) as first:
        assert first.post('/api/locations/search', json={'query': '서울 중구'}).status_code == 200
    with TestClient(app, client=(prefix + ':2::20', 1)) as same_range:
        assert same_range.post('/api/locations/search', json={'query': '서울 중구'}).status_code == 429
    with TestClient(app, client=(unique_v6_prefix() + '::1', 1)) as other_range:
        assert other_range.post('/api/locations/search', json={'query': '서울 중구'}).status_code == 200


def test_ipv4_neighbours_are_limited_separately(monkeypatch):
    geocode_stub(monkeypatch)
    monkeypatch.setenv('DATEMATE_IP_GEOCODE_PER_MINUTE', '1')
    a, b = unique_ip(), unique_ip()
    for address in (a, b):
        with TestClient(app, client=(address, 1)) as client:
            assert client.post('/api/locations/search', json={'query': '서울 중구'}).status_code == 200


def test_expensive_routes_have_their_own_lower_ip_limit(monkeypatch):
    monkeypatch.setenv('DATEMATE_IP_EXPENSIVE_REQUESTS_PER_MINUTE', '2')
    monkeypatch.delenv('TOUR_API_KEY', raising=False)
    url = f'/api/festivals?start={today()}&end={today()}'
    with TestClient(app, client=(unique_ip(), 1)) as client:
        assert client.get(url).status_code == 200
        client.cookies.clear()
        assert client.get(url).status_code == 200
        client.cookies.clear()
        assert client.get(url).status_code == 429
        # Ordinary routes still work.
        assert client.get('/api/status').status_code == 200


def test_recommendation_ip_limit_applies_across_sessions(monkeypatch):
    from app.execution import recommendation_slot
    monkeypatch.setenv('DATEMATE_IP_RECOMMENDATIONS_PER_MINUTE', '1')
    token = bind_client('recommendation-range-' + uuid.uuid4().hex)
    try:
        with recommendation_slot('first-owner-' + uuid.uuid4().hex):
            pass
        with pytest.raises(HTTPException) as error:
            with recommendation_slot('second-owner-' + uuid.uuid4().hex):
                pass
        assert error.value.status_code == 429
    finally:
        unbind_client(token)


def test_chat_ip_limit_applies_across_sessions(monkeypatch):
    monkeypatch.setenv('DATEMATE_IP_CHATS_PER_MINUTE', '1')
    with TestClient(app, client=(unique_ip(), 1)) as client:
        # The first question is admitted (then fails on the missing place).
        assert client.post('/api/chat/place/missing', json={'question': '질문'}).status_code == 404
        client.cookies.clear()
        assert client.post('/api/chat/place/missing', json={'question': '질문'}).status_code == 429


# --- D. global provider budget protection ----------------------------------

def test_place_blogs_are_cached_and_failures_are_not(monkeypatch):
    from app import blog_search
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID', 'test')
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET', 'secret')
    calls = []
    fail = {'on': True}

    def get(self, url, **kwargs):
        calls.append(url)
        if fail['on']:
            raise httpx.ConnectError('down')
        return httpx.Response(200, request=httpx.Request('GET', url), json={'items': [
            dict(title='캐시장소 후기', link='https://blog.naver.com/a/1', postdate='20261001')]})

    monkeypatch.setattr(httpx.Client, 'get', get)
    place = {'id': 'blog-cache-' + uuid.uuid4().hex, 'name': '캐시장소'}
    assert blog_search.place_blogs(place)['status'] == 'unavailable'
    assert blog_search.place_blogs(place)['status'] == 'unavailable'
    assert len(calls) == 2
    fail['on'] = False
    first = blog_search.place_blogs(place)
    second = blog_search.place_blogs(place)
    assert first == second and first['status'] == 'available' and len(calls) == 3


def test_media_refresh_is_limited_per_owner_and_ip(monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, 'media_info', lambda p, **kw: dict(status='not_found', photos=[]))
    pid = places('demo')[0]['id']
    url = f'/api/places/{pid}/media?mode=demo&refresh=true'
    with TestClient(app, client=(unique_ip(), 1)) as client:
        assert client.get(url).status_code == 200
        assert client.get(url).status_code == 429
        assert client.get(f'/api/places/{pid}/media?mode=demo').status_code == 200
    monkeypatch.setenv('DATEMATE_IP_REFRESHES_PER_MINUTE', '1')
    with TestClient(app, client=(unique_ip(), 1)) as client:
        assert client.get(url).status_code == 200
        client.cookies.clear()
        assert client.get(url).status_code == 429


def test_explore_query_length_and_uncached_search_limit(monkeypatch):
    from app import explore
    monkeypatch.setattr(explore, 'search_enabled', lambda: True)
    monkeypatch.setattr(explore, 'lookup', lambda client, query: (query, [], 'available'))
    monkeypatch.setenv('DATEMATE_IP_EXPLORE_SEARCHES_PER_MINUTE', '1')
    word = uuid.uuid4().hex[:8]
    with TestClient(app, client=(unique_ip(), 1)) as client:
        assert client.get('/api/explore', params={'region': '부산', 'q': '가' * 61}).status_code == 422
        assert client.get('/api/explore', params={'region': '부산', 'q': word}).status_code == 200
        # Cached results are free; a new search from the same range is refused.
        assert client.get('/api/explore', params={'region': '부산', 'q': word}).status_code == 200
        client.cookies.clear()
        assert client.get('/api/explore', params={'region': '부산', 'q': word + 'x'}).status_code == 429


def test_festival_start_date_window(monkeypatch):
    monkeypatch.delenv('TOUR_API_KEY', raising=False)
    now = today()
    with TestClient(app) as client:
        for start, ok in ((now - timedelta(days=31), True), (now + timedelta(days=366), True),
                          (now - timedelta(days=32), False), (now + timedelta(days=367), False)):
            response = client.get(f'/api/festivals?start={start}&end={start}')
            assert (response.status_code == 200) is ok, (start, response.status_code)


def test_festival_detail_only_for_listed_ids(monkeypatch):
    monkeypatch.setenv('TOUR_API_KEY', 'test-only-secret')
    listed = str(880000 + uuid.uuid4().int % 9999)
    unlisted = str(int(listed) + 100000)
    day = today().strftime('%Y%m%d')

    class Response:
        content = b'{}'

        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self.payload

    calls = []

    def fake_get(fn, url, params):
        calls.append(url)
        if url.endswith('searchFestival2'):
            return Response({'response': {'header': {'resultCode': '0000'}, 'body': {'totalCount': 1, 'items': {'item': [
                {'contentid': listed, 'title': '목록 축제', 'addr1': '서울특별시 중구',
                 'eventstartdate': day, 'eventenddate': day}]}}}})
        return Response({'response': {'header': {'resultCode': '0000'},
                                      'body': {'items': {'item': [{'usetimefestival': '무료'}]}}}})

    monkeypatch.setattr(festivals, 'observed_http', fake_get)
    with TestClient(app) as client:
        assert client.get(f'/api/festivals/{unlisted}/detail').status_code == 404
        assert calls == []
        region = '서울'
        result = client.get(f'/api/festivals?start={today()}&end={today()}&region={region}').json()
        assert listed in [row['id'] for row in result['festivals']]
        detail = client.get(f'/api/festivals/{listed}/detail')
        assert detail.status_code == 200 and detail.json()['fee'] == '무료'
        assert client.get(f'/api/festivals/{unlisted}/detail').status_code == 404


def test_provider_budget_has_a_per_ip_share(monkeypatch):
    from app.telemetry import observed_http
    monkeypatch.setenv('DATEMATE_PROVIDER_CALLS_PER_HOUR', '100')
    monkeypatch.setenv('DATEMATE_PROVIDER_CALLS_PER_IP_PER_HOUR', '1')
    host = f'https://share-{uuid.uuid4().hex[:8]}.example/x'
    def call(*args, **kwargs):
        return httpx.Response(200)

    token = bind_client('range-a-' + uuid.uuid4().hex)
    try:
        assert observed_http(call, host).status_code == 200
        with pytest.raises(httpx.PoolTimeout):
            observed_http(call, host)
    finally:
        unbind_client(token)
    token = bind_client('range-b-' + uuid.uuid4().hex)
    try:
        # The global budget still has room for other ranges.
        assert observed_http(call, host).status_code == 200
    finally:
        unbind_client(token)
    # Without a request context only the global budget applies.
    assert observed_http(call, host).status_code == 200


def test_default_ip_share_is_half_of_the_global_budget(monkeypatch):
    # 둘러보기 한 화면이 사진 조회로 수십 번 호출하므로 1/4은 정상 사용에 빠듯했다.
    from app.telemetry import provider_limits
    monkeypatch.setenv('DATEMATE_PROVIDER_CALLS_PER_HOUR', '600')
    monkeypatch.delenv('DATEMATE_PROVIDER_CALLS_PER_IP_PER_HOUR', raising=False)
    token = bind_client('half')
    try:
        assert [limit for _, limit in provider_limits('p.example')] == [600, 300]
    finally:
        unbind_client(token)


def test_queued_recommendation_keeps_requester_ip_range(monkeypatch):
    from app import plan_jobs
    seen = []
    done = threading.Event()

    def record(key, data, owner):
        seen.append(client_range())
        plan_jobs._jobs.pop(key, None)
        done.set()

    monkeypatch.setattr(plan_jobs, '_run', record)
    address = unique_ip()
    with TestClient(app, client=(address, 1)) as client:
        assert client.post('/api/plan-jobs', json=base_conditions()).status_code == 202
    assert done.wait(5)
    assert seen == [hashlib.sha256(web_security.range_of(address).encode()).hexdigest()]


# --- F. shared slots do not queue request threads ---------------------------

def test_busy_blog_slot_fails_fast(monkeypatch):
    from app import blog_search
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID', 'test')
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET', 'secret')
    monkeypatch.setattr(blog_search, 'LOCK_WAIT_SECONDS', 0.05)
    monkeypatch.setattr(httpx.Client, 'get', lambda *a, **k: (_ for _ in ()).throw(AssertionError('no call')))
    assert blog_search._lock.acquire(timeout=1)
    try:
        started = time.monotonic()
        result = blog_search.place_blogs({'id': 'busy-' + uuid.uuid4().hex, 'name': '바쁜장소'})
        assert result['status'] == 'unavailable' and time.monotonic() - started < 1
    finally:
        blog_search._lock.release()


def test_busy_menu_and_photo_slots_fail_fast(monkeypatch):
    from app import menus, public_place_photos
    monkeypatch.setattr(menus, 'LOCK_WAIT_SECONDS', 0.05)
    monkeypatch.setattr(public_place_photos, 'LOCK_WAIT_SECONDS', 0.05)
    monkeypatch.setattr(menus, 'fetch_page', lambda *a: (_ for _ in ()).throw(AssertionError('no call')))
    monkeypatch.setattr(public_place_photos, 'fetch_page', lambda *a: (_ for _ in ()).throw(AssertionError('no call')))
    place = dict(id='busy-menu-' + uuid.uuid4().hex, name='바쁜식당', address='서울특별시 중구 테스트로 1',
                 lat=37.56, lon=126.99, region='서울')
    held = 0
    while menus._limit.acquire(blocking=False):
        held += 1
    try:
        started = time.monotonic()
        menu = menus.restaurant_menu(place)
        photos = public_place_photos.public_place_photos(place)
        assert menu['status'] == 'unavailable' and menu['reason'] == 'busy'
        assert photos['status'] == 'unavailable' and photos['photos'] == []
        assert time.monotonic() - started < 1
    finally:
        for _ in range(held):
            menus._limit.release()
    # Busy answers are not cached as results.
    assert store.cached('restaurant-menu-v4:' + place['id']) is None


def test_busy_image_slot_fails_fast_without_caching(monkeypatch):
    from app import image_search
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID', 'test')
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET', 'secret')
    monkeypatch.setattr(image_search, 'LOCK_WAIT_SECONDS', 0.05)
    held = 0
    while image_search._image_slots.acquire(blocking=False):
        held += 1
    try:
        result = image_search.search_place_images({'id': 'busy-img-' + uuid.uuid4().hex, 'name': '바쁜곳'})
        assert result == {'status': 'unavailable', 'photos': []}
    finally:
        for _ in range(held):
            image_search._image_slots.release()


def test_wiki_pacing_only_for_wikipedia_and_bounded(monkeypatch):
    from app import collection
    monkeypatch.delenv('WIKI_CONTACT', raising=False)
    monkeypatch.setattr(collection, 'LOCK_WAIT_SECONDS', 0.05)

    class Ok:
        def raise_for_status(self):
            pass

        def json(self):
            return {'ok': True}

    monkeypatch.setattr(collection, 'observed_http', lambda *a, **k: Ok())
    started = time.monotonic()
    for _ in range(3):
        assert collection.fetch_json('https://maps.apigw.ntruss.com/map-direction/v1/driving') == {'ok': True}
    assert time.monotonic() - started < 1  # directions are not spaced 6 s apart
    assert collection._lock.acquire(timeout=1)
    try:
        started = time.monotonic()
        with pytest.raises(httpx.PoolTimeout):
            collection.fetch_json('https://ko.wikipedia.org/w/api.php')
        assert time.monotonic() - started < 1
    finally:
        collection._lock.release()
    # A caller whose turn is more than one interval away gives up instead of queueing.
    monkeypatch.setattr(collection, '_last', time.monotonic() + 30)
    with pytest.raises(httpx.PoolTimeout):
        collection.fetch_json('https://ko.wikipedia.org/w/api.php')


# --- G. low-severity fixes ---------------------------------------------------

def test_amount_regex_is_linear_and_still_parses_amounts():
    from app.request_intent import interpret
    started = time.monotonic()
    interpret('1,' * 4000 + '원' + uuid.uuid4().hex)
    interpret('1,1' * 3000 + uuid.uuid4().hex)
    assert time.monotonic() - started < 0.2
    assert interpret('예산 5만원')['patch']['budget'] == 50000
    assert interpret('예산 30,000원')['patch']['budget'] == 30000
    assert interpret('1.5만원 정도')['patch']['budget'] == 15000


def test_http_client_loggers_do_not_log_request_urls():
    assert logging.getLogger('httpx').getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger('httpcore').getEffectiveLevel() >= logging.WARNING


def test_status_is_cached_and_drops_internal_fields(monkeypatch):
    import app.main as main
    calls = []
    real = main.collections

    def counted(mode):
        calls.append(mode)
        return real(mode)

    monkeypatch.setattr(main, 'collections', counted)
    monkeypatch.setitem(main._status_cache, 'value', None)
    with TestClient(app) as client:
        first = client.get('/api/status').json()
        second = client.get('/api/status').json()
    assert first == second and len(calls) == 2  # demo + real, once
    assert 'route' not in first
    for field in ('region', 'counts', 'llm', 'embedding', 'themes', 'date_categories',
                  'map_js_key', 'geocoding_available', 'map_tile_url', 'map_tile_attribution'):
        assert field in first
