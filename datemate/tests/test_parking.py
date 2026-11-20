"""자동차로 도착하는 장소 근처 주차장: 대상 장소, 공공데이터 주차장만 쓰는 목록, 상태, 한도.

2026-11-20 2단계: 네이버 지역 검색 결과를 주차장 목록의 입력으로 쓰지 않는다(app/parking.py). 외부 호출이 없다."""
import copy
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

import json

from app import parking, public_parking, store, web_security
from app.catalog import places
from app.condition_audit import audit_plan
from app.main import app
from app.models import Conditions
from app.planner import evaluate

ORIGIN = dict(name='서울 종로구 출발', lat=37.575, lon=126.985)
LOT_FIELDS = {'id', 'name', 'category', 'address', 'lat', 'lon', 'distance_m', 'walk_minutes', 'public'}
COLUMNS = ['id', 'name', 'kind', 'address', 'lat', 'lon', 'fee_kind', 'base_minutes', 'base_fee', 'extra_minutes', 'extra_fee',
           'day_fee', 'days', 'weekday', 'saturday', 'holiday', 'as_of', 'provider', 'free_days', 'district']


def unique_ip():
    n = uuid.uuid4().int
    return f'198.51.{n % 250}.{(n >> 8) % 250 + 1}'


def rows(count=3):
    """출발지에서 북쪽으로 약 1.1km씩 떨어진 실제 모드 장소. 이름은 테스트마다 달라 캐시가 섞이지 않는다."""
    tag = uuid.uuid4().hex[:6]
    picked = copy.deepcopy(places('demo')[:count])
    for i, p in enumerate(picked):
        p.update(hours=[0, 1440], closed_days=[], closed_dates=[], last_entry=None, breaks=None,
                 price=[1000, 1000], price_unit='person', stay=30, reservation=False, demo=False,
                 name=f'테스트장소{i + 1}-{tag}', address=f'서울특별시 종로구 삼청동 {i + 10}', region='서울',
                 lat=ORIGIN['lat'] + 0.01 * (i + 1), lon=ORIGIN['lon'])
    return picked


def make_plan(mode='real', transport='walk', car_legs=(), places_rows=None, **fields):
    picked = places_rows or rows()
    ids = ['origin', *[p['id'] for p in picked], 'home']
    leg_modes = [{'from': ids[i], 'to': ids[i + 1], 'mode': 'car'} for i in car_legs]
    base = dict(mode=mode, visit_date=date(2026, 10, 24), count=len(picked), budget=500000, max_leg=180,
                end='23:00', origin=ORIGIN, transport=transport, leg_modes=leg_modes)
    if mode == 'real':
        base['allow_estimates'] = True
    base.update(fields)
    c = Conditions(**base)
    plan, error = evaluate(picked, c)
    assert not error, error
    return audit_plan(plan, c)


def public_rows(tmp_path, rows_):
    """공공데이터 주차장 파일을 tmp 에 쓰고 그 파일로 바꾼다."""
    path = tmp_path / 'public_parking.json'
    path.write_text(json.dumps(dict(columns=COLUMNS, rows=rows_), ensure_ascii=False), encoding='utf-8')
    public_parking.reset(path)


def public_row(name, lat, lon, **fields):
    row = dict(id='P-' + name, name=name, kind='공영', address='서울특별시 종로구 삼청동 1', lat=lat, lon=lon, fee_kind='유료',
               base_minutes=30, base_fee=500, extra_minutes=10, extra_fee=200, day_fee=None, days='평일+토요일+공휴일',
               weekday=['09:00', '21:00'], saturday=['10:00', '18:00'], holiday=None, as_of='2026-04-16', provider='종로구',
               free_days=None, district='종로구')
    row.update(fields)
    return [row[c] for c in COLUMNS]


@pytest.fixture(autouse=True)
def no_public_parking(tmp_path):
    """기본은 공공데이터 주차장 없음(저장소의 실제 파일과 섞이지 않게). 필요한 테스트만 public_rows 로 채운다."""
    public_rows(tmp_path, [])
    yield
    public_parking.reset()


