from datetime import date
import copy
from app.condition_audit import audit_plan
from app.catalog import places
from app.models import Conditions
from app.planner import recommend

def test_all_conflicting_conditions_and_unknowns_are_reported():
    c=Conditions(mode='real',allow_estimates=False,visit_date=date(2026,10,24),
        origin=dict(name='요청 출발지',lat=37.5,lon=127),start='11:00',end='12:00',people=3,budget=100,
        count=3,themes=['카페·미식'],date_category='날씨별',date_subcategory='비 오는 날',theme_mode='focus',
        setting='indoor',avoid=['게임'],reservation=False,max_leg=5,max_walk=5,return_home=True,
        home=dict(name='요청 귀가지',lat=37.5,lon=127),locked={0:'wanted'},stay_minutes=30,request='조용한 장소',use_mbti=True)
    a,b=[copy.deepcopy(p) for p in places('demo')[:2]]
    a.update(name='게임 공원',category='산책·풍경',setting='outdoor',closed_days=[5],hours=[660,690],last_entry=675,breaks=[[660,900]],reservation=True)
    b.update(region='경기',category='문화·예술',setting=None,hours=None,closed_days=None,reservation=None,stay=None)
    plan=dict(conditions=c.model_dump(mode='json'),places=[a,b],minutes=180,walking=20,finish='14:00',
        legs=[dict(origin='다른 출발지',destination=a['name'],minutes=20,walking=10,status='estimated'),
              dict(origin=a['name'],destination=b['name'],minutes=20,walking=10,status='estimated')],
        timeline=[dict(arrival='11:20',departure='12:20',stay=60),dict(arrival='12:40',departure='13:40',stay=60)],
        total=[200,500],costs=[dict(amount=[200,500],status='estimated'),dict(amount=None,status='unknown')],unknown=['주차비'])
    result=audit_plan(plan,c)
    unmet={r['condition'] for r in result['deviations'] if r['state']=='unmet'}
    assert {'region','origin','visit_date','end','budget','count','themes','date_subcategory','weather','theme_mode',
        'setting','avoid','reservation','max_leg','max_walk','return_home','stay_minutes','allow_estimates','locked'}<=unmet
    unknown={r['condition'] for r in result['deviations'] if r['state']=='unknown'}
    assert {'visit_date','budget','transport','weather','setting','reservation','request','mbti'}<=unknown
    assert any(r['condition']=='people' and r['state']=='met' for r in result['condition_checks'])
    assert result['conditions']==c.model_dump(mode='json')

def test_standard_results_also_explain_unknown_budget_and_reservations():
    c=Conditions(mode='real',allow_estimates=True,visit_date=date(2026,10,24))
    plan=recommend(c)['plans'][0]
    assert not plan.get('best_effort')
    assert {'budget','reservation','visit_date'}<={r['condition'] for r in plan['deviations']}
    assert {'region','mode','origin','visit_date','start','end','people','budget','transport','count','themes',
        'date_subcategory','theme_mode','setting','avoid','reservation','max_leg','max_walk','return_home',
        'stay_minutes','allow_estimates','mbti','request','locked'}<={r['condition'] for r in plan['condition_checks']}

def test_verified_matching_conditions_are_not_reported_as_unmet():
    c=Conditions(visit_date=date(2026,10,24))
    plan=recommend(c)['plans'][0]
    # 데모의 고정 체류 시간이 입력값과 다르면 체류 차이는 정직하게 표시한다.
    assert not any(r['state']=='unmet' and r['condition']!='stay_minutes' for r in plan['condition_checks'])
    assert {'count','budget','max_leg','end','origin','region','locked'}<={r['condition'] for r in plan['condition_checks'] if r['state'] in ('met','estimated')}
