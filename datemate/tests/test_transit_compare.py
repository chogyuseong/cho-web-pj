"""대중교통 지하철·버스 비교(app/transit_compare.py, GET /api/plans/{id}/transit-compare). TMAP 은 모두 가짜 httpx.post.

확인하는 것: pathType 묶음·가장 빠른 것·꼬리표·노선 이름·지도 좌표 파싱, 원화 아닌 요금, 이상한 응답, 키 없음·데모·대중교통 없음(호출 0),
캐시(두 번째 호출 없음, TTL 이 약관 24시간보다 짧음), 하루 상한, 응답에 키 없음, 코스 불변, 반복·IP 한도."""
import copy
import itertools
import uuid
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from app import store, transit_compare, web_security
from app.catalog import places
from app.condition_audit import audit_plan
from app.main import app
from app.models import Conditions
from app.planner import evaluate
from test_parking import unique_ip

KEY = 'private-tmap-test-key'


def itinerary(path_type, seconds, walk=300, transfers=0, fare=1500, currency='KRW', legs=None):
    return dict(pathType=path_type, totalTime=seconds, totalWalkTime=walk, transferCount=transfers, totalDistance=4000,
                fare=dict(regular=dict(totalFare=fare, currency=dict(currencyCode=currency))), legs=legs or [])


SUBWAY_LEGS = [
    dict(mode='WALK', sectionTime=120, steps=[dict(linestring='127.0000,37.5000 127.0010,37.5005')]),
    dict(mode='SUBWAY', route='수도권2호선', sectionTime=900, passShape=dict(linestring='127.0010,37.5005 127.0200,37.5100')),
    dict(mode='SUBWAY', route='수도권분당선', sectionTime=300, passShape=dict(linestring='127.0200,37.5100 127.0300,37.5200')),
]
BUS_LEGS = [dict(mode='BUS', route='간선:741', sectionTime=1200, passShape=dict(linestring='127.0000,37.5000 127.0300,37.5200'))]
ANSWER = dict(metaData=dict(plan=dict(itineraries=[
    itinerary(1, 1500, walk=540, transfers=1, fare=1550, legs=SUBWAY_LEGS),   # 지하철 25분
    itinerary(1, 1800, walk=400, transfers=0, fare=1550),                    # 더 느린 지하철 → 버림
    itinerary(2, 1680, walk=240, transfers=0, fare=1500, legs=BUS_LEGS),       # 버스 28분, 덜 걸음
    itinerary(3, 1620, walk=420, transfers=2, fare=1650),                    # 혼합 27분
    itinerary(5, 900, walk=60, transfers=0, fare=8000),                      # 기차 → 뺌
])))


@pytest.fixture
def tmap(monkeypatch):
    """가짜 TMAP. state['answer'] 를 바꿔 끼우고, 부른 요청(body·headers)을 남긴다."""
    monkeypatch.setenv(transit_compare.KEY_ENV, KEY)
    state = dict(calls=[], answer=ANSWER, status=200)

    def post(url, **kwargs):
        state['calls'].append(kwargs)
        return httpx.Response(state['status'], request=httpx.Request('POST', url), json=state['answer'])

    monkeypatch.setattr(httpx, 'post', post)
    return state


# 코스마다 좌표를 옮기는 양. 캐시 키는 좌표를 소수점 5자리로 반올림하므로(app/transit_compare.cache_key) 무작위만 쓰면
# 같은 실행 안의 두 코스가 같은 키가 될 수 있었다(약 1,000칸, PostgreSQL 은 캐시가 실행 내내 남아 CI 에서 가끔 실패).
# 실행마다 다른 시작점 + 코스마다 1e-4(반올림 칸의 10배)씩 늘리는 순번으로, 같은 실행 안에서는 반드시 다른 키가 되게 한다.
_SESSION_SHIFT = (uuid.uuid4().int % 500) / 1e4
_PLAN_SEQ = itertools.count()


def make_plan(transport='transit', mode='real', count=2, **fields):
    """출발지에서 북쪽으로 장소를 둔 코스. 좌표를 코스마다 옮겨 캐시(좌표 기준)가 다른 코스와 섞이지 않게 한다."""
    shift = _SESSION_SHIFT + next(_PLAN_SEQ) * 1e-4
    origin = dict(name='출발', lat=37.5 + shift, lon=127.0 + shift)
    picked = copy.deepcopy(places('demo')[:count])
    for i, p in enumerate(picked):
        p.update(hours=[0, 1440], closed_days=[], closed_dates=[], last_entry=None, breaks=None, price=[1000, 1000],
                 price_unit='person', stay=30, reservation=False, demo=False, region='서울',
                 lat=origin['lat'] + 0.01 * (i + 1), lon=origin['lon'])
    base = dict(mode=mode, visit_date=date(2026, 10, 24), count=count, budget=500000, max_leg=180, end='23:00',
                origin=origin, transport=transport, people=2)
    if mode == 'real':
        base['allow_estimates'] = True
    base.update(fields)
    c = Conditions(**base)
    plan, error = evaluate(picked, c)
    assert not error, error
    return dict(audit_plan(plan, c), id='plan-' + uuid.uuid4().hex)


