"""지각을 반영해 고친 코스(delay_recovery)에서 식사 추가·합의 코스를 해도 지연이 말없이 사라지지 않는다
(docs/superpowers/specs/2026-11-23-delay-kept-meal-consensus-design.md).
- 식사 추가: 지연을 적어 둔 장소 번호를 식당을 끼운 만큼 옮겨 이어 간다(같은 자리 교체는 그대로).
- 합의 코스: 지연 장소가 새 코스에 있으면 그 번호로 옮겨 이어 가고, 없으면 버리고 알린다."""
import copy

from fastapi.testclient import TestClient

from app import experience, planner, store
from app.condition_audit import audit_plan
from app.main import app
from app.models import Conditions
from app.planner import evaluate, minutes
from test_delay_recovery import NEAR, course, hm, place, pool, recover, saved  # noqa: F401  (pool: 후보 고정 장치)
from test_experience import food_fixture

NOTE = '앞서 반영한 40분 지연은 그대로 뒀어요'


def recovered(client):
    """A 전시 → (B 카페 대신) 가까운 늦은 카페 → C 산책. 2번째 장소(번호 1)부터 40분 늦음을 반영한 코스."""
    stored = saved(client, course())
    response = recover(client, stored, index=1, minutes=40, target=1, replacement_id=NEAR['id'])
    assert response.status_code == 200, response.text
    new = response.json()
    assert new['delay_recovery']['delays'] == {'1': 40} and new['places'][1]['id'] == NEAR['id']
    return new


def plain(plan):
    """같은 장소·같은 조건을 지연 없이 계산한 시간표."""
    result, error = evaluate(plan['places'], Conditions.model_validate(plan['conditions']), soft=True)
    assert not error, error
    return result


def meal(client, plan, monkeypatch, **where):
    food = food_fixture(monkeypatch, plan)
    body = dict(restaurant_id=food['id'], locked=[])
    body.update(where)
    response = client.post(f"/api/plans/{plan['id']}/meal-preview", json=body)
    assert response.status_code == 200, response.text
    return food, response.json()


# --- 식사 추가 ---
def test_meal_before_the_late_place_moves_the_delay_with_it(pool, monkeypatch):
    with TestClient(app) as client:
        new = recovered(client)
        food, draft = meal(client, new, monkeypatch, after_index=0)
        proposed = draft['plan']
        # 식당이 번호 1 자리에 들어가 늦은 카페는 번호 2 — 지연도 따라간다.
        assert [p['id'] for p in proposed['places']] == [new['places'][0]['id'], food['id'], NEAR['id'], new['places'][2]['id']]
        assert proposed['delay_recovery']['delays'] == {'2': 40} and proposed['delay_recovery']['kept'] == 'meal'
        base = plain(proposed)
        assert minutes(proposed['timeline'][2]['arrival']) == minutes(base['timeline'][2]['arrival']) + 40
        # 식당(늦은 장소 앞)은 제시각.
        assert proposed['timeline'][1] == base['timeline'][1]
        assert NOTE in draft['summary']
        applied = client.post(f"/api/plans/{new['id']}/draft-apply", json=dict(token=draft['token'])).json()
        assert applied['delay_recovery']['delays'] == {'2': 40} and NOTE in applied['change_reason']
        # 지각 확인은 늦은 카페(이제 번호 2)에서 이어서 본다.
        again = client.get(f"/api/plans/{applied['id']}/delay-check", params=dict(index=2, minutes=0)).json()
        assert again['carried'] == 40 and again['planned_arrival'] == applied['timeline'][2]['arrival']
        assert client.post(f"/api/plans/{applied['id']}/undo", json={}).json()['id'] == new['id']


def test_meal_after_the_late_place_keeps_the_number(pool, monkeypatch):
    with TestClient(app) as client:
        new = recovered(client)
        _, draft = meal(client, new, monkeypatch, after_index=2)
        proposed = draft['plan']
        assert proposed['delay_recovery']['delays'] == {'1': 40}
        assert proposed['timeline'][:3] == new['timeline'][:3]
        assert NOTE in draft['summary']


def test_meal_replacing_the_late_place_keeps_the_delay_in_that_slot(pool, monkeypatch):
    # 같은 자리 교체는 번호가 그대로다(81차 장소 바꾸기가 늦은 장소를 바꿔도 지연을 그 자리에 두는 것과 같다).
    with TestClient(app) as client:
        new = recovered(client)
        food, draft = meal(client, new, monkeypatch, replace_index=1)
        proposed = draft['plan']
        assert proposed['places'][1]['id'] == food['id']
        assert proposed['delay_recovery']['delays'] == {'1': 40}
        assert minutes(proposed['timeline'][1]['arrival']) == minutes(plain(proposed)['timeline'][1]['arrival']) + 40


def test_meal_without_a_delay_record_is_unchanged(monkeypatch):
    with TestClient(app) as client:
        stored = saved(client, course())
        _, draft = meal(client, stored, monkeypatch, after_index=2)
        assert 'delay_recovery' not in draft['plan'] and '지연' not in draft['summary']


