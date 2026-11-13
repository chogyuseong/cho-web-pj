"""가격 확인 단계의 측정 장치와 대기 시간 줄이기(2026-11-14 둘째 작업). 외부 호출 없음."""
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import httpx
import pytest

from app import perf_trace
from app.perf_trace import recording, stage
from app.request_usage import context_map, measure
from app.telemetry import observed_http
from test_recommendation_speed import SCENARIOS, clean_region, naver, run  # noqa: F401 (naver: fixture)


def slow(seconds):
    def call(url, **kwargs):
        time.sleep(seconds)
        return httpx.Response(200)
    return call


def test_external_calls_are_also_summarised_per_stage():
    with recording() as trace, measure(), ThreadPoolExecutor(max_workers=3) as pool:
        stage('장소 검색')
        observed_http(slow(.03), 'https://naverapihub.apigw.ntruss.com/search/v1/local')
        stage('가격 확인')
        context_map(pool, lambda _: observed_http(slow(.1), 'https://naverapihub.apigw.ntruss.com/search/v1/blog'), range(3))
        perf_trace.count('price.lookups', 3)
        perf_trace.count('price.lookups_used', 0)
        summary = trace.summary()
    price = summary['external_by_stage']['가격 확인']
    assert price['calls'] == 3 and price['peak_parallel'] == 3
    assert price['wait_ms_sum'] > price['wall_ms'] >= 95
    assert summary['external_by_stage']['장소 검색']['calls'] == 1
    # 0 은 남기지 않는다.
    assert summary['counts'] == {'price.lookups': 3}


def shape(*plans):
    return [(tuple(ids), name, text) for ids, name, text in plans]


def counted(before, after_plans, price=None, refill=None):
    from app.recommendation_service import _count_pricing
    with recording() as trace:
        _count_pricing(before, after_plans, price or {}, refill or {})
        return trace.summary()['counts']


def plan(ids, name, text='설명'):
    return dict(places=[dict(id=i) for i in ids], option_purpose=name, option_description=text)


def test_pricing_counts_name_what_changed_without_place_text():
    before = shape((['a', 'b', 'c'], '기준 코스', '설명'), (['d', 'e', 'f'], '카페 넣은 코스', '설명'), (['g', 'h', 'i'], '이동이 짧은 안', '설명'))
    # 둘째 안이 빠지고 셋째 안이 둘째 자리로 오며 설명이 바뀌었다. 조회한 장소 중 a·g 만 최종 안에 남았다.
    after = [plan(['a', 'b', 'c'], '기준 코스'), plan(['g', 'h', 'i'], '이동이 짧은 안', '설명이 바뀜')]
    counts = counted(before, after, price=dict(places=5, cached=2, looked_up={'a', 'd', 'g'}, statuses={'available': 1, 'not_found': 2}))
    assert counts == {'price.plans_before': 3, 'price.plans_after': 2, 'price.plans_unchanged': 1, 'price.plans_dropped': 1,
                      'price.plans_moved': 1, 'price.redescribed': 1, 'price.places': 5, 'price.cached': 2, 'price.lookups': 3,
                      'price.lookups_used': 2, 'price.status_available': 1, 'price.status_not_found': 2}
    assert all(key.isascii() for key in counts) and '코스' not in json.dumps(counts, ensure_ascii=False)


def test_pricing_counts_refill_and_order_changes():
    before = shape((['a', 'b'], '기준 코스', 't'),)
    after = [plan(['b', 'a'], '기준 코스', 't'), plan(['x', 'y'], '같은 구성 · 다른 장소', 't')]
    counts = counted(before, after, refill=dict(places=2, cached=0, looked_up={'x', 'y'}, statuses={'not_found': 2}))
    assert counts['price.order_changed'] == 1 and counts['price.plans_added'] == 1
    assert counts['price.refill.lookups'] == 2 and counts['price.refill.lookups_used'] == 2
    assert 'price.plans_unchanged' not in counts


def test_pricing_counts_failure_never_breaks_the_recommendation(caplog):
    import logging
    from app.recommendation_service import _count_pricing
    with caplog.at_level(logging.WARNING), recording():
        _count_pricing([(('a',), 'x', 'y')], [dict(places=None)], {}, {})
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
    from app.pricing import search_client
    with recording() as trace, measure():
        stage('가격 확인')
        with search_client() as client:
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


def test_shared_client_sends_the_same_request_as_httpx_get(monkeypatch):
    """가격 검색 요청(주소·검색어·헤더·시간 제한)은 묶음 클라이언트로 보내도 httpx.get 과 같다."""
    from app import pricing
    from test_leisure_results import fixture_plan
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID', 'test-id')
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET', 'test-secret')
    sent = []

    def handle(self, request):
        sent.append((request.method, str(request.url), sorted(request.headers.items()), request.extensions.get('timeout')))
        return httpx.Response(200, json=dict(items=[]), request=request)

    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', handle)
    place = fixture_plan()['places'][0]
    pricing.lookup_price(place, force=True, writes=[])
    with pricing.search_client() as client:
        pricing.lookup_price(place, force=True, writes=[], client=client)
    assert len(sent) == 2 and sent[0] == sent[1]


def test_price_plans_uses_one_client_per_batch_and_closes_it(monkeypatch):
    from app import pricing
    from test_leisure_results import fixture_plan
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID', 'test-id')
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET', 'test-secret')
    made, calls = [], []

    def client():
        def handler(request):
            calls.append(request.url.params['query'])
            return httpx.Response(200, json=dict(items=[]))
        c = httpx.Client(transport=httpx.MockTransport(handler))
        made.append(c)
        return c

    monkeypatch.setattr(pricing, 'search_client', client)
    plan = fixture_plan()
    plan['conditions'].update(mode='real')
    for i, p in enumerate(plan['places']):
        p.update(id=f'price-stage-{uuid.uuid4().hex}-{i}', price=None)
    priced = pricing.price_plans([plan])
    assert len(made) == 1 and made[0].is_closed and len(calls) == len(plan['places'])
    assert all(r['price_lookup_status'] == 'not_found' for r in priced[0]['costs'] if r.get('price_kind'))
    # 모두 캐시에 있으면 클라이언트를 만들지 않는다.
    pricing.price_plans([plan])
    assert len(made) == 1


def test_fixed_input_recommendation_reports_the_price_stage(naver):
    clean_region(SCENARIOS['jeonju']['region'])
    result = run('jeonju', naver)
    timing = result['diagnostics']['timing']
    counts = timing['counts']
    # 고정 입력(전주, 캐시 빈 상태): 가격 조회 7건이 모두 최종 3안의 장소이고, 가격 확인이 3안을 바꾸지 않는다.
    assert counts['price.places'] == counts['price.lookups'] == counts['price.lookups_used'] == 7
    assert counts['price.plans_before'] == counts['price.plans_after'] == counts['price.plans_unchanged'] == 3
    assert timing['external_by_stage']['가격 확인']['calls'] == 7
    assert {'price.cache_read', 'price.lookups', 'price.cache_write'} <= set(timing['spans'])
    warm = run('jeonju', naver)
    counts = warm['diagnostics']['timing']['counts']
    assert counts['price.cached'] == 7 and 'price.lookups' not in counts
