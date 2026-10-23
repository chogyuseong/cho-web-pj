from app import explore,store

def item(name='서울카페',address='서울특별시 중구 테스트로 1',x='1269900000',y='375600000',category='카페,디저트'):
    return dict(title=name,roadAddress=address,mapx=x,mapy=y,category=category)

def test_seoul_and_supported_activity_only():
    assert explore.venue(item(),'서울 데이트',1)
    assert explore.venue(item(address='경기도 고양시 길 1'),'서울 데이트',1) is None
    assert explore.venue(item(category='병원,의원'),'서울 데이트',1) is None
    assert explore.venue(item(x='bad'),'서울 데이트',1) is None

def test_dedup_keeps_separate_branches():
    bank={}
    first=explore.venue(item(),'A',1)
    assert explore.add_unique(bank,first)
    duplicate=explore.venue(item(name='서울 카페',address='서울 중구 테스트로 1'),'B',2)
    assert not explore.add_unique(bank,duplicate)
    assert len(bank)==1 and len(first['found_in'])==2
    branch=explore.venue(item(name='서울카페 별관',address='서울특별시 중구 테스트로 2'),'C',1)
    assert explore.add_unique(bank,branch) and len(bank)==2

def test_collect_caps_500_and_persists_details(monkeypatch):
    monkeypatch.setattr(explore,'queries',lambda:[str(i) for i in range(120)])
    def lookup(client,q):
        return q,[item(name=f'장소{q}-{rank}',address=f'서울특별시 중구 테스트로 {int(q)*5+rank}') for rank in range(5)],'available'
    monkeypatch.setattr(explore,'lookup',lookup)
    explore.collect()
    snapshot=store.cached(explore.KEY)
    assert snapshot['status']=='ready' and len(snapshot['places'])==500
    assert len({p['id'] for p in snapshot['places']})==500
    assert store.cached('explore-place:'+snapshot['places'][0]['id'])
    monkeypatch.setattr(explore,'ensure',lambda: snapshot)
    page=explore.explore(q='',offset=480,limit=24)
    assert page['total']==500 and len(page['places'])==20 and not page['has_more']
    assert explore.explore(q='없는장소',offset=0,limit=24)['total']==0

def test_provider_failure_does_not_fabricate_500(monkeypatch):
    store.cache(explore.KEY,{'places':[],'status':'partial'},60)
    monkeypatch.setattr(explore,'queries',lambda:['one'])
    monkeypatch.setattr(explore,'lookup',lambda *args:('one',[],'permission_required'))
    explore.collect()
    state=store.cached(explore.KEY)
    assert state['status']=='permission_required' and state['places']==[]
