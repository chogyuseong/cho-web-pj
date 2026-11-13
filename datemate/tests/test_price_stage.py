"""가격 확인 단계의 측정 장치와 대기 시간 줄이기(2026-11-14 둘째 작업). 외부 호출 없음."""
import json
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

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
