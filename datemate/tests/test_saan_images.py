import httpx
from app.image_search import search_place_images


def test_saan_alias_scoped_to_euljiro_and_rejects_unrelated_images(monkeypatch):
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID','test');monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET','test')
    queries=[]
    def get(client,url,**kwargs):
        queries.append(kwargs['params']['query'])
        return httpx.Response(200,request=httpx.Request('GET',url),json={'items':[
            dict(title='을지로 카페 #SAAN 서울 중구 충무로4길 3',thumbnail='https://example.com/thumb.jpg',link='https://example.com/cafe.jpg'),
            dict(title='SAAN Google Play 앱',thumbnail='https://example.com/app.jpg',link='https://example.com/app-original.jpg')]})
    monkeypatch.setattr(httpx.Client,'get',get)
    place=dict(name='SAAN 2',address='서울특별시 중구 충무로4길 3 1층')
    result=search_place_images(place)
    assert result['status']=='available' and len(result['photos'])==1
    assert queries==['SAAN 을지로 카페 서울','SAAN2 카페']
    assert 'image_aliases' not in place
    search_place_images(dict(place,address='서울특별시 다른 주소'))
    assert queries[-1]=='SAAN 2 서울'
