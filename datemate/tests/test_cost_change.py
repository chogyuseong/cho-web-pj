"""수단·장소를 바꾼 뒤의 비용 표기: 바꾸기 전·후 예상 비용 범위를 나란히 보여 주고, 범위끼리의 차이는 내지 않는다."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from test_functional_audit import audit_page, generate  # noqa: F401
from test_leg_modes import owned


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_changes_carry_the_cost_range_before_the_change(client):
    plan = owned(client)
    saved = client.post(f"/api/plans/{plan['id']}/transport", json={'legs': [{'index': 1, 'mode': 'car'}]}).json()
    assert saved['delta']['total_before'] == plan['total']
    options = client.post(f"/api/plans/{plan['id']}/alternatives", json={'index': 1, 'locked': []}).json()['alternatives']
    assert options and all(o['delta']['total_before'] == plan['total'] for o in options)
    replaced = client.post(f"/api/plans/{plan['id']}/replace",
                           json={'index': 1, 'locked': [], 'replacement_id': options[0]['places'][1]['id']}).json()
    assert replaced['delta']['total_before'] == plan['total']


CASES = [
    ([23000, 43000], [27000, 47000], '예상 비용 23,000원 ~ 43,000원 → 27,000원 ~ 47,000원 · 약 4,000원 늘어요'),
    ([23000, 43000], [20000, 40000], '예상 비용 23,000원 ~ 43,000원 → 20,000원 ~ 40,000원 · 약 3,000원 줄어요'),
    ([23000, 43000], [23000, 43000], '비용은 그대로예요 · 예상 비용 23,000원 ~ 43,000원'),
    ([23000, 43000], [27000, 39027], '예상 비용 23,000원 ~ 43,000원 → 27,000원 ~ 39,027원'),
    ([5000, 5000], [9000, 9000], '예상 비용 5,000원 → 9,000원 · 약 4,000원 늘어요'),
    (None, [9000, 9000], '예상 비용 9,000원'),
]


def test_cost_change_text_and_detail_after_a_transport_change(audit_page):
    page, base, errors = audit_page
    for before, after, text in CASES:
        assert page.evaluate('([b,a])=>costChangeText(b,a)', [before, after]) == text
    # 예전에 저장한 코스(total_before 없음)는 범위끼리의 차이에서 바꾸기 전 범위를 되짚는다.
    legacy = {'parent': 'x', 'total': [27000, 47000], 'delta': {'cost': [27000 - 43000, 47000 - 23000]}}
    assert page.evaluate('p=>totalBefore(p)', legacy) == [23000, 43000]
    generate(page)
    original = page.evaluate('selected.id')
    page.locator('#plan-detail .route-mode-toggle').first.click()
    page.locator('#transport-chooser-0').get_by_role('button', name='자동차', exact=True).click()
    page.wait_for_function('(id)=>selected.id!==id', arg=original)
    notice = page.locator('#plan-detail .detail > .warning').first.inner_text()
    assert '비용 변화' not in notice
    expected = page.evaluate('costChangeText(selected.delta.total_before, selected.total)')
    assert expected in notice and ('예상 비용' in notice or '비용은 그대로예요' in notice)
