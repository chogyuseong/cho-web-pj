"""같은 업체 확인을 공공 자료로(app/place_identity.py, 2026-11-20 특약 2단계 3.6(b)).

- 판정은 소상공인 상가정보(위치 확인)와 행안부 인허가(영업 중·폐업으로 등록됨)에서만 나온다. 네이버 지역 검색은 부르지 않는다.
- 사용자 요청(verify_identity, /media, /identity)은 저장된 판정만 읽고 공공 API 를 부르지 않는다. 없으면 배경 조회에 맡기고 pending.
- 자료에 없음·실패·시간 초과·키 없음·네이버 검색 장소는 판정 없음(unknown)이고 화면은 링크만 그린다.
외부 호출은 모두 가짜 응답이다(httpx.MockTransport).
"""
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app import place_identity, store

CAFE = dict(id='identity-cafe', name='어니언 성수점', category='카페·미식', lat=37.5446, lon=127.0557,
            address='서울 성동구 아차산로9길 8', region='서울')
MEAL = dict(id='identity-meal', name='명동교자 본점', category='카페·미식', meal=True, lat=37.562571, lon=126.985757,
            address='서울 중구 명동10길 29', region='서울')
# 인허가 자료의 실제 좌표(EPSG:5174) — 명동10길 29.
MEAL_X, MEAL_Y = '198672.005950725', '451143.699280519'


def store_row(name, lat, lon, branch='', road='서울특별시 성동구 아차산로9길 8'):
    return dict(bizesNm=name, brchNm=branch, lat=lat, lon=lon, rdnmAdr=road, lnoAdr='')


def license_row(name, road='서울특별시 중구 명동10길 29 (명동2가, 1,2,3,4층)', code='01', closed='', x=MEAL_X, y=MEAL_Y, changed='2026-06-02 18:02:54'):
    return dict(BPLC_NM=name, ROAD_NM_ADDR=road, SALS_STTS_CD=code, SALS_STTS_NM='영업/정상' if code == '01' else '폐업',
                CLSBIZ_YMD=closed, CRD_INFO_X=x, CRD_INFO_Y=y, LAST_MDFCN_PNT=changed, DAT_UPDT_PNT='2026-06-03 03:03:03')


def store_body(rows, total=None, month='202609'):
    return dict(header=dict(resultCode='00', stdrYm=month), body=dict(items=rows, totalCount=len(rows) if total is None else total))


def license_body(rows, total=None):
    return dict(response=dict(header=dict(resultCode='0', resultMsg='정상'),
                              body=dict(items=dict(item=rows), totalCount=len(rows) if total is None else total)))


@pytest.fixture
def public_api(monkeypatch):
    """공공 API 가짜. box['store'], box['일반음식점'], box['휴게음식점'] 에 응답(dict·httpx.Response·예외)을 넣고 box['calls'] 로 호출을 본다."""
    monkeypatch.setenv('TOUR_API_KEY', "'test-public-key'")
    box = dict(calls=[], store=store_body([]), 일반음식점=license_body([]), 휴게음식점=license_body([]))

    def handler(request):
        path = request.url.path
        kind = 'store' if 'storeListInRadius' in path else '일반음식점' if 'general_restaurants' in path else '휴게음식점' if 'rest_cafes' in path else None
        if kind is None:  # 같은 키로 부르는 TourAPI 등은 이 테스트의 대상이 아니다.
            return httpx.Response(404, text='not mocked')
        box['calls'].append((kind, dict(request.url.params)))
        answer = box[kind]
        if callable(answer):
            answer = answer(request)
        if isinstance(answer, Exception):
            raise answer
        return answer if isinstance(answer, httpx.Response) else httpx.Response(200, json=answer)

    real = httpx.Client.__init__
    monkeypatch.setattr(httpx.Client, '__init__', lambda self, *a, **k: real(self, *a, **dict(k, transport=httpx.MockTransport(handler))))
    return box


# ---------------------------------------------------------------- 주소·이름 규칙


