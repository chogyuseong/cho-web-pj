import json
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import httpx
import pytest
from fastapi.testclient import TestClient
from app import store, plan_jobs
from app.config import validate_runtime
from app.database import parameters, postgres_enabled
from app.main import app


def test_production_requires_persistent_database(monkeypatch):
    monkeypatch.setenv('DATEMATE_ENV', 'production')
    monkeypatch.setenv('DATABASE_URL', '')
    monkeypatch.delenv('DATEMATE_EPHEMERAL_DEMO', raising=False)
    with pytest.raises(RuntimeError, match='PostgreSQL'):
        validate_runtime()


@pytest.mark.parametrize('url', ['http://example.com', 'https://example.com/path',
                               'https://user:secret@example.com', 'https://example.com?x=1'])
def test_invalid_production_origin_is_rejected(monkeypatch, url):
    monkeypatch.setenv('DATEMATE_ENV', 'production')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://unused/example')
    monkeypatch.setenv('DATEMATE_PUBLIC_ORIGIN', url)
    with pytest.raises(RuntimeError, match='HTTPS'):
        validate_runtime()


def test_error_headers_hosts_and_cross_site_requests(monkeypatch):
    monkeypatch.setenv('DATEMATE_ALLOWED_HOSTS', 'testserver')
    with TestClient(app) as client:
        response = client.get('/', headers={'Host':'attacker.example'})
        assert response.status_code == 400
        response = client.post('/api/conditions/parse', json={'text':'카페'},
                               headers={'Origin':'https://attacker.example'})
        assert response.status_code == 403
        assert '다른 사이트' in response.json()['detail']
        assert response.headers['cache-control'] == 'no-store'
        assert response.headers['x-request-id']
        assert "frame-ancestors 'none'" in response.headers['content-security-policy']
        assert client.post('/api/conditions/parse', json={'text':'카페'},
                           headers={'Sec-Fetch-Site':'cross-site'}).status_code == 403
        assert client.get('/static/http-client.mjs').headers['cache-control'].endswith('must-revalidate')


def test_https_session_cookie():
    with TestClient(app, base_url='https://testserver') as client:
        cookie=client.get('/').headers['set-cookie'].lower()
        assert 'secure' in cookie and 'httponly' in cookie and 'samesite=strict' in cookie


def test_ip_budget_survives_cookie_rotation(monkeypatch):
    monkeypatch.setenv('DATEMATE_IP_REQUESTS_PER_MINUTE', '2')
    with TestClient(app, client=('192.0.2.123', 12345)) as client:
        assert client.post('/api/conditions/parse',json={'text':'카페'}).status_code == 200
        client.cookies.clear()
        assert client.post('/api/conditions/parse',json={'text':'카페'}).status_code == 200
        client.cookies.clear()
        response=client.post('/api/conditions/parse',json={'text':'카페'})
        assert response.status_code == 429
        assert response.headers['retry-after'] == '60'
        assert client.get('/healthz').status_code == 200


