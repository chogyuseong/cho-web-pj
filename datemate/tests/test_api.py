import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.indexing import index_places
from app.catalog import places

@pytest.fixture
def client():
    with TestClient(app) as c:yield c

def test_full_api_flow(client):
    index_places(places(),'demo')
    assert client.get('/').status_code==200
    assert client.get('/static/app.js').headers['content-type'].startswith('text/javascript')
    assert client.get('/api/status').json()['llm']=='GMS 키 없음'
    p=client.post('/api/plans',json={'visit_date':'2026-10-24'}).json()['plans'][0]
    assert client.get('/api/plans/'+p['id']).json()['id']==p['id']
    options=client.post('/api/plans/'+p['id']+'/alternatives',json={'index':1,'locked':[0]}).json()['alternatives']
    new=client.post('/api/plans/'+p['id']+'/replace',json={'index':1,'locked':[0],'replacement_id':options[0]['places'][1]['id']}).json()
    assert new['parent']==p['id'] and new['aggregate_key']!=p['aggregate_key']
    assert client.post('/api/plans/'+new['id']+'/undo',json={}).json()['id']==p['id']
    result=client.post('/api/chat/place/'+p['places'][0]['id'],json={'question':'가격은?','mode':'demo'})
    assert result.status_code==200 and result.json()['status']=='demo'
    review=client.put('/api/plans/'+p['id']+'/review',json={'rating':5,'body':'좋은 가상 시연','nickname':'테스터','visited':'2026-01-01'})
    assert review.status_code==200
    row=review.json()['rows'][0]
    assert client.post('/api/reviews/'+row['id']+'/report',json={'reason':'검토 테스트'}).status_code==200
    assert client.delete('/api/reviews/'+row['id']).status_code==200

def test_permissions_validation_and_error_states(client):
    p=client.post('/api/plans',json={'visit_date':'2026-10-24'}).json()['plans'][0]
    with TestClient(app) as other:
        assert other.post('/api/plans/'+p['id']+'/alternatives',json={'index':0}).status_code==404
    assert client.post('/api/plans',json={'visit_date':'2026-10-24','count':9}).status_code==422
    assert client.post('/api/plans',json={'visit_date':'2026-10-24'},headers={'Origin':'https://malicious.example'}).status_code==403
    assert client.post('/api/conditions/parse',content='x'*(2*1024*1024+1)).status_code==413
    assert client.get('/api/places/missing').status_code==404
    result=client.post('/api/plans',json={'visit_date':'2026-10-24','mode':'real'}).json()
    assert result['plans'] and result['status']=='best_effort'
    assert result['plans'][0]['best_effort'] and result['plans'][0]['deviations']
