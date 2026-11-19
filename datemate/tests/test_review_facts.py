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
def fake(monkeypatch, naver_pages_allowed):
    # 본문 읽기(app/naver_pages.py)가 꺼져 있으면 review_facts 는 블로그 검색도 부르지 않는다(2026-11-20).
    # 남겨 둔 읽기 규칙을 시험하려고 켠다(실제 호출은 아래 가짜가 막는다).
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
    assert review_facts.review_facts(place(demo=True))['status'] == 'demo'
    fake['blogs'] = dict(status='not_found', posts=[])
    assert review_facts.review_facts(place())['status'] == 'not_found'
    fake['blogs'] = dict(status='available', posts=posts('https://blog.naver.com/a/' + uuid.uuid4().hex))
    empty = review_facts.review_facts(place())
    assert empty['status'] == 'not_found' and empty['hours'] is None
    assert fake['fetched'] and all('blog.naver.com' in u for u in fake['fetched'])


def test_no_blog_search_when_bodies_are_not_read(monkeypatch):
    # 본문을 읽지 않으면 결과가 나올 수 없으므로 블로그 검색 API 를 부르지 않는다(사용자마다 나가는 호출 줄이기).
    monkeypatch.setattr(blog_search, 'place_blogs', lambda p: pytest.fail('블로그 검색 호출'))
    assert review_facts.review_facts(place())['status'] == 'not_found'


def test_route_is_expensive_and_unknown_place_is_404():
    assert any(p.match('GET /api/places/abc/review-facts') for p in web_security.EXPENSIVE)
    with TestClient(app) as client:
        assert client.get('/api/places/discovered:none/review-facts').status_code == 404


MENU = ('온목당 경주황리단길본점 주소: 경북 경주시 사정로57번길 6 메뉴 맑은한돈곰탕 12,000원 들기름 칼국수 12,000원 '
        '감자만두 10,000원 주차는 시간당 3,000원 칼국수 2개 24,000원 총 46,000원 결제')


def test_reads_menu_prices_and_drops_parking_and_totals():
    p = place(name='온목당 경주황리단길 본점', address='경상북도 경주시 사정로57번길 6')
    found = review_facts.read_prices(MENU, p)
    assert found == [('맑은한돈곰탕', 12000), ('들기름 칼국수', 12000), ('감자만두', 10000)]
    # 다른 지점(다른 시·군·구) 뒤의 가격은 읽지 않는다.
    branch = '온목당 부산점 주소: 부산 해운대구 우동 1 메뉴 맑은한돈곰탕 15,000원'
    assert review_facts.read_prices(branch, p) == []


def test_prices_are_returned_even_without_hours_and_for_places_with_known_hours(fake):
    tag = uuid.uuid4().hex[:6]
    urls = [f'https://blog.naver.com/p/{tag}{i}' for i in range(2)]
    fake['blogs'] = dict(status='available', posts=posts(*urls))
    fake['bodies'] = {urls[0]: MENU, urls[1]: '온목당 경주황리단길본점 감자만두 10,000원 맑은한돈곰탕 12,000원'}
    p = place(name='온목당 경주황리단길 본점', address='경상북도 경주시 사정로57번길 6', hours=[660, 1290])
    result = review_facts.review_facts(p)
    assert result['status'] == 'available' and result['hours'] is None
    assert [(x['item'], x['amount']) for x in result['prices']] == [('맑은한돈곰탕', 12000), ('감자만두', 10000), ('들기름 칼국수', 12000)]
    assert result['prices'][0]['url'] == urls[0] and result['prices'][0]['posted_at'] == '2026-10-08'


@pytest.mark.parametrize('text,closed', [
    ('정기휴무 : 매주 월요일', '정기휴무 : 매주 월요일'),
    ('휴무일 : 일요일', '휴무일 : 일요일'),
    ('휴무 화', '휴무 화'),
    ('매주 화요일 휴무', '화요일 휴무'),
    ('연중무휴', '연중무휴'),
    # '휴무일' 한 낱말(뒤에 요일이 없음)은 휴무 정보가 아니다.
    ('휴무일 확인은 인스타그램에서', None),
])
def test_closed_day_phrases(text, closed):
    body = '소소함박 황리단길점 영업시간 매일 11:00 - 21:00 ' + text
    found = review_facts.read_post(body, place())
    assert found and found[0][1] == closed
