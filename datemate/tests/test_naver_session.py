"""추천 작업 하나 동안 네이버 API 허브 호출이 한 연결 풀을 쓰는지(telemetry.naver_session), 그리고
테스트가 httpx.get·pricing.search_client 를 가짜로 바꿔 둔 경우에는 그 가짜를 그대로 써 실제 네이버를 부르지 않는지 본다.
네트워크는 쓰지 않는다(가짜 클라이언트를 문맥에 직접 꽂음)."""
import httpx

from app import pricing, telemetry
from app.telemetry import naver_session, observed_http, shared_naver_client

NAVER = 'https://naverapihub.apigw.ntruss.com/search/v1/local'


class FakeClient:
    def __init__(self):
        self.calls = []
        self.closed = False

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs.get('params')))
        return httpx.Response(200, json={'items': []}, request=httpx.Request('GET', url))

    def close(self):
        self.closed = True


def with_session(fake, action):
    token = telemetry._naver_session.set(fake)
    try:
        return action()
    finally:
        telemetry._naver_session.reset(token)


def test_real_httpx_get_to_naver_goes_through_the_job_session():
    fake = FakeClient()
    assert telemetry._REAL_GET is httpx.get  # 이 테스트에서는 httpx.get 을 바꾸지 않았다
    response = with_session(fake, lambda: observed_http(httpx.get, NAVER, params={'query': '성수 카페'}))
    assert response.status_code == 200
    assert fake.calls == [(NAVER, {'query': '성수 카페'})]


def test_a_patched_httpx_get_is_kept_so_tests_never_reach_naver(monkeypatch):
    fake, seen = FakeClient(), []

    def fake_get(url, **kwargs):
        seen.append(url)
        return httpx.Response(200, json={}, request=httpx.Request('GET', url))

    monkeypatch.setattr(httpx, 'get', fake_get)
    with_session(fake, lambda: observed_http(httpx.get, NAVER))
    assert seen == [NAVER] and fake.calls == []


def test_other_hosts_and_calls_outside_a_job_are_unchanged(monkeypatch):
    fake = FakeClient()
    sent = []
    monkeypatch.setattr(telemetry, '_REAL_GET', lambda url, **kw: (sent.append(url), httpx.Response(200, request=httpx.Request('GET', url)))[1])
    real = telemetry._REAL_GET
    # 네이버가 아닌 호스트는 작업 풀로 보내지 않는다.
    with_session(fake, lambda: observed_http(real, 'https://m.blog.naver.com/someone/1'))
    # 작업 밖(풀 없음)에서는 받은 함수를 그대로 쓴다.
    observed_http(real, NAVER)
    assert fake.calls == [] and sent == ['https://m.blog.naver.com/someone/1', NAVER]


def test_session_is_shared_when_nested_and_closed_at_the_end():
    assert shared_naver_client() is None
    with naver_session() as outer:
        with naver_session() as inner:
            assert inner is outer and shared_naver_client() is outer
        assert not outer.is_closed
    assert outer.is_closed and shared_naver_client() is None


def test_price_lookups_reuse_the_job_session_and_leave_it_open(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(pricing, 'search_enabled', lambda: True)
    used = []
    monkeypatch.setattr(pricing, 'lookup_price', lambda place, force=False, writes=None, client=None:
                        (used.append(pricing._batch_client.get()), {'status': 'not_found'})[1])
    plan = {'conditions': {'mode': 'real'}, 'places': [{'id': 'naver-session-probe-1', 'price': None}]}
    monkeypatch.setattr(pricing, 'apply_prices', lambda p, data: p)
    with_session(fake, lambda: pricing.price_plans([plan], force=True))
    assert used == [fake] and not fake.closed


def test_price_lookups_use_a_patched_search_client_even_inside_a_job(monkeypatch):
    fake, mock = FakeClient(), FakeClient()
    monkeypatch.setattr(pricing, 'search_enabled', lambda: True)
    monkeypatch.setattr(pricing, 'search_client', lambda: mock)
    used = []
    monkeypatch.setattr(pricing, 'lookup_price', lambda place, force=False, writes=None, client=None:
                        (used.append(pricing._batch_client.get()), {'status': 'not_found'})[1])
    monkeypatch.setattr(pricing, 'apply_prices', lambda p, data: p)
    plan = {'conditions': {'mode': 'real'}, 'places': [{'id': 'naver-session-probe-2', 'price': None}]}
    with_session(fake, lambda: pricing.price_plans([plan], force=True))
    assert used == [mock] and mock.closed and not fake.closed