@pytest.fixture(autouse=True)
def no_naver_local_search(monkeypatch):
    """주차장 조회는 네이버 지역 검색을 부르지 않는다. 키가 있어도 마찬가지다."""
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID', 'test')
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET', 'secret')
    monkeypatch.setattr('app.naver_local.lookup', lambda *a, **k: pytest.fail('네이버 지역 검색 호출'))
    monkeypatch.setattr('httpx.get', lambda *a, **k: pytest.fail('외부 호출'))


def test_all_walking_course_is_not_car():
    result = parking.parking_near(make_plan())
    assert result['status'] == 'not_car' and result['stops'] == []


def test_only_places_reached_by_car_get_parking(tmp_path):
    plan = make_plan(car_legs=(0, 2))
    assert [leg['mode'] for leg in plan['legs']] == ['car', 'walk', 'car']
    result = parking.parking_near(plan)
    assert [s['index'] for s in result['stops']] == [0, 2]
    assert [s['place_id'] for s in result['stops']] == [plan['places'][0]['id'], plan['places'][2]['id']]
    # 공공데이터에 없으면 지어내지 않고, 민영 주차장은 네이버 지도에서 찾으라고 안내한다.
    assert result['status'] == 'not_found' and result['source_type'] == '공공데이터포털 전국주차장정보표준데이터'
    assert all(s['lots'] == [] and '네이버 지도' in s['message'] for s in result['stops'])


def test_return_home_by_car_is_not_a_parking_stop():
    plan = make_plan(car_legs=(3,), return_home=True, home=dict(name='우리 집', lat=37.575, lon=126.995))
    assert [leg['mode'] for leg in plan['legs']] == ['walk', 'walk', 'walk', 'car']
    assert parking.parking_near(plan)['status'] == 'not_car'


def test_demo_status():
    assert parking.parking_near(make_plan(mode='demo', transport='car'))['status'] == 'demo'


def test_public_lots_are_listed_nearest_first_with_fees_and_hours(tmp_path):
    plan = make_plan(car_legs=(0,), places_rows=rows(2), count=2)  # 방문일 2026-10-24(토)
    place = plan['places'][0]
    lat, lon = place['lat'], place['lon']
    public_rows(tmp_path, [
        public_row('삼청 공영주차장', lat + 0.0012, lon),
        # 이름에 '주차'가 없으면 붙인다.
        public_row('삼청동 2', lat + 0.002, lon, fee_kind='무료', base_fee=0),
        public_row('셋째', lat + 0.003, lon),
        public_row('넷째', lat + 0.004, lon),
        # 800m 밖, 다른 시·도 주소, 좌표 없는 행은 뺀다.
        public_row('먼 곳', lat + 0.009, lon),
        public_row('다른 시도', lat + 0.001, lon, address='경기도 성남시 분당구 1'),
        public_row('좌표 없음', None, None),
    ])
    result = parking.parking_near(plan)
    lots = result['stops'][0]['lots']
    assert result['status'] == 'available' and result['message'] == ''
    assert [lot['name'] for lot in lots] == ['삼청 공영주차장', '삼청동 2 주차장', '셋째 주차장'], '장소당 가까운 3곳'
    first, second, _ = lots
    assert first['public'] == dict(fee='기본 30분 500원 · 추가 10분당 200원', hours='방문일(토) 10:00~18:00', kind='공영',
                                   as_of='2026-04-16', source='공공데이터포털 전국주차장정보표준데이터')
    assert second['public']['fee'] == '무료' and all(set(lot) == LOT_FIELDS and lot['id'].startswith('parking:public-') for lot in lots)
    assert first['distance_m'] < second['distance_m'] and first['walk_minutes'] >= 1
    assert result['diagnostics'] == dict(public_candidates=4, public_bus_only=0, live_candidates=0, live_attached=0)


def test_a_lot_near_two_stops_is_listed_under_the_nearer_one(tmp_path):
    plan = make_plan(transport='car', places_rows=rows(2), count=2)
    a, b = plan['places']
    middle = (a['lat'] + b['lat']) / 2 - 0.001
    public_rows(tmp_path, [public_row('사이 주차장', middle, a['lon'])])
    result = parking.parking_near(plan)
    assert [[lot['name'] for lot in s['lots']] for s in result['stops']] == [['사이 주차장'], []]
    assert result['stops'][1]['status'] == 'not_found' and result['status'] == 'available'


