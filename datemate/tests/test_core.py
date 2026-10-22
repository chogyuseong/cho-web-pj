import copy
import json
from datetime import date
import pytest
from app import store
from app.catalog import places
from app.models import Conditions,ReviewInput
from app.planner import evaluate,recommend,recommend_strict,replacements
from app.routes import leg
from app.indexing import index_places,index_documents,collections,retrieve
from app.collection import queries,select_candidates
from app.rag import graph,ask,Answer,Quote,validate_quotes

def conditions(**kwargs):return Conditions(visit_date=date(2026,10,24),**kwargs)

def doc(place,id='d1',body='서울 공원의 산책로와 전시 공간에 대한 공식 문서입니다. '*35):
    return dict(id=id,place_id=place,title='공원 안내',body=body,source='https://example.org/park',type='test fixture',collected_at='2026-10-21',license='test',own=True)

def test_catalog_and_idempotent_index():
    rows=places('real');assert len(rows)>=100;assert len({p['id'] for p in rows})==len(rows)
    assert all(not p['demo'] for p in rows)
    assert all(p['price'] is None or p.get('operations_source') for p in rows)
    assert index_places(rows,'real')==len(rows)
    assert index_places(rows,'real')==len(rows)
    assert index_places(places(),'demo')==28

def test_own_query_and_short_document_preservation():
    p=places()[0];own=p['name']+' '+p['region']
    assert queries(p,'가격')[0]==own
    docs=[{'id':1,'title':'다른 제목','summary':'','own':True},{'id':2,'title':p['name'],'summary':'부산','own':False}]
    assert [d['id'] for d in select_candidates(p,'가격',docs)]==[1]

def test_cache_expiry():
    store.cache('good',{'data':1},60);assert store.cached('good')=={'data':1}
    store.cache('expired',{},-1);assert store.cached('expired') is None

def test_chunk_refresh_filter_topk():
    index_places(places(),'demo')
    index_documents([doc('demo-01'),doc('demo-02')],'demo',size=100,overlap=10)
    _,col=collections('demo');old=col.get(where={'owner':'demo-01::d1'})['ids'];other=col.get(where={'owner':'demo-02::d1'})['ids']
    index_documents([doc('demo-01',body='갱신된 짧은 문서')],'demo',size=200,overlap=0)
    assert len(col.get(where={'owner':'demo-01::d1'})['ids'])==1
    assert not set(old)&set(col.get()['ids'])
    assert set(other)<=set(col.get()['ids'])
    evidence=retrieve(['demo-01'],'공원','demo',1)
    assert all(e['place_id']=='demo-01' for e in evidence)
    assert len([e for e in evidence if e['type']!='metadata'])<=1
    assert any(e['type']=='metadata' for e in evidence)
    # 갱신 후 해당 장소 청크가 1개뿐이어도 큰 Top-k로 안전하게 조회해야 한다.
    assert len([e for e in retrieve(['demo-01'],'공원','demo',20) if e['type']!='metadata'])==1
    with pytest.raises(ValueError):index_documents([],'demo',size=100,overlap=100)

def test_graph_unknown_and_citations():
    index_places(places(),'demo')
    assert set(graph.nodes)=={'__start__','retrieve','generate'}
    result=ask(['demo-01'],'외계인과의 접촉 기록','demo')
    assert '확인할 수 없습니다' in result['answer'];assert not result['citations'];assert result['trace']==['retrieve','generate']
    e=[dict(number=1,body='입장료 5000원')]
    a=Answer(quotes=[Quote(number=2,quote='입장료 5000원'),Quote(number=1,quote='무료'),Quote(number=1,quote='5000원')])
    assert len(validate_quotes(a,e))==1

def test_chat_scope():
    store.chat_save('one','demo:place:a','A 질문','A 답변')
    store.chat_save('one','demo:plan:a','일정 질문','일정 답변')
    assert len(store.history('one','demo:place:a'))==2
    assert not store.history('two','demo:place:a')
    assert not store.history('one','demo:place:b')

def test_plan_constraints_and_return():
    c=conditions(return_home=True,home={'name':'귀가','lat':37.575,'lon':126.985})
    result=recommend(c);assert 1<=len(result['plans'])<=3
    for p in result['plans']:
        assert len(p['places'])==3;assert len({x['id'] for x in p['places']})==3
        assert len(p['legs'])==4;assert p['total'][1]<=c.budget;assert p['finish']<=c.end
        assert all(r['minutes']<=c.max_leg for r in p['legs'])
    for changes in [dict(budget=0,themes=['카페·미식']),dict(end='11:15'),dict(max_walk=0)]:
        result=recommend(conditions(**changes))
        assert result['status']=='best_effort' and result['plans'][0]['deviations']

