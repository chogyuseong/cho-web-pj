"""추천 대기 시간 줄이기(2026-11-14)의 동작 확인. 외부 호출 없음.

1) 고정 입력 비교: 네이버 검색을 고정 자료로 흉내 내고 실제 장소 모드 추천 전체(generate)를 돌려,
   3안의 장소·순서·이름·비용과 조건 확인이 기준 파일과 같은지 본다. 캐시가 빈 상태와 찬 상태 모두.
   기준 파일은 DATEMATE_WRITE_RECOMMENDATION_GOLDEN=1 로 이 테스트를 돌려 만든다.
   2026-11-20(네이버 검색 API 특약 2단계)에 다시 만들었다: 블로그 글을 추천 계산에 쓰지 않고(가산점·이유 문장 없음),
   블로그 요약에서 가격을 읽지 않아(가격 검색 호출 0건) 3안과 비용이 달라졌다. 블로그 결과와 추천의 분리는 tests/test_blog_independent_block.py.
2) 바꾼 부분 단위 확인: 저장 묶음(store.cached_many·cache_many), 외부 호출 지표 묶어 쓰기, 긴 폴링(단계가 바뀔 때·취소될 때 바로 답함).
"""
import asyncio
import json
import os
import threading
import time
import uuid
from datetime import datetime as real_datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app import store
from app.models import Conditions

GOLDEN = Path(__file__).parent / 'fixtures' / 'recommendation_golden.json'
POSTDATE = '20261101'

JEONJU = dict(name='전북 전주 한옥마을 지역 중심', lat=35.8150, lon=127.1530)
SEONGSU = dict(name='서울 성수역 지역 중심', lat=37.5446, lon=127.0559)


def card(region, origin, mood, category):
    return dict(course_query='', mode='real', allow_price_estimates=True, allow_estimates=True, stay_minutes=60, region=region,
                origin=origin, visit_date='2026-11-15', start='11:00', end='19:00', people=2, budget=100000, transport='walk',
                count=3, themes=[], date_category=category, date_subcategory=mood, theme_mode='mix', setting='any', avoid=[],
                reservation=False, max_leg=30, request='', locked={}, include_meal=True, neighborhood_radius_km=2.5,
                priority='balanced', trust_mode='balanced', hard_constraints=[], explicit_fields=[])


SCENARIOS = {
    'jeonju': card('전북', JEONJU, '편안한 데이트', '콘셉트별'),
    'seongsu': card('서울', SEONGSU, '지적인 데이트', '콘셉트별'),
}

# 지역 검색 검색어(마지막 낱말)별 결과: (상호, 업종, 위도 차, 경도 차). 출발지 반경 2km 안에 흩어 둔다.
LOCAL = {
    '맛집': [('한옥 비빔밥', '음식점>한식>비빔밥', .002, .001), ('골목 칼국수', '음식점>한식>칼국수,만두', -.003, .002)],
    '음식점': [('남문 피순대', '음식점>한식>순대,순댓국', .004, -.002), ('카페 담', '음식점>카페,디저트', .001, .003)],
    '카페': [('한옥 찻집', '카페,디저트>전통찻집', -.002, -.001), ('기와 로스터리', '카페,디저트>카페', .003, .004)],
    '전시': [('골목 갤러리', '문화,예술>갤러리,화랑', -.004, .001), ('행사 대행사', '지원,대행>전시,행사대행', .001, .001)],
    '미술관': [('작은 미술관', '문화,예술>미술관', .005, .002)],
    '공원': [('오목대 공원', '여행,명소>공원', -.001, -.004)],
    '산책': [('천변 산책로', '여행,명소>산책로', .006, -.003)],
    '공방': [('한지 공방', '공예,공방>한지공예', -.005, -.003), ('도자기 체험', '공예,공방>도자기', .002, -.005)],
    '식당': [('전주 백반', '음식점>한식>백반,가정식', -.006, .002)],
    '디저트': [('초코 디저트', '카페,디저트>디저트', .004, .005)],
    '갤러리': [], '명소': [], '체험': [],
}
ADDRESS = {'전북': '전북특별자치도 전주시 완산구 기린대로', '서울': '서울특별시 성동구 왕십리로'}

