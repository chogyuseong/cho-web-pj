"""식사 추가로 지연을 이어 간 코스(delay_recovery.kept='meal')를 휴대폰 폭에서 연다:
안내에 '앞서 반영한 N분 지연은 그대로 뒀어요', 되돌리기 단추는 '지각 반영 되돌리기'가 아니라 '교체 되돌리기', 지각 확인은 이어 받은 지연 기준."""
from fastapi.testclient import TestClient

from app.main import app
from test_delay_kept_meal_consensus import NOTE, meal, recovered
from test_delay_recovery import pool  # noqa: F401  (후보 고정 장치)
from test_delay_recovery_ui import NO_OVERFLOW, open_saved
from test_functional_audit import audit_page, wait_for_selected_detail  # noqa: F401  (브라우저 고정 장치)


def test_meal_course_with_a_kept_delay_on_a_narrow_phone(audit_page, pool, monkeypatch):  # noqa: F811
    page, base, errors = audit_page
    with TestClient(app) as client:
        new = recovered(client)
        _, draft = meal(client, new, monkeypatch, after_index=0)
        applied = client.post(f"/api/plans/{new['id']}/draft-apply", json=dict(token=draft['token'])).json()
        owner = client.cookies['dm_session']
    assert applied['delay_recovery']['kept'] == 'meal'
    page.set_viewport_size({'width': 320, 'height': 700})
    open_saved(page, base, applied, owner)
    detail = page.locator('#plan-detail')
    assert NOTE in detail.inner_text()
    assert detail.locator('.undo-actions button').inner_text() == '교체 되돌리기'
    # 지각 확인 상자: 늦은 카페(이제 3번째 장소)를 고르면 이어 받은 40분이 든 도착 예정이 기준이다.
    box = detail.locator('details.delay-check')
    if not box.evaluate('d=>d.open'):
        box.locator('summary').click()
    box.locator('select').select_option('2')
    box.locator('input[type=number]').fill('0')
    box.get_by_role('button', name='확인').click()
    page.wait_for_function("document.querySelector('#plan-detail .delay-check-basis')", timeout=20000)
    assert '앞서 40분 늦음을 반영해 저장한 시각' in detail.locator('.delay-check-basis').inner_text()
    assert page.evaluate(NO_OVERFLOW)
    assert not errors
