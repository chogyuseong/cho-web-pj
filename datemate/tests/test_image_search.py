import httpx
from app.image_search import search_place_images

def test_search_missing_key_and_demo(monkeypatch):
    monkeypatch.delenv('NAVER_SEARCH_CLIENT_ID',raising=False)
    assert search_place_images({'name':'경복궁','demo':False})['status']=='key_missing'
    assert search_place_images({'name':'가상 장소','demo':True})['status']=='demo'

def test_naver_search_mapping_and_filter(monkeypatch):
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID','test-id');monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET','test-secret')
    def get(self,url,**kwargs):
        assert kwargs['params']['query']=='경복궁 서울'
        assert url=='https://naverapihub.apigw.ntruss.com/search/v1/image'
        assert kwargs['headers']['X-NCP-APIGW-API-KEY-ID']=='test-id'
        assert kwargs['headers']['X-NCP-APIGW-API-KEY']=='test-secret'
        assert kwargs['params']['format']=='json'
        return httpx.Response(200,request=httpx.Request('GET',url),json={'items':[
            {'title':'<b>경복궁</b> 사진','thumbnail':'https://example.org/thumb.jpg','link':'https://example.org/original.jpg'},
            {'title':'다른 장소','thumbnail':'https://example.org/other.jpg','link':'https://example.org/other.jpg'},
            {'title':'경복궁 중복','thumbnail':'https://example.org/thumb.jpg','link':'https://example.org/original.jpg'},
            {'title':'경복궁 위험 링크','thumbnail':'javascript:alert(1)','link':'https://example.org/x.jpg'}]})
    monkeypatch.setattr(httpx.Client,'get',get)
    result=search_place_images({'name':'경복궁','demo':False})
    assert len(result['photos'])==1
    photo=result['photos'][0]
    assert photo['kind']=='search_result' and photo['license'] is None and '<b>' not in photo['title']
    assert 'test-secret' not in str(photo)

def test_naver_error_does_not_leak_secret(monkeypatch):
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID','test');monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET','secret')
    def get(*args,**kwargs):raise httpx.ConnectError('secret')
    monkeypatch.setattr(httpx.Client,'get',get)
    result=search_place_images({'name':'경복궁','demo':False})
    assert result=={'status':'unavailable','photos':[]}

def test_branch_keywords_allow_word_order_but_reject_other_branch(monkeypatch):
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID','test');monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET','secret')
    def get(self,url,**kwargs):
        return httpx.Response(200,request=httpx.Request('GET',url),json={'items':[
            {'title':'북촌에서 오설록 방문','thumbnail':'https://example.org/1.jpg','link':'https://example.org/2.jpg'},
            {'title':'오설록 제주점 방문','thumbnail':'https://example.org/3.jpg','link':'https://example.org/4.jpg'}]})
    monkeypatch.setattr(httpx.Client,'get',get)
    photos=search_place_images({'name':'오설록 티하우스 북촌점','image_keywords':['오설록','북촌']})['photos']
    assert len(photos)==1 and '북촌' in photos[0]['title']

def test_name_tokens_can_be_separated_by_hotel_and_punctuation(monkeypatch):
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID','test');monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET','test')
    def get(self,url,**kwargs):
        return httpx.Response(200,request=httpx.Request('GET',url),json={'items':[
            {'title':'라망시크레 #레스케이프호텔 서울','thumbnail':'https://example.org/a.jpg','link':'https://example.org/b.jpg'},
            {'title':'다른 호텔 라망','thumbnail':'https://example.org/c.jpg','link':'https://example.org/d.jpg'}]})
    monkeypatch.setattr(httpx.Client,'get',get)
    result=search_place_images({'name':'레스케이프 라망 시크레','address':'서울특별시 중구 퇴계로 67'})
    assert len(result['photos'])==1

def test_branch_token_is_not_dropped():
    from app.image_search import title_matches
    place={'name':'오설록 티하우스 북촌점'}
    assert title_matches(place,'북촌점, 오설록 티하우스 방문',[])
    assert not title_matches(place,'오설록 티하우스 제주점',[])

def test_district_retry_after_empty_search(monkeypatch):
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID','test');monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET','test')
    queries=[]
    def get(self,url,**kwargs):
        queries.append(kwargs['params']['query'])
        items=[] if len(queries)==1 else [{'title':'테스트카페 중구','thumbnail':'https://example.org/a.jpg','link':'https://example.org/b.jpg'}]
        return httpx.Response(200,request=httpx.Request('GET',url),json={'items':items})
    monkeypatch.setattr(httpx.Client,'get',get)
    assert search_place_images({'name':'테스트카페','address':'서울특별시 중구 세종대로 1'})['photos']
    assert queries==['테스트카페 서울','테스트카페 서울특별시 중구 세종대로 1']

def test_null_address_still_searches(monkeypatch):
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID','test');monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET','test')
    def get(self,url,**kwargs):
        return httpx.Response(200,request=httpx.Request('GET',url),json={'items':[{'title':'서울공예박물관','thumbnail':'https://example.org/a.jpg','link':'https://example.org/b.jpg'}]})
    monkeypatch.setattr(httpx.Client,'get',get)
    assert search_place_images({'name':'서울공예박물관','address':None})['photos']