# 블로그 본문: 이미 있는 장소(서울숲 등)와 지역 검색으로 찾을 장소를 섞어 언급한다.
BODIES = [
    '서울숲 산책 뒤 건국대학교박물관 관람. 한옥 비빔밥 점심이 좋았어요. 입장료는 무료였어요.',
    '기와 로스터리 아메리카노 5,000원. 골목 갤러리 전시도 봤어요. 서울숲은 다시 갈 거예요.',
    '한지 공방 체험 1인 체험비 25,000원. 남문 피순대는 비추천이에요.',
    '오목대 공원 산책 · 작은 미술관 관람료 3,000원. 광고 포함 글입니다.',
    '천변 산책로 따라 걷다가 한옥 찻집 쌍화차 7,000원.',
]


def blog_items(query):
    words = query.split()
    return [dict(title=f'{words[0]} 데이트 코스 후기 {i}', description=f'{words[0]} 데이트 {BODIES[i][:40]}',
                 link=f'https://blog.naver.com/author{i}/22300000000{i}', postdate=POSTDATE) for i in range(5)] + [
        dict(title='같은 작성자 다른 글', description='중복', link='https://blog.naver.com/author0/223999999999', postdate=POSTDATE)]


def local_items(query, region):
    term = query.split()[-1]
    lat, lon = (JEONJU if region == '전북' else SEONGSU)['lat'], (JEONJU if region == '전북' else SEONGSU)['lon']
    return [dict(title=title, category=category, roadAddress=f'{ADDRESS[region]} {i + 1}',
                 mapx=str(lon + dlon), mapy=str(lat + dlat)) for i, (title, category, dlat, dlon) in enumerate(LOCAL.get(term, []))]


class FixedDatetime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        return real_datetime(2026, 11, 14, 12, 0, tzinfo=tz) if tz else real_datetime(2026, 11, 14, 12, 0)


@pytest.fixture
def naver(monkeypatch):
    """네이버 검색 키가 있는 것처럼 하고, 모든 외부 호출을 고정 자료로 답한다.
    blog 에 함수를 넣으면 블로그 검색 응답(items)을 바꿀 수 있다(검색어를 받음). 코스 블로그 검색(display=20)이 아닌 블로그 검색
    (예전의 가격 검색)은 나가면 안 되므로 호출 기록에 'unexpected-blog'로 남긴다."""
    from app import course_search
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID', 'test-id')
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET', 'test-secret')
    monkeypatch.setenv('DATEMATE_OPTION_SELECTOR', 'experience')
    monkeypatch.setattr(course_search, 'datetime', FixedDatetime)
    calls = []
    region = {}
    state = SimpleNamespace(calls=calls, region=region, blog=blog_items)

    def fake_get(url, params=None, **kwargs):
        query = (params or {}).get('query', '')
        path = httpx.URL(url).path
        if path == '/search/v1/local':
            items = local_items(query, region['name'])
        elif path == '/search/v1/blog' and params.get('display') == 20:
            items = state.blog(query)
        else:
            path = 'unexpected-blog' if path == '/search/v1/blog' else path
            items = []
        calls.append(path)
        return httpx.Response(200, json=dict(items=items), request=httpx.Request('GET', url))

    monkeypatch.setattr(httpx, 'get', fake_get)
    before = discovered_keys()
    yield state
    # 이 테스트가 찾은 장소는 지운다(다른 테스트가 장소 목록을 그대로 세는 경우가 있음).
    with store.connect() as db:
        for key in discovered_keys() - before:
            db.execute('DELETE FROM cache WHERE key=?', (key,))


def discovered_keys():
    with store.connect() as db:
        return {row[0] for row in db.execute("SELECT key FROM cache WHERE key LIKE 'discovered-place:%'")}


def clean_region(region):
    """다른 테스트가 남긴 같은 지역의 찾은 장소·검색 캐시를 지워 매번 같은 출발 상태에서 시작한다."""
    with store.connect() as db:
        rows = db.execute("SELECT key,payload FROM cache WHERE key LIKE 'discovered-place:%'").fetchall()
        for key, payload in rows:
            if json.loads(payload).get('region') == region:
                db.execute('DELETE FROM cache WHERE key=?', (key,))
        for prefix in ('course-blog-v4:', 'intent-local-v6'):
            db.execute('DELETE FROM cache WHERE key LIKE ?', (prefix + '%',))


