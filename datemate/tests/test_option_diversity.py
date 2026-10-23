from app.option_diversity import select_options,changed_places
from app.models import Conditions


def plan(ids,minutes=20,cost=100):
    return dict(places=[dict(id=i,name=i,lat=37.5,lon=127) for i in ids],legs=[dict(minutes=minutes)],total=[cost,cost])


def test_permutations_removed_and_two_places_differ_with_roles():
    c=Conditions(visit_date='2026-10-24')
    a=plan('abc');other_order=plan('cba');similar=plan('abd')
    b=plan('def',minutes=30);fast=plan('ghi',minutes=5)
    result=select_options([a,other_order,similar,b,fast],c)
    assert len(result)==3 and result[0] is a and result[2] is fast
    assert all(changed_places(p,q)>=2 for i,p in enumerate(result) for q in result[i+1:])
    assert [p['option_purpose'] for p in result]==['취향 우선','다른 매력','편안한 동선']


def test_shared_locked_places_and_limited_candidates_explained():
    c=Conditions(visit_date='2026-10-24',locked={0:'a',1:'b'})
    result=select_options([plan('abc'),plan('abd'),plan('abe')],c)
    assert len(result)==3
    assert all('고정한 장소' in p['diversity_note'] for p in result)
    c=Conditions(visit_date='2026-10-24')
    result=select_options([plan('abc'),plan('abd')],c)
    assert all('후보가 부족' in p['diversity_note'] for p in result)
