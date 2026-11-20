"""장소 블로그 검색(app/blog_search.py): 네이버가 준 순서·건수·제목·요약 그대로 돌려준다(특약 2.2)."""
import httpx

from app.blog_search import original_text, place_blogs


def keys(monkeypatch):
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID', 'test')
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET', 'secret')


def test_results_are_returned_as_received(monkeypatch):
    keys(monkeypatch)
    items = [dict(title='<b>경복궁</b> 방문', description='서울 <b>경복궁</b> 산책 &amp; 야간개장...', link='https://blog.naver.com/test/1', postdate='20261021', bloggername='테스트'),
             dict(title='다른 장소', description='정보', link='https://blog.naver.com/test/2'),
             dict(title='경복궁', link='https://unrelated.example/1')]

    def get(self, url, **kwargs):
        assert url.endswith('/search/v1/blog')
        assert kwargs['headers']['X-NCP-APIGW-API-KEY'] == 'secret'
        assert kwargs['params'] == {'query': '경복궁 서울 방문 후기', 'display': 10, 'start': 1, 'sort': 'sim', 'format': 'json'}
        return httpx.Response(200, request=httpx.Request('GET', url), json={'items': items})

    monkeypatch.setattr(httpx.Client, 'get', get)
    result = place_blogs({'name': '경복궁', 'demo': False})
    # 이름이 안 나온 글도, 네이버 블로그가 아닌 글도 빼지 않는다. 순서도 그대로.
    assert [p['url'] for p in result['posts']] == [i['link'] for i in items]
    assert result['posts'][0] == dict(title='경복궁 방문', description='서울 경복궁 산책 & 야간개장...', url='https://blog.naver.com/test/1',
                                      blogger='테스트', posted_at='2026-10-21')
    assert result['query'] == '경복궁 서울 방문 후기' and 'secret' not in str(result)


def test_all_ten_results_are_kept_and_keywords_do_not_filter(monkeypatch):
    keys(monkeypatch)
    items = [dict(title='오설록 제주 후기', link='https://blog.naver.com/test/0')]
    items += [dict(title=f'북촌 오설록 후기 {i}', link=f'https://blog.naver.com/test/{i}') for i in range(1, 10)]
    monkeypatch.setattr(httpx.Client, 'get', lambda self, url, **kwargs: httpx.Response(200, request=httpx.Request('GET', url), json={'items': items}))
    result = place_blogs({'name': '오설록 티하우스 북촌점', 'image_keywords': ['오설록', '북촌']})
    assert [p['url'] for p in result['posts']] == [f'https://blog.naver.com/test/{i}' for i in range(10)]


def test_text_is_not_trimmed_or_tidied():
    long_title = '아주 긴 제목 ' * 60 + '...'
    assert original_text('<b>' + long_title + '</b>') == long_title
    assert original_text('성수<b>동</b>  카페 &lt;어니언&gt;…') == '성수동  카페 <어니언>…'
    assert original_text(None) == ''


def test_blog_demo_no_key_and_bad_response(monkeypatch):
    monkeypatch.delenv('NAVER_SEARCH_CLIENT_ID', raising=False)
    assert place_blogs({'name': '경복궁', 'demo': False})['status'] == 'key_missing'
    assert place_blogs({'demo': True})['status'] == 'demo'
    keys(monkeypatch)
    monkeypatch.setattr(httpx.Client, 'get', lambda self, url, **kwargs: httpx.Response(200, request=httpx.Request('GET', url), json={'items': 'x'}))
    assert place_blogs({'name': '경복궁', 'demo': False})['status'] == 'unavailable'
