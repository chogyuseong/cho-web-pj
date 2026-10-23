from app.search_relaxation import relaxation_steps,search_progressively
from app.models import Conditions
from app.catalog import places
import pytest


def conditions(**patch):
    return Conditions(**(dict(mode='real',allow_estimates=True,visit_date='2026-10-24',
        origin=dict(name='선택 지역',lat=37.575,lon=126.985),budget=10000,count=3)|patch))


def test_each_preference_changes_separately_before_radius_and_inputs_preserved():
    c=conditions(themes=['문화·예술'],theme_mode='focus',setting='indoor',max_walk=20,
                 request='카페 투어, 식당 제외',avoid=['공방'],trust_mode='operating_sources')
    before=c.model_dump(mode='json');steps=list(relaxation_steps(c))
    assert all(a.origin==c.origin and a.visit_date==c.visit_date and a.people==c.people and a.transport==c.transport for a,_,_ in steps)
    assert len(steps)>10
    changes=[set(delta) for _,_,delta in steps]
    assert {'theme_mode'} in changes and {'setting'} in changes and any('avoid' in delta for delta in changes)
    assert any('max_walk' in delta for delta in changes)
    radii=[a.neighborhood_radius_km for a,_,_ in steps]
    assert radii==sorted(radii)
    budgets=[a.budget for a,_,_ in steps]
    assert budgets==sorted(budgets) and max(budgets)>c.budget
    assert c.model_dump(mode='json')==before


def test_required_fields_and_locked_positions_are_never_relaxed():
    c=conditions(hard_constraints=['themes','setting','avoid','budget','end','max_leg','max_walk','reservation','meal','neighborhood'],
                 themes=['문화·예술'],setting='indoor',avoid=['카페'],locked={2:'locked'},max_walk=20)
    for a,_,_ in relaxation_steps(c):
        for field in ('themes','setting','avoid','budget','end','max_leg','max_walk','reservation','include_meal','neighborhood_radius_km','locked'):
            assert getattr(a,field)==getattr(c,field)
        assert a.count>=3


def test_stops_at_first_feasible_budget_and_compares_to_original(monkeypatch):
    rows=[dict(p,id='step-'+str(i),region='서울',demo=False,lat=37.575+i*.0001,lon=126.985,
               hours=[0,1440],closed_days=[],breaks=[],last_entry=None,reservation=False,
               stay=30,price=[5000,5000],price_unit='person') for i,p in enumerate(places('demo')[:3])]
    monkeypatch.setattr('app.catalog.places',lambda *args,**kwargs:rows)
    c=conditions();result=search_progressively(c)
    assert result
    p=result[0];adjust=p['search_adjustments']
    assert adjust['effective_conditions']['budget']==30000
    assert adjust['effective_radius_km']==c.neighborhood_radius_km
    assert p['conditions']['budget']==10000 and p['conditions']['origin']==c.origin.model_dump()
    assert any(r['condition']=='budget' and r['state']=='unmet' for r in p['condition_checks'])
    assert adjust['attempts'][-1]['plans']>0
    assert all(row['plans']==0 for row in adjust['attempts'][:-1])


@pytest.mark.parametrize('patch,field',[
    ({'themes':['체험·제작']},'themes'),({'setting':'indoor'},'setting'),
    ({'budget':10000},'budget'),({'end':'11:20'},'end'),
    ({'max_leg':1},'max_leg'),({'max_walk':2},'max_walk'),
    ({'count':5},'count'),({'avoid':['검증장소']},'avoid'),
    ({'trust_mode':'operating_sources'},'trust_mode'),
])
def test_real_planning_retries_individual_condition(monkeypatch,patch,field):
    rows=[dict(p,id='matrix-'+str(i),name='검증장소'+str(i),category='카페·미식',themes=['카페·미식'],
               region='서울',demo=False,lat=37.584+i*.001,lon=126.985,setting='outdoor',
               hours=[0,1440],closed_days=[],breaks=[],last_entry=None,reservation=False,
               stay=30,price=[5000,5000],price_unit='person',operations_source=None)
          for i,p in enumerate(places('demo')[:3])]
    monkeypatch.setattr('app.catalog.places',lambda *args,**kwargs:rows)
    base=dict(budget=200000,max_leg=180,end='23:00',count=3)
    c=conditions(**(base|patch))
    from app.planner import recommend
    result=recommend(c)
    assert result['plans'],field
    p=result['plans'][0]
    assert p['conditions']==c.model_dump(mode='json')
    changes=[a['changes'] for a in p['search_adjustments']['attempts']]
    assert any(field in change for change in changes),(field,changes)
