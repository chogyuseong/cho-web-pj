from fastapi.testclient import TestClient
from app.main import app
from app.feedback_preferences import personalizing,bonus,explanation


def test_preferences_are_opt_in_owner_scoped_and_never_invented():
    with TestClient(app) as owner,TestClient(app) as other:
        plan=owner.post('/api/plans',json={'visit_date':'2026-11-01','max_leg':180,'budget':1000000}).json()['plans'][0]
        owner.post('/api/plans/'+plan['id']+'/feedback',json={'kind':'visit','visited':'yes','obstacle':'none','reuse':'yes'})
        token=owner.cookies['dm_session']
        with personalizing(token,True,'demo') as profile:
            assert bonus(plan)>0
            assert profile['visit_samples']==1
            assert any(p['category'] in ' '.join(explanation(profile)['messages']) for p in plan['places'])
        with personalizing(token,False):assert bonus(plan)==0
        with personalizing(token,True,'real') as profile:assert profile['samples']==0
        other.get('/')
        with personalizing(other.cookies['dm_session'],True) as profile:
            assert profile['samples']==0 and bonus(plan)==0
