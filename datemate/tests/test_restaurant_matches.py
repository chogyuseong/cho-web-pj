import httpx
from app.restaurants import search_nearby,restaurant_matches
from app.models import Conditions


def sample():
    a=dict(id='near-stop',name='광화문',lat=37.575,lon=126.977,address='서울 종로구 세종로',region='서울')
    b=dict(a,id='last-stop',name='마지막 코스',lat=37.576)
    return dict(places=[a,b],conditions=Conditions(mode='real',allow_estimates=True,visit_date='2026-10-24').model_dump(mode='json'))


def test_last_stop_and_strict_500m_with_district_top5(monkeypatch):
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID','test');monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET','secret')
    def get(url,**kwargs):
        district=kwargs['params']['query']=='서울 종로구 맛집'
        rows=[dict(title=f'음식점{i}',category='음식점>한식',roadAddress=f'서울 종로구 새문안로 {i}',
                   mapx=str(126.977),mapy=str(37.576+i*.001)) for i in range(5)] if district else [
            dict(title='가까운 식당',category='음식점>한식',roadAddress='서울 종로구 세종로 1',mapx='126.977',mapy='37.576'),
            dict(title='500m 밖 식당',category='음식점>한식',roadAddress='서울 종로구 세종로 2',mapx='126.977',mapy='37.583')]
        return httpx.Response(200,request=httpx.Request('GET',url),json={'items':rows})
    monkeypatch.setattr(httpx,'get',get)
    plan=sample()
    last=search_nearby(plan,1)
    assert [r['name'] for r in last['restaurants']]==['가까운 식당']
    result=restaurant_matches(plan)
    assert len(result['groups'])==len(plan['places'])
    assert all(r['distance_m']<=500 for g in result['groups'] for r in g['restaurants'])
    assert result['popular']['district']=='종로구'
    assert len(result['popular']['restaurants'])==5
    assert '별점' in result['popular']['ranking_basis']
    assert len(plan['places'])==2


def test_no_radius_expansion_or_invented_popular_results(monkeypatch):
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID','test');monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET','secret')
    monkeypatch.setattr(httpx,'get',lambda url,**kwargs:httpx.Response(200,request=httpx.Request('GET',url),json={'items':[
        dict(title='다른 구 식당',category='음식점>한식',roadAddress='서울 마포구 연남로',mapx='126.92',mapy='37.56')]}))
    plan=sample();plan['places']=[dict(plan['places'][0],id='far-stop',name='범위 테스트',lat=37.6,lon=126.95)]
    result=restaurant_matches(plan)
    assert not result['groups'][0]['restaurants']
    assert not result['popular']['restaurants']