VOLATILE = {'checked_at', 'pricing_checked_at', 'recommendation_group_id', 'timing', 'created'}


def scrub(value):
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items() if k not in VOLATILE and not k.endswith('checked_at')}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def comparable(result):
    plans = []
    for plan in result['plans']:
        plan = {k: v for k, v in plan.items() if k not in ('id', 'parent')}
        plans.append(scrub(plan))
    return dict(status=result.get('status'), reasons=result.get('reasons'), plans=plans,
                course_search=scrub(result.get('course_search')),
                option_selection_after_pricing=scrub((result.get('diagnostics') or {}).get('option_selection_after_pricing')))


def summary(result):
    """실패했을 때 읽기 쉬운 요약: 안마다 이름·장소·비용."""
    return [(p.get('option_purpose'), [x['name'] for x in p['places']], p.get('total')) for p in result['plans']]


def run(name, naver, owner=None):
    # 네이버 검색 결과는 사용자별로만 보관한다(app/naver_cache, 2026-11-20). '캐시가 찬 상태'는 같은 사용자가 같은 조건으로 다시 추천할 때다.
    from app.recommendation_service import generate
    data = SCENARIOS[name]
    naver.region['name'] = data['region']
    return generate(Conditions(**data), owner or store.owner_of('golden-' + uuid.uuid4().hex))


@pytest.mark.parametrize('name', sorted(SCENARIOS))
def test_same_input_and_cache_state_give_the_same_recommendation_as_before(name, naver):
    clean_region(SCENARIOS[name]['region'])
    owner = store.owner_of('golden-' + uuid.uuid4().hex)
    cold = run(name, naver, owner)
    cold_calls = list(naver.calls)
    warm = run(name, naver, owner)
    got = dict(cold=comparable(cold), warm=comparable(warm), cold_calls=sorted(cold_calls))
    if os.getenv('DATEMATE_WRITE_RECOMMENDATION_GOLDEN'):
        golden = json.loads(GOLDEN.read_text('utf-8')) if GOLDEN.exists() else {}
        golden[name] = got
        GOLDEN.write_text(json.dumps(golden, ensure_ascii=False, indent=1, sort_keys=True), 'utf-8')
        pytest.skip('기준 파일을 썼어요.')
    expected = json.loads(GOLDEN.read_text('utf-8'))[name]
    assert cold['plans'] and len(cold['plans']) == len(expected['cold']['plans'])
    assert summary(cold) == [(p.get('option_purpose'), [x['name'] for x in p['places']], p.get('total')) for p in expected['cold']['plans']]
    assert summary(warm) == [(p.get('option_purpose'), [x['name'] for x in p['places']], p.get('total')) for p in expected['warm']['plans']]
    # 외부 호출 종류와 횟수도 같다(묶음 저장·지표 묶어 쓰기는 호출 수를 바꾸지 않음).
    assert got['cold_calls'] == expected['cold_calls']
    # 블로그 검색은 코스 조사 패널용 한 번뿐이다(가격을 찾는 블로그 검색 없음). 같은 사용자의 같은 조건 재추천은 외부 호출이 없다.
    assert cold_calls.count('/search/v1/blog') == 1 and 'unexpected-blog' not in naver.calls
    assert naver.calls == cold_calls
    assert json.loads(json.dumps(got, ensure_ascii=False, sort_keys=True)) == expected


# --- 저장 묶음 ---

def test_cached_many_and_cache_many_round_trip():
    store.cache_many([('speed:a', {'v': 1}, 60), ('speed:b', [1, 2], 60), ('speed:a', {'v': 2}, 60), ('speed:old', 1, -1)])
    found = store.cached_many(['speed:a', 'speed:b', 'speed:old', 'speed:missing', 'speed:a'])
    assert found == {'speed:a': {'v': 2}, 'speed:b': [1, 2]}
    assert store.cached('speed:a') == {'v': 2}
    assert store.cached_many([]) == {}
    store.cache_many([])
    many = [f'speed:n{i}' for i in range(450)]
    store.cache_many([(k, i, 60) for i, k in enumerate(many)])
    assert len(store.cached_many(many)) == 450