def test_closed_break_last_entry():
    p=copy.deepcopy(places()[0]);p['closed_days']=[5]
    assert evaluate([p],conditions(count=2),partial=True)[1]=='방문일 휴무'
    p['closed_days']=[];p['last_entry']=600
    assert '입장' in evaluate([p],conditions(),partial=True)[1]
    p['last_entry']=None;p['hours']=[600,680]
    assert '영업시간' in evaluate([p],conditions(),partial=True)[1]
    p['hours']=[600,1260];p['breaks']=[[660,780]]
    plan,_=evaluate([p],conditions(),partial=True)
    assert plan['timeline'][0]['arrival']=='13:00'

def test_replacement_preserves_neighbors_and_locks():
    p=recommend(conditions())['plans'][0]
    with pytest.raises(ValueError):replacements(p,1,[1])
    options=replacements(p,1,[0,2]);assert options
    n=options[0];assert n['places'][0]==p['places'][0] and n['places'][2]==p['places'][2]
    assert n['legs'][1]['destination']==n['places'][1]['name']
    assert n['legs'][2]['origin']==n['places'][1]['name']
    assert n['total'][1]<=n['conditions']['budget']
    locked={0:p['places'][0]['id'],2:p['places'][2]['id']}
    result=recommend(conditions(locked=locked))
    assert all(plan['places'][i]['id']==id for plan in result['plans'] for i,id in locked.items())

def test_unknown_cost_and_unsupported_route():
    p=copy.deepcopy(places()[0]);p['price']=None
    plan,_=evaluate([p],conditions(),partial=True)
    assert plan['unknown'] and plan['costs'][0]['amount'] is None
    assert '미확인' in plan['status']
    c=conditions(mode='real',transport='walk');route=leg(c.origin.model_dump(),p,c)
    assert route['status']=='unavailable' and route['cost'] is None and route['minutes'] is None

def test_review_key_threshold_and_upsert(monkeypatch):
    assert store.aggregate_key(['a','b'])==store.aggregate_key(['a','b'])
    assert store.aggregate_key(['a','b'])!=store.aggregate_key(['b','a'])
    key=store.aggregate_key(['test-a','test-b']);data=ReviewInput(rating=4,body='긴 후기입니다. '*10000,nickname='별명',visited=date(2026,1,1))
    for i in range(9):store.put_review(key,f'person-{i}',data)
    assert store.reviews(key)['average'] is None
    store.put_review(key,'person-9',data);assert store.reviews(key)['average']==4
    monkeypatch.setattr(store.time,'time',lambda:9999999999)
    store.put_review(key,'person-9',data);assert store.reviews(key)['count']==10
    with store.connect() as db:db.execute('DELETE FROM reviews WHERE aggregate_key=? AND author=?',(key,'person-9'))
    assert store.reviews(key)['count']==9 and store.reviews(key)['average'] is None

def test_invalid_inputs():
    with pytest.raises(ValueError):conditions(end='09:00')
    with pytest.raises(ValueError):conditions(return_home=True)
    with pytest.raises(ValueError):conditions(locked={0:'a',1:'a'})
    with pytest.raises(ValueError):ReviewInput(rating=5,body=' ',nickname='a',visited=date(2026,1,1))

def test_answer_cache_changes_with_question_and_evidence():
    index_places(places(),'demo')
    with store.connect() as db:db.execute("DELETE FROM cache WHERE key LIKE 'answer:%'")
    first=ask(['demo-03'],'가격 확인 질문','demo')
    second=ask(['demo-03'],'가격 확인 질문','demo')
    assert not first['cache_hit'] and second['cache_hit']
    assert not ask(['demo-03'],'가격 확인 질문 변경','demo')['cache_hit']
    index_documents([doc('demo-03',id='cache-doc',body='새로운 근거 문서')],'demo')
    assert not ask(['demo-03'],'가격 확인 질문','demo')['cache_hit']

def test_mode_and_theme_boundaries():
    c=conditions(themes=['카페·미식'],count=2,use_mbti=True,mbti='ENTP')
    result=recommend(c)
    assert result['plans'] and all(x['category']=='카페·미식' for p in result['plans'] for x in p['places'])
    result=recommend(conditions(count=5))
    assert result['plans'] and all(len(p['places'])==5 for p in result['plans'])
    result=recommend(conditions(themes=['체험·제작'],reservation=False))
    assert result['plans'] and result['status']=='best_effort'

def test_recommendation_explains_data_and_origin_limits():
    result=recommend_strict(conditions(mode='real'))
    assert result['status']=='constraints_unmet' and not result['plans']
    assert result['reasons']
    result=recommend_strict(conditions(origin={'name':'멀리 있는 출발지','lat':37.5,'lon':127.05}))
    assert result['status']=='origin_too_far'
    assert result['diagnostics']['nearest_minutes']>30
    result=recommend(conditions())
    assert result['status']=='ok' and len(result['plans'])==3
