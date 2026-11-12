from app.models import Conditions
from app.routes import leg
from app.planner import evaluate
from app.catalog import places

A={'name':'A','lat':37.56,'lon':126.98}
B={'name':'B','lat':37.57,'lon':126.99}


def test_transition_buffer_changes_finish_not_walking_time():
    c=Conditions(visit_date='2026-11-01',count=2,max_leg=180,budget=1000000)
    venues=places()[:2]
    before,error=evaluate(venues,c,soft=True);assert not error
    after,error=evaluate(venues,c.model_copy(update={'transition_buffer_minutes':10}),soft=True);assert not error
    assert after['minutes']-before['minutes']==20
    assert after['walking']==before['walking']


def test_candidate_search_never_spends_route_calls_even_with_estimates_disabled(monkeypatch):
    from app import collection
    from app.routes import candidate_routes
    monkeypatch.setenv('NAVER_MAPS_KEY_ID','test-id');monkeypatch.setenv('NAVER_MAPS_KEY','test-key')
    def unexpected(*args,**kwargs):raise AssertionError('Candidate route must not request a provider')
    monkeypatch.setattr(collection,'fetch_json',unexpected)
    c=Conditions(visit_date='2026-11-01',mode='real',transport='car',allow_estimates=False)
    with candidate_routes():assert leg(A,B,c)['status']=='estimated'
    assert not c.allow_estimates
