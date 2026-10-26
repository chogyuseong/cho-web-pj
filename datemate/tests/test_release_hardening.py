import json
import sqlite3
import time
import pytest
from fastapi.testclient import TestClient
from app import store,plan_jobs
from app.main import app
from app.models import Conditions
from app.request_intent import normalize
from app.maintenance import snapshot
from scripts.restore_database import restore
from threading import Event,Thread
from types import SimpleNamespace
from app.execution import bounded_recommendation
from fastapi import HTTPException

if store.postgres_enabled():
    from psycopg import IntegrityError
else:
    from sqlite3 import IntegrityError


def plan_for(client):
    client.get('/')
    return store.save_plan({'places':[{'id':'sample','name':'공개 장소','category':'문화','address':'서울'}],
        'timeline':[{'arrival':'12:00','departure':'13:00'}],
        'conditions':{'origin':{'name':'SECRET_HOME'},'request':'SECRET_REQUEST'},
        'extra_private_field':'SECRET_FUTURE'},client.cookies['dm_session'])


def test_shared_projection_revocation_and_guest_vote():
    with TestClient(app) as owner, TestClient(app) as guest:
        plan=plan_for(owner)
        assert guest.get('/api/plans/'+plan['id']).status_code==404
        assert guest.get('/api/chat/plan/'+plan['id']).status_code==404
        share=owner.post('/api/plans/'+plan['id']+'/shares').json()
        headers={'Authorization':'Bearer '+share['url'].split('#')[1]}
        result=guest.get('/api/shared-plan',headers=headers)
        assert result.status_code==200
        assert 'SECRET' not in result.text
        assert 'conditions' not in result.json()
        assert guest.post('/api/shared-plan/vote',headers=headers,json={'choices':{'sample':'yes'}}).status_code==200
        assert owner.delete('/api/plans/'+plan['id']+'/shares').status_code==200
        assert guest.get('/api/shared-plan',headers=headers).status_code==404
        assert guest.post('/api/shared-plan/vote',headers=headers,json={'choices':{'sample':'yes'}}).status_code==404


def test_expired_share_and_static_request_without_session():
    with TestClient(app) as client:
        assert 'set-cookie' not in client.get('/static/style.css').headers
        plan=plan_for(client)
        token=client.post('/api/plans/'+plan['id']+'/shares').json()['url'].split('#')[1]
        with store.connect() as db:db.execute('UPDATE plan_shares SET expires=0 WHERE plan_id=?',(plan['id'],))
        assert client.get('/api/shared-plan',headers={'Authorization':'Bearer '+token}).status_code==404


def test_delete_blocks_late_writers_and_clears_memory():
    with TestClient(app) as client:
        plan=plan_for(client);owner=client.cookies['dm_session']
        plan_jobs._jobs['late-test']={'owner':owner,'status':'running','started':time.monotonic()}
        assert client.delete('/api/me/data').status_code==200
        assert 'late-test' not in plan_jobs._jobs
        with pytest.raises(IntegrityError):store.save_plan(plan,owner)
        with pytest.raises(IntegrityError):store.chat_save(owner,'x','private','answer')
        with pytest.raises(IntegrityError):store.cache('late-draft',{'owner':owner,'private':'text'})
        assert store.get_plan(plan['id']) is None


def test_manual_fields_win_over_natural_language():
    conditions=Conditions(visit_date='2026-10-24',request='2명 5만원 카페 3곳',people=4,budget=80000,count=2,
                          explicit_fields=['people','budget','count'])
    result=normalize(conditions)
    assert (result.people,result.budget,result.count)==(4,80000,2)


@pytest.mark.skipif(store.postgres_enabled(), reason='SQLite backup/restore')
def test_backup_restore_roundtrip(tmp_path):
    with store.connect() as db:db.execute('INSERT OR REPLACE INTO sessions VALUES(?,?)',('restore-proof',42))
    backup=snapshot(tmp_path/'backup.sqlite')
    restored=restore(backup,tmp_path/'restored')
    with sqlite3.connect(restored) as db:
        assert db.execute('SELECT created FROM sessions WHERE token=?',('restore-proof',)).fetchone()[0]==42
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    with pytest.raises(ValueError):restore(backup,tmp_path/'restored')


def test_running_job_cannot_restore_deleted_data(monkeypatch):
    import app.recommendation_service as service
    entered,release=Event(),Event()
    with TestClient(app) as client:
        plan=plan_for(client);owner=client.cookies['dm_session'];key='deletion-race'
        def slow_create(data,owner):
            entered.set();assert release.wait(5)
            return {'plans':[store.save_plan(plan,owner)]}
        monkeypatch.setattr(service,'generate',slow_create)
        plan_jobs._jobs[key]={'owner':owner,'status':'running','started':time.monotonic()}
        worker=Thread(target=plan_jobs._run,args=(key,None,owner))
        worker.start()
        try:
            assert entered.wait(5)
            assert client.delete('/api/me/data').status_code==200
        finally:release.set();worker.join(5)
        assert not worker.is_alive()
        assert key not in plan_jobs._jobs
        with store.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM plans WHERE owner=?',(owner,)).fetchone()[0]==0
        assert store.cached('plan-job:'+key) is None