def test_road_key_and_query_come_from_the_road_address():
    assert place_identity.road_key('서울 중구 명동10길 29 (명동2가, 1,2,3,4층)') == ('명동10길', '29')
    assert place_identity.road_key('서울특별시 중구 다산로 151, 신당스퀘어 2층 (신당동)') == ('다산로', '151')
    assert place_identity.road_key('경기 수원시 팔달구 정조로 800-1') == ('정조로', '800-1')
    assert place_identity.road_key('서울 성동구 성수동2가 280-10') is None, '지번 주소로는 인허가를 찾지 않는다'
    assert place_identity.road_query('서울 중구 명동10길 29') == '중구 명동10길 29'
    assert place_identity.road_query('경기 수원시 팔달구 정조로 800') == '팔달구 정조로 800'
    assert place_identity.road_query('세종 한누리대로 2130') == '한누리대로 2130'
    assert place_identity.road_query('서울 성동구 성수동2가 280-10') is None


def test_store_info_needs_the_same_name_nearby_at_one_address():
    near = store_row('어니언', 37.5448, 127.0559)
    assert place_identity.store_matches(CAFE, [near]) == 1, '지점 낱말을 뗀 이름도 같은 업소로 본다'
    assert place_identity.store_matches(CAFE, [store_row('어니언', 37.5448, 127.0559, branch='성수점')]) == 1, '상호 + 지점명'
    assert place_identity.store_matches(CAFE, [near, dict(near)]) == 1, '같은 주소의 중복 행은 한 곳'
    assert place_identity.store_matches(CAFE, [near, store_row('어니언', 37.5450, 127.0561, road='서울특별시 성동구 성수이로 1')]) == 2
    assert place_identity.store_matches(CAFE, [store_row('어니언', 37.5600, 127.0700)]) == 0, '400m 밖'
    assert place_identity.store_matches(CAFE, [store_row('어니언수제어묵', 37.5448, 127.0559)]) == 0, '이름이 다르다'
    assert place_identity.store_matches(CAFE, [dict(bizesNm='어니언'), None]) == 0, '좌표가 없거나 깨진 행'


def test_license_match_needs_the_same_building_and_a_matching_name():
    rows = [license_row('명동교자 후'), license_row('주식회사 명동교자', road='서울특별시 중구 퇴계로 129, 명동교자 (충무로2가)'),
            license_row('다른식당'), license_row('명동교자', road='부산광역시 중구 명동10길 29', x='390000', y='180000')]
    assert [row['BPLC_NM'] for row in place_identity.license_matches(MEAL, rows)] == ['명동교자 후']
    assert place_identity.license_verdict(MEAL, rows, '일반음식점')['status'] == 'open'
    assert place_identity.license_matches(dict(MEAL, address='서울 중구 명동2가 25-2'), rows) == [], '도로명 주소가 없으면 맞추지 않는다'
    assert place_identity.license_matches(dict(MEAL, name='교자'), [license_row('명동교자 후')]) == [], '두 글자 이름의 부분 일치는 쓰지 않는다'


def test_license_verdict_open_closed_or_none():
    closed = [license_row('명동교자', code='03', closed='2024-01-31'), license_row('명동교자 후', code='03', closed='20260302')]
    verdict = place_identity.license_verdict(MEAL, closed, '일반음식점')
    assert verdict['status'] == 'closed' and verdict['closed_on'] == '2026-03-02' and verdict['kind'] == '일반음식점'
    reopened = closed + [license_row('명동교자 후')]
    verdict = place_identity.license_verdict(MEAL, reopened, '일반음식점')
    assert verdict['status'] == 'open' and verdict['modified_on'] == '2026-06-02', '폐업 이력이 있어도 지금 영업 중인 인허가가 있으면 영업 중'
    assert place_identity.license_verdict(MEAL, [license_row('명동교자', code='02')], '일반음식점') is None, '휴업 등은 판정하지 않는다'
    assert place_identity.license_verdict(MEAL, [license_row('다른식당')], '일반음식점') is None


# ---------------------------------------------------------------- 조회(배경 일꾼이 부르는 함수)


