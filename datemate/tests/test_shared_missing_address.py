"""공유 화면: 주소가 없는 장소(주소 값이 None)에 'null' 이 보이던 것(2026-11-23 운영 확인에서 찾음).

저장된 장소의 address 키가 있는데 값이 None 이면 서버가 그대로 null 을 보내고, 화면이 '14:26 ~ 15:26 · null' 로 적었다.
서버는 빈 글로 보내고(app/sharing.py), 화면은 주소가 없으면 ' · 주소' 부분을 적지 않는다(static/shared.js).
"""
from fastapi.testclient import TestClient

from app.main import app
from test_festival_middle import planned
from test_festival_middle_ui import owner_plan
from test_functional_audit import audit_page  # noqa: F401  (브라우저 고정 장치)


def shared(client, plan):
    stored, _ = owner_plan(client, plan)
    token = client.post('/api/plans/' + stored['id'] + '/shares').json()['url']
    return stored, token


def without_address():
    plan = planned()
    plan['places'][0]['address'] = None
    return plan


def test_shared_plan_sends_an_empty_address_not_null():
    with TestClient(app) as client:
        _, token = shared(client, without_address())
        data = client.get('/api/shared-plan', headers={'Authorization': 'Bearer ' + token.split('#')[1]}).json()
        assert data['places'][0]['address'] == ''
        assert data['places'][1]['address']


def test_shared_screen_leaves_a_missing_address_out(audit_page):  # noqa: F811
    page, base, errors = audit_page
    with TestClient(app) as client:
        stored, token = shared(client, without_address())
    page.route('**/api/festivals?*', lambda route: route.fulfill(json=dict(status='available', festivals=[], message='')))
    page.goto(base + token)
    page.wait_for_function('document.querySelectorAll("#shared-places article").length===2')
    first, second = (page.locator('#shared-places article p').nth(i).inner_text() for i in (0, 1))
    t0, t1 = stored['timeline']
    assert first == f"{t0['arrival']} ~ {t0['departure']}"
    assert second == f"{t1['arrival']} ~ {t1['departure']} · {stored['places'][1]['address']}"
    assert 'null' not in page.locator('#shared-places').inner_text()
    assert not errors
