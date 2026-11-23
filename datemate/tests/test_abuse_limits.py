"""한 브라우저·한 IP 가 다른 사용자에게 영향을 주는 경로의 제한 (docs/reviews/2026-11-24-full-review.md S1·S2·S3).

S1 장소 제보: 서로 다른 브라우저 3곳 이상이 30일 안에 제보해야 모든 사용자의 추천에서 감점·'제보 확인 필요'로 보인다.
   제보한 본인의 추천·코스에는 1건이어도 바로 반영된다.
S2 추천 작업: 전역 진행 6개에 더해 IP 범위(IPv4 주소·IPv6 /64)당 진행 중 작업 2개까지.
S3 다시 계산 경로: 미리보기·적용 경로를 비싼 경로 목록에 넣고, 합의 코스 미리보기는 추천 한도에도 센다.
"""
import copy
import threading
import time
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import naver_cache, quality, store, web_security
from app.catalog import places
from app.main import app
from app.models import Conditions
from app.planner import evaluate


def unique_ip():
    n = uuid.uuid4().int
    return f'198.51.{n % 250}.{(n >> 8) % 250 + 1}'


# --- S1. 장소 제보 -----------------------------------------------------------

@pytest.fixture
def no_reports():
    # 같은 실행의 다른 테스트가 남긴 제보(데모 장소 id 는 고정)가 집계에 섞이지 않게 비운다.
    with store.connect() as db:
        db.execute('DELETE FROM place_reports')
    yield
    with store.connect() as db:
        db.execute('DELETE FROM place_reports')


def owned(client):
    """데모 장소 두 곳으로 만든 이 브라우저의 코스(브라우저가 달라도 같은 장소가 든다)."""
    client.get('/api/places?mode=demo')
    rows = copy.deepcopy(places('demo')[:2])
    for p in rows:
        p.update(demo=False, hours=[0, 1440], closed_days=[], last_entry=None, breaks=None,
                 price=[1000, 1000], price_unit='person', stay=30)
    c = Conditions(mode='real', visit_date=date(2026, 10, 24), allow_estimates=True, count=2,
                   budget=200000, max_leg=180, end='23:00')
    plan, error = evaluate(rows, c)
    assert not error
    return store.save_plan(plan, store.owner_of(client.cookies['dm_session']))


def owner_of(client):
    return store.owner_of(client.cookies['dm_session'])


def add_report(owner, place_id, reason='closed', days_ago=0.0, resolved=0):
    with store.connect() as db:
        db.execute('INSERT INTO place_reports(id,owner,place_id,reason,note,created,resolved) VALUES(?,?,?,?,?,?,?)',
                   (uuid.uuid4().hex, owner, place_id, reason, '', time.time() - days_ago * 86400, resolved))


def shown_pending(client, plan, place_id):
    rows = client.get('/api/plans/' + plan['id']).json()['verification']['places']
    row = next(r for r in rows if r['id'] == place_id)
    assert row['pending'] == (row['label'] == '제보 확인 필요')
    return row['pending']


def ranked_pending(owner, place_id):
    """추천 후보(감점 -3 의 근거)에 붙는 report_pending."""
    with naver_cache.scope(owner):
        rows = quality.pool(Conditions(mode='demo', visit_date=date(2026, 10, 24)))
    return next(p['report_pending'] for p in rows if p['id'] == place_id)


@pytest.mark.usefixtures('no_reports')
def test_single_report_only_changes_the_reporters_own_view():
    with TestClient(app) as reporter, TestClient(app) as other:
        mine, theirs = owned(reporter), owned(other)
        target = mine['places'][0]['id']
        assert target in {p['id'] for p in theirs['places']}
        response = reporter.post(f"/api/plans/{mine['id']}/place-report", json=dict(place_id=target, reason='closed'))
        assert response.status_code == 200
        assert shown_pending(reporter, mine, target)
        assert ranked_pending(owner_of(reporter), target)
        # 다른 사용자의 코스·새 추천에는 제보 1건이 반영되지 않는다.
        assert not shown_pending(other, theirs, target)
        assert not ranked_pending(owner_of(other), target)


@pytest.mark.usefixtures('no_reports')
def test_three_distinct_browsers_flag_the_place_for_everyone():
    with TestClient(app) as viewer:
        plan = owned(viewer)
        target = plan['places'][0]['id']
        viewer_owner = owner_of(viewer)
        # 한 브라우저가 사유를 바꿔 여러 번 제보해도 1곳으로 센다.
        spammer = 'spammer-' + uuid.uuid4().hex
        for reason in ('closed', 'moved', 'hours'):
            add_report(spammer, target, reason)
        add_report('second-' + uuid.uuid4().hex, target)
        assert not shown_pending(viewer, plan, target)
        assert not ranked_pending(viewer_owner, target)
        add_report('third-' + uuid.uuid4().hex, target)
        assert shown_pending(viewer, plan, target)
        assert ranked_pending(viewer_owner, target)


@pytest.mark.usefixtures('no_reports')
def test_reports_expire_after_30_days_and_resolved_ones_do_not_count():
    with TestClient(app) as viewer:
        plan = owned(viewer)
        target = plan['places'][0]['id']
        viewer_owner = owner_of(viewer)
        for _ in range(3):
            add_report('old-' + uuid.uuid4().hex, target, days_ago=31)
        for _ in range(3):
            add_report('done-' + uuid.uuid4().hex, target, resolved=1)
        add_report(viewer_owner, target, days_ago=31)
        assert not shown_pending(viewer, plan, target)
        assert not ranked_pending(viewer_owner, target)
        # 29일 된 제보 3곳은 아직 유효하다.
        for _ in range(3):
            add_report('recent-' + uuid.uuid4().hex, target, days_ago=29)
        assert shown_pending(viewer, plan, target)


