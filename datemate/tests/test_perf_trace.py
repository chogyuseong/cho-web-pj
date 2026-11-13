"""추천 1회 소요 시간 기록(app/perf_trace.py). 외부 호출 없음."""
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from app import perf_trace, store, telemetry
from app.models import Conditions
from app.perf_trace import call_kind, recording, span, stage
from app.request_usage import cache_hit, context_map, measure
from app.telemetry import observed_http


def slow(seconds, status=200):
    def call(url, **kwargs):
        time.sleep(seconds)
        return httpx.Response(status)
    return call


def test_call_kind_names_fixed_paths_and_hides_blog_posts():
    assert call_kind('https://naverapihub.apigw.ntruss.com/search/v1/blog?query=비밀') == 'blog_search'
    assert call_kind('https://naverapihub.apigw.ntruss.com/search/v1/local') == 'local_search'
    assert call_kind('https://maps.apigw.ntruss.com/map-direction/v1/driving') == 'driving_route'
    assert call_kind('https://m.blog.naver.com/someone/223000000000') == 'blog_body'
    assert call_kind('https://example.test/anything/else') == 'other'


def test_nothing_is_recorded_outside_a_recommendation():
    assert perf_trace.current() is None
    observed_http(slow(0), 'https://naverapihub.apigw.ntruss.com/search/v1/blog')
    stage('장소 검색')
    with span('ignored'):
        pass
    cache_hit('price')
    with store.connect() as db:
        db.execute('SELECT 1')
    assert perf_trace.current() is None


def test_stages_spans_cache_and_db_are_summarised():
    with recording() as trace:
        stage('장소 검색')
        with span('research.course_search'):
            time.sleep(.02)
        stage('코스 구성')
        cache_hit('price')
        cache_hit('price')
        with store.connect() as db:
            db.execute('SELECT 1')
        summary = trace.summary()
    names = [row['name'] for row in summary['stages']]
    assert names == ['준비', '장소 검색', '코스 구성']
    assert summary['stages'][1]['ms'] >= 20
    assert sum(row['ms'] for row in summary['stages']) == pytest.approx(summary['total_ms'], abs=3)
    assert summary['spans']['research.course_search']['count'] == 1
    assert summary['spans']['research.course_search']['ms'] >= 20
    assert summary['cache_hits'] == {'price': 2}
    assert summary['db']['count'] == 1
    assert summary['db']['by_stage']['코스 구성']['count'] == 1


def test_parallel_calls_are_counted_by_kind_with_wall_time_and_peak():
    with recording() as trace, measure(), ThreadPoolExecutor(max_workers=4) as pool:
        stage('장소 검색')
        context_map(pool, lambda _: observed_http(slow(.1), 'https://naverapihub.apigw.ntruss.com/search/v1/local?query=x'), range(4))
        observed_http(slow(.05, 500), 'https://naverapihub.apigw.ntruss.com/search/v1/blog')
        summary = trace.summary()
    external = summary['external']
    assert external['calls'] == 5 and external['failed'] == 1
    # 4건이 겹쳐 실행됐으면 기다린 시간의 합(약 450ms)이 실제 차지한 시간(약 150ms)보다 크다.
    assert external['peak_parallel'] >= 2
    assert external['wait_ms_sum'] > external['wall_ms'] >= 140
    rows = {(r['stage'], r['kind']): r for r in external['by_kind']}
    assert rows[('장소 검색', 'local_search')]['count'] == 4
    assert rows[('장소 검색', 'blog_search')]['failed'] == 1
    assert rows[('장소 검색', 'local_search')]['provider'] == 'naverapihub.apigw.ntruss.com'


def test_rejected_calls_are_counted_without_wait(monkeypatch):
    monkeypatch.setenv('DATEMATE_EXTERNAL_CALLS_PER_RECOMMENDATION', '1')
    with recording() as trace, measure():
        observed_http(slow(0), 'https://naverapihub.apigw.ntruss.com/search/v1/local')
        with pytest.raises(httpx.PoolTimeout):
            observed_http(slow(0), 'https://naverapihub.apigw.ntruss.com/search/v1/local')
        summary = trace.summary()
    row = summary['external']['by_kind'][0]
    assert row['count'] == 1 and row['rejected'] == 1
    assert summary['external']['rejected'] == 1


def test_capacity_rejection_is_counted(monkeypatch):
    class Full:
        def acquire(self, blocking=True):
            return False

    monkeypatch.setattr(telemetry, '_slots', Full())
    with recording() as trace:
        with pytest.raises(httpx.PoolTimeout):
            observed_http(slow(0), 'https://naverapihub.apigw.ntruss.com/search/v1/blog')
        summary = trace.summary()
    assert summary['external']['rejected'] == 1 and summary['external']['calls'] == 0


def test_summary_has_no_query_text_or_post_path():
    with recording() as trace, measure():
        observed_http(slow(0), 'https://naverapihub.apigw.ntruss.com/search/v1/blog?query=전주한옥마을비밀')
        observed_http(slow(0), 'https://m.blog.naver.com/secretblogger/223456789')
        text = json.dumps(trace.summary(), ensure_ascii=False)
    for secret in ('전주한옥마을비밀', 'secretblogger', '223456789', 'query'):
        assert secret not in text


def test_recommendation_result_and_event_carry_timing():
    from app import recommendation_service as service

    owner = 'timing-' + uuid.uuid4().hex
    result = service.generate(Conditions(visit_date='2026-10-31'), owner)
    timing = result['diagnostics']['timing']
    names = [row['name'] for row in timing['stages']]
    assert names[:4] == ['준비', '장소 검색', '코스 구성', '가격 확인']
    assert 'compose.recommend' in timing['spans'] and 'save.plans' in timing['spans']
    assert timing['external']['calls'] == 0
    # 저장된 코스에는 시간 기록을 싣지 않는다.
    assert all('timing' not in json.dumps(p.get('diagnostics') or {}) for p in result['plans'])
    with store.connect() as db:
        row = db.execute("SELECT payload FROM experience_events WHERE owner=? AND kind='recommendation'", (owner,)).fetchone()
    event = json.loads(row[0])
    assert event['timing']['stages']['장소 검색'] >= 0
    assert set(event['timing']['external']) == {'calls', 'failed', 'rejected', 'wait_ms_sum', 'wall_ms', 'peak_parallel'}
