from fastapi.testclient import TestClient
from app import explore,store
from app.main import app

def item(name='서울카페',address='서울특별시 중구 테스트로 1',x='1269900000',y='375600000',category='카페,디저트'):
    return dict(title=name,roadAddress=address,mapx=x,mapy=y,category=category)

def busan(name,number):
    return item(name=name,address=f'부산광역시 해운대구 테스트로 {number}',x='1291600000',y='351600000')

def test_selected_region_and_supported_activity_only():
    assert explore.venue(item(),'서울 데이트',1)['region']=='서울'
    assert explore.venue(item(address='경기도 고양시 길 1'),'서울 데이트',1) is None
    assert explore.venue(item(category='병원,의원'),'서울 데이트',1) is None
    assert explore.venue(item(x='bad'),'서울 데이트',1) is None
    assert explore.venue(busan('바다카페',1),'부산 카페',1,'부산')['region']=='부산'
    assert explore.venue(item(),'부산 카페',1,'부산') is None
    assert explore.venue(busan('좌표밖',1)|dict(mapx='1500000000'),'부산 카페',1,'부산') is None

def test_dedup_keeps_separate_branches():
    bank={}
    first=explore.venue(item(),'A',1)
    assert explore.add_unique(bank,first)
    duplicate=explore.venue(item(name='서울 카페',address='서울 중구 테스트로 1'),'B',2)
    assert not explore.add_unique(bank,duplicate)
    assert len(bank)==1 and len(first['found_in'])==2
    branch=explore.venue(item(name='서울카페 별관',address='서울특별시 중구 테스트로 2'),'C',1)
    assert explore.add_unique(bank,branch) and len(bank)==2

def test_query_plans_stay_within_budget():
    for activity in ['',*explore.ACTIVITIES]:
        for q in ('','해운대'):
            planned=explore.queries('부산',activity,q)
            assert 0<len(planned)<=explore.MAX_QUERIES and all(p.startswith('부산 ') for p in planned)
            assert all(q in p for p in planned) and all(activity in p for p in planned)
    assert explore.queries('부산')[0]=='부산 데이트 장소'
    assert '부산 해운대 카페' in explore.queries('부산','카페','해운대')

def fake_provider(monkeypatch):
    calls=[]
    def lookup(client,query):
        calls.append(query)
        rows=[busan(f'{query} 장소{rank}',len(calls)*10+rank) for rank in range(4)]
        rows.append(item(name=f'{query} 서울가게',address=f'서울특별시 중구 테스트로 {len(calls)}'))
        return query,rows,'available'
    monkeypatch.setattr(explore,'search_enabled',lambda:True)
    monkeypatch.setattr(explore,'lookup',lookup)
    return calls

def test_busan_search_filters_other_regions_and_pages_from_cache(monkeypatch):
    calls=fake_provider(monkeypatch)
    client=TestClient(app)
    first=client.get('/api/explore',params=dict(region='부산',activity='',q='',offset=0,limit=24)).json()
    assert first['status']=='ready' and first['region']=='부산' and len(first['places'])==24
    assert 0<len(calls)<=16 and first['queries_used']==len(calls)
    assert first['total']==len(calls)*4 and first['has_more']
    assert all(p['address'].startswith('부산광역시') and p['region']=='부산' for p in first['places'])
    used=len(calls)
    second=client.get('/api/explore',params=dict(region='부산',offset=24,limit=24)).json()
    assert len(calls)==used and second['offset']==24
    assert not {p['id'] for p in first['places']}&{p['id'] for p in second['places']}
    assert client.get('/api/places/'+second['places'][0]['id'],params={'mode':'real'}).json()['name']==second['places'][0]['name']
    client.get('/api/explore',params=dict(region='부산',activity='카페',q='해운대'))
    assert used<len(calls)<=used+16 and any('해운대' in q and '카페' in q for q in calls[used:])

def test_invalid_conditions_and_missing_key(monkeypatch):
    client=TestClient(app)
    assert client.get('/api/explore',params=dict(region='도쿄')).status_code==422
    assert client.get('/api/explore',params=dict(region='부산',activity='골프')).status_code==422
    monkeypatch.setattr(explore,'search_enabled',lambda:False)
    data=client.get('/api/explore',params=dict(region='제주',activity='카페',q='키없음점검')).json()
    assert data['status']=='key_missing' and data['places']==[] and data['total']==0

def test_provider_failure_is_not_cached_or_fabricated(monkeypatch):
    monkeypatch.setattr(explore,'search_enabled',lambda:True)
    monkeypatch.setattr(explore,'lookup',lambda client,query:(query,[],'permission_required'))
    data=explore.results('대구','서점','실패점검')
    assert data['status']=='permission_required' and data['places']==[]
    calls=[]
    monkeypatch.setattr(explore,'lookup',lambda client,query:(calls.append(query),(query,[],'available'))[1])
    assert explore.results('대구','서점','실패점검')['status']=='empty' and calls
