"""코스 조사용 블로그 검색(app/course_search.py): 검색어는 조건에서 만들고, 검색 결과는 받은 그대로 돌려준다.
추천 계산과의 분리는 tests/test_blog_independent_block.py."""
from datetime import date

import httpx

from app import course_search
from app.course_search import course_query, search_courses
from app.models import Conditions


def conditions(**changes):
    return Conditions(**(dict(mode='real', visit_date=date(2026, 10, 24), course_query='종로 데이트 코스') | changes))


def test_query_comes_from_the_conditions():
    c = Conditions(visit_date=date(2026, 10, 24), origin=dict(name='홍대입구역 지역 중심', lat=37.5572, lon=126.9254))
    assert course_query(c) == '연남동 데이트 코스'
    assert course_query(c.model_copy(update={'course_query': '종로 실내 데이트 코스'})) == '종로 실내 데이트 코스'


def test_posts_keep_naver_order_count_and_text(monkeypatch):
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID', 'test')
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET', 'secret')
    long_text = '요약 ' * 200 + '끝…'
    items = [
        dict(title='협찬 받은 <b>종로</b> 맛집 BEST 10...', description=long_text, link='https://blog.naver.com/ad/1', postdate='20200101', bloggername='광고&amp;협찬'),
        dict(title='같은 작성자 두 번째 글', description='', link='https://blog.naver.com/ad/2', postdate='20261020', bloggername='광고&amp;협찬'),
        dict(title='다른 동네 글', description='부산 이야기', link='https://example.tistory.com/3', postdate='', bloggername='티스토리'),
        dict(title='링크가 이상한 글', description='', link='javascript:alert(1)', postdate='20261019', bloggername='x'),
    ] + [dict(title=f'글 {i}', description=f'요약 {i}', link=f'https://blog.naver.com/b/{i}', postdate='20261001', bloggername='b') for i in range(16)]
    seen = []

    def get(url, **kwargs):
        seen.append(kwargs['params'])
        return httpx.Response(200, request=httpx.Request('GET', url), json={'items': items})

    monkeypatch.setattr(httpx, 'get', get)
    result = search_courses(conditions())
    assert seen == [dict(query='종로 데이트 코스', display=20, start=1, sort='sim', format='json')]
    posts = result['posts']
    # 받은 건수 그대로(오래된 글·광고 문구·같은 작성자·네이버 밖 블로그도 빼지 않는다), 받은 순서 그대로.
    assert len(posts) == len(items) == 20
    assert [p['title'] for p in posts[1:4]] == ['같은 작성자 두 번째 글', '다른 동네 글', '링크가 이상한 글']
    assert [p['url'] for p in posts[4:]] == [f'https://blog.naver.com/b/{i}' for i in range(16)]
    # 제목·요약은 강조 태그와 엔티티만 글자로 바꾸고 자르거나 다듬지 않는다.
    assert posts[0] == dict(title='협찬 받은 종로 맛집 BEST 10...', description=long_text, url='https://blog.naver.com/ad/1',
                            blogger='광고&협찬', posted_at='2020-01-01')
    assert posts[2]['url'] == 'https://example.tistory.com/3' and posts[2]['posted_at'] is None
    assert posts[3]['url'] is None, '웹 주소가 아닌 링크는 링크만 뺀다'
    assert result['format'] == course_search.FORMAT == 2 and result['status'] == 'available'
    # 우리가 붙이던 선정·판정 정보는 없다.
    assert not {'matches', 'discovery', 'discovered_ids', 'selection_note', 'rating_note'} & set(result)
    assert not {'rank', 'search_rank', 'selection_reason', 'commercial_disclosure', 'evidence_note', 'mentioned_places', 'author'} & set(posts[0])


def test_search_relaxes_only_after_an_empty_result_and_keeps_the_requested_query(monkeypatch):
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID', 'test')
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET', 'secret')
    queries = []

    def get(url, **kwargs):
        queries.append(kwargs['params']['query'])
        items = [] if len(queries) == 1 else [dict(title='종로 코스', description='박물관', link='https://blog.naver.com/example/123', postdate='20261020')]
        return httpx.Response(200, request=httpx.Request('GET', url), json={'items': items})

    monkeypatch.setattr(httpx, 'get', get)
    result = search_courses(conditions(date_category='콘셉트별', date_subcategory='지적인 데이트'))
    assert '박물관' in queries[0] and queries[1] == '종로 데이트 코스'
    assert result['search_relaxed'] and len(result['search_history']) == 2
    assert result['requested_query'] == queries[0] and result['query'] == queries[1]


def test_without_key_or_on_failure_nothing_is_invented(monkeypatch):
    monkeypatch.delenv('NAVER_SEARCH_CLIENT_ID', raising=False)
    missing = search_courses(conditions())
    assert missing['status'] == 'key_missing' and missing['posts'] == [] and missing['requested_query'] == '종로 데이트 코스'
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID', 'test')
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET', 'secret')

    def fail(url, **kwargs):
        raise httpx.ConnectError('down')

    monkeypatch.setattr(httpx, 'get', fail)
    failed = search_courses(conditions())
    assert failed['status'] == 'unavailable' and failed['posts'] == [] and '영향이 없어요' in failed['message']
