from datetime import date
from app.models import Conditions
from app.planner import recommend, recommend_strict, replacements
from app.catalog import places
import pytest
from app.taxonomy import DATE_CATEGORIES, classification_themes

def conditions(**changes):
    data=dict(mode='real',allow_estimates=True,visit_date=date(2026,10,24),origin=dict(name='서울시청',lat=37.5665,lon=126.978))
    return Conditions(**(data|changes))

def test_real_inputs_change_actual_places_without_fabricating_operations():
    first=recommend(conditions())['plans'][0]
    other=recommend(conditions(origin=dict(name='용산',lat=37.524,lon=126.98),count=2))['plans'][0]
    assert len(first['places'])==3 and len(other['places'])==2
    assert first['places'][0]['id']!=other['places'][0]['id']
    assert all(not p['demo'] and (p['hours'] is None or p.get('operations_source')) for p in first['places'])
    assert any('영업시간' in u for u in first['unknown'])
    assert all(r['status']=='estimated' and not r['path'] for r in first['legs'])
    assert all(t['stay']==60 for t in first['timeline'])
    assert all(p['hours'] is None for p in places('real') if not p.get('operations_source'))
    assert replacements(first,0,[])

def test_real_limits_and_explicit_estimate_opt_in():
    assert not recommend_strict(conditions(allow_estimates=False))['plans']
    assert recommend(conditions(allow_estimates=False))['status']=='best_effort'
    assert recommend(conditions(end='11:30'))['status']=='best_effort'
    plan=recommend(conditions(stay_minutes=30,themes=['산책·풍경']))['plans'][0]
    assert all(p['category']=='산책·풍경' for p in plan['places'])
    assert all(t['stay']==30 for t in plan['timeline'])

@pytest.mark.parametrize('category,subcategory',[(k,s) for k,values in DATE_CATEGORIES.items() for s in values])
def test_all_date_choices_have_real_recommendations(category,subcategory):
    c=conditions(date_category=category,date_subcategory=subcategory)
    result=recommend(c)
    assert result['plans'],(category,subcategory,result)
    for plan in result['plans']:
        assert len(plan['places'])==3
        assert all(set(p.get('themes') or [p['category']]).intersection(classification_themes(c)) for p in plan['places'])
        if subcategory in ['비 오는 날','눈 오는 날']:
            assert all(p['setting']=='indoor' for p in plan['places'])

def test_cafe_and_indoor_filters_do_not_silently_relax():
    plans=recommend(conditions(themes=['카페·미식'],setting='indoor'))['plans']
    assert plans
    assert all(p['setting']=='indoor' and '카페·미식' in p['themes'] for plan in plans for p in plan['places'])
    result=recommend(conditions(themes=['카페·미식'],setting='outdoor'))
    assert result['plans'] and result['status']=='best_effort'
    assert any(d['condition']=='setting' for d in result['plans'][0]['deviations'])

def test_curated_metadata_updates_existing_venue_without_duplicate():
    rows=places('real')
    assert len({p['id'] for p in rows})==len(rows)
    assert sum(p['id']=='Q121406424' for p in rows)==1
    assert not any(p['id']=='seoul:hikr-ground' for p in rows)
    venue=next(p for p in rows if p['id']=='Q121406424')
    assert venue['setting']=='indoor' and '오락·놀이' in venue['themes']
