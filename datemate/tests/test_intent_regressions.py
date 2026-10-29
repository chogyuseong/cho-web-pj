"""Reported user misunderstandings, including form/API precedence."""
import pytest
from app.models import Conditions
from app.request_intent import interpret, normalize, resolved_patch, search_terms


@pytest.mark.parametrize('text,people,total', [
    ('둘이서 1인당 3만원', 2, 60000),
    ('인당 30,000원', 4, 120000),
    ('셋이서 각자 2만5천원', 2, 75000),
    ('전체 예산 6만원', 2, 60000),
    ('1인당 2.5만원', 2, 50000),
    ('총 9천원', 2, 9000),
    ('1인 예약 가능, 총 예산 6만원', 2, 60000),
])
def test_budget_units(text, people, total):
    c=normalize(Conditions(visit_date='2026-11-01',request=text,people=people))
    assert c.budget==total


def test_explicit_people_and_budget_remain_authoritative():
    c=Conditions(visit_date='2026-11-01',request='둘이서 1인당 3만원',people=4,explicit_fields=['people'])
    assert normalize(c).budget==120000
    assert normalize(c).people==4
    assert normalize(c.model_copy(update={'budget':90000,'explicit_fields':['people','budget']})).budget==90000
    assert resolved_patch(interpret(c.request),4,True)['budget']==120000


def test_weather_alternative_is_not_silently_decided():
    parsed=interpret('비 오면 실내, 맑으면 야외 산책')
    assert 'setting' not in parsed['patch']
    assert parsed['warnings']
    assert interpret('비 오는 날 실내 카페')['patch']['setting']=='indoor'


def test_movie_and_jazz_flow_to_search():
    c=Conditions(visit_date='2026-11-01',request='영화 보고 재즈바 가고 싶어')
    assert set(interpret(c.request)['intents'])=={'cinema','jazz'}
    assert search_terms(c)==['영화관','재즈바']
    assert interpret('영화 말고 연극')['intents']==['performance']


def test_out_of_range_people_does_not_match_trailing_digit():
    assert 'people' not in interpret('21명')['patch']


def test_multiple_money_amounts_do_not_silently_become_total_budget():
    parsed=interpret('식사는 2만원, 카페는 1만원')
    assert 'budget' not in parsed['patch'] and parsed['warnings']


def test_parse_api_uses_form_people():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as client:
        response=client.post('/api/conditions/parse',json={'text':'1인당 3만원','people':4})
        assert response.status_code==200
        assert response.json()['patch']['budget']==120000