def test_provider_metrics_are_written_once_when_the_recommendation_ends():
    from app.request_usage import measure
    from app.telemetry import observed_http

    def metric():
        with store.connect() as db:
            row = db.execute('SELECT SUM(calls) AS calls,SUM(errors) AS errors FROM provider_metrics WHERE provider=?', ('batch.example',)).fetchone()
        # 이름으로 읽는다: PostgreSQL 의 Record(dict, app/database.py)는 순회하면 값이 아니라 열 이름을 내준다.
        return (row['calls'] or 0, row['errors'] or 0)

    before = metric()
    with measure() as usage:
        for status in (200, 200, 503):
            observed_http(lambda url, **kw: httpx.Response(status), 'https://batch.example/x')
        assert metric() == before and len(usage.metrics) == 3
    assert metric() == (before[0] + 3, before[1] + 1)
    # 작업이 끝난 뒤의 호출은 바로 쓴다.
    observed_http(lambda url, **kw: httpx.Response(200), 'https://batch.example/x')
    assert metric() == (before[0] + 4, before[1] + 1)


def test_parallel_lookups_share_one_permission_check_and_keep_partial_failures(monkeypatch):
    from app import intent_discovery, discovery
    from app.request_usage import measure
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID', 'test-id')
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET', 'test-secret')
    reads = []
    original = store.cached
    monkeypatch.setattr(discovery.store, 'cached', lambda key: (reads.append(key), original(key))[1])

    def fake_get(url, params=None, **kwargs):
        term = params['query'].split()[-1]
        if term == '실패':
            raise httpx.ConnectTimeout('boom')
        if term == '권한':
            return httpx.Response(401, request=httpx.Request('GET', url))
        return httpx.Response(200, json=dict(items=[{'title': term}]), request=httpx.Request('GET', url))

    monkeypatch.setattr(httpx, 'get', fake_get)
    try:
        with measure():
            found = intent_discovery.lookup_all([('k', t, '전북 전주') for t in ('카페', '실패', '공원', '권한')])
        assert [s for _, s in found] == ['available', 'unavailable', 'available', 'permission_required']
        assert found[0][0] == [{'title': '카페'}]
        assert reads.count('discovery-local-permission') == 1
        # 권한 없음이 기록되면 다음 묶음은 검색하지 않는다(전과 같음).
        assert intent_discovery.lookup_all([('k', '카페', '전북 전주')]) == [([], 'permission_required')]
        # 묶음 밖의 단건 검색은 전처럼 스스로 권한 표시를 확인한다.
        assert discovery.local_lookup('카페', '전북 전주') == ([], 'permission_required')
    finally:
        with store.connect() as db:
            db.execute("DELETE FROM cache WHERE key='discovery-local-permission'")


def test_discovered_places_are_saved_in_one_write_without_overwriting_richer_rows(monkeypatch, naver):
    from app import intent_discovery
    from app.perf_trace import recording
    clean_region('전북')
    naver.region['name'] = '전북'
    data = Conditions(**SCENARIOS['jeonju']).model_copy(update={'area_center': Conditions(**SCENARIOS['jeonju']).origin})
    existing = local_items('전북 맛집', '전북')[0]
    import hashlib
    address = existing['roadAddress']
    pid = 'discovered:' + hashlib.sha256((existing['title'] + address).encode()).hexdigest()[:20]
    from app import naver_cache
    naver_cache.cache('discovered-place:' + pid, dict(id=pid, name=existing['title'], region='전북', lat=JEONJU['lat'], lon=JEONJU['lon'],
                                                 category='카페·미식', discovery_evidence={'quote': '블로그 인용'}), 600)
    with recording() as trace:
        result = intent_discovery.discover_requested_places(data)
        timing = trace.summary()
    assert result['status'] == 'available' and result['resolved'] >= 5
    assert naver_cache.cached('discovered-place:' + pid)['discovery_evidence'] == {'quote': '블로그 인용'}
    saved = naver_cache.cached_many('discovered-place:' + p for p in [pid])
    assert saved
    # 찾은 장소가 여러 곳이어도 DB 사용은 몇 번뿐이다(전에는 장소마다 읽기·쓰기 2번).
    assert timing['db']['count'] <= 8 + 2 * result['lookups'], timing['db']


