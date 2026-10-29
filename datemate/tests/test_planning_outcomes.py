import json
import time
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from app import store
from app.main import app
from scripts.operations_report import report


def enroll(client):
    response=client.post('/api/planning-sessions',json={'consented':True})
    assert response.status_code==200,response.text
    return response.json()['session_id']


def course(client,sid=''):
    response=client.post('/api/plans',json={'visit_date':'2026-11-01','max_leg':180,'budget':1000000,'planning_session_id':sid})
    assert response.status_code==200,response.text
    return response.json()['plans'][0]


def test_consent_required_and_default_decision_has_no_research_answers():
    with TestClient(app) as client,TestClient(app) as outsider:
        assert client.post('/api/planning-sessions',json={'consented':False}).status_code==422
        plan=course(client);url='/api/plans/'+plan['id']+'/decision'
        first=client.post(url,json={'extra_search':'none','manual_planning_minutes':30}).json()['decision']
        assert set(first)=={'confirmed_at','group_id'}
        assert client.post(url,json={}).json()['decision']==first
        assert outsider.get(url).status_code==404
        assert outsider.post(url,json={}).status_code==404
        assert client.get('/api/my/decisions').json()['items'][0]['id']==plan['id']
        assert outsider.get('/api/my/decisions').json()['items']==[]


def test_opt_in_timing_and_answers_are_separate_and_idempotent():
    since=time.time()
    with TestClient(app) as client:
        sid=enroll(client)
        record=store.cached('planning-study:'+sid);record['started_at']-=120
        store.cache('planning-study:'+sid,record)
        plan=course(client,sid);url='/api/plans/'+plan['id']+'/decision'
        first=client.post(url,json={'extra_search':'none','manual_planning_minutes':40}).json()['decision']
        assert first['elapsed_seconds']>=120
        updated=client.post(url,json={'extra_search':'some','manual_planning_minutes':50}).json()['decision']
        assert updated['confirmed_at']==first['confirmed_at']
        assert updated['elapsed_seconds']==first['elapsed_seconds']
        assert client.post(url,json={'manual_planning_minutes':-1}).status_code==422
        result=report(since)['planning_study']
        assert (result['enrolled_sessions'],result['decided_sessions'])==(1,1)
        assert result['extra_search_answered']==1 and result['no_extra_search']==0
        assert result['manual_baseline_samples']==1


def test_failed_or_unfinished_starts_remain_in_cohort_and_options_count_once():
    since=time.time()
    with TestClient(app) as client:
        sid=enroll(client);enroll(client)
        response=client.post('/api/plans',json={'visit_date':'2026-11-01','max_leg':180,'budget':1000000,'planning_session_id':sid})
        plans=response.json()['plans']
        for p in plans[:2]:assert client.post('/api/plans/'+p['id']+'/decision',json={}).status_code==200
        assert client.get('/api/plans/'+plans[0]['id']+'/decision').json()['decision'] is None
        assert len(client.get('/api/my/decisions').json()['items'])==1
        result=report(since)['planning_study']
        assert result['enrolled_sessions']==2 and result['decided_sessions']==1
        assert result['decision_rate']==.5
        assert result['no_extra_search_rate'] is None


def test_session_cannot_be_reused_by_another_browser():
    with TestClient(app) as owner,TestClient(app) as other:
        sid=enroll(owner)
        response=other.post('/api/plans',json={'visit_date':'2026-11-01','planning_session_id':sid})
        assert response.status_code==409


def test_expired_study_does_not_prevent_deciding_existing_course():
    with TestClient(app) as client:
        sid=enroll(client);plan=course(client,sid)
        with store.connect() as db:db.execute('DELETE FROM cache WHERE key=?',('planning-study:'+sid,))
        result=client.post('/api/plans/'+plan['id']+'/decision',json={'extra_search':'none'})
        assert result.status_code==200
        assert set(result.json()['decision'])=={'confirmed_at','group_id'}


def test_simultaneous_confirmation_stores_one_decision():
    with TestClient(app) as client:
        plan=course(client);url='/api/plans/'+plan['id']+'/decision'
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:client.post(url,json={}).status_code,range(8)))
        assert results==[200]*8
        with store.connect() as db:
            assert db.execute("SELECT COUNT(*) FROM experience_events WHERE plan_id=? AND kind='course_decision'",(plan['id'],)).fetchone()[0]==1


def test_delete_removes_enrollment_state_and_decision():
    with TestClient(app) as client:
        sid=enroll(client);plan=course(client,sid);owner=client.cookies['dm_session']
        client.post('/api/plans/'+plan['id']+'/decision',json={})
        assert client.delete('/api/me/data').status_code==200
        assert store.cached('planning-study:'+sid) is None
        with store.connect() as db:assert db.execute('SELECT COUNT(*) FROM experience_events WHERE owner=?',(owner,)).fetchone()[0]==0


def test_must_and_dislike_conflict_then_resolve_without_discarding_preference():
    with TestClient(app) as owner,TestClient(app) as guest:
        plan=course(owner);ids=[p['id'] for p in plan['places']]
        mine={i:'neutral' for i in ids};mine[ids[0]]='must'
        theirs={i:'neutral' for i in ids};theirs[ids[0]]='no'
        owner.post('/api/plans/'+plan['id']+'/agreement',json={'choices':mine})
        token=owner.post('/api/plans/'+plan['id']+'/shares').json()['url'].split('#')[1]
        headers={'Authorization':'Bearer '+token}
        assert guest.post('/api/shared-plan/vote',headers=headers,json={'choices':theirs}).status_code==200
        conflict=owner.post('/api/plans/'+plan['id']+'/agreement-preview',json={})
        assert conflict.status_code==409 and plan['places'][0]['name'] in conflict.text
        theirs[ids[0]]='neutral'
        guest.post('/api/shared-plan/vote',headers=headers,json={'choices':theirs})
        shared=guest.get('/api/shared-plan',headers=headers).json()
        assert shared['my_choices']==theirs and 'conditions' not in shared
        result=owner.post('/api/plans/'+plan['id']+'/agreement-preview',json={})
        assert result.status_code==200,result.text
        assert result.json()['plan']['places'][0]['id']==ids[0]