def test_groups_by_path_type_and_keeps_the_fastest_of_each(tmap):
    plan = make_plan()
    body = transit_compare.compare(plan)
    assert body['status'] == 'available' and len(body['legs']) == len(plan['legs']) == 2
    assert len(tmap['calls']) == 2  # 구간마다 1건
    leg = body['legs'][0]
    subway, bus, mixed = (leg['options'][k] for k in ('subway', 'bus', 'mixed'))
    assert (subway['minutes'], subway['walk_minutes'], subway['transfers'], subway['fare_per_person']) == (25, 9, 1, 1550)
    assert (bus['minutes'], bus['walk_minutes'], bus['transfers']) == (28, 4, 0)
    assert mixed['minutes'] == 27
    assert set(leg['options']) == {'subway', 'bus', 'mixed'}  # 기차(pathType 5)는 없다
    assert leg['best'] == dict(fastest='subway', least_walk='bus', fewest_transfers='bus')
    assert [line['name'] for line in subway['lines']] == ['수도권2호선', '수도권분당선'] and bus['lines'] == [dict(mode='bus', name='간선:741')]
    # 지도 조각: 도보·지하철을 나눠 [경도, 위도] 로.
    assert [part['kind'] for part in subway['path']] == ['walk', 'subway', 'subway']
    assert subway['path'][1]['points'] == [[127.001, 37.5005], [127.02, 37.51]]
    assert leg['origin'] == plan['legs'][0]['origin'] and leg['estimate_minutes'] == plan['legs'][0]['minutes']
    assert body['source'].startswith('TMAP 대중교통') and body['expires_in'] + transit_compare.CACHE_SECONDS < 86400
    # 요청: 앱 키 머리글, 좌표 순서(경도=X), 지난 방문일(2026-10-24)은 searchDttm 없이.
    call = tmap['calls'][0]
    assert call['headers']['appKey'] == KEY and call['follow_redirects'] is False
    assert call['json']['startX'] == str(plan['conditions']['origin']['lon']) and 'searchDttm' not in call['json']
    assert KEY not in str(body)


def test_cache_is_reused_and_kept_shorter_than_the_24_hour_terms(tmap, monkeypatch):
    ttls = []
    real_cache = store.cache
    monkeypatch.setattr(store, 'cache', lambda key, value, ttl=86400: (ttls.append((key, ttl)), real_cache(key, value, ttl))[1])
    plan = make_plan(count=2)
    first = transit_compare.compare(plan)
    again = transit_compare.compare(plan)
    # 첫 비교 때만 구간 수만큼 부르고, 두 번째는 모두 캐시.
    assert len(tmap['calls']) == len(plan['legs']) and first['legs'] == again['legs']
    stored = [ttl for key, ttl in ttls if key.startswith('tmap-transit-v1:')]
    assert stored and all(ttl == transit_compare.CACHE_SECONDS < 86400 for ttl in stored)


def test_visit_date_in_the_future_sends_the_departure_time(tmap):
    plan = make_plan(visit_date=date(2099, 5, 2), start='13:07')
    transit_compare.compare(plan)
    assert tmap['calls'][0]['json']['searchDttm'] == '209905021300'  # 10분 단위로 내림
    departure = plan['timeline'][0]['departure'].replace(':', '')
    assert tmap['calls'][1]['json']['searchDttm'] == '20990502' + departure[:3] + '0'


def test_bad_or_foreign_answers_are_not_shown_as_routes(tmap):
    # 원화가 아니면 요금만 비우고 경로는 쓴다.
    tmap['answer'] = dict(metaData=dict(plan=dict(itineraries=[itinerary(2, 600, currency='USD')])))
    leg = transit_compare.compare(make_plan(count=2))['legs'][0]
    assert leg['status'] == 'available' and leg['options']['bus']['fare_per_person'] is None and leg['options']['subway'] is None
    # 이상한 숫자(도보가 전체보다 김)·빈 목록·서버 오류는 그 구간 unavailable, 캐시하지 않는다.
    for answer, status in ((dict(metaData=dict(plan=dict(itineraries=[itinerary(1, 100, walk=200)]))), 200),
                           (dict(metaData=dict(plan=dict(itineraries=[]))), 200), (dict(error='x'), 500)):
        tmap['answer'], tmap['status'] = answer, status
        before = len(tmap['calls'])
        body = transit_compare.compare(make_plan(count=2))
        assert body['status'] == 'unavailable' and all(leg['status'] == 'unavailable' for leg in body['legs'])
        assert all(leg['options'] == dict(subway=None, bus=None, mixed=None) for leg in body['legs'])
        assert len(tmap['calls']) > before