def test_chat_budget_rejects_before_model(monkeypatch):
    monkeypatch.setenv('DATEMATE_USER_CHATS_PER_MINUTE', '1')
    with TestClient(app) as client:
        client.get('/')
        owner=client.cookies['dm_session']
        store.reserve_budget([('chat:'+owner,1)],int(time.time()//60))
        assert client.post('/api/chat/place/missing',json={'question':'질문'}).status_code == 429


def test_shared_progress_is_not_mistaken_for_server_restart():
    owner='remote-worker-owner'; key='remote-worker-job'
    job=dict(id=key,owner=owner,status='running',stage='검색',message='진행 중',
             heartbeat=time.time(),deadline=time.time()+300)
    store.cache('plan-job:'+key,job)
    request=SimpleNamespace(state=SimpleNamespace(owner=owner))
    assert plan_jobs.poll(key,request)['status'] == 'running'
    assert plan_jobs.cancel(key,request)['cancelled']
    assert store.cached('plan-job:'+key)['status'] == 'cancelled'


def test_remote_cancellation_wins_over_late_worker_result():
    owner='cancel-remote-owner';key='cancel-remote-job'
    plan_jobs._jobs[key]=dict(owner=owner,status='complete',result={'plans':[]},started=time.monotonic())
    store.cache('plan-job:'+key,dict(owner=owner,status='cancelled',message='취소'))
    try:
        plan_jobs._persist(key)
        assert store.cached('plan-job:'+key)['status']=='cancelled'
        assert plan_jobs._jobs[key]['status']=='cancelled'
    finally:plan_jobs._jobs.pop(key,None)


def test_dead_worker_becomes_retryable_failure():
    key='dead-worker-job';owner='dead-worker-owner'
    store.cache('plan-job:'+key,dict(owner=owner,status='running',heartbeat=time.time()-100,deadline=time.time()+100))
    assert plan_jobs.poll(key,SimpleNamespace(state=SimpleNamespace(owner=owner)))['status']=='failed'
    assert store.cached('plan-job:'+key)['status']=='failed'


def test_request_budget_atomic_under_concurrency():
    scope='concurrent-budget-'+str(time.time_ns())
    def attempt(_):return store.reserve_budget([(scope,3)],123)
    with ThreadPoolExecutor(max_workers=8) as workers:
        assert sum(workers.map(attempt,range(12)))==3


def test_public_stream_and_sdk_share_budget_control(monkeypatch):
    from app.telemetry import observed_stream, invoke_model
    monkeypatch.setenv('DATEMATE_PROVIDER_CALLS_PER_HOUR','1')
    transport=httpx.MockTransport(lambda request:httpx.Response(200,text='ok'))
    with httpx.Client(transport=transport) as client:
        with observed_stream(client,'GET','https://stream-budget.example/test') as response:
            assert response.read()==b'ok'
        with pytest.raises(httpx.PoolTimeout):
            with observed_stream(client,'GET','https://stream-budget.example/test'):pass
    with store.connect() as db:
        db.execute('DELETE FROM request_budgets WHERE scope=?',('provider:sdk:llm',))
    model=SimpleNamespace(invoke=lambda _: 'ok')
    assert invoke_model(model,[])=='ok'
    with pytest.raises(httpx.PoolTimeout):invoke_model(model,[])


def test_postgres_parameter_translation_preserves_literals():
    assert parameters("SELECT '?' WHERE payload LIKE 'x%' AND key=?") == "SELECT '?' WHERE payload LIKE 'x%%' AND key=%s"


def test_explore_does_not_duplicate_another_instances_collection(monkeypatch):
    from app import explore
    key='explore-lease-check'
    monkeypatch.setattr(explore,'KEY',key)
    monkeypatch.setattr(explore,'_future',None)
    store.cache(key,dict(status='collecting',places=[],collector='other-instance',collection_heartbeat=time.time()))
    assert explore.ensure()['collector']=='other-instance'
    explore.save(dict(status='ready',places=[]))
    assert store.cached(key)['status']=='collecting'


def test_operations_report_is_json_serializable():
    from scripts.operations_report import report
    assert 'providers' in json.loads(json.dumps(report()))


@pytest.mark.skipif(not postgres_enabled(), reason='requires disposable PostgreSQL')
def test_postgres_revocation_and_cache_owner_triggers():
    import psycopg
    owner='pg-revoked-'+str(time.time_ns())
    store.cache('pg-private',{'owner':owner,'private':'text'})
    with store.connect() as db:
        assert db.execute('SELECT owner FROM cache_owners WHERE key=?',('pg-private',)).fetchone()[0]==owner
        db.execute('INSERT INTO revoked_sessions VALUES(?,?)',(owner,time.time()))
        db.execute('DELETE FROM cache WHERE key=?',('pg-private',))
    with pytest.raises(psycopg.IntegrityError):
        store.cache('pg-late',{'owner':owner})
    with pytest.raises(psycopg.IntegrityError):
        store.chat_save(owner,'scope','late','answer')