def test_bus_only_lots_are_left_out(tmp_path):
    plan = make_plan(car_legs=(0,), places_rows=rows(2), count=2)
    place = plan['places'][0]
    lat, lon = place['lat'], place['lon']
    public_rows(tmp_path, [
        public_row('DDP동측(양쪽) 관광버스전용 주차장(시)', lat + 0.001, lon, fee_kind='무료', base_fee=0),
        public_row('훈련원공원 앞 관광버스 전용 주차장(시)', lat + 0.003, lon, fee_kind='무료', base_fee=0),
        public_row('동대문 공영주차장(시)', lat + 0.002, lon),
    ])
    result = parking.parking_near(plan)
    assert [lot['name'] for lot in result['stops'][0]['lots']] == ['동대문 공영주차장(시)']
    assert result['diagnostics']['public_bus_only'] == 2 and result['diagnostics']['public_candidates'] == 1


@pytest.mark.usefixtures('same_rate_window')
def test_route_is_expensive_rate_limited_and_leaves_the_plan_alone(monkeypatch, tmp_path):
    assert any(p.match('GET /api/plans/abc/parking') for p in web_security.EXPENSIVE)
    # 운영은 1초. 전체 테스트를 돌리는 느린 기계에서는 첫 응답과 둘째 요청 사이가 1초를 넘어 막히지 않은 적이 있어,
    # 이 검사에서는 막는 시간을 늘린다(막는 동작 자체를 본다).
    from app import main as app_main
    monkeypatch.setattr(app_main, 'PARKING_REPEAT_SECONDS', 30)
    with TestClient(app, client=(unique_ip(), 1)) as client:
        client.get('/api/status')
        plan = store.save_plan(make_plan(transport='car'), store.owner_of(client.cookies['dm_session']))
        place = plan['places'][1]
        public_rows(tmp_path, [public_row('경로 주차장', place['lat'] + 0.001, place['lon'])])
        before = client.get('/api/plans/' + plan['id']).json()
        response = client.get(f"/api/plans/{plan['id']}/parking")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['status'] == 'available'
        assert set(body) == {'status', 'stops', 'note', 'source_type', 'message', 'diagnostics'}
        lots = [lot for stop in body['stops'] for lot in stop['lots']]
        assert lots and all(set(lot) == LOT_FIELDS for lot in lots)
        # 같은 브라우저의 1초 안 연속 요청은 막는다.
        assert client.get(f"/api/plans/{plan['id']}/parking").status_code == 429
        after = client.get('/api/plans/' + plan['id']).json()
        assert after['total'] == before['total'] and after['places'] == before['places'] and after['legs'] == before['legs']
    # IP 한도는 주변 식당 조회와 함께 쓴다.
    monkeypatch.setenv('DATEMATE_IP_LOCAL_SEARCHES_PER_MINUTE', '1')
    # 같은 IP 의 다른 브라우저(세션)도 함께 센다. 계획은 만든 브라우저만 열 수 있어 각자 하나씩 만든다.
    address = unique_ip()
    codes = []
    for _ in range(2):
        with TestClient(app, client=(address, 1)) as client:
            client.get('/api/status')
            plan = store.save_plan(make_plan(transport='car'), store.owner_of(client.cookies['dm_session']))
            response = client.get(f"/api/plans/{plan['id']}/parking")
            codes.append(response.status_code)
    assert codes == [200, 429] and response.json()['detail'] == '주차장 검색은 잠시 후 다시 시도해 주세요.'


def test_fee_and_hours_text():
    from datetime import date
    lot = dict(fee_kind='유료', base_minutes=30, base_fee=1200, extra_minutes=15, extra_fee=600, day_fee=14400,
               days='평일+토요일', weekday=['00:00', '23:59'], saturday=['09:00', '18:00'], holiday=None)
    assert public_parking.fee_text(lot) == '기본 30분 1,200원 · 추가 15분당 600원 · 1일 14,400원'
    assert public_parking.fee_text(dict(lot, fee_kind='무료')) == '무료'
    assert public_parking.fee_text(dict(lot, fee_kind='혼합', extra_fee=None, day_fee=None)) == '유료·무료 혼합 · 기본 30분 1,200원'
    assert public_parking.fee_text(dict(fee_kind='유료', base_minutes=None, base_fee=None)) is None
    assert public_parking.hours_text(lot, date(2026, 11, 16)) == '방문일(월) 24시간'
    assert public_parking.hours_text(lot, date(2026, 11, 21)) == '방문일(토) 09:00~18:00'
    assert public_parking.hours_text(lot, date(2026, 11, 22)) == '방문일(일) 운영하지 않아요(운영요일: 평일+토요일)'
    assert public_parking.hours_text(lot, None) is None


