"""점검 보고서(docs/reviews/2026-11-24-full-review.md) 낮음 S4·F9·F10 의 회귀 시험.

F9: '이동 N분'이 화면마다 달랐다 — 카드·지도(decision_summary)는 legs 만, 순서 제안은 행사장 구간(festival_visit.leg)까지 더했다.
    이제 한 함수(recommendation_summary.travel_minutes)로 같은 값을 쓴다.
"""
from app import option_diversity, order_suggestion
from app.recommendation_summary import enrich, travel_minutes
from app.planner import evaluate
from test_festival_add import base_conditions, base_plan, with_festival
from test_festival_middle import stops


def festival_course(hours, rows=None):
    c = base_conditions()
    plain = base_plan(c, rows)
    added = with_festival(c, hours)
    plan, error = evaluate(plain['places'], added)
    assert not error, error
    enrich(plan)
    return plan


def test_middle_festival_travel_includes_the_venue_leg_everywhere():
    plan = festival_course('11:30~13:00', stops(2, stay=90))
    assert plan['festival_visit']['position'] == 'middle'
    venue_leg = plan['festival_visit']['leg']['minutes']
    legs = sum(leg['minutes'] for leg in plan['legs'])
    assert venue_leg > 0
    # 카드·지도(decision_summary)와 순서 제안·코스 비교가 같은 합계 — 행사장까지 가는 구간을 넣는다.
    assert plan['decision_summary']['travel_minutes'] == legs + venue_leg
    assert order_suggestion.travel_minutes(plan) == plan['decision_summary']['travel_minutes']
    assert option_diversity.travel_minutes(plan) == plan['decision_summary']['travel_minutes']
    assert f"이동 약 {legs + venue_leg}분" in plan['decision_summary']['reason']


def test_course_without_a_festival_keeps_the_legs_sum():
    plan = base_plan()
    enrich(plan)
    assert 'festival_visit' not in plan or not (plan.get('festival_visit') or {}).get('leg')
    assert travel_minutes(plan) == sum(leg['minutes'] for leg in plan['legs']) == plan['decision_summary']['travel_minutes']


# --- S4: 상대방 자리를 엉뚱한 브라우저가 차지하면 만든 브라우저가 비울 수 있다 ---
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

PAYLOAD = {'visit_date': '2026-10-24', 'max_leg': 180, 'budget': 1000000}


def _share(owner, plan):
    token = owner.post('/api/plans/' + plan['id'] + '/shares').json()['url'].split('#')[1]
    return {'Authorization': 'Bearer ' + token}


def test_owner_can_free_the_partner_seat_and_the_real_partner_can_vote():
    with TestClient(app) as owner, TestClient(app) as stranger, TestClient(app) as partner:
        plan = owner.post('/api/plans', json=PAYLOAD).json()['plans'][0]
        ids = [p['id'] for p in plan['places']]
        assert owner.post('/api/plans/' + plan['id'] + '/agreement', json=dict(choices={ids[0]: 'yes'})).status_code == 200
        headers = _share(owner, plan)
        assert stranger.post('/api/shared-plan/vote', headers=headers, json=dict(choices={ids[0]: 'no'})).status_code == 200
        # 진짜 상대는 막힌다(두 브라우저까지). 공유를 취소하고 새 링크를 만들어도 그대로였다 — 취소는 남은 의견 수를 알려 준다.
        assert partner.post('/api/shared-plan/vote', headers=headers, json=dict(choices={ids[0]: 'yes'})).status_code >= 400
        revoked = owner.delete('/api/plans/' + plan['id'] + '/shares').json()
        assert revoked == {'revoked': True, 'opinions': 1}
        headers = _share(owner, plan)
        assert partner.post('/api/shared-plan/vote', headers=headers, json=dict(choices={ids[0]: 'yes'})).status_code >= 400
        # 상대방 브라우저는 지울 수 없다(만든 브라우저의 코스만 연다 — 404).
        assert stranger.delete('/api/plans/' + plan['id'] + '/agreement/partner').status_code == 404
        cleared = owner.delete('/api/plans/' + plan['id'] + '/agreement/partner')
        assert cleared.status_code == 200
        body = cleared.json()
        assert body['participants'] == 1 and body['mine'] == {ids[0]: 'yes'} and body['places'][ids[0]]['no'] == 0
        assert partner.post('/api/shared-plan/vote', headers=headers, json=dict(choices={ids[0]: 'yes'})).status_code == 200
        status = owner.get('/api/plans/' + plan['id'] + '/agreement').json()
        assert status['participants'] == 2 and status['places'][ids[0]]['yes'] == 2