# --- S2. IP 범위당 진행 중 추천 작업 ---------------------------------------

def test_running_plan_jobs_are_limited_per_ip_range(monkeypatch):
    from app import plan_jobs
    monkeypatch.delenv('DATEMATE_IP_CONCURRENT_PLAN_JOBS', raising=False)
    release = threading.Event()
    started = []

    def hold(key, data, owner):
        started.append(key)
        release.wait(20)
        with plan_jobs._lock:
            if key in plan_jobs._jobs:
                plan_jobs._jobs[key].update(status='cancelled', finished=time.monotonic())

    monkeypatch.setattr(plan_jobs, '_run', hold)
    ip, other_ip = unique_ip(), unique_ip()
    clients = [TestClient(app, client=(ip, 1)) for _ in range(3)] + [TestClient(app, client=(other_ip, 1))]
    keys = []
    try:
        codes = []
        for i, client in enumerate(clients):
            response = client.post('/api/plan-jobs', json=dict(visit_date='2026-10-31', people=2 + i))
            codes.append(response.status_code)
            if response.status_code == 202:
                keys.append(response.json()['id'])
            else:
                detail = response.json()['detail']
        assert codes == [202, 202, 429, 202]
        assert '진행 중인 검색' in detail
    finally:
        release.set()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and any(plan_jobs._jobs.get(k, {}).get('status') == 'running' for k in keys):
            time.sleep(0.05)
        for client in clients:
            client.close()


# --- S3. 다시 계산하는 경로 ------------------------------------------------

@pytest.mark.parametrize('route', ['agreement-preview', 'meal-preview', 'delay-recovery', 'leisure-select', 'draft-apply'])
def test_recalculating_routes_are_expensive(route):
    path = f'POST /api/plans/{uuid.uuid4().hex}/{route}'
    assert any(pattern.match(path) for pattern in web_security.EXPENSIVE)


PAYLOAD = {'visit_date': '2026-10-24', 'max_leg': 180, 'budget': 1000000}


def agreed_plan(owner, partner):
    plan = owner.post('/api/plans', json=PAYLOAD).json()['plans'][0]
    first = plan['places'][0]['id']
    token = owner.post(f"/api/plans/{plan['id']}/shares").json()['url'].split('#', 1)[1]
    headers = {'Authorization': 'Bearer ' + token}
    assert partner.post('/api/shared-plan/vote', headers=headers, json={'choices': {first: 'yes'}}).status_code == 200
    assert owner.post(f"/api/plans/{plan['id']}/agreement", json={'choices': {first: 'yes'}}).status_code == 200
    return plan


@pytest.mark.usefixtures('same_rate_window')
def test_agreement_preview_counts_toward_the_recommendation_limit(monkeypatch):
    with TestClient(app, client=(unique_ip(), 1)) as owner, TestClient(app, client=(unique_ip(), 1)) as partner:
        monkeypatch.setenv('DATEMATE_USER_RECOMMENDATIONS_PER_MINUTE', '2')
        plan = agreed_plan(owner, partner)  # 새 추천 1회
        assert owner.post(f"/api/plans/{plan['id']}/agreement-preview", json={}).status_code == 200  # 2회
        response = owner.post(f"/api/plans/{plan['id']}/agreement-preview", json={})
        assert response.status_code == 429
        assert '검색 한도' in response.json()['detail']


@pytest.mark.usefixtures('same_rate_window')
def test_normal_preview_then_apply_fits_default_limits(monkeypatch):
    # 사용자 분당 추천 6회·IP 분당 12회·비싼 경로 분당 120회(기본값) 안에서 추천 → 미리보기(두 번) → 적용이 된다.
    for name in ('DATEMATE_USER_RECOMMENDATIONS_PER_MINUTE', 'DATEMATE_IP_RECOMMENDATIONS_PER_MINUTE',
                 'DATEMATE_IP_EXPENSIVE_REQUESTS_PER_MINUTE'):
        monkeypatch.delenv(name, raising=False)
    with TestClient(app, client=(unique_ip(), 1)) as owner, TestClient(app, client=(unique_ip(), 1)) as partner:
        plan = agreed_plan(owner, partner)
        first = owner.post(f"/api/plans/{plan['id']}/agreement-preview", json={})
        assert first.status_code == 200, first.text
        draft = owner.post(f"/api/plans/{plan['id']}/agreement-preview", json={'locked': [0]})
        assert draft.status_code == 200, draft.text
        applied = owner.post(f"/api/plans/{plan['id']}/draft-apply", json={'token': draft.json()['token']})
        assert applied.status_code == 200, applied.text


# --- S5. 내 데이터 삭제가 소유자 해시가 든 제한 키도 지운다 ---------------------

def test_deleting_my_data_removes_owner_rate_keys():
    with TestClient(app) as client:
        client.get('/api/status')
        owner = owner_of(client)
        prefixes = ('parking-rate:', 'replace-refresh:', 'transport-refresh:', 'reorder-refresh:')
        for prefix in prefixes:
            store.cache(prefix + owner, True, 60)
        assert client.delete('/api/me/data').status_code == 200
        with store.connect() as db:
            left = [r[0] for r in db.execute('SELECT key FROM cache WHERE key LIKE ?', ('%' + owner,))]
        assert left == []
