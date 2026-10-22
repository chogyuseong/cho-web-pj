from datetime import date
from app.models import Conditions
from app.quality import configure,in_area,meal_penalty,meal_due
from app import discovery


def test_area_uses_searched_neighborhood_not_distant_origin():
    c=configure(Conditions(visit_date=date(2026,10,24)), '연남동 데이트 코스')
    assert in_area(dict(lat=37.56,lon=126.925),c)
    assert not in_area(dict(lat=37.5446,lon=127.0559),c)


def test_same_real_place_cannot_appear_twice_under_different_ids():
    from app.quality import same_place
    a=dict(id='wiki',name='서울숲',lat=37.544,lon=127.037)
    b=dict(id='discovered',name='서울숲',lat=37.545,lon=127.038)
    assert same_place(a,b)
    assert not same_place(a,dict(b,name='다른 공원'))


def test_meal_requires_real_food_and_lunch_window():
    c=Conditions(visit_date=date(2026,10,24),include_meal=True,start='11:00',end='17:00')
    assert meal_due(c)
    p=dict(places=[dict(id='cafe',meal=False)],timeline=[dict(arrival='12:00',departure='13:00')])
    assert meal_penalty(p,c)==4
    p['places'][0]['meal']=True
    assert meal_penalty(p,c)==0
    p['timeline'][0]=dict(arrival='15:00',departure='16:00')
    assert meal_penalty(p,c)==2
    assert not meal_due(c.model_copy(update={'start':'15:00','end':'16:00'}))


def test_extraction_rejects_invented_address_and_instruction(monkeypatch):
    class Fake:
        def with_structured_output(self,_):return self
        def invoke(self,_):return discovery.Mentions(places=[discovery.Mention(name='테스트식당',address='서울 마포구 없는길 99',kind='restaurant',rank=1,quote='테스트식당 서울 마포구 없는길 99')])
    monkeypatch.setenv('GMS_KEY','test')
    monkeypatch.setattr(discovery,'llm',lambda:Fake())
    mentions,status=discovery.extract([dict(rank=1,title='테스트식당',description='방문했어요',_body='주소는 알 수 없어요')])
    assert status=='available' and not mentions


def test_resolve_falls_back_to_unique_quoted_address(monkeypatch):
    monkeypatch.setattr(discovery,'local_lookup',lambda *_:([],'permission_required'))
    monkeypatch.setattr(discovery,'search_address',lambda _:dict(results=[dict(name='서울 마포구 테스트로 1',lat=37.56,lon=126.925)]))
    saved=[];monkeypatch.setattr(discovery.store,'cache',lambda *args:saved.append(args))
    mention=dict(name='테스트식당',address='서울 마포구 테스트로 1',kind='restaurant',rank=1,quote='테스트식당 서울 마포구 테스트로 1')
    row,status=discovery.resolve(mention,[dict(rank=1,url='https://blog.naver.com/example/1')],'연남동 데이트 코스')
    assert row['meal'] and row['hours'] is None and row['rating'] is None
    assert row['discovery_evidence']['source'].startswith('https://blog.naver.com/')
    assert '영업 여부 미검증' in row['discovery_verification']
    assert saved
    monkeypatch.setattr(discovery,'search_address',lambda _:dict(results=[dict(name='서울 A'),dict(name='서울 B')]))
    assert discovery.resolve(mention,[dict(rank=1,url='https://blog.naver.com/example/1')],'연남동')[0] is None