def test_shared_admission_control_releases_slot_after_failure():
    entered,release=Event(),Event()
    request=SimpleNamespace(state=SimpleNamespace(owner='admission-test'))
    @bounded_recommendation
    def slow(data,request):entered.set();release.wait(5)
    worker=Thread(target=slow,args=(None,request));worker.start()
    try:
        assert entered.wait(5)
        with pytest.raises(HTTPException) as error:slow(None,request)
        assert error.value.status_code==429
    finally:release.set();worker.join(5)
    assert slow(None,request) is None


def test_cancelled_job_cannot_publish_result(monkeypatch):
    import app.recommendation_service as service
    entered,release=Event(),Event()
    with TestClient(app) as client:
        plan=plan_for(client);owner=client.cookies['dm_session'];key='cancel-race'
        def slow_create(data,owner):
            entered.set();assert release.wait(5)
            plan_jobs.check_current()
            return {'plans':[plan]}
        monkeypatch.setattr(service,'generate',slow_create)
        plan_jobs._jobs[key]={'owner':owner,'status':'running','started':time.monotonic()}
        worker=Thread(target=plan_jobs._run,args=(key,None,owner));worker.start()
        try:
            assert entered.wait(5)
            assert client.delete('/api/plan-jobs/'+key).status_code==200
        finally:release.set();worker.join(5)
        state=client.get('/api/plan-jobs/'+key).json()
        assert state['status']=='cancelled' and 'result' not in state
        plan_jobs._jobs.pop(key,None)


def test_provider_metrics_never_store_query_or_credentials():
    import httpx
    from app.telemetry import observed_http
    result=observed_http(lambda *a,**kw:httpx.Response(503),
                        'https://provider.example/search?query=SECRET_ADDRESS',headers={'Authorization':'SECRET_TOKEN'})
    assert result.status_code==503
    with store.connect() as db:
        rows=[dict(r) for r in db.execute('SELECT * FROM provider_metrics WHERE provider=?',('provider.example',))]
    assert rows[0]['errors']>=1
    assert 'SECRET' not in json.dumps(rows)


def test_common_rate_budget_blocks_direct_api(monkeypatch):
    monkeypatch.setenv('DATEMATE_USER_RECOMMENDATIONS_PER_MINUTE','1')
    with TestClient(app) as client:
        client.get('/')
        owner=client.cookies['dm_session']
        assert store.reserve_budget([('recommendations:'+owner,1)],int(time.time()//60))
        assert client.post('/api/plans',json={'visit_date':'2026-10-24'}).status_code==429


def test_cache_owner_index_tracks_replace_and_delete():
    store.cache('owner-index-test',{'owner':'first','answer':'private'})
    store.cache('owner-index-test',{'owner':'second','answer':'private'})
    with store.connect() as db:
        assert db.execute('SELECT owner FROM cache_owners WHERE key=?',('owner-index-test',)).fetchone()[0]=='second'
        db.execute('DELETE FROM cache WHERE key=?',('owner-index-test',))
        assert db.execute('SELECT owner FROM cache_owners WHERE key=?',('owner-index-test',)).fetchone() is None


def test_answer_cache_is_session_scoped_and_deleted(monkeypatch):
    from app import rag
    monkeypatch.setattr(rag,'generate_node',lambda state:{'answer':'private','citations':[],'status':'ok','trace':[]})
    with TestClient(app) as client:
        client.get('/');owner=client.cookies['dm_session']
        state={'evidence':[],'question':'personal question','mode':'demo','owner':owner}
        assert rag.cached_generate_node(state)['cache_hit'] is False
        assert rag.cached_generate_node(state)['cache_hit'] is True
        assert rag.cached_generate_node(dict(state,owner='another'))['cache_hit'] is False
        client.delete('/api/me/data')
        with store.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM cache_owners WHERE owner=?',(owner,)).fetchone()[0]==0


def test_cloud_run_requires_explicit_ephemeral_demo(monkeypatch):
    from app import cloud_start
    monkeypatch.setenv('K_SERVICE','test-service')
    monkeypatch.setenv('DATABASE_URL','')
    monkeypatch.delenv('DATEMATE_EPHEMERAL_DEMO',raising=False)
    with pytest.raises(RuntimeError):cloud_start.main()


@pytest.mark.skipif(store.postgres_enabled(), reason='SQLite automatic backup')
def test_automatic_backup_and_expired_cleanup(monkeypatch,tmp_path):
    from app.maintenance import maintain
    monkeypatch.setenv('DATEMATE_BACKUP_DIR',str(tmp_path/'backups'))
    store.cache('expired-for-maintenance',{},-1)
    maintain()
    backups=list((tmp_path/'backups').glob('*.sqlite'))
    assert len(backups)==1
    with sqlite3.connect(backups[0]) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('SELECT COUNT(*) FROM cache WHERE key=?',('expired-for-maintenance',)).fetchone()[0]==0