# --- 합의 코스 ---
EARLY_WALK = place('w3', '일찍 닫는 산책길', '산책·풍경', [0, hm('17:50')], 45, dlat=0.003)
OTHER_SEE = place('g2', '다른 전시', '문화·예술', [hm('10:00'), hm('21:00')], 60, dlat=0.0012)


def agree(client, guest, plan, monkeypatch, *orders):
    """두 브라우저가 모두 '상관없어요'로 의견을 저장하고, 합의 계산(planner.recommend)은 orders 순서의 코스를 낸다."""
    rows = {p['id']: p for p in plan['places'] + [EARLY_WALK, OTHER_SEE]}

    def fake(c):
        out = []
        for order in orders:
            result, error = evaluate([copy.deepcopy(rows[i]) for i in order], c, soft=True)
            assert not error, error
            out.append(audit_plan(result))
        return dict(plans=out)

    monkeypatch.setattr(planner, 'recommend', fake)
    votes = {p['id']: 'neutral' for p in plan['places']}
    assert client.post(f"/api/plans/{plan['id']}/agreement", json=dict(choices=votes)).status_code == 200
    token = client.post(f"/api/plans/{plan['id']}/shares").json()['url'].split('#')[1]
    assert guest.post('/api/shared-plan/vote', headers={'Authorization': 'Bearer ' + token}, json=dict(choices=votes)).status_code == 200
    return client.post(f"/api/plans/{plan['id']}/agreement-preview", json={})


def test_agreement_keeps_the_delay_on_the_place_that_stays(pool, monkeypatch):
    with TestClient(app) as client, TestClient(app) as guest:
        new = recovered(client)
        a, late, c = (p['id'] for p in new['places'])
        response = agree(client, guest, new, monkeypatch, [a, c, late])
        assert response.status_code == 200, response.text
        draft = response.json()
        proposed = draft['plan']
        # 늦은 카페가 번호 2 로 옮겨졌다 — 지연도 따라간다.
        assert [p['id'] for p in proposed['places']] == [a, c, late]
        assert proposed['delay_recovery']['delays'] == {'2': 40} and proposed['delay_recovery']['kept'] == 'agreement'
        assert minutes(proposed['timeline'][2]['arrival']) == minutes(plain(proposed)['timeline'][2]['arrival']) + 40
        assert NOTE in draft['summary']
        applied = client.post(f"/api/plans/{new['id']}/draft-apply", json=dict(token=draft['token'])).json()
        assert applied['delay_recovery']['delays'] == {'2': 40} and NOTE in applied['change_reason']
        assert client.post(f"/api/plans/{applied['id']}/undo", json={}).json()['id'] == new['id']


def test_agreement_without_the_late_place_drops_the_delay_and_says_so(pool, monkeypatch):
    with TestClient(app) as client, TestClient(app) as guest:
        new = recovered(client)
        a, _, c = (p['id'] for p in new['places'])
        response = agree(client, guest, new, monkeypatch, [a, OTHER_SEE['id'], c])
        assert response.status_code == 200, response.text
        draft = response.json()
        assert 'delay_recovery' not in draft['plan']
        assert '앞서 반영한 40분 지연은 가까운 늦은 카페가 합의 코스에서 빠져 넣지 않았어요' in draft['summary']
        assert '지각 확인을 다시' in draft['summary']


def test_agreement_skips_a_course_that_does_not_fit_with_the_delay(pool, monkeypatch):
    # 지연을 넣으면 일찍 닫는 산책길에 늦는 첫 후보는 건너뛰고, 맞는 다음 후보를 쓴다(늦지 않은 시간표를 대신 내지 않는다).
    with TestClient(app) as client, TestClient(app) as guest:
        new = recovered(client)
        a, late, c = (p['id'] for p in new['places'])
        response = agree(client, guest, new, monkeypatch, [a, late, EARLY_WALK['id']], [a, late, c])
        assert response.status_code == 200, response.text
        proposed = response.json()['plan']
        assert [p['id'] for p in proposed['places']] == [a, late, c]
        assert proposed['delay_recovery']['delays'] == {'1': 40}


def test_agreement_refuses_when_no_course_fits_with_the_delay(pool, monkeypatch):
    with TestClient(app) as client, TestClient(app) as guest:
        new = recovered(client)
        a, late, _ = (p['id'] for p in new['places'])
        response = agree(client, guest, new, monkeypatch, [a, late, EARLY_WALK['id']])
        assert response.status_code == 409
        assert '앞서 반영한 40분 지연을 넣으면' in response.json()['detail']


def test_agreement_without_a_delay_record_is_unchanged(monkeypatch):
    with TestClient(app) as client, TestClient(app) as guest:
        stored = saved(client, course())
        a, b, c = (p['id'] for p in stored['places'])
        draft = agree(client, guest, stored, monkeypatch, [a, b, EARLY_WALK['id']]).json()
        assert 'delay_recovery' not in draft['plan'] and '지연' not in draft['summary']
