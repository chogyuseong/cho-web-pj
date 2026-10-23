import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client():
    with TestClient(app) as c:yield c

import time
from app.recommendation_summary import enrich

def test_job_owner_and_result(client):
    response=client.post('/api/plan-jobs',json={'visit_date':'2026-10-24'})
    assert response.status_code==202
    key=response.json()['id']
    for _ in range(200):
        state=client.get('/api/plan-jobs/'+key).json()
        if state['status']!='running':break
        time.sleep(.02)
    assert state['status']=='complete',state
    assert state['result']['plans'][0]['decision_summary']['travel_minutes']>=0
    assert state['result']['plans'][0]['place_evidence']
    cookies=dict(client.cookies)
    client.cookies.clear()
    assert client.get('/api/plan-jobs/'+key).status_code==404
    client.cookies.update(cookies)

def test_evidence_does_not_invent_verification():
    p={'places':[{'id':'a','name':'A','category':'카페·미식'}],'costs':[{'status':'unknown'}],'legs':[{'minutes':4}]}
    enrich(p)
    assert p['place_evidence'][0]['operating_status']=='최신 운영 확인 필요'
    assert p['place_evidence'][0]['price_kind']=='unknown'
    assert not p['place_evidence'][0]['blog_match']

def test_textual_exclusions_survive_every_relaxation():
    from app.models import Conditions
    from app.search_relaxation import relaxation_steps
    from app.request_intent import intent
    c=Conditions(mode='real',visit_date='2026-10-24',request='카페 투어, 볼링은 제외, 식당은 싫어',avoid=['공방'])
    original=set(intent(c)['excluded'])
    assert original
    for relaxed,_,_ in relaxation_steps(c):
        assert original<=set(intent(relaxed)['excluded'])

def test_completed_job_survives_in_memory_eviction(client):
    from app import plan_jobs,store
    key='durability-test'
    owner=client.get('/api/status').cookies.get('dm_session') or client.cookies.get('dm_session')
    store.cache('plan-job:'+key,dict(owner=owner,status='complete',result={'plans':[]}),600)
    plan_jobs._jobs.pop(key,None)
    response=client.get('/api/plan-jobs/'+key)
    assert response.status_code==200 and response.json()['status']=='complete'

def test_interrupted_job_reports_recovery(client):
    from app import store
    client.get('/api/status')
    store.cache('plan-job:interrupted',dict(owner=client.cookies.get('dm_session'),status='running'),600)
    response=client.get('/api/plan-jobs/interrupted')
    assert response.json()['status']=='failed'
    assert '재시작' in response.json()['message']

def test_duplicate_start_reuses_job_and_other_conditions_blocked(client,monkeypatch):
    from app import plan_jobs
    monkeypatch.setattr(plan_jobs._pool,'submit',lambda *args:None)
    payload={'visit_date':'2026-10-24'}
    first=client.post('/api/plan-jobs',json=payload).json()['id']
    try:
        assert client.post('/api/plan-jobs',json=payload).json()['id']==first
        assert client.post('/api/plan-jobs',json=payload|{'budget':120000}).status_code==429
    finally:plan_jobs._jobs.pop(first,None)

def test_failed_job_is_persisted_without_exception_details(client,monkeypatch):
    from app import main,plan_jobs
    def fail(*args):raise ValueError('private-error-detail')
    monkeypatch.setattr(main,'create',fail)
    response=client.post('/api/plan-jobs',json={'visit_date':'2026-10-24'})
    key=response.json()['id']
    for _ in range(100):
        state=client.get('/api/plan-jobs/'+key).json()
        if state['status']!='running':break
        time.sleep(.02)
    assert state['status']=='failed' and 'private-error-detail' not in str(state)
    plan_jobs._jobs.pop(key,None)
    assert client.get('/api/plan-jobs/'+key).json()['status']=='failed'

def test_nullable_optional_research_does_not_break_recommendation():
    p={'places':[{'id':'a','category':'카페·미식'}],'costs':[],'legs':[],
       'course_search':None,'search_adjustments':None,'reasons':None,'option_purpose':None}
    enrich(p)
    assert p['decision_summary'] and len(p['place_evidence'])==1

def test_inspiration_uses_real_sourced_places(client):
    data=client.get('/api/inspirations').json()
    assert isinstance(data['items'],list)
    for idea in data['items']:
        assert idea['places'] and len(idea['places'])<=3
        assert idea['origin']['name'] and idea['request']
        assert all(p['source'].startswith('https://') and not p['id'].startswith('demo') for p in idea['places'])

def test_fit_reason_counts_actual_candidates():
    p={'conditions':{'request':'카페 투어','setting':'indoor'},'places':[
      {'id':'a','name':'커피 카페','category':'카페·미식','tags':['cafe'],'setting':'indoor'},
      {'id':'b','name':'전시 미술관','category':'문화·예술','setting':None}],
      'costs':[],'legs':[{'minutes':8}],'reasons':[]}
    enrich(p)
    reasons=' '.join(p['decision_summary']['fit_reasons'])
    assert '후보 1곳' in reasons and '1/2곳' in reasons
    assert '카페·식사 1곳' in p['decision_summary']['title']
