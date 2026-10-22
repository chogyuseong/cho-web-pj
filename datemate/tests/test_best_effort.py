from datetime import date
from app.models import Conditions
from app.planner import recommend,replacements
from app.planner import evaluate
from app.best_effort import annotate
from app.catalog import places

def conditions(**patch):
    return Conditions(**(dict(mode='real',allow_estimates=True,visit_date=date(2026,10,24),
        origin=dict(name='강동구',lat=37.5301,lon=127.1238),transport='transit',themes=['카페·미식'])|patch))

def test_far_origin_returns_ranked_alternatives_with_original_conditions():
    c=conditions()
    result=recommend(c)
    assert result['status']=='best_effort' and result['plans']
    assert [p['penalty'] for p in result['plans']]==sorted(p['penalty'] for p in result['plans'])
    for plan in result['plans']:
        assert plan['conditions']==c.model_dump(mode='json')
        assert len(plan['places'])==3
        assert any(d['condition'] in ('max_leg','themes') for d in plan['deviations'])
        assert plan['unknown']

def test_fallback_replacement_and_locks_preserve_original_request():
    c=conditions();plan=recommend(c)['plans'][0]
    options=replacements(plan,1,[0,2])
    assert options
    for option in options:
        assert option['best_effort'] and option['conditions']==plan['conditions']
        assert option['places'][0]==plan['places'][0] and option['places'][2]==plan['places'][2]
    locked=recommend(conditions(locked={0:plan['places'][0]['id']}))['plans']
    assert locked and all(p['places'][0]['id']==plan['places'][0]['id'] for p in locked)

def test_empty_theme_setting_intersection_still_yields_explained_alternative():
    result=recommend(conditions(setting='outdoor'))
    assert result['plans'] and result['status']=='best_effort'
    assert all(p['deviations'] for p in result['plans'])

def test_avoid_is_kept_in_approximate_results():
    result=recommend(conditions(avoid=['오설록','다원']))
    assert result['plans']
    assert all('오설록' not in p['name'] and '다원' not in p['name'] for plan in result['plans'] for p in plan['places'])

def test_weather_mismatch_and_missing_data_are_distinct():
    c=conditions(themes=[],count=2,date_category='날씨별',date_subcategory='비 오는 날')
    selected=[dict(p) for p in places('real')[:2]]
    selected[0]['setting']='outdoor';selected[1]['setting']=None
    plan,error=evaluate(selected,c,soft=True)
    assert not error
    plan=annotate(plan,c)
    weather=[d for d in plan['deviations'] if d['condition']=='weather']
    assert {d['state'] for d in weather}=={'unmet','unknown'}
    assert all(d['label']=='날씨' and '비 오는 날' in d['message'] for d in weather)
    assert '야외' in weather[0]['message'] and '확인되지' in weather[1]['message']
    assert '날씨' in plan['condition_summary'] and '충족 여부' in plan['condition_summary']

def test_indoor_weather_match_is_not_reported_as_weather_failure():
    c=conditions(themes=[],count=2,date_category='날씨별',date_subcategory='눈 오는 날')
    selected=[dict(p,setting='indoor') for p in places('real')[:2]]
    plan,error=evaluate(selected,c,soft=True)
    assert not error
    assert not any(d['condition']=='weather' for d in annotate(plan,c)['deviations'])
