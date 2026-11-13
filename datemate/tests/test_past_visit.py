"""새 추천 요청의 지난 날짜·시각 검사(한국 시각). 만든 코스에 대한 요청은 막지 않는다."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Conditions
from app.service_time import past_visit_message, planning_now
from test_functional_audit import audit_page  # noqa: F401
from test_leg_modes import owned


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def at(monkeypatch, moment):
    monkeypatch.setenv('DATEMATE_PLANNING_NOW', moment)


def check(**fields):
    return past_visit_message(Conditions(**(dict(visit_date=date(2026, 11, 13)) | fields)))


def test_planning_clock_reads_seoul_time(monkeypatch):
    at(monkeypatch, '2026-11-13T23:30')
    assert planning_now().isoformat() == '2026-11-13T23:30:00+09:00'
    # UTC 로 준 시각도 한국 날짜로 바꿔 읽는다(UTC 11-13 16:00 = 한국 11-14 01:00).
    at(monkeypatch, '2026-11-13T16:00+00:00')
    assert planning_now().date() == date(2026, 11, 14)
    monkeypatch.delenv('DATEMATE_PLANNING_NOW')
    assert planning_now().utcoffset().total_seconds() == 9 * 3600


def test_past_day_and_finished_today_are_rejected_but_started_today_is_not(monkeypatch):
    at(monkeypatch, '2026-11-13T15:00')
    assert check(visit_date=date(2026, 11, 12)) == '방문 날짜(2026-11-12)가 이미 지났어요. 오늘(2026-11-13) 이후 날짜를 골라 주세요.'
    assert check(start='11:00', end='14:59') == '오늘은 종료 시각 14:59이 이미 지났어요. 종료 시각을 늦추거나 다른 날짜를 골라 주세요.'
    assert check(start='11:00', end='15:00') is not None
    # 시작 시각만 지난 경우는 막지 않는다.
    assert check(start='11:00', end='19:00') is None
    assert check(visit_date=date(2026, 11, 14), start='09:00', end='10:00') is None


def test_new_recommendations_return_korean_422(client, monkeypatch):
    at(monkeypatch, '2026-11-13T20:00')
    for path in ('/api/plans', '/api/plan-jobs'):
        response = client.post(path, json={'visit_date': '2026-10-24'})
        assert response.status_code == 422, path
        assert response.json() == {'detail': '방문 날짜(2026-10-24)가 이미 지났어요. 오늘(2026-11-13) 이후 날짜를 골라 주세요.'}
        response = client.post(path, json={'visit_date': '2026-11-13', 'start': '11:00', 'end': '19:00'})
        assert response.status_code == 422 and '종료 시각 19:00' in response.json()['detail'], path


def test_existing_plans_stay_usable_after_their_day(client, monkeypatch):
    plan = owned(client)  # 방문일 2026-10-24
    at(monkeypatch, '2026-11-13T20:00')
    assert client.get('/api/plans/' + plan['id']).status_code == 200
    changed = client.post(f"/api/plans/{plan['id']}/transport", json={'legs': [{'index': 1, 'mode': 'car'}]})
    assert changed.status_code == 200, changed.text
    options = client.post(f"/api/plans/{plan['id']}/alternatives", json={'index': 1, 'locked': []})
    assert options.status_code == 200, options.text
    assert client.post(f"/api/plans/{plan['id']}/shares", json={}).status_code == 200


def test_screen_shows_the_server_notice_for_a_past_day(audit_page, monkeypatch):
    page, base, errors = audit_page
    at(monkeypatch, '2026-11-13T20:00')
    page.evaluate("form.elements.mode.value='demo';form.elements.mode.dispatchEvent(new Event('change',{bubbles:true}));form.elements.visit_date.value='2026-10-24'")
    page.locator('#submit-plan').click()
    page.wait_for_function("document.querySelector('#progress').textContent.includes('이미 지났어요')")
    progress = page.locator('#progress').inner_text()
    assert '검색을 완료하지 못했어요' in progress
    assert '방문 날짜(2026-10-24)가 이미 지났어요. 오늘(2026-11-13) 이후 날짜를 골라 주세요.' in progress
