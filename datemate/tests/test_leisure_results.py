import pytest
from app.models import Conditions
from app.catalog import places
from app.planner import evaluate
from app.leisure import nearby_sports,options

def fixture_plan():
    c=Conditions(visit_date='2026-10-24',count=2,budget=1000000,max_leg=180,start='09:00',end='23:00')
    rows=places('demo')[:2]
    plan,error=evaluate(rows,c)
    assert not error
    return plan

def test_nearby_sports_radius_dedup_and_other_stops_preserved(monkeypatch):
    plan=fixture_plan();a=plan['places'][0]
    sport=dict(a,id='sport-test',name='실내 클라이밍',tags=['클라이밍'],category='레저·활동',themes=['레저·활동'])
    distant=dict(sport,id='far-test',lat=a['lat']+.1)
    monkeypatch.setattr('app.catalog.places',lambda *args:[sport,distant,*plan['places']])
    assert [p['id'] for _,p in nearby_sports(plan,0)]==['sport-test']
    result=options(plan,0,[])
    assert result and result[0]['plan']['places'][0]['id']=='sport-test'
    assert result[0]['plan']['places'][1]==plan['places'][1]
    assert plan['places'][0]['id']!=sport['id']
    with pytest.raises(ValueError):options(plan,0,[0])
    with pytest.raises(ValueError):options(plan,9,[])

def test_leisure_api_replace_undo_permissions(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app import store
    with TestClient(app) as client:
        client.get('/api/status')
        plan=store.save_plan(fixture_plan(),client.cookies.get('dm_session'))
        base=plan['places'][0]
        sport=dict(base,id='api-sport',name='클라이밍 센터',category='레저·활동',themes=['레저·활동'],tags=['climbing'])
        monkeypatch.setattr('app.catalog.places',lambda *args:[sport,*plan['places']])
        url='/api/plans/'+plan['id']
        response=client.post(url+'/leisure-options',json={'index':0})
        assert response.status_code==200,response.text
        assert response.json()['options'][0]['place']['id']=='api-sport'
        updated=client.post(url+'/leisure-select',json={'index':0,'replacement_id':'api-sport'})
        assert updated.status_code==200,updated.text
        updated=updated.json()
        assert updated['places'][0]['id']=='api-sport'
        assert updated['places'][1]==plan['places'][1]
        assert updated['parent']==plan['id'] and updated['decision_summary']
        assert client.post('/api/plans/'+updated['id']+'/undo',json={}).json()['id']==plan['id']
        assert client.post(url+'/leisure-select',json={'index':0,'locked':[0],'replacement_id':'api-sport'}).status_code==422
        assert client.post(url+'/leisure-select',json={'index':0,'replacement_id':'unknown'}).status_code==409
        with TestClient(app) as other:
            assert other.post(url+'/leisure-options',json={'index':0}).status_code==404