def test_hours_with_the_same_start_and_end_are_unknown():
    from datetime import date
    # 서울 파일: 운영요일은 시각 칸이 있으면 넣으므로 '00:00 00:00' 도 운영일로 들어온다. 뜻(휴무·24시간·자료 없음)을 알 수 없어 줄을 비운다.
    seoul = dict(days='평일+토요일+공휴일', weekday=['09:00', '19:00'], saturday=['09:00', '15:00'], holiday=['00:00', '00:00'])
    assert public_parking.hours_text(seoul, date(2026, 11, 22)) is None
    assert public_parking.hours_text(seoul, date(2026, 11, 17)) == '방문일(화) 09:00~19:00'
    every = dict(days='평일+토요일+공휴일', weekday=['00:00', '00:00'], saturday=['00:00', '00:00'], holiday=['00:00', '00:00'])
    assert public_parking.hours_text(every, date(2026, 11, 17)) is None
    assert public_parking.hours_text(dict(every, weekday=['23:59', '23:59']), date(2026, 11, 17)) is None
    # 전국 자료: '00:00 00:00' 인 요일은 운영요일에서 빠져 있어 지금처럼 '운영하지 않아요'로 보인다.
    national = dict(days='평일+토요일', weekday=['08:00', '20:00'], saturday=['08:00', '20:00'], holiday=['00:00', '00:00'])
    assert public_parking.hours_text(national, date(2026, 11, 22)) == '방문일(일) 운영하지 않아요(운영요일: 평일+토요일)'
    assert public_parking.hours_text(dict(seoul, holiday=['00:00', '24:00']), date(2026, 11, 22)) == '방문일(일) 24시간'


def test_bus_only_names():
    for name in ['DDP동측(양쪽) 관광버스전용 주차장(시)', '훈련원공원 앞 관광버스 전용 주차장(시)', '낙산성곽 버스전용 주차장(구)',
                 '정동진 바다부채길 주차장1(대형버스 전용)', '황매산 대형버스주차장', '송도해수욕장 버스주차장', '중앙로관광버스전용주차장']:
        assert public_parking.bus_only(name), name
    for name in ['동대문 공영주차장(시)', '시외버스터미널 공영주차장', '버스터미널주차장', '영산포버스터미널건너편주차장',
                 '대흥천변 버스정류장 주차장', '수동면버스승강장주차장', '대형버스·승용차 주차장', None]:
        assert not public_parking.bus_only(name), name


