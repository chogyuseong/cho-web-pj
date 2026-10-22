import httpx
from app.blog_search import place_blogs

def test_blog_mapping_and_naver_filter(monkeypatch):
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID','test');monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET','secret')
    def get(self,url,**kwargs):
        assert url.endswith('/search/v1/blog')
        assert kwargs['headers']['X-NCP-APIGW-API-KEY']=='secret'
        items=[dict(title='<b>경복궁</b> 방문',description='서울 경복궁 산책',link='https://blog.naver.com/test/1',postdate='20261021',bloggername='테스트'),
               dict(title='다른 장소',description='정보',link='https://blog.naver.com/test/2'),
               dict(title='경복궁',link='https://unrelated.example/1')]
        return httpx.Response(200,request=httpx.Request('GET',url),json={'items':items})
    monkeypatch.setattr(httpx.Client,'get',get)
    result=place_blogs({'name':'경복궁','demo':False})
    assert len(result['posts'])==1 and result['posts'][0]['posted_at']=='2026-10-21'
    assert '<b>' not in result['posts'][0]['title'] and 'secret' not in str(result)

def test_blog_demo_and_no_key(monkeypatch):
    monkeypatch.delenv('NAVER_SEARCH_CLIENT_ID',raising=False)
    assert place_blogs({'name':'경복궁','demo':False})['status']=='key_missing'
    assert place_blogs({'demo':True})['status']=='demo'

def test_top_three_preserve_provider_order_and_branch(monkeypatch):
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID','test');monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET','secret')
    def get(self,url,**kwargs):
        assert kwargs['params']['sort']=='sim'
        items=[dict(title='오설록 제주 후기',link='https://blog.naver.com/test/0')]
        items += [dict(title=f'북촌 오설록 후기 {i}',link=f'https://blog.naver.com/test/{i}') for i in range(1,7)]
        return httpx.Response(200,request=httpx.Request('GET',url),json={'items':items})
    monkeypatch.setattr(httpx.Client,'get',get)
    result=place_blogs({'name':'오설록 티하우스 북촌점','image_keywords':['오설록','북촌']})
    assert [p['url'] for p in result['posts']]==[f'https://blog.naver.com/test/{i}' for i in range(1,4)]
