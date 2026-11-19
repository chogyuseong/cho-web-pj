"""함께 결정: 무응답과 '상관없어요'(28), 저장 후 수정 상태(34), 공유본 버전(31), 공유 만료 시각(32)."""
import json

from fastapi.testclient import TestClient

from app import store
from app.main import app
from test_experience import food_fixture, owned
from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401 (fixture)

PAYLOAD = {'visit_date': '2026-10-24', 'max_leg': 180, 'budget': 1000000}


def share(owner, plan_id):
    token = owner.post('/api/plans/' + plan_id + '/shares').json()['url'].split('#')[1]
    return {'Authorization': 'Bearer ' + token}


def test_partial_answers_stay_unanswered_and_empty_save_is_refused():
    with TestClient(app) as owner, TestClient(app) as guest:
        plan = owner.post('/api/plans', json=PAYLOAD).json()['plans'][0]
        ids = [p['id'] for p in plan['places']]
        headers = share(owner, plan['id'])
        # 아무것도 고르지 않은 저장은 막는다.
        empty = guest.post('/api/shared-plan/vote', headers=headers, json=dict(choices={}))
        assert empty.status_code == 409 and '한 곳 이상' in empty.json()['detail']
        # 한 곳만 답하면 그 곳만 저장되고 나머지는 '상관없어요'로 세지 않는다.
        assert guest.post('/api/shared-plan/vote', headers=headers, json=dict(choices={ids[0]: 'no'})).status_code == 200
        assert owner.post('/api/plans/' + plan['id'] + '/agreement', json=dict(choices={p: 'neutral' for p in ids})).status_code == 200
        status = owner.get('/api/plans/' + plan['id'] + '/agreement').json()
        assert status['places'][ids[0]] == dict(yes=0, no=1, neutral=1, must=0)
        assert status['places'][ids[1]] == dict(yes=0, no=0, neutral=1, must=0), '상대가 답하지 않은 곳은 중립으로 세지 않는다'
        assert status['answered'] == dict(mine=len(ids), others=[1]) and status['place_count'] == len(ids)
        assert guest.get('/api/shared-plan', headers=headers).json()['my_choices'] == {ids[0]: 'no'}
        # 이 코스에 없는 장소는 받지 않는다.
        assert guest.post('/api/shared-plan/vote', headers=headers, json=dict(choices={'demo:nope': 'yes'})).status_code in (409, 422)
        # 한 사람이 일부만 답해도 합의 계산은 된다(빼주세요가 반영된다).
        draft = owner.post('/api/plans/' + plan['id'] + '/agreement-preview', json={})
        assert draft.status_code == 200, draft.text
        assert ids[0] not in [p['id'] for p in draft.json()['plan']['places']]


def test_old_full_answers_are_kept_as_they_were():
    with TestClient(app) as owner:
        plan = owner.post('/api/plans', json=PAYLOAD).json()['plans'][0]
        ids = [p['id'] for p in plan['places']]
        # 예전 화면은 모든 장소를 채워 보냈다(기본값 neutral). 그 값은 다시 분류하지 않는다.
        assert owner.post('/api/plans/' + plan['id'] + '/agreement', json=dict(choices={p: 'neutral' for p in ids})).status_code == 200
        status = owner.get('/api/plans/' + plan['id'] + '/agreement').json()
        assert all(status['places'][p]['neutral'] == 1 for p in ids) and status['answered']['mine'] == len(ids)


def test_share_status_names_links_still_open_on_the_version_before(monkeypatch):
    with TestClient(app) as owner, TestClient(app) as other:
        plan = owned(owner)
        food = food_fixture(monkeypatch, plan)
        share(owner, plan['id'])
        draft = owner.post('/api/plans/' + plan['id'] + '/meal-preview', json=dict(restaurant_id=food['id'], after_index=1)).json()
        child = owner.post('/api/plans/' + plan['id'] + '/draft-apply', json=dict(token=draft['token'])).json()
        status = owner.get('/api/plans/' + child['id'] + '/shares').json()
        assert status['current'] == dict(plan_id=child['id'], active=0, expires=None)
        assert [row['plan_id'] for row in status['earlier']] == [plan['id']] and status['earlier'][0]['active'] == 1
        assert 'token' not in json.dumps(status) and other.get('/api/plans/' + child['id'] + '/shares').status_code == 404
        owner.delete('/api/plans/' + plan['id'] + '/shares')
        assert owner.get('/api/plans/' + child['id'] + '/shares').json()['earlier'] == []


def test_shared_page_marks_unsent_changes_and_owner_sees_expiry(audit_page):
    page, base, _ = audit_page
    generate(page)
    wait_for_selected_detail(page)
    # 만료 시각 문구: 약속 날이 만료 뒤면 경고한다(브라우저 시간대 기준).
    texts = page.evaluate("""()=>[shareExpiryText(Date.UTC(2026,10,20,5,0)/1000,'2026-11-20'), shareExpiryText(Date.UTC(2026,10,20,5,0)/1000,'2026-11-23')]""")
    assert '까지 열려요' in texts[0] and '만료돼요' not in texts[0]
    assert '약속 날' in texts[1] and '만료돼요' in texts[1]
    page.evaluate("Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{window.copiedShare=text;}}})")
    page.get_by_role('button', name='공유 링크 복사', exact=True).click()
    page.wait_for_function('!!window.copiedShare')
    page.wait_for_function("document.querySelector('#plan-detail .share-status')?.textContent.includes('이 코스의 공유 링크 1개')", timeout=15000)
    token = page.evaluate('window.copiedShare').split('/shared#')[1]
    guest = page.context.browser.new_context(viewport={'width': 390, 'height': 844}, bypass_csp=True)
    try:
        shared = guest.new_page()
        shared.goto(base + '/shared#' + token)
        shared.wait_for_function("!document.getElementById('shared-form').hidden", timeout=30000)
        selects = shared.locator('#shared-places select')
        assert all(v == '' for v in selects.evaluate_all('els=>els.map(e=>e.value)')), '기본은 아직 안 정함'
        dirty = shared.locator('.shared-dirty')
        assert '아직 전달한 의견이 없어요' in dirty.inner_text()
        shared.get_by_role('button', name='내 의견 전달하기').click()
        assert '한 곳 이상' in shared.locator('#shared-status').inner_text()
        selects.first.select_option('yes')
        assert '아직 전달하지 않은 곳이 1곳' in dirty.inner_text()
        shared.get_by_role('button', name='내 의견 전달하기').click()
        shared.wait_for_function("document.querySelector('.shared-dirty').textContent.includes('같아요')", timeout=15000)
        selects.nth(1).select_option('no')
        assert '아직 전달하지 않은 곳이 1곳' in dirty.inner_text(), '저장 뒤 다시 바꾸면 전달되지 않았다고 알린다'
        assert shared.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth')
    finally:
        guest.close()
