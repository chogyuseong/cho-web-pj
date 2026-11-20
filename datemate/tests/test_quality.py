from datetime import date
from app.models import Conditions
from app.quality import configure,in_area,meal_penalty,meal_due
from app import discovery


def test_area_uses_searched_neighborhood_not_distant_origin():
    c=configure(Conditions(visit_date=date(2026,10,24)), '연남동 데이트 코스')
    assert in_area(dict(lat=37.56,lon=126.925),c)
    assert not in_area(dict(lat=37.5446,lon=127.0559),c)


def test_same_real_place_cannot_appear_twice_under_different_ids():
    from app.quality import same_place
    a=dict(id='wiki',name='서울숲',lat=37.544,lon=127.037)
    b=dict(id='discovered',name='서울숲',lat=37.545,lon=127.038)
    assert same_place(a,b)
    assert not same_place(a,dict(b,name='다른 공원'))


def test_meal_requires_real_food_and_lunch_window():
    c=Conditions(visit_date=date(2026,10,24),include_meal=True,start='11:00',end='17:00')
    assert meal_due(c)
    p=dict(places=[dict(id='cafe',meal=False)],timeline=[dict(arrival='12:00',departure='13:00')])
    assert meal_penalty(p,c)==4
    p['places'][0]['meal']=True
    assert meal_penalty(p,c)==0
    p['timeline'][0]=dict(arrival='15:00',departure='16:00')
    assert meal_penalty(p,c)==2
    assert not meal_due(c.model_copy(update={'start':'15:00','end':'16:00'}))


def test_blog_discovery_path_is_removed():
    # 네이버 검색 API 특약 2.2·2.3(2026-09): 블로그 검색 결과에서 장소를 뽑아 후보로 쓰지 않는다. LLM 추출·주소 연결 코드를 없앴다.
    assert not any(hasattr(discovery,name) for name in ('llm','extract','resolve','discover'))
