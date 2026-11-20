"""가격 확인 단계의 측정 장치(2026-11-14 둘째 작업). 외부 호출 없음.
2026-11-20: 블로그 요약에서 가격을 읽던 조회를 없애(네이버 검색 API 특약 2.2·2.3) 가격 검색 묶음·동시 건수·조회 수 통계 테스트를 지웠다."""
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import httpx
import pytest

from app import perf_trace, store
from app.perf_trace import recording, stage
from app.request_usage import context_map, measure
from app.telemetry import observed_http
from test_recommendation_speed import SCENARIOS, clean_region, naver, run  # noqa: F401 (naver: fixture)


def slow(seconds):
    def call(url, **kwargs):
        time.sleep(seconds)
        return httpx.Response(200)
    return call


def together(count, seconds):
    """count 개의 호출이 모두 도착할 때까지 서로 기다린 뒤 seconds 동안 잠드는 가짜 호출.
    그냥 slow() 를 쓰면 전체 테스트처럼 기계가 바쁠 때 한 스레드가 늦게 시작해 앞 호출이 끝난 뒤 들어가
    겹친 수가 2로 나왔다(2026-11-18 Docker 전체 실행 두 번 연속 실패). 측정 장치가 '실제로 겹친' 호출을 세는지 보는 테스트라
    겹침 자체는 이렇게 보장한다. 셋이 5초 안에 모이지 못하면(자리 부족 등) BrokenBarrierError 로 바로 드러난다."""
    gate = threading.Barrier(count, timeout=5)

    def call(url, **kwargs):
        gate.wait()
        time.sleep(seconds)
        return httpx.Response(200)
    return call


def test_external_calls_are_also_summarised_per_stage():
    with recording() as trace, measure(), ThreadPoolExecutor(max_workers=3) as pool:
        stage('장소 검색')
        observed_http(slow(.03), 'https://naverapihub.apigw.ntruss.com/search/v1/local')
        stage('가격 확인')
        blog = together(3, .1)
        context_map(pool, lambda _: observed_http(blog, 'https://naverapihub.apigw.ntruss.com/search/v1/blog'), range(3))
        perf_trace.count('probe.kept', 3)
        perf_trace.count('probe.zero', 0)
        summary = trace.summary()
    price = summary['external_by_stage']['가격 확인']
    assert price['calls'] == 3 and price['peak_parallel'] == 3
    assert price['wait_ms_sum'] > price['wall_ms'] >= 95
    assert summary['external_by_stage']['장소 검색']['calls'] == 1
    # 0 은 남기지 않는다.
    assert summary['counts'] == {'probe.kept': 3}


def shape(*plans):
    return [(tuple(ids), name, text) for ids, name, text in plans]


def counted(before, after_plans):
    from app.recommendation_service import _count_pricing
    with recording() as trace:
        _count_pricing(before, after_plans)
        return trace.summary()['counts']


def plan(ids, name, text='설명'):
    return dict(places=[dict(id=i) for i in ids], option_purpose=name, option_description=text)


def test_pricing_counts_name_what_changed_without_place_text():
    before = shape((['a', 'b', 'c'], '기준 코스', '설명'), (['d', 'e', 'f'], '카페 넣은 코스', '설명'), (['g', 'h', 'i'], '이동이 짧은 안', '설명'))
    # 둘째 안이 빠지고 셋째 안이 둘째 자리로 오며 설명이 바뀌었다.
    after = [plan(['a', 'b', 'c'], '기준 코스'), plan(['g', 'h', 'i'], '이동이 짧은 안', '설명이 바뀜')]
    counts = counted(before, after)
    # 가격을 찾는 조회가 없으므로 조회 수(price.places·lookups·cached·status_*)는 더 이상 남기지 않는다.
    assert counts == {'price.plans_before': 3, 'price.plans_after': 2, 'price.plans_unchanged': 1, 'price.plans_dropped': 1,
                      'price.plans_moved': 1, 'price.redescribed': 1}
    assert all(key.isascii() for key in counts) and '코스' not in json.dumps(counts, ensure_ascii=False)


def test_pricing_counts_refill_and_order_changes():
    before = shape((['a', 'b'], '기준 코스', 't'),)
    after = [plan(['b', 'a'], '기준 코스', 't'), plan(['x', 'y'], '같은 구성 · 다른 장소', 't')]
    counts = counted(before, after)
    assert counts['price.order_changed'] == 1 and counts['price.plans_added'] == 1
    assert 'price.plans_unchanged' not in counts and not [key for key in counts if 'lookups' in key]


def test_pricing_counts_failure_never_breaks_the_recommendation(caplog):
    import logging
    from app.recommendation_service import _count_pricing
    with caplog.at_level(logging.WARNING), recording():
        _count_pricing([(('a',), 'x', 'y')], [dict(places=None)])
    assert 'pricing_counts_failed' in caplog.text


