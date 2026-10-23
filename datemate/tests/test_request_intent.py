from copy import deepcopy
import pytest
from app.models import Conditions
from app.request_intent import interpret,normalize,matches
from app.course_search import course_query
from app.catalog import places
from app.planner import recommend


@pytest.mark.parametrize('text,wanted',[
 ('카페투어',['cafe']),('카페 투어 하고 싶어요',['cafe']),('커피랑 디저트',['cafe']),
 ('맛집 투어',['meal']),('밥집 추천',['meal']),('전시 보고 산책',['culture','walk']),
 ('박물관 데이트',['museum']),('독립서점 책방 투어',['book']),('도자기 공방 원데이',['workshop']),
 ('한강 피크닉',['walk']),('야경과 전망',['view']),('방탈출 보드게임',['game']),
 ('클라이밍 볼링',['climbing','bowling']),('소품샵 쇼핑',['shopping']),('비 오는 날 실내 카페',['cafe']),
 ('카페 말고 전시',['culture']),('박물관 제외하고 산책',['walk']),
 ('카페 안 가고 맛집',['meal']),('전시 빼고 서점',['book']),
])
def test_common_requests(text,wanted):
    assert set(interpret(text)['intents'])==set(wanted)


def test_constraints_and_negative_words_are_interpreted():
    parsed=interpret('카페 말고 전시, 비 오는 날 실내에서 셋이서 8만 5천원 2곳 지하철로 예약 없이')
    assert parsed['excluded']==['cafe']
    assert parsed['patch']==dict(themes=['문화·예술'],setting='indoor',count=2,people=3,budget=85000,transport='transit',reservation=False)
    c=normalize(Conditions(visit_date='2026-10-24',course_query='카페투어',include_meal=True,date_category='콘셉트별',date_subcategory='지적인 데이트'))
    assert c.themes==['카페·미식'] and not c.include_meal and not c.date_subcategory
    assert '카페투어' in course_query(c) and course_query(c)!='카페투어'
    assert not matches(dict(id='food:test',name='카페 옆 식당',meal=True,category='카페·미식'),'cafe')
    assert interpret('사진 찍고 대화하며 도보 20분 이내')['patch']['priority']=='photo'
    assert interpret('사진 찍고 대화하며 도보 20분 이내')['patch']['max_walk']==20


def venues():
    template=places()[0];rows=[]
    for i,(name,category,key) in enumerate([
        ('커피 카페 A','카페·미식','cafe'),('디저트 카페 B','카페·미식','cafe'),('티하우스 C','카페·미식','cafe'),
        ('음식점 D','카페·미식','meal'),('밥집 E','카페·미식','meal'),('역사 박물관','문화·예술','museum'),
        ('미술관 전시','문화·예술','culture'),('숲길 공원 산책','산책·풍경','walk'),('독립 서점','문화·예술','book')]):
        p=deepcopy(template);p.update(id=f'fixture-{i}',name=name,category=category,themes=[category],tags=[key],meal=key=='meal',
            lat=37.575+i*.0003,lon=126.985,setting='outdoor' if key=='walk' else 'indoor',price=[1000,1000],reservation=False)
        rows.append(p)
    return rows


@pytest.mark.parametrize('field',['course_query','request'])
def test_cafe_tour_in_either_field_returns_cafes_not_restaurants(monkeypatch,field):
    monkeypatch.setattr('app.quality.pool',lambda c:venues())
    c=Conditions(visit_date='2026-10-24',include_meal=True,max_leg=180,**{field:'카페투어'})
    plan=recommend(c)['plans'][0]
    assert all(matches(p,'cafe') for p in plan['places'])
    assert len(plan['places'])==3
    assert not plan['conditions']['include_meal']


def test_mixed_request_covers_both_activities_and_excludes_cafes(monkeypatch):
    rows=venues();monkeypatch.setattr('app.quality.pool',lambda c:[p for p in rows if not matches(p,'cafe')])
    c=Conditions(visit_date='2026-10-24',request='카페 말고 전시 보고 산책',max_leg=180,count=2)
    plan=recommend(c)['plans'][0]
    assert any(matches(p,'culture') for p in plan['places'])
    assert any(matches(p,'walk') for p in plan['places'])


def test_negative_activity_filters_the_real_candidate_pool(monkeypatch):
    from app.quality import pool
    monkeypatch.setattr('app.catalog.places',lambda *a:venues())
    c=normalize(Conditions(visit_date='2026-10-24',request='카페 말고 전시'))
    selected=pool(c)
    assert selected and not any(matches(p,'cafe') for p in selected)


def test_abbreviated_region_in_search_is_preserved():
    from app.quality import configure
    for text,region in [('성수 카페투어','성수동'),('연남 맛집','연남동'),('망원 산책','망원동')]:
        c=normalize(Conditions(visit_date='2026-10-24',course_query=text))
        query=course_query(c)
        assert query.startswith(text)
        assert configure(c,query).area_center.name==region+' 중심'


def test_local_cafe_discovery_checks_category_coordinates_and_area(monkeypatch):
    from app.intent_discovery import discover_requested_places
    monkeypatch.setattr('app.intent_discovery.search_enabled',lambda:True)
    monkeypatch.setattr('app.intent_discovery.local_lookup',lambda *a:([
        dict(title='실제 카페',category='카페,디저트',roadAddress='서울 종로구 인사동길',mapx=1269850000,mapy=375750000),
        dict(title='음식점',category='음식점>한식',roadAddress='서울 종로구 인사동길',mapx=1269850000,mapy=375750000),
        dict(title='먼 카페',category='카페,디저트',roadAddress='서울 강남구',mapx=1270500000,mapy=375000000)],'available'))
    c=normalize(Conditions(mode='real',visit_date='2026-10-24',course_query='종로 카페투어',area_center=dict(name='종로',lat=37.575,lon=126.985)))
    assert discover_requested_places(c)['resolved']==1
    found=[p for p in places('real') if p['name']=='실제 카페']
    assert found and matches(found[0],'cafe') and found[0]['hours'] is None
    from app import store
    with store.connect() as db:
        db.execute('DELETE FROM cache WHERE key=?',('discovered-place:'+found[0]['id'],))
