from concurrent.futures import ThreadPoolExecutor
import httpx
from app.request_usage import measure,context_map,cache_hit
from app.telemetry import observed_http


def test_budget_is_shared_across_worker_threads_and_does_not_count_rejections(monkeypatch):
    monkeypatch.setenv('DATEMATE_EXTERNAL_CALLS_PER_RECOMMENDATION','3')
    def action(_):
        try:
            observed_http(lambda url:httpx.Response(200),'https://supplier.test/data')
            return True
        except httpx.PoolTimeout:return False
    with measure() as usage,ThreadPoolExecutor(max_workers=3) as pool:
        results=context_map(pool,action,range(8))
        snapshot=usage.snapshot()
    assert sum(results)==3
    assert snapshot['total_calls']==3 and snapshot['budget_exhausted']
    assert snapshot['estimated_http_usd'] is None


def test_prices_are_optional_and_context_does_not_leak(monkeypatch):
    monkeypatch.setenv('DATEMATE_HTTP_USD_PER_1000','{"priced.test":2}')
    with measure() as usage:
        observed_http(lambda url:httpx.Response(200),'https://priced.test/data')
        cache_hit()
        assert usage.snapshot()['estimated_http_usd']==.002
        assert usage.snapshot()['cache_hits']==1
    with measure() as next_request:assert next_request.snapshot()['total_calls']==0
