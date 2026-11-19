"""합의 코스 계산 도중·후에 상대 의견이 바뀌는 경우 (docs/product-priorities-deep-review.ko.md 1번).

재현 상황: 내가 '합의한 취향으로 다시 계산'을 누를 때 장소 A 의 반대는 0표다. 추천 계산이 도는 동안 상대가 A 를
'빼주세요'로 바꾼다. 예전에는 make_draft 가 계산이 끝난 뒤 의견을 다시 읽어 스냅샷을 만들었기 때문에, A 가 들어간
옛 계산 결과에 새 의견 스냅샷이 붙어 적용 검사가 변경을 놓쳤다.
변경 시점은 sleep 대신 추천 함수(app.planner.recommend)를 감싼 콜백 안에서 고정한다. 계산 입력을 읽은 뒤,
결과를 만들기 전에 의견을 바꾸므로 언제 실행해도 같은 순서다.
"""
import json
from fastapi.testclient import TestClient
from app.main import app
from app import store, experience
import app.planner as planner

PAYLOAD = {'visit_date': '2026-10-24', 'max_leg': 180, 'budget': 1000000}


def setup_pair(owner, guest):
    """만든 사람·공유받은 사람이 모두 의견을 저장한 코스. 첫 장소 A 는 두 사람 모두 '좋아요'라 계산에서 고정된다."""
    plan = owner.post('/api/plans', json=PAYLOAD).json()['plans'][0]
    ids = [p['id'] for p in plan['places']]
    votes = {pid: 'neutral' for pid in ids}
    votes[ids[0]] = 'yes'
    assert owner.post('/api/plans/' + plan['id'] + '/agreement', json=dict(choices=votes)).status_code == 200
    token = owner.post('/api/plans/' + plan['id'] + '/shares').json()['url'].split('#')[1]
    headers = {'Authorization': 'Bearer ' + token}
    assert guest.post('/api/shared-plan/vote', headers=headers, json=dict(choices=votes)).status_code == 200
    return plan, ids, votes, headers


def children(plan_id):
    with store.connect() as db:
        return db.execute('SELECT COUNT(*) FROM plans WHERE parent=?', (plan_id,)).fetchone()[0]


def guest_rejects_first_place(plan, ids, votes, guest):
    """공유받은 사람이 A 를 '빼주세요'로 바꾼다(HTTP 를 거치지 않고 같은 저장 함수로, 계산 도중에 부를 수 있게)."""
    row = store.get_plan(plan['id'])
    changed = dict(votes, **{ids[0]: 'no'})
    experience.save_votes(json.loads(row['payload']), store.owner_of(guest.cookies['dm_session']), row['owner'], changed)
    return changed


def test_vote_changed_during_calculation_is_not_applied_and_latest_votes_exclude_it(monkeypatch):
    with TestClient(app) as owner, TestClient(app) as guest:
        plan, ids, votes, _ = setup_pair(owner, guest)
        real = planner.recommend
        fired = []

        def recommend_then_vote_changes(conditions, *args, **kwargs):
            # 계산 입력(고정·제외 장소)은 이미 정해졌다. 이 시점에 상대 의견이 바뀐다.
            if not fired:
                fired.append(guest_rejects_first_place(plan, ids, votes, guest))
            return real(conditions, *args, **kwargs)

        monkeypatch.setattr(planner, 'recommend', recommend_then_vote_changes)
        draft = owner.post('/api/plans/' + plan['id'] + '/agreement-preview', json={}).json()
        assert fired, '콜백이 계산 도중에 불려야 한다'
        assert ids[0] in [p['id'] for p in draft['plan']['places']], '옛 의견(A 반대 0표)으로 계산했으므로 A 가 들어 있다'
        # 초안에는 계산에 실제로 쓴 집계(A 반대 0표)가 남아야 한다. 예전에는 여기서 반대 1표가 기록됐다.
        assert draft['vote_snapshot'][ids[0]]['no'] == 0

        response = owner.post('/api/plans/' + plan['id'] + '/draft-apply', json=dict(token=draft['token']))
        assert response.status_code == 409
        detail = response.json()['detail']
        assert detail['code'] == 'votes_changed'
        assert detail['changed'] == [dict(place_id=ids[0], name=plan['places'][0]['name'], change='좋아요 2→1 · 빼주세요 0→1')]
        assert children(plan['id']) == 0, '오래된 초안으로는 자식 일정이 생기지 않는다'

        monkeypatch.setattr(planner, 'recommend', real)
        fresh = owner.post('/api/plans/' + plan['id'] + '/agreement-preview', json={}).json()
        assert ids[0] not in [p['id'] for p in fresh['plan']['places']], '최신 의견으로 다시 계산하면 A 가 빠진다'
        applied = owner.post('/api/plans/' + plan['id'] + '/draft-apply', json=dict(token=fresh['token']))
        assert applied.status_code == 200, applied.text
        assert ids[0] not in [p['id'] for p in applied.json()['places']]
        assert children(plan['id']) == 1


def test_vote_changed_after_preview_is_rejected_without_saving():
    with TestClient(app) as owner, TestClient(app) as guest:
        plan, ids, votes, headers = setup_pair(owner, guest)
        draft = owner.post('/api/plans/' + plan['id'] + '/agreement-preview', json={}).json()
        assert draft['vote_snapshot'][ids[0]] == dict(yes=2, no=0, neutral=0, must=0)
        assert guest.post('/api/shared-plan/vote', headers=headers, json=dict(choices=dict(votes, **{ids[0]: 'no'}))).status_code == 200
        response = owner.post('/api/plans/' + plan['id'] + '/draft-apply', json=dict(token=draft['token']))
        assert response.status_code == 409 and response.json()['detail']['code'] == 'votes_changed'
        assert children(plan['id']) == 0


def test_unchanged_votes_apply_once_and_reapplying_the_same_draft_returns_the_same_child():
    with TestClient(app) as owner, TestClient(app) as guest:
        plan, ids, _, _ = setup_pair(owner, guest)
        draft = owner.post('/api/plans/' + plan['id'] + '/agreement-preview', json={}).json()
        assert draft['can_apply'] and ids[0] in [p['id'] for p in draft['plan']['places']]
        first = owner.post('/api/plans/' + plan['id'] + '/draft-apply', json=dict(token=draft['token']))
        assert first.status_code == 200, first.text
        again = owner.post('/api/plans/' + plan['id'] + '/draft-apply', json=dict(token=draft['token']))
        assert again.status_code == 200 and again.json()['id'] == first.json()['id']
        assert children(plan['id']) == 1
        assert first.json()['places'][0]['id'] == ids[0], '두 사람 모두 좋아요인 A 는 고정돼 그대로 남는다'


def test_lock_change_check_still_runs_before_the_vote_check():
    with TestClient(app) as owner, TestClient(app) as guest:
        plan, _, _, _ = setup_pair(owner, guest)
        draft = owner.post('/api/plans/' + plan['id'] + '/agreement-preview', json={}).json()
        owner.post('/api/plans/' + plan['id'] + '/locks', json=dict(locked=[1]))
        response = owner.post('/api/plans/' + plan['id'] + '/draft-apply', json=dict(token=draft['token']))
        assert response.status_code == 409 and '고정 장소' in response.json()['detail']
        assert children(plan['id']) == 0
