"""'예산 무관'(budget_unlimited) 서버 처리. 가상 장소 데모라 외부 호출이 없다.

true면 budget 숫자를 조건·감점·필수 조건·완화에 쓰지 않는다. 코스의 remaining은 null, 조건 확인의 예산 항목은
'예산 무관'(info). 저장·다시 열기·공유·장소 교체·수단 변경 뒤에도 conditions.budget_unlimited가 남는다.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app import planner
from app.main import app
from app.models import Conditions
from app.plan_chat import answer_plan
from app.search_relaxation import relaxation_steps

BASE = {'visit_date': '2026-10-24', 'budget': 0}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def budget_checks(plan):
    return [r for r in plan['condition_checks'] if r['condition'] == 'budget']


def assert_unlimited(plan):
    assert plan['conditions']['budget_unlimited'] is True
    assert plan['remaining'] is None
    checks = budget_checks(plan)
    assert checks and all(r['state'] == 'info' and r['label'] == '예산 무관' for r in checks)
    assert not any(d['condition'] == 'budget' for d in plan.get('deviations', []))
    text = json.dumps(plan, ensure_ascii=False)
    assert '예산 0원' not in text and '예산을 넘는' not in text


def test_budget_is_not_a_filter_when_unlimited():
    # 예산 0원이면 모든 가상 코스가 예산 초과다. 예산 무관이면 엄격 탐색에서 그대로 3안이 나온다.
    c = Conditions(**BASE, budget_unlimited=True)
    strict = planner.recommend_strict(c)
    assert len(strict['plans']) == 3 and strict['status'] == 'ok'
    assert all(p['total'][1] > 0 and p['remaining'] is None for p in strict['plans'])
    result = planner.recommend(c)
    assert result['status'] == 'ok' and len(result['plans']) == 3
    for plan in result['plans']:
        assert not plan.get('best_effort') and not plan.get('search_adjustments')
        assert_unlimited(plan)


def test_unlimited_matches_a_budget_large_enough_for_everything():
    # 예산을 빼고 가장 잘 맞는 코스 = 예산이 충분히 클 때의 코스와 같은 장소.
    ids = lambda r: [[p['id'] for p in plan['places']] for plan in r['plans']]
    unlimited = planner.recommend(Conditions(**BASE, budget_unlimited=True))
    roomy = planner.recommend(Conditions(**(BASE | {'budget': 10000000})))
    assert ids(unlimited) == ids(roomy)


def test_false_keeps_budget_behaviour():
    c = Conditions(**BASE)
    assert c.budget_unlimited is False
    # 예산 0원이면 무료 코스(산책 등)만 남고, 예산 완화 단계도 그대로 있다.
    strict = planner.recommend_strict(c)
    assert all(p['total'][1] <= 0 for p in strict['plans'])
    assert any('예산' in h[-1] for _, h, _ in relaxation_steps(c))
    result = planner.recommend(c)
    unlimited = planner.recommend(Conditions(**BASE, budget_unlimited=True))
    assert [p['total'] for p in result['plans']] != [p['total'] for p in unlimited['plans']]
    plan = result['plans'][0]
    assert isinstance(plan['remaining'], list) and plan['remaining'][0] == -plan['total'][1]
    assert plan['conditions']['budget_unlimited'] is False
    assert all(r['label'] == '예산' for r in budget_checks(plan))
    # 명시한 false와 생략은 같은 결과다.
    explicit = planner.recommend(Conditions(**BASE, budget_unlimited=False))
    strip = lambda r: json.dumps(r['plans'], ensure_ascii=False, sort_keys=True)
    assert strip(explicit) == strip(result)


@pytest.mark.parametrize('unlimited', [True, False])
def test_price_check_keeps_remaining_null_and_no_over_budget_status(unlimited):
    from app.pricing import apply_prices
    plan = planner.recommend(Conditions(**BASE, budget_unlimited=True))['plans'][0]
    plan['conditions'] = dict(plan['conditions'], mode='real', allow_estimates=True, budget_unlimited=unlimited)
    priced = apply_prices(plan, {})
    if unlimited:
        assert priced['remaining'] is None and not priced['status'].startswith('예산을 넘는') and not priced.get('best_effort')
        assert_unlimited(priced)
    else:
        assert priced['remaining'] == [-priced['total'][1], -priced['total'][0]]
        assert priced['best_effort'] and any(r['label'] == '예산' and r['state'] == 'unmet' for r in budget_checks(priced))


def test_relaxation_never_moves_budget_when_unlimited():
    c = Conditions(**BASE, budget_unlimited=True, max_leg=1)
    labels = [h[-1] for _, h, _ in relaxation_steps(c)]
    assert labels and not any('예산' in label for label in labels)


def test_chat_answer_does_not_quote_a_budget():
    plan = planner.recommend(Conditions(**BASE, budget_unlimited=True))['plans'][0]
    answer = answer_plan(plan, '비용은 얼마예요?')['answer']
    assert '예산 무관' in answer and '입력 예산은' not in answer


def test_flag_survives_save_reopen_share_replace_and_transport(client):
    response = client.post('/api/plans', json=BASE | {'budget_unlimited': True})
    assert response.status_code == 200, response.text
    plans = response.json()['plans']
    assert len(plans) == 3
    plan = plans[0]
    assert_unlimited(plan)
    reopened = client.get('/api/plans/' + plan['id']).json()
    assert_unlimited(reopened)
    options = client.post(f"/api/plans/{plan['id']}/alternatives", json={'index': 1, 'locked': []}).json()['alternatives']
    assert options and all(o['remaining'] is None for o in options)
    replaced = client.post(f"/api/plans/{plan['id']}/replace",
                           json={'index': 1, 'locked': [], 'replacement_id': options[0]['places'][1]['id']})
    assert replaced.status_code == 200, replaced.text
    assert_unlimited(replaced.json())
    moved = client.post(f"/api/plans/{plan['id']}/transport", json={'default': 'transit'})
    assert moved.status_code == 200, moved.text
    assert_unlimited(moved.json())
    url = client.post(f"/api/plans/{plan['id']}/shares", json={}).json()['url']
    shared = client.get('/api/shared-plan', headers={'Authorization': 'Bearer ' + url.split('#', 1)[1]}).json()
    # 공유 응답은 장소·시각만 보이는 공개 투영(app/sharing.py public_plan)이라 비용·예산이 없다. 원본은 그대로다.
    assert shared['places'] and 'conditions' not in shared and '예산' not in json.dumps(shared, ensure_ascii=False)
    assert_unlimited(client.get('/api/plans/' + plan['id']).json())


def test_plan_job_accepts_the_flag(client):
    response = client.post('/api/plan-jobs', json=BASE | {'budget_unlimited': True})
    assert response.status_code in (200, 202), response.text