def test_build_script_reads_the_cp949_csv(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location('build_public_parking', Path(__file__).parents[1] / 'scripts' / 'build_public_parking.py')
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    header = ('주차장관리번호,주차장명,주차장구분,소재지도로명주소,소재지지번주소,운영요일,평일운영시작시각,평일운영종료시각,'
              '토요일운영시작시각,토요일운영종료시각,공휴일운영시작시각,공휴일운영종료시각,요금정보,주차기본시간,주차기본요금,'
              '추가단위시간,추가단위요금,1일주차권요금,위도,경도,데이터기준일자,제공기관명')
    lines = [header,
             '1-1,포석로공영주차장,공영,,경상북도 경주시 황남동 1,평일+토요일,10:00,18:00,10:00,18:00,,,유료,30,500,10,200,"10,000",35.83,129.21,2026-04-16,경상북도 경주시',
             '1-2,좌표없음,공영,,경상북도 경주시 2,평일,,,,,,,무료,0,0,,,,,,2026-04-16,경상북도 경주시']
    source = tmp_path / 'parking.csv'
    source.write_bytes('\n'.join(lines).encode('cp949'))
    out = tmp_path / 'out.json'
    monkeypatch.setattr(build, 'OUT', out)
    build.main(str(source))
    payload = json.loads(out.read_text(encoding='utf-8'))
    assert payload['columns'] == COLUMNS and len(payload['rows']) == 1
    row = dict(zip(COLUMNS, payload['rows'][0]))
    assert row['name'] == '포석로공영주차장' and row['address'] == '경상북도 경주시 황남동 1' and row['day_fee'] == 10000
    assert row['weekday'] == ['10:00', '18:00'] and row['holiday'] is None and row['as_of'] == '2026-04-16'


def test_name_core_and_district():
    assert public_parking.name_core('성수2가3동(건물) 공영주차장(구)') == public_parking.name_core('성수2가3동 공영주차장') == '성수2가3동'
    assert public_parking.district('서울특별시 성동구 성수동2가 299-19') == '성동구'
    assert public_parking.district('경상북도 경주시 황남동 1') == '경주시'


def test_build_script_merges_the_seoul_file(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location('build_public_parking', Path(__file__).parents[1] / 'scripts' / 'build_public_parking.py')
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    national = ('주차장관리번호,주차장명,주차장구분,소재지도로명주소,소재지지번주소,운영요일,평일운영시작시각,평일운영종료시각,'
                '토요일운영시작시각,토요일운영종료시각,공휴일운영시작시각,공휴일운영종료시각,요금정보,주차기본시간,주차기본요금,'
                '추가단위시간,추가단위요금,1일주차권요금,위도,경도,데이터기준일자,제공기관명\n'
                '1-1,종로 공영주차장,공영,서울특별시 종로구 종로 1,,평일,09:00,18:00,,,,,유료,30,1000,,,,37.57,126.98,2026-04-16,서울특별시 종로구\n')
    seoul = ('주차장코드,주차장명,주소,주차장 종류명,유무료구분명,평일 운영 시작시각(HHMM),평일 운영 종료시각(HHMM),'
             '주말 운영 시작시각(HHMM),주말 운영 종료시각(HHMM),공휴일 운영 시작시각(HHMM),공휴일 운영 종료시각(HHMM),'
             '최종데이터 동기화 시간,토요일 유,무료 구분명,공휴일 유,무료 구분명,기본 주차 요금,기본 주차 시간(분 단위),'
             '추가 단위 요금,추가 단위 시간(분 단위),일 최대 요금,위도,경도\n')
    # '토요일 유,무료 구분명'처럼 쉼표가 든 열 이름은 따옴표로 감싼다.
    seoul = seoul.replace('토요일 유,무료 구분명', '"토요일 유,무료 구분명"').replace('공휴일 유,무료 구분명', '"공휴일 유,무료 구분명"')
    seoul += ('1,종로(건물) 공영주차장(구),종로구 종로 1,노외 주차장,유료,0000,2400,0000,2400,0000,2400,2026-11-02 17:11:12,무료,무료,250,5,0,0,,37.57,126.98\n'
              '2,삼청동(건물) 공영주차장(구),종로구 삼청동 35,노외 주차장,유료,0900,1900,0900,1900,,,2026-11-02 17:11:12,무료,유료,250,5,0,0,,,\n')
    a, b = tmp_path / 'n.csv', tmp_path / 's.csv'
    a.write_bytes(national.encode('cp949'))
    b.write_bytes(seoul.encode('cp949'))
    out = tmp_path / 'out.json'
    monkeypatch.setattr(build, 'OUT', out)
    build.main(str(a), str(b))
    payload = json.loads(out.read_text(encoding='utf-8'))
    got = [dict(zip(payload['columns'], r)) for r in payload['rows']]
    # 전국 자료의 같은 주차장(같은 이름 핵심, 50m 안)은 빠지고 서울 파일 두 곳만 남는다.
    assert [r['name'] for r in got] == ['종로(건물) 공영주차장(구)', '삼청동(건물) 공영주차장(구)']
    first, second = got
    assert first['weekday'] == ['00:00', '24:00'] and first['free_days'] == '토요일·공휴일 무료' and first['as_of'] == '2026-11-02'
    assert second['lat'] is None and second['district'] == '종로구' and second['free_days'] == '토요일 무료'
    assert second['address'] == '서울특별시 종로구 삼청동 35' and second['days'] == '평일+토요일'
