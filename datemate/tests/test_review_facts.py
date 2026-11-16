"""블로그 후기 본문에서 읽은 영업시간·휴무: 이름 근처만 읽기, 다른 지점·공원 거르기, 캐시, 경로. 외부 호출은 모두 가짜."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app import blog_search, course_search, review_facts, web_security
from app.main import app


def place(**fields):
    base = dict(id='discovered:' + uuid.uuid4().hex[:20], name='소소함박 황리단길 점', category='카페·미식',
                address='경상북도 경주시 손효자길 21', region='경북', lat=35.84, lon=129.21, demo=False, hours=None)
    base.update(fields)
    return base


BODY = ('경주 여행 첫날! 점심은 소소함박 황리단길점 경북 경주시 손효자길 21 소소함박 황리단길점 '
        '[영업시간] 매일 11:00 - 21:00 정기휴무 : 매주 월요일 함박스테이크가 정말 맛있었어요.')


def test_reads_hours_and_closed_days_next_to_the_name():
    found = review_facts.read_post(BODY, place())
    assert found and found[0][0] == '매일 11:00~21:00' and found[0][1] == '정기휴무 : 매주 월요일'
    assert '영업시간' in found[0][2]


def test_ignores_hours_far_from_the_name_and_other_branches():
    # 이름이 없는 곳의 시간(다른 가게)은 읽지 않는다.
    other = '근처 카페 영업시간 08:00 - 22:00 ' + ' ' * 800 + '소소함박 황리단길점 다녀왔어요'
    assert review_facts.read_post(other, place()) == []
    # 이름과 시간 사이에 다른 시·군·구 주소가 나오면 다른 지점이다(전주 가게 글에 군산점 정보).
    p = place(name='조점례남문피순대', address='전북특별자치도 전주시 완산구 전동3가 2-198')
    branch = '조점례남문피순대 군산점 위치 : 전북 군산시 공단대로 89 1층 영업시간 : 매일 09:00 ~ 22:00'
    assert review_facts.read_post(branch, p) == []
    same = '조점례남문피순대 주소 전북 전주시 완산구 전동3가 영업시간 매일 06:00 - 22:00'
    assert review_facts.read_post(same, p)[0][0] == '매일 06:00~22:00'


def test_place_words_in_the_name_are_not_searched_alone():
    # '안목해변'(지명)만으로는 찾지 않는다. 다른 가게 글에도 흔하다.
    p = place(name='강릉 샌드 안목해변 점', address='강원특별자치도 강릉시 창해로14번길 14')
    body = '안목해변 카페거리 보사노바 커피로스터스 영업시간 : 매일 07:00 ~ 22:00'
    assert review_facts.read_post(body, p) == []
    assert review_facts.read_post('강릉샌드 안목해변점 영업시간 : 매일 09:00~20:00', p)[0][0] == '매일 09:00~20:00'


@pytest.fixture
def fake(monkeypatch):
    state = dict(blogs=dict(status='available', posts=[]), bodies={}, fetched=[])

    def blogs(p):
        return state['blogs']

    def body(url):
        state['fetched'].append(url)
        return state['bodies'].get(url, '')

    monkeypatch.setattr(blog_search, 'place_blogs', blogs)
    monkeypatch.setattr(course_search, 'public_body', body)
    return state


def posts(*urls):
    return [dict(title='글 ' + u, url=u, posted_at='2026-10-08', blogger='누군가') for u in urls]


def test_most_agreed_hours_with_source_and_cache(fake):
    tag = uuid.uuid4().hex[:6]
    urls = [f'https://blog.naver.com/a/{tag}{i}' for i in range(3)]
    fake['blogs'] = dict(status='available', posts=posts(*urls))
    fake['bodies'] = {urls[0]: BODY, urls[1]: BODY, urls[2]: '소소함박 황리단길점 영업시간 10:00-20:00'}
    p = place()
    result = review_facts.review_facts(p)
    assert result['status'] == 'available' and result['hours'] == '매일 11:00~21:00' and result['agreeing_posts'] == 2
    assert result['closed'] == '정기휴무 : 매주 월요일' and result['source']['url'] == urls[0]
    assert result['source']['posted_at'] == '2026-10-08' and '다를 수 있어요' in result['note']
    assert len(fake['fetched']) == 3
    again = review_facts.review_facts(p)
    assert again == result and len(fake['fetched']) == 3


def test_skips_parks_known_hours_demo_and_missing_blogs(fake):
    assert review_facts.review_facts(place(category='산책·풍경'))['status'] == 'skipped'
    assert review_facts.review_facts(place(hours=[600, 1260]))['status'] == 'skipped'
    assert review_facts.review_facts(place(demo=True))['status'] == 'demo'
    fake['blogs'] = dict(status='not_found', posts=[])
    assert review_facts.review_facts(place())['status'] == 'not_found'
    fake['blogs'] = dict(status='available', posts=posts('https://blog.naver.com/a/' + uuid.uuid4().hex))
    empty = review_facts.review_facts(place())
    assert empty['status'] == 'not_found' and empty['hours'] is None
    assert fake['fetched'] and all('blog.naver.com' in u for u in fake['fetched'])


def test_route_is_expensive_and_unknown_place_is_404():
    assert any(p.match('GET /api/places/abc/review-facts') for p in web_security.EXPENSIVE)
    with TestClient(app) as client:
        assert client.get('/api/places/discovered:none/review-facts').status_code == 404