def test_no_calls_without_key_in_demo_or_without_transit_legs(monkeypatch):
    calls = []
    monkeypatch.setattr(httpx, 'post', lambda *a, **k: calls.append(1))
    assert transit_compare.compare(make_plan())['status'] == 'key_missing'
    monkeypatch.setenv(transit_compare.KEY_ENV, KEY)
    assert transit_compare.compare(make_plan(mode='demo'))['status'] == 'demo'
    assert transit_compare.compare(make_plan(transport='walk'))['status'] == 'not_transit'
    assert calls == []


def test_only_transit_legs_of_a_mixed_course_are_compared(tmap):
    plan = make_plan(transport='walk', count=2)
    # 두 번째 구간만 대중교통으로(구간 수단은 legs[].mode 를 먼저 본다, app/leg_modes.py leg_mode).
    plan['legs'][1]['mode'] = 'transit'
    body = transit_compare.compare(plan)
    assert [leg['index'] for leg in body['legs']] == [1] and len(tmap['calls']) == 1


def test_daily_cap_stops_calls(tmap, monkeypatch):
    monkeypatch.setenv(transit_compare.DAILY_LIMIT_ENV, '1')
    with store.connect() as db:
        db.execute("DELETE FROM request_budgets WHERE scope='tmap-transit:day'")
    body = transit_compare.compare(make_plan(count=2))
    statuses = [leg['status'] for leg in body['legs']]
    assert statuses[0] == 'available' and set(statuses[1:]) == {'limited'} and len(tmap['calls']) == 1
    body = transit_compare.compare(make_plan(count=2))
    assert body['status'] == 'limited' and body['message'].startswith('오늘 대중교통 비교 한도') and len(tmap['calls']) == 1
    with store.connect() as db:
        db.execute("DELETE FROM request_budgets WHERE scope='tmap-transit:day'")


@pytest.mark.usefixtures('same_rate_window')
def test_route_is_expensive_rate_limited_and_leaves_the_plan_alone(tmap, monkeypatch):
    assert any(p.match('GET /api/plans/abc/transit-compare') for p in web_security.EXPENSIVE)
    from app import main as app_main
    monkeypatch.setattr(app_main, 'TRANSIT_COMPARE_REPEAT_SECONDS', 30)
    app_main._status_cache['value'] = None  # /api/status 는 잠시 캐시된다
    with TestClient(app, client=(unique_ip(), 1)) as client:
        assert client.get('/api/status').json()['transit_compare_available'] is True
        plan = make_plan()
        saved = store.save_plan({k: v for k, v in plan.items() if k != 'id'}, store.owner_of(client.cookies['dm_session']))
        before = client.get('/api/plans/' + saved['id']).json()
        response = client.get(f"/api/plans/{saved['id']}/transit-compare")
        assert response.status_code == 200, response.text
        assert set(response.json()) == {'status', 'legs', 'source', 'expires_in', 'checked_at', 'message'}
        assert client.get(f"/api/plans/{saved['id']}/transit-compare").status_code == 429
        after = client.get('/api/plans/' + saved['id']).json()
        assert after['legs'] == before['legs'] and after['total'] == before['total'] and after['places'] == before['places']
        assert 'transit' not in str(after.get('conditions', {}).get('leg_modes'))
    # IP 범위 한도: 같은 IP 의 다른 브라우저도 함께 센다.
    monkeypatch.setenv('DATEMATE_IP_TRANSIT_COMPARES_PER_MINUTE', '1')
    address, codes = unique_ip(), []
    for _ in range(2):
        with TestClient(app, client=(address, 1)) as client:
            client.get('/api/status')
            saved = store.save_plan({k: v for k, v in make_plan().items() if k != 'id'}, store.owner_of(client.cookies['dm_session']))
            codes.append(client.get(f"/api/plans/{saved['id']}/transit-compare").status_code)
    assert codes == [200, 429]


def test_status_flag_is_off_without_key():
    from app import main as app_main
    app_main._status_cache['value'] = None
    with TestClient(app) as client:
        assert client.get('/api/status').json()['transit_compare_available'] is False
    app_main._status_cache['value'] = None