# --- 제공자 예산 미리 잡기 ---

def budget_used(provider):
    bucket = int(time.time() // 3600)
    with store.connect() as db:
        row = db.execute('SELECT calls FROM request_budgets WHERE scope=? AND bucket=?', ('provider:' + provider, bucket)).fetchone()
    return row[0] if row else 0


def test_reserve_budget_up_to_matches_reserving_one_by_one():
    for used, wanted in ((0, 3), (3, 4), (5, 2), (7, 3)):
        a, b = 'speed-seq-' + uuid.uuid4().hex, 'speed-batch-' + uuid.uuid4().hex
        for _ in range(used):
            store.reserve_budget([(a, 100), (a + ':ip', 6)], 1)
            store.reserve_budget([(b, 100), (b + ':ip', 6)], 1)
        one_by_one = sum(store.reserve_budget([(a, 100), (a + ':ip', 6)], 1) for _ in range(wanted))
        assert store.reserve_budget_up_to([(b, 100), (b + ':ip', 6)], 1, wanted) == one_by_one
        with store.connect() as db:
            rows = lambda s: [tuple(r) for r in db.execute('SELECT calls FROM request_budgets WHERE scope IN (?,?) AND bucket=1 ORDER BY scope', (s, s + ':ip'))]
            assert rows(a) == rows(b)


def test_prepaid_calls_share_one_reservation_and_return_the_unused_part(monkeypatch):
    from app import telemetry
    from app.request_usage import context_map, measure
    from concurrent.futures import ThreadPoolExecutor
    provider = 'prepaid-' + uuid.uuid4().hex[:8] + '.example'
    url = f'https://{provider}/search'
    reserves = []
    original = store.reserve_budget
    monkeypatch.setattr(store, 'reserve_budget', lambda limits, bucket: (reserves.append(limits), original(limits, bucket))[1])

    def call(status):
        if status == 'timeout':
            raise httpx.ConnectTimeout('slow')
        return httpx.Response(status)

    with measure(), telemetry.prepaid(url, 5) as box, ThreadPoolExecutor(max_workers=4) as pool:
        assert box['left'] == 5
        results = context_map(pool, lambda s: _safe(lambda: telemetry.observed_http(lambda u, **kw: call(s), url)), [200, 500, 'timeout'])
    # 실패한 호출도 제공자 호출로 센다(전과 같음). 쓰지 않은 2건은 돌려준다.
    assert [getattr(r, 'status_code', r) for r in results] == [200, 500, 'ConnectTimeout']
    assert not [l for l in reserves if l[0][0] == 'provider:' + provider]
    assert budget_used(provider) == 3


def _safe(action):
    try:
        return action()
    except httpx.HTTPError as error:
        return type(error).__name__


@pytest.mark.usefixtures('same_rate_window')
def test_prepaid_never_exceeds_the_hourly_provider_budget(monkeypatch):
    from app import telemetry
    monkeypatch.setenv('DATEMATE_PROVIDER_CALLS_PER_HOUR', '4')
    provider = 'prepaid-' + uuid.uuid4().hex[:8] + '.example'
    url = f'https://{provider}/search'
    telemetry.observed_http(lambda u, **kw: httpx.Response(200), url)
    outcomes = []
    with telemetry.prepaid(url, 6) as box:
        assert box['left'] == 3
        for _ in range(6):
            outcomes.append(_safe(lambda: telemetry.observed_http(lambda u, **kw: httpx.Response(200), url).status_code))
    assert outcomes == [200, 200, 200, 'PoolTimeout', 'PoolTimeout', 'PoolTimeout']
    assert budget_used(provider) == 4


# --- 긴 폴링 ---

def start_job(owner, stage='장소 검색', status='running'):
    from app import plan_jobs
    key = 'speed-' + uuid.uuid4().hex
    plan_jobs._jobs[key] = dict(owner=owner, status=status, stage=stage, message='찾는 중', started=time.monotonic())
    return key


class Disconnected:
    def __init__(self, after=None):
        self.after = after
        self.started = time.monotonic()

    async def is_disconnected(self):
        return self.after is not None and time.monotonic() - self.started > self.after


def wait(key, owner, stage, seconds, request=None):
    from app import plan_jobs
    started = time.monotonic()
    asyncio.run(plan_jobs._wait_for_change(key, owner, stage, seconds, request or Disconnected()))
    return time.monotonic() - started


def test_long_poll_answers_at_once_when_the_stage_already_changed():
    from app import plan_jobs
    key = start_job('owner-a', stage='코스 구성')
    try:
        assert wait(key, 'owner-a', '장소 검색', 5) < .3
        assert wait(key, 'other-owner', '코스 구성', 5) < .3
        assert wait('missing-job', 'owner-a', '장소 검색', 5) < .3
    finally:
        plan_jobs._jobs.pop(key, None)


def test_long_poll_returns_soon_after_the_stage_or_status_changes():
    from app import plan_jobs
    key = start_job('owner-b')
    try:
        threading.Timer(.4, lambda: plan_jobs._jobs[key].update(stage='코스 구성')).start()
        took = wait(key, 'owner-b', '장소 검색', 5)
        assert .35 < took < 1.0
        threading.Timer(.3, lambda: plan_jobs._jobs[key].update(status='cancelled', message='검색을 취소했어요.')).start()
        took = wait(key, 'owner-b', '코스 구성', 5)
        assert .25 < took < .9
    finally:
        plan_jobs._jobs.pop(key, None)


def test_long_poll_is_capped_and_stops_when_the_browser_leaves(monkeypatch):
    from app import plan_jobs
    monkeypatch.setattr(plan_jobs, 'MAX_WAIT_SECONDS', .5)
    key = start_job('owner-c')
    try:
        assert .45 < wait(key, 'owner-c', '장소 검색', 30) < 1.0
        monkeypatch.setattr(plan_jobs, 'MAX_WAIT_SECONDS', 8.0)
        assert wait(key, 'owner-c', '장소 검색', 8, Disconnected(after=.2)) < .8
    finally:
        plan_jobs._jobs.pop(key, None)


def test_long_poll_over_http_with_cancel(monkeypatch):
    """실제 경로: wait·stage 를 보내면 기다리고, DELETE 로 취소하면 기다리던 요청이 곧바로 cancelled 를 받는다."""
    from fastapi.testclient import TestClient
    from app import plan_jobs, recommendation_service
    from app.main import app
    entered = threading.Event()
    release = threading.Event()

    def slow_research(data):
        plan_jobs.report('장소 검색', '찾는 중')
        entered.set()
        release.wait(10)
        plan_jobs.check_current()
        return data, {'plans': []}

    monkeypatch.setattr(recommendation_service, '_research', slow_research)
    with TestClient(app) as client:
        key = client.post('/api/plan-jobs', json={'visit_date': '2026-10-24'}).json()['id']
        try:
            assert entered.wait(10)
            state = client.get(f'/api/plan-jobs/{key}').json()
            assert state['stage'] == '장소 검색'
            # 같은 단계면 기다린다(여기서는 0.5초 뒤 그대로 답함).
            started = time.monotonic()
            again = client.get(f'/api/plan-jobs/{key}', params={'wait': .5, 'stage': '장소 검색'}).json()
            assert again['status'] == 'running' and time.monotonic() - started >= .45
            answers = []
            poller = threading.Thread(target=lambda: answers.append(
                (client.get(f'/api/plan-jobs/{key}', params={'wait': 8, 'stage': '장소 검색'}).json(), time.monotonic())))
            poller.start()
            time.sleep(.3)
            cancelled_at = time.monotonic()
            assert client.delete(f'/api/plan-jobs/{key}').status_code == 200
            poller.join(10)
            state, answered_at = answers[0]
            assert state['status'] == 'cancelled' and 'preview' not in state
            assert answered_at - cancelled_at < 1.5
        finally:
            release.set()
            for _ in range(100):
                if plan_jobs._jobs.get(key, {}).get('finished'):
                    break
                time.sleep(.05)
        assert client.get(f'/api/plan-jobs/{key}').json()['status'] == 'cancelled'


# --- 계측·예산 돌려주기 실패가 추천을 망치지 않음 (2026-11-14 검토 반영) ---

def test_release_failure_keeps_the_batch_result(monkeypatch):
    import sqlite3
    from app import telemetry
    monkeypatch.setattr(store, 'release_budget', lambda *a: (_ for _ in ()).throw(sqlite3.OperationalError('database is locked')))
    url = f'https://release-{uuid.uuid4().hex[:8]}.example/x'
    with telemetry.prepaid(url, 3):
        answer = telemetry.observed_http(lambda u, **kw: httpx.Response(200), url)
    assert answer.status_code == 200


def test_release_failure_does_not_hide_the_original_error(monkeypatch):
    import sqlite3
    from app import telemetry
    monkeypatch.setattr(store, 'release_budget', lambda *a: (_ for _ in ()).throw(sqlite3.OperationalError('database is locked')))
    with pytest.raises(ValueError, match='원래 오류'):
        with telemetry.prepaid(f'https://release-{uuid.uuid4().hex[:8]}.example/x', 3):
            raise ValueError('원래 오류')


def test_prepay_failure_falls_back_to_reserving_per_call(monkeypatch):
    import sqlite3
    from app import telemetry
    monkeypatch.setattr(store, 'reserve_budget_up_to', lambda *a: (_ for _ in ()).throw(sqlite3.OperationalError('locked')))
    provider = 'prepay-' + uuid.uuid4().hex[:8] + '.example'
    with telemetry.prepaid(f'https://{provider}/x', 2) as box:
        assert box['left'] == 0
        assert telemetry.observed_http(lambda u, **kw: httpx.Response(200), f'https://{provider}/x').status_code == 200
    assert budget_used(provider) == 1


def test_timing_failure_keeps_a_successful_recommendation(monkeypatch):
    from app import perf_trace, recommendation_service as service
    monkeypatch.setattr(perf_trace.Trace, 'summary', lambda self: 1 / 0)
    owner = 'timing-fail-' + uuid.uuid4().hex
    result = service.generate(Conditions(visit_date='2026-10-31'), owner)
    assert result['plans'] and 'timing' not in (result.get('diagnostics') or {})
    with store.connect() as db:
        row = db.execute("SELECT payload FROM experience_events WHERE owner=? AND kind='recommendation'", (owner,)).fetchone()
    event = json.loads(row[0])
    assert event['status'] == 'complete' and 'timing' not in event


def test_timing_failure_does_not_hide_the_original_error(monkeypatch):
    from app import perf_trace, recommendation_service as service
    monkeypatch.setattr(perf_trace.Trace, 'summary', lambda self: 1 / 0)
    monkeypatch.setattr(service, '_research', lambda data: (_ for _ in ()).throw(ValueError('original failure')))
    owner = 'timing-fail-' + uuid.uuid4().hex
    with pytest.raises(ValueError, match='original failure'):
        service.generate(Conditions(visit_date='2026-10-31'), owner)
    with store.connect() as db:
        row = db.execute("SELECT payload FROM experience_events WHERE owner=?", (owner,)).fetchone()
    assert json.loads(row[0])['status'] == 'failed'


def test_response_timing_hides_hosts_and_rejections_but_server_keeps_them(caplog, naver):
    import logging
    clean_region('전북')
    with caplog.at_level(logging.INFO, logger='app.recommendation_service'):
        result = run('jeonju', naver)
    external = result['diagnostics']['timing']['external']
    assert set(external) == {'calls', 'failed', 'wait_ms_sum', 'wall_ms', 'peak_parallel'}
    assert 'naverapihub' not in json.dumps(result['diagnostics']['timing'])
    line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith('recommendation_timing'))
    logged = json.loads(line.split(' ', 2)[2])
    assert logged['by_kind'] and logged['by_kind'][0]['provider'] and 'rejected' in logged['external']
