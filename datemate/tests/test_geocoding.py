import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.geocoding import search_address

def test_missing_key_does_not_invent_coordinates(monkeypatch):
    monkeypatch.delenv('NAVER_MAPS_KEY',raising=False)
    result=search_address('서울 중구 세종대로 110')
    assert result['status']=='key_missing' and result['results']==[]

def test_naver_road_and_jibun(monkeypatch):
    monkeypatch.setenv('NAVER_MAPS_KEY','test');monkeypatch.setenv('NAVER_MAPS_KEY_ID','test')
    def get(self,url,**kwargs):
        assert kwargs['params']['query']=='서울 중구 세종대로 110'
        return httpx.Response(200,json={'status':'OK','addresses':[
            {'roadAddress':'서울 중구 세종대로 110','jibunAddress':'서울 중구 태평로1가 31','x':'126.978','y':'37.566'},
            {'roadAddress':'','jibunAddress':'서울 종로구 1','x':'126.98','y':'37.57'},
            {'roadAddress':'잘못된 좌표','x':'NaN','y':'1000'}]},request=httpx.Request('GET',url))
    monkeypatch.setattr(httpx.Client,'get',get)
    result=search_address('서울 중구 세종대로 110')
    assert len(result['results'])==2
    assert result['results'][0]['lat']==37.566
    assert result['results'][1]['name']=='서울 종로구 1'

def test_provider_error_sanitized(monkeypatch):
    monkeypatch.setenv('NAVER_MAPS_KEY','secret');monkeypatch.setenv('NAVER_MAPS_KEY_ID','test')
    def get(*args,**kwargs):raise httpx.ConnectError('secret')
    monkeypatch.setattr(httpx.Client,'get',get)
    assert search_address('서울시청')['status']=='unavailable'
    assert 'secret' not in str(search_address('서울시청'))

def test_location_endpoint_validation_and_rate_limit():
    with TestClient(app) as client:
        assert client.post('/api/locations/search',json={'query':'  '}).status_code==422
        first=client.post('/api/locations/search',json={'query':'서울시청'})
        assert first.status_code==200
        assert client.post('/api/locations/search',json={'query':'서울시청'}).status_code==429


def test_region_endpoint_reads_province_from_reverse_geocoding(monkeypatch):
    monkeypatch.setenv('NAVER_MAPS_KEY','test');monkeypatch.setenv('NAVER_MAPS_KEY_ID','test')
    def get(url,**kwargs):
        assert kwargs['params']['coords']=='129.16,35.16'
        return httpx.Response(200,json={'results':[{'region':{'area1':{'name':'부산광역시'},'area2':{'name':'해운대구'},'area3':{'name':'우동'}}}]},request=httpx.Request('GET',url))
    monkeypatch.setattr(httpx,'get',get)
    with TestClient(app) as client:
        data=client.post('/api/locations/region',json={'lat':35.16,'lon':129.16}).json()
        assert data['status']=='ok' and data['region']=='부산' and data['label']=='부산 해운대구 우동'
        # 연속 요청 제한
        assert client.post('/api/locations/region',json={'lat':35.16,'lon':129.16}).status_code==429


def test_region_endpoint_key_missing_outside_and_failure(monkeypatch):
    monkeypatch.delenv('NAVER_MAPS_KEY',raising=False);monkeypatch.delenv('NAVER_MAPS_KEY_ID',raising=False)
    def never(*args,**kwargs):raise AssertionError('no provider call expected')
    monkeypatch.setattr(httpx,'get',never)
    with TestClient(app) as client:
        assert client.post('/api/locations/region',json={'lat':35.16,'lon':129.16}).json()['status']=='key_missing'
        outside=client.post('/api/locations/region',json={'lat':40.7,'lon':-74.0}).json()
        assert outside['status']=='outside' and outside['region'] is None
        assert client.post('/api/locations/region',json={'lat':100,'lon':0}).status_code==422
        monkeypatch.setenv('NAVER_MAPS_KEY','secret');monkeypatch.setenv('NAVER_MAPS_KEY_ID','test')
        def fail(*args,**kwargs):raise httpx.ConnectError('secret')
        monkeypatch.setattr(httpx,'get',fail)
        failed=client.post('/api/locations/region',json={'lat':35.16,'lon':129.16})
        assert failed.json()['status']=='unavailable' and 'secret' not in failed.text