def test_store_lookup_reads_pages_and_the_data_month(public_api):
    public_api['store'] = lambda request: store_body([store_row('어니언', 37.5448, 127.0559)] if request.url.params['pageNo'] == '1' else [], total=1)
    with httpx.Client() as client:
        result = place_identity.store_lookup(CAFE, client)
    assert result['status'] == 'located' and result['data_month'] == '202609'
    kind, params = public_api['calls'][0]
    assert kind == 'store' and params['radius'] == str(place_identity.STORE_RADIUS_M) and params['cx'] == '127.0557' and params['cy'] == '37.5446'
    assert params['serviceKey'] == 'test-public-key', '작은따옴표로 감싼 키도 받는다'
    public_api['store'] = dict(header=dict(resultCode='03', resultMsg='NODATA_ERROR'), body={})
    with httpx.Client() as client:
        assert place_identity.store_lookup(CAFE, client)['status'] == 'not_found'
    # 반경 안 업소가 너무 많아 다 못 보면 판정하지 않는다(하나뿐인지 알 수 없음).
    public_api['calls'].clear()
    public_api['store'] = store_body([store_row('어니언', 37.5448, 127.0559)], total=99999)
    with httpx.Client() as client:
        assert place_identity.store_lookup(CAFE, client)['status'] == 'not_found'
    assert len(public_api['calls']) == place_identity.STORE_MAX_PAGES


def test_license_lookup_searches_by_road_address_never_whole_lists(public_api):
    public_api['일반음식점'] = license_body([license_row('명동교자 후')])
    with httpx.Client() as client:
        result = place_identity.license_lookup(MEAL, client)
    assert result['status'] == 'open' and result['kind'] == '일반음식점'
    assert [kind for kind, _ in public_api['calls']] == ['일반음식점'], '식사 장소는 일반음식점부터, 찾으면 멈춘다'
    params = public_api['calls'][0][1]
    assert params['cond[ROAD_NM_ADDR::LIKE]'] == '중구 명동10길 29' and params['numOfRows'] == '100' and params['pageNo'] == '1'
    # 카페는 휴게음식점부터 보고, 없으면 일반음식점도 본다.
    public_api['calls'].clear()
    with httpx.Client() as client:
        assert place_identity.license_lookup(CAFE, client)['status'] == 'not_found'
    assert [kind for kind, _ in public_api['calls']] == ['휴게음식점', '일반음식점']
    # 음식점·카페가 아니거나 도로명 주소가 없으면 부르지 않는다.
    public_api['calls'].clear()
    with httpx.Client() as client:
        assert place_identity.license_lookup(dict(CAFE, category='문화·예술'), client)['status'] == 'not_applicable'
        assert place_identity.license_lookup(dict(MEAL, address='서울 중구 명동2가 25-2'), client)['status'] == 'not_applicable'
    assert public_api['calls'] == []


def test_license_lookup_adds_the_name_when_a_building_has_too_many_rows(public_api):
    def general(request):
        if 'cond[BPLC_NM::LIKE]' in request.url.params:
            return license_body([license_row('명동교자 후')])
        return license_body([license_row('다른식당')], total=350)

    public_api['일반음식점'] = general
    with httpx.Client() as client:
        assert place_identity.license_lookup(MEAL, client)['status'] == 'open'
    assert public_api['calls'][1][1]['cond[BPLC_NM::LIKE]'] == '명동교자'


@pytest.mark.parametrize('failure', [httpx.ReadTimeout('slow'), httpx.Response(504, text='gateway'),
                                     httpx.Response(200, text='<OpenAPI_ServiceResponse>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</OpenAPI_ServiceResponse>')])
def test_license_failures_give_no_verdict(public_api, failure):
    public_api['일반음식점'] = failure
    with httpx.Client() as client:
        assert place_identity.license_lookup(MEAL, client) is None, '실패는 not_found 로 남기지 않는다'


# ---------------------------------------------------------------- 화면용 판정(저장된 것만 읽음)


