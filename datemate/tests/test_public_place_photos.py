import pytest
import json
from app.public_place_photos import extract_place_photos
from app.image_search import search_place_images

def fixture(name='검증카페',lat=37.56,lon=126.99):
    base={'__typename':'PlaceDetailBase','id':'123','name':name,'coordinate':{'x':str(lon),'y':str(lat)},'roadAddress':'서울 중구 검증로 1'}
    state={'PlaceDetailBase:123':base,'ROOT_QUERY':{'detail':{'base':{'__ref':'PlaceDetailBase:123'},'images':{'images':[{'origin':'https://ldb-phinf.pstatic.net/place.jpg'}]},'menuImages':[{'imageUrl':'https://ldb-phinf.pstatic.net/menu.jpg'}]}},'unrelated':{'imageUrl':'https://ldb-phinf.pstatic.net/other.jpg'}}
    return state

def test_only_matched_business_images_and_no_menu_or_other_images():
    state=fixture();place={'name':'검증카페','lat':37.56,'lon':126.99}
    urls,pid=extract_place_photos('window.__APOLLO_STATE__ = '+json.dumps(state),place)
    assert urls==['https://ldb-phinf.pstatic.net/place.jpg'] and pid=='123'
    assert not extract_place_photos('window.__APOLLO_STATE__ = '+json.dumps(state),place|{'name':'다른지점'})[0]
    assert not extract_place_photos('window.__APOLLO_STATE__ = '+json.dumps(state),place|{'lat':37.65})[0]

def test_ambiguous_business_and_external_host_rejected():
    state=fixture();state['PlaceDetailBase:456']={**state['PlaceDetailBase:123'],'id':'456'}
    assert not extract_place_photos('window.__APOLLO_STATE__ = '+json.dumps(state),{'name':'검증카페','lat':37.56,'lon':126.99})[0]
    state=fixture();state['ROOT_QUERY']['detail']['images']['images'][0]['origin']='https://unrelated.example/image.jpg'
    assert not extract_place_photos('window.__APOLLO_STATE__ = '+json.dumps(state),{'name':'검증카페','lat':37.56,'lon':126.99})[0]

def test_https_thumbnail_is_usable_with_http_original(monkeypatch):
    import httpx
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID','test');monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET','test')
    def get(self,url,**kwargs):return httpx.Response(200,request=httpx.Request('GET',url),json={'items':[{'title':'검증카페','thumbnail':'https://search.pstatic.net/thumbnail.jpg','link':'http://example.com/original.jpg'}]})
    monkeypatch.setattr(httpx.Client,'get',get)
    result=search_place_images({'name':'검증카페'})
    assert result['photos'][0]['image_url'].startswith('https://')

def test_api_empty_result_uses_identified_place_photo(monkeypatch):
    from app.media import media_info
    monkeypatch.setattr('app.media.search_enabled',lambda:True)
    monkeypatch.setattr('app.public_place_photos.public_place_photos',lambda *args:{'status':'available','photo_source':'naver_public_place','photos':[{'image_url':'https://ldb-phinf.pstatic.net/place.jpg'}]})
    assert media_info({'id':'test-miss','name':'검증카페'})['photo_source']=='priority_place_photos'


@pytest.fixture(autouse=True)
def approved_visual_service(monkeypatch):
    monkeypatch.setattr('app.photo_relevance.classify',lambda *args:{'status':'approved','category':'interior','confidence':0.99})