@pytest.fixture
def local_server():
    """연결 재사용을 보는 로컬 HTTP/1.1 서버(keep-alive). 받은 요청의 경로·헤더를 남긴다."""
    seen = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def do_GET(self):
            seen.append(dict(path=self.path, headers=dict(self.headers)))
            body = json.dumps(dict(items=[])).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Set-Cookie', 'gateway=1; Path=/')
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield SimpleNamespace(url=f'http://127.0.0.1:{server.server_port}/search/v1/blog', seen=seen)
    finally:
        server.shutdown()
        server.server_close()


def test_connection_probe_counts_new_and_reused_connections(local_server):
    from app.telemetry import naver_session
    with recording() as trace, measure():
        stage('가격 확인')
        # 추천 작업의 연결 풀(telemetry.naver_session)과 같은 설정의 클라이언트로 연결 재사용을 센다.
        with naver_session() as client:
            for _ in range(3):
                observed_http(client.get, local_server.url, params=dict(query='q'))
        # 호출마다 새 클라이언트(httpx.get)는 연결을 알 수 없어 세지 않는다.
        observed_http(httpx.get, local_server.url, params=dict(query='q'))
        summary = trace.summary()
    row = next(r for r in summary['external']['by_kind'] if r['provider'] == '127.0.0.1')
    assert row['count'] == 4 and row['connection_observed'] == 3 and row['new_connections'] == 1
    price = summary['external_by_stage']['가격 확인']
    assert price['connection_observed'] == 3 and price['new_connections'] == 1
    # 쿠키는 받아 두지도 다시 보내지도 않는다(호출마다 새 클라이언트였던 때와 같음).
    assert not any('Cookie' in r['headers'] for r in local_server.seen)


def test_preview_options_are_the_options_before_pricing_without_prices(naver, monkeypatch):
    from app import recommendation_service
    reported = []
    original = recommendation_service.report
    monkeypatch.setattr(recommendation_service, 'report', lambda *a, **kw: (reported.append(kw), original(*a, **kw))[1])
    clean_region(SCENARIOS['jeonju']['region'])
    owner = store.owner_of('price-stage-' + uuid.uuid4().hex)
    result = run('jeonju', naver, owner)
    options = next(kw['preview_options'] for kw in reported if 'preview_options' in kw)
    # 고정 입력에서는 가격 확인이 3안을 바꾸지 않으므로 확정 전 후보 = 확정 코스(장소 id·순서·이름).
    assert [[p['id'] for p in o['places']] for o in options] == [[p['id'] for p in plan['places']] for plan in result['plans']]
    assert [o['purpose'] for o in options] == [plan['option_purpose'] for plan in result['plans']]
    # 가격·비용·조건 확인 값은 싣지 않는다.
    assert all(set(o) == {'purpose', 'places'} and all(set(p) == {'id', 'name'} for p in o['places']) for o in options)


def test_job_state_carries_preview_options_until_cancelled(monkeypatch):
    from fastapi.testclient import TestClient
    from app import plan_jobs, recommendation_service
    from app.main import app
    entered, release = threading.Event(), threading.Event()
    options = [dict(purpose='기준 코스', places=[dict(id='a', name='가')])]

    def slow_research(data):
        plan_jobs.report('가격 확인', '확인 중', preview=[['가']], preview_options=options)
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
            assert state['preview_options'] == options and state['preview'] == [['가']]
            assert client.delete(f'/api/plan-jobs/{key}').status_code == 200
            state = client.get(f'/api/plan-jobs/{key}').json()
            assert state['status'] == 'cancelled' and 'preview' not in state and 'preview_options' not in state
        finally:
            release.set()
            for _ in range(100):
                if plan_jobs._jobs.get(key, {}).get('finished'):
                    break
                time.sleep(.05)


def test_fixed_input_recommendation_reports_the_price_stage(naver):
    clean_region(SCENARIOS['jeonju']['region'])
    owner = store.owner_of('price-stage-' + uuid.uuid4().hex)
    result = run('jeonju', naver, owner)
    timing = result['diagnostics']['timing']
    counts = timing['counts']
    # 고정 입력(전주, 캐시 빈 상태): 비용 계산이 3안을 바꾸지 않고, 가격 확인 단계에서 나가는 외부 호출이 없다
    # (블로그 요약에서 가격을 읽지 않는다. 예전에는 장소마다 블로그 검색 1건, 이 입력에서 7건이었다).
    assert counts['price.plans_before'] == counts['price.plans_after'] == counts['price.plans_unchanged'] == 3
    assert not [key for key in counts if 'lookups' in key or 'cached' in key or 'status_' in key]
    assert (timing['external_by_stage'].get('가격 확인') or {}).get('calls', 0) == 0
    assert 'price.price_plans' in timing['spans'] and not {'price.cache_read', 'price.lookups', 'price.cache_write'} & set(timing['spans'])
    assert 'unexpected-blog' not in naver.calls and naver.calls.count('/search/v1/blog') == 1
