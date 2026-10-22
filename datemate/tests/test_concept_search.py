import httpx
from app.models import Conditions
from app.course_search import course_query,search_courses
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


def test_search_relaxes_only_after_empty_result_and_records_queries(monkeypatch):
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID','test');monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET','secret')
    queries=[]
    def get(url,**kwargs):
        queries.append(kwargs['params']['query'])
        items=[] if len(queries)==1 else [dict(title='종로 코스',description='박물관',link='https://blog.naver.com/example/123',postdate='20261020')]
        return httpx.Response(200,request=httpx.Request('GET',url),json={'items':items})
    monkeypatch.setattr(httpx,'get',get)
    monkeypatch.setattr('app.course_search.public_body',lambda url:'')
    areas=[]
    monkeypatch.setattr('app.discovery.discover',lambda posts,area:(areas.append(area) or [],{}))
    result=search_courses(conditions('지적인 데이트'))
    assert '박물관' in queries[0] and queries[1]=='종로 데이트 코스'
    assert result['search_relaxed'] and len(result['search_history'])==2
    assert result['requested_query']==queries[0]
    assert areas==['종로 데이트 코스']