def test_request_path_never_calls_public_apis_and_queues_the_lookup(public_api):
    first = place_identity.verify_identity(MEAL)
    assert first == dict(status='unknown', pending=True, source=None, reason='checking')
    assert public_api['calls'] == [], '사용자 요청은 공공 API 를 부르지 않는다'
    assert len(place_identity._queue) == 1
    # 배경 일꾼이 돌면 판정이 저장되고, 다음 요청은 그것을 읽는다.
    public_api['store'] = store_body([store_row('명동교자', 37.562573, 126.985761, road='서울특별시 중구 명동10길 29')])
    public_api['일반음식점'] = license_body([license_row('명동교자 후')])
    place_identity._work()
    assert not place_identity._queue
    calls = len(public_api['calls'])
    seen = place_identity.verify_identity(MEAL)
    assert seen['status'] == 'open' and seen['source'] == 'license' and seen['license_kind'] == '일반음식점'
    assert seen['pending'] is False and seen['age_days'] == 0 and seen['modified_on'] == '2026-06-02'
    assert len(public_api['calls']) == calls and not place_identity._queue, '저장된 판정이 있으면 다시 맡기지 않는다'


def test_store_info_only_gives_located_with_the_data_month(public_api):
    public_api['store'] = store_body([store_row('어니언', 37.5448, 127.0559)])
    place_identity.lookup(CAFE)
    seen = place_identity.verify_identity(CAFE)
    assert seen['status'] == 'located' and seen['source'] == 'store_info' and seen['data_month'] == '202609'
    assert seen['radius_m'] == 200 and seen['pending'] is False


def test_closed_license_wins_over_store_info(public_api):
    public_api['store'] = store_body([store_row('명동교자', 37.562573, 126.985761, road='서울특별시 중구 명동10길 29')])
    public_api['일반음식점'] = license_body([license_row('명동교자 후', code='03', closed='2026-03-02')])
    place_identity.lookup(MEAL)
    seen = place_identity.verify_identity(MEAL)
    assert seen['status'] == 'closed' and seen['closed_on'] == '2026-03-02' and seen['source'] == 'license'


def test_age_days_counts_from_the_stored_check_time(public_api):
    old = (datetime.now(timezone.utc) - timedelta(days=3, hours=1)).isoformat()
    store.cache(place_identity.cache_key(MEAL, 'license'), dict(status='open', kind='일반음식점', checked_at=old), 3600)
    store.cache(place_identity.cache_key(MEAL, 'store'), dict(status='not_found', checked_at=old), 3600)
    assert place_identity.verify_identity(MEAL)['age_days'] == 3


def test_slow_or_failing_api_leaves_no_verdict_and_backs_off(public_api):
    public_api['store'] = httpx.Response(500, text='error')
    public_api['일반음식점'] = httpx.ReadTimeout('slow')
    public_api['휴게음식점'] = httpx.Response(504, text='gateway')
    place_identity.lookup(MEAL)
    calls = len(public_api['calls'])
    seen = place_identity.verify_identity(MEAL)
    # 조회 실패는 '자료에 없음'(not_found)이 아니라 '연결 실패'(unavailable)로 답한다(2026-11-20 운영 키 오류 점검).
    assert seen == dict(status='unknown', pending=False, source=None, reason='unavailable'), '판정 없음 — 화면은 링크만'
    assert not place_identity._queue, '실패 직후에는 다시 맡기지 않는다(RETRY_SECONDS)'
    place_identity.lookup(MEAL)
    assert len(public_api['calls']) == calls
    # 실패는 판정으로 저장되지 않는다.
    assert store.cached(place_identity.cache_key(MEAL, 'license')) is None and store.cached(place_identity.cache_key(MEAL, 'store')) is None


def test_not_found_everywhere_is_unknown(public_api):
    place_identity.lookup(CAFE)
    assert place_identity.verify_identity(CAFE) == dict(status='unknown', pending=False, source=None, reason='not_found')


