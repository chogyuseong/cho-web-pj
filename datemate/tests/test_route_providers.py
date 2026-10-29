import httpx
import pytest
from app import route_providers as providers
from app.models import Conditions
from app.routes import leg
from app.planner import evaluate
from app.catalog import places

A={'name':'A','lat':37.56,'lon':126.98}
B={'name':'B','lat':37.57,'lon':126.99}


def test_walking_request_cache_and_units(monkeypatch):
    monkeypatch.setenv('TMAP_APP_KEY','private-test-key');calls=[]
    def post(url,**kwargs):
        calls.append(kwargs)
        return httpx.Response(200,request=httpx.Request('POST',url),json={'features':[{'properties':{'totalTime':601,'totalDistance':700},'geometry':{'type':'LineString','coordinates':[[126.98,37.56],[126.99,37.57]]}}]})
    monkeypatch.setattr(providers.httpx,'post',post)
    c=Conditions(visit_date='2026-11-01',mode='real')
    result=leg(A,B,c,force_api=True)
    assert result['status']=='api' and result['minutes']==11 and result['walking']==11
    assert result['distance_km']==.7 and result['path'][0]==[126.98,37.56]
    assert leg(A,B,c,force_api=True)['minutes']==11 and len(calls)==1
    assert calls[0]['json']['startX']==126.98
    assert 'private-test-key' not in str(result)


def test_transit_fare_scales_without_another_call(monkeypatch):
    monkeypatch.setenv('TMAP_TRANSIT_APP_KEY','private-test-key');calls=[]
    def post(url,**kwargs):
        calls.append(1)
        return httpx.Response(200,request=httpx.Request('POST',url),json={'metaData':{'plan':{'itineraries':[{'totalTime':1200,'totalWalkTime':240,'totalDistance':3200,'transferCount':1,'fare':{'regular':{'totalFare':1500,'currency':{'currencyCode':'KRW'}}}}]}}})
    monkeypatch.setattr(providers.httpx,'post',post)
    assert providers.route(A,B,'transit',2)['cost']==3000
    assert providers.route(A,B,'transit',4)['cost']==6000
    assert len(calls)==1


def test_missing_keys_and_malformed_provider_data_are_not_verified(monkeypatch):
    assert providers.route(A,B,'walk',2)['status']=='unavailable'
    monkeypatch.setenv('TMAP_APP_KEY','private-test-key')
    monkeypatch.setattr(providers.httpx,'post',lambda url,**kwargs:httpx.Response(200,request=httpx.Request('POST',url),json={'features':[]}))
    assert providers.route(dict(A,lon=126.981),B,'walk',2)['status']=='unavailable'
    with pytest.raises(ValueError):providers.parse_transit({'metaData':{'plan':{'itineraries':[{'totalTime':100,'totalWalkTime':200}]}}})


def test_transition_buffer_changes_finish_not_walking_time():
    c=Conditions(visit_date='2026-11-01',count=2,max_leg=180,budget=1000000)
    venues=places()[:2]
    before,error=evaluate(venues,c,soft=True);assert not error
    after,error=evaluate(venues,c.model_copy(update={'transition_buffer_minutes':10}),soft=True);assert not error
    assert after['minutes']-before['minutes']==20
    assert after['walking']==before['walking']


def test_candidate_search_never_spends_route_calls_even_with_estimates_disabled(monkeypatch):
    from app.routes import candidate_routes
    def unexpected(*args):raise AssertionError('Candidate route must not request a provider')
    monkeypatch.setattr(providers,'route',unexpected)
    c=Conditions(visit_date='2026-11-01',mode='real',allow_estimates=False)
    with candidate_routes():assert leg(A,B,c)['status']=='estimated'
    assert not c.allow_estimates
