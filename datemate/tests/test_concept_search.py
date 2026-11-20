from app.models import Conditions
from app.course_search import course_query
from app.preferences import fit_score
from app.taxonomy import concept_score


def conditions(concept):
    return Conditions(mode='real',visit_date='2026-10-24',course_query='종로 데이트 코스',date_category='콘셉트별',date_subcategory=concept)


def test_each_concept_changes_query_and_concrete_place_ranking():
    queries={course_query(conditions(c)) for c in ['즐거운 데이트','편안한 데이트','지적인 데이트','동심 데이트']}
    assert len(queries)==4
    intellectual=conditions('지적인 데이트')
    assert '박물관' in course_query(intellectual)
    museum=dict(id='museum',name='역사 박물관',category='문화·예술',tags=[],description='전시')
    workshop=dict(id='workshop',name='도자기 공방',category='체험·제작',tags=[],description='공방')
    assert concept_score(museum,intellectual)>concept_score(workshop,intellectual)
    assert fit_score({'places':[museum],'legs':[]},intellectual)>fit_score({'places':[workshop],'legs':[]},intellectual)
    child=conditions('동심 데이트')
    arcade=dict(id='arcade',name='장난감과 캐릭터 오락실',category='오락·놀이',tags=[])
    game=dict(id='game',name='전략 게임',category='오락·놀이',tags=[])
    assert concept_score(arcade,child)>concept_score(game,child)
    assert concept_score(dict(name='박물관',description=None,tags=None,search_aliases=None),intellectual)>0

# 검색 결과가 없을 때 검색어를 줄여 다시 찾는 것은 tests/test_course_search.py 에서 본다.