def test_no_key_demo_and_naver_places_are_never_looked_up(public_api, monkeypatch):
    for place in (dict(CAFE, demo=True), dict(CAFE, lat=None), dict(CAFE, naver_result=True),
                  dict(CAFE, id='discovered:abc'), dict(CAFE, source_type='네이버 지역 검색')):
        assert place_identity.verify_identity(place) == dict(status='unknown', pending=False, source=None, reason='not_applicable')
    monkeypatch.setenv('TOUR_API_KEY', '')
    assert place_identity.verify_identity(CAFE) == dict(status='unknown', pending=False, source=None, reason='key_missing')
    assert not place_identity._queue and public_api['calls'] == []


def test_stored_verdict_holds_no_key_and_no_store_list(public_api):
    public_api['store'] = store_body([store_row('명동교자', 37.562573, 126.985761, road='서울특별시 중구 명동10길 29')])
    public_api['일반음식점'] = license_body([license_row('명동교자 후')])
    place_identity.lookup(MEAL)
    with store.connect() as db:
        rows = db.execute("SELECT key,payload FROM cache WHERE key LIKE 'public-identity-v1:%'").fetchall()
    text = ' '.join(str(row['key']) + str(row['payload']) for row in rows)
    assert len(rows) == 2 and 'test-public-key' not in text and '명동교자' not in text and 'ROAD_NM_ADDR' not in text


def test_queue_keeps_the_newest_places_and_drops_the_oldest(public_api, monkeypatch):
    monkeypatch.setattr(place_identity, 'QUEUE_MAX', 3)
    for index in range(5):
        place_identity.enqueue(dict(CAFE, id=f'queue-{index}'))
    place_identity.enqueue(dict(CAFE, id='queue-3'))
    assert [place['id'] for place in place_identity._queue.values()] == ['queue-2', 'queue-4', 'queue-3']
    assert set(next(iter(place_identity._queue.values()))) == {'id', 'name', 'address', 'lat', 'lon', 'category', 'meal'}


def test_slow_license_call_does_not_hold_an_external_slot(public_api, monkeypatch):
    """인허가 조회(수십 초)는 동시 외부 호출 자리를 잡지 않는다. 자리가 모두 찬 상태에서도 조회가 나간다."""
    from app import telemetry

    monkeypatch.setenv('DATEMATE_EXTERNAL_SLOT_WAIT_SECONDS', '0')
    held = 0
    while telemetry._slots.acquire(blocking=False):
        held += 1
    try:
        public_api['일반음식점'] = license_body([license_row('명동교자 후')])
        with httpx.Client() as client:
            assert place_identity.license_lookup(MEAL, client)['status'] == 'open'
            with pytest.raises(httpx.PoolTimeout):
                place_identity.store_lookup(MEAL, client)
    finally:
        for _ in range(held):
            telemetry._slots.release()


# ---------------------------------------------------------------- HTTP


def test_media_and_identity_endpoints_answer_from_the_cache_only(public_api):
    from app.main import app

    with TestClient(app) as client:
        media = client.get('/api/places/Q482485/media?mode=real').json()
        assert media['identity']['status'] == 'unknown' and media['identity']['pending'] is True
        again = client.get('/api/places/Q482485/identity?mode=real')
        assert again.status_code == 200 and again.json()['place_id'] == 'Q482485' and again.json()['identity']['pending'] is True
        assert client.get('/api/places/demo-01/identity?mode=demo').json()['identity'] == dict(status='unknown', pending=False, source=None, reason='not_applicable')
        assert client.get('/api/places/not-found/identity?mode=real').status_code == 404
    assert public_api['calls'] == [], '요청 안에서는 상가정보·인허가 API 를 부르지 않는다'


def test_naver_local_search_is_not_used_for_identity(public_api, monkeypatch):
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID', 'id')
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET', 'secret')
    monkeypatch.setattr('app.naver_local.lookup', lambda *a, **k: pytest.fail('네이버 지역 검색 호출'))
    public_api['store'] = store_body([store_row('어니언', 37.5448, 127.0559)])
    place_identity.verify_identity(CAFE)
    place_identity._work()
    assert place_identity.verify_identity(CAFE)['status'] == 'located'
    assert all('naver' not in str(params) for _, params in public_api['calls'])
