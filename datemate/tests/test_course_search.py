from datetime import date
from app.course_search import BlogText,match_places,course_query,priority,public_body
from app.models import Conditions
from app.planner import recommend_strict
from app.catalog import places


def test_public_blog_body_excludes_script_and_navigation():
    parser=BlogText();parser.feed('<div>navigation</div><div class="se-main-container"><div>서울숲</div><script>fake</script>산책</div><div>footer</div>')
    assert ' '.join(parser.parts)=='서울숲 산책'
    assert public_body('https://example.com/private')==''


def test_ranked_mentions_and_no_fabricated_ratings():
    posts=[dict(rank=1,title='연남동 데이트',description='서울숲 산책',_body=''),dict(rank=3,title='다른 글',description='',_body='서울숲')]
    matches=match_places(posts,[dict(id='park',name='서울숲')])
    assert matches['park']==dict(ranks=[1,3],score=4)
    assert priority(dict(places=[dict(id='park')]),dict(matches=matches))==4


def test_negative_mentions_do_not_reward_closed_or_unrecommended_places():
    posts=[dict(rank=1,title='방문 기록',description='서울숲은 추천하지 않아요.',_body='')]
    assert match_places(posts,[dict(id='park',name='서울숲')])=={}
    posts[0]['description']='서울숲은 산책하기 좋아요. 다른 가게는 폐업했어요.'
    assert 'park' in match_places(posts,[dict(id='park',name='서울숲')])


def test_explicit_sponsorship_is_downweighted_not_claimed_verified():
    from app.course_search import select_posts
    items=[dict(link=f'https://blog.naver.com/author{i}/123',title='종로구 데이트',description=desc) for i,desc in enumerate(['협찬 제공받은 후기','직접 찾은 장소'])]
    posts=select_posts(items,'종로구 데이트')
    assert posts[0]['author']=='author1'
    assert posts[1]['commercial_disclosure'] is True


def test_query_and_search_prioritization():
    c=Conditions(visit_date=date(2026,10,24),origin=dict(name='홍대입구역 지역 중심',lat=37.5572,lon=126.9254))
    assert course_query(c)=='연남동 데이트 코스'
    assert course_query(c.model_copy(update={'course_query':'종로 실내 데이트 코스'}))=='종로 실내 데이트 코스'
    c=Conditions(visit_date=date(2026,10,24),max_leg=180,budget=1000000)
    normal=recommend_strict(c)['plans']
    assert normal
    target=next(p for p in places() if p['id'] not in {p['id'] for p in normal[0]['places']})
    evidence={'matches':{target['id']:{'score':6}}}
    result=recommend_strict(c,evidence)['plans']
    assert any(p['id']==target['id'] for p in result[0]['places'])
