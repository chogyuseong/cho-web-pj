"""피드백 탭: 작성 API, 요청 제한, 미끼 칸, 끄는 스위치, 관리자 열람, 마이그레이션."""
import sqlite3
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app import maintenance, store, user_feedback
from app.config import ROOT
from app.main import app
from app.migrations import MIGRATIONS, upgrade, v0004_user_feedback

FAKE_KEY = 'test-only-' + uuid.uuid4().hex


def unique_ip():
    n = uuid.uuid4().int
    return f'198.18.{n % 250}.{(n >> 8) % 250 + 1}'


def client():
    return TestClient(app, client=(unique_ip(), 1))


def body(**fields):
    return dict(dict(message='결과 화면에서 지도 버튼을 찾기 어려웠어요.', screen='results',
                     contact='me@example.com', viewport_width=390), **fields)


def rows():
    with store.connect() as db:
        return [dict(r) for r in db.execute('SELECT * FROM feedback_entries ORDER BY created')]


def find(message):
    return [r for r in rows() if r['message'] == message]


def auth(key=FAKE_KEY):
    return {'Authorization': 'Bearer ' + key}


@pytest.fixture
def admin(monkeypatch):
    monkeypatch.setenv('FEEDBACK_ADMIN_KEY', FAKE_KEY)


# --- 작성 -------------------------------------------------------------------

def test_feedback_is_stored_trimmed_and_without_ip():
    text = '  지도 버튼이\r\n잘 안 보여요\x00\x07‮  '
    with client() as c:
        response = c.post('/api/feedback', json=body(message=text, contact='  a@b.c \n '),
                          headers={'User-Agent': 'Mozilla/5.0 (iPhone) Mobile Safari/604.1'})
    assert response.status_code == 200
    assert response.json()['received'] is True
    [row] = find('지도 버튼이\n잘 안 보여요')
    assert row['contact'] == 'a@b.c'
    assert row['screen'] == 'results' and row['viewport_width'] == 390
    assert row['browser'] == 'Safari · 모바일'
    assert row['handled'] == 0
    assert set(row) == {'id', 'created', 'message', 'screen', 'contact', 'viewport_width', 'browser', 'handled'}


@pytest.mark.parametrize('fields', [
    dict(message='짧아'),
    dict(message='   가나   '),
    dict(message='\x00\x01\x02\x03\x04\x05가'),
    dict(message='가' * 1001),
    dict(contact='a' * 101),
    dict(screen='settings'),
    dict(viewport_width=0),
    dict(session='abc'),
])
def test_invalid_feedback_is_rejected(fields):
    with client() as c:
        assert c.post('/api/feedback', json=body(**fields)).status_code == 422


def test_length_limits_count_cleaned_text():
    with client() as c:
        assert c.post('/api/feedback', json=body(message='  ' + '나' * 1000 + '  ')).status_code == 200
        assert c.post('/api/feedback', json=body(message='다섯글자요')).status_code == 200


def test_script_text_is_stored_as_plain_text():
    text = '<script>alert(1)</script><img src=x onerror=alert(2)> ' + uuid.uuid4().hex
    with client() as c:
        assert c.post('/api/feedback', json=body(message=text)).status_code == 200
    assert len(find(text)) == 1


def test_ip_rate_limit_ten_minutes(monkeypatch):
    with client() as c:
        for _ in range(3):
            assert c.post('/api/feedback', json=body()).status_code == 200
        blocked = c.post('/api/feedback', json=body())
    assert blocked.status_code == 429
    assert '잠시 후' in blocked.json()['detail']
    with client() as other:
        assert other.post('/api/feedback', json=body()).status_code == 200


def test_ip_rate_limit_per_day(monkeypatch):
    monkeypatch.setenv('DATEMATE_IP_FEEDBACK_PER_10_MINUTES', '100')
    monkeypatch.setenv('DATEMATE_IP_FEEDBACK_PER_DAY', '2')
    with client() as c:
        assert [c.post('/api/feedback', json=body()).status_code for _ in range(3)] == [200, 200, 429]


def test_validation_errors_do_not_use_the_budget(monkeypatch):
    monkeypatch.setenv('DATEMATE_IP_FEEDBACK_PER_10_MINUTES', '1')
    with client() as c:
        for _ in range(3):
            assert c.post('/api/feedback', json=body(message='짧')).status_code == 422
        assert c.post('/api/feedback', json=body()).status_code == 200


def test_honeypot_looks_successful_but_stores_nothing():
    text = '미끼 칸 확인 ' + uuid.uuid4().hex
    with client() as c:
        response = c.post('/api/feedback', json=body(message=text, website='http://spam.example'))
    assert response.status_code == 200 and response.json()['received'] is True
    assert find(text) == []


def test_switch_off_hides_tab_page_and_write_api(monkeypatch, admin):
    with client() as c:
        assert user_feedback.NAV_LINK in c.get('/').text
        assert c.get('/feedback').status_code == 200
    monkeypatch.setenv('DATEMATE_FEEDBACK_ENABLED', '0')
    with client() as c:
        assert user_feedback.NAV_LINK not in c.get('/').text
        assert c.get('/feedback').status_code == 404
        assert c.post('/api/feedback', json=body()).status_code == 404
        # 관리자 열람은 꺼도 남는다.
        assert c.get('/feedback/admin').status_code == 200
        assert c.get('/api/feedback/admin/entries', headers=auth()).status_code == 200


def test_home_menu_link_matches_the_switch_marker():
    assert user_feedback.NAV_LINK in (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')


# --- 관리자 ------------------------------------------------------------------

UNKNOWN = {'detail': 'Not Found'}


def test_admin_routes_are_404_without_a_configured_key(monkeypatch):
    monkeypatch.delenv('FEEDBACK_ADMIN_KEY', raising=False)
    with client() as c:
        assert c.get('/feedback/admin').status_code == 404
        response = c.get('/api/feedback/admin/entries', headers=auth())
        assert response.status_code == 404 and response.json() == UNKNOWN
        assert c.get('/api/feedback/admin/entries', headers=auth('')).status_code == 404
    monkeypatch.setenv('FEEDBACK_ADMIN_KEY', '   ')
    with client() as c:
        assert c.get('/feedback/admin').status_code == 404
        assert c.get('/api/feedback/admin/entries', headers=auth('   ')).status_code == 404


def test_wrong_or_missing_key_is_404_like_an_unknown_path(admin):
    with client() as c:
        unknown = c.get('/api/feedback/admin/nothing-here')
        for headers in ({}, auth('wrong'), auth(FAKE_KEY + 'x'), {'Authorization': FAKE_KEY}):
            response = c.get('/api/feedback/admin/entries', headers=headers)
            assert response.status_code == 404
            assert response.json() == unknown.json() == UNKNOWN
        assert c.patch('/api/feedback/admin/entries/' + 'a' * 32, json={'handled': True},
                       headers=auth('wrong')).status_code == 404
        assert c.delete('/api/feedback/admin/entries/' + 'a' * 32, headers=auth('wrong')).status_code == 404


def test_admin_page_is_not_cached_or_indexed(admin):
    with client() as c:
        response = c.get('/feedback/admin')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-robots-tag'] == 'noindex, nofollow'
    assert response.headers['referrer-policy'] == 'no-referrer'
    assert 'noindex' in response.text
    assert FAKE_KEY not in response.text


def test_key_guessing_is_limited(monkeypatch, admin):
    monkeypatch.setenv('DATEMATE_IP_FEEDBACK_ADMIN_FAILURES_PER_10_MINUTES', '3')
    with client() as c:
        for _ in range(3):
            assert c.get('/api/feedback/admin/entries', headers=auth('guess')).status_code == 404
        # 같은 IP 범위는 맞는 키로도 10분 동안 열리지 않는다(맞았는지 알려 주지 않음).
        assert c.get('/api/feedback/admin/entries', headers=auth()).status_code == 404
    with client() as other:
        assert other.get('/api/feedback/admin/entries', headers=auth()).status_code == 200


def test_admin_lists_newest_first_marks_and_deletes(admin):
    tag = uuid.uuid4().hex
    with store.connect() as db:
        db.execute('DELETE FROM feedback_entries')
    with client() as c:
        for i in range(23):
            with store.connect() as db:
                db.execute('INSERT INTO feedback_entries(id,created,message,screen,contact,viewport_width,browser,handled) '
                           'VALUES(?,?,?,?,?,?,?,0)', (uuid.uuid4().hex, 1000 + i, f'{tag} {i}', 'home', '', 1440, 'Edge'))
        first = c.get('/api/feedback/admin/entries', headers=auth()).json()
        assert first['total'] == 23 and first['pages'] == 2 and first['unhandled'] == 23
        assert [e['message'] for e in first['entries'][:2]] == [f'{tag} 22', f'{tag} 21']
        assert len(first['entries']) == 20 and first['entries'][0]['screen_label'] == '홈'
        second = c.get('/api/feedback/admin/entries?page=2', headers=auth()).json()
        assert [e['message'] for e in second['entries']] == [f'{tag} 2', f'{tag} 1', f'{tag} 0']

        target = first['entries'][0]['id']
        marked = c.patch(f'/api/feedback/admin/entries/{target}', json={'handled': True}, headers=auth())
        assert marked.status_code == 200 and marked.json()['handled'] is True
        listed = c.get('/api/feedback/admin/entries', headers=auth()).json()
        assert listed['unhandled'] == 22 and listed['entries'][0]['handled'] is True
        assert c.patch(f'/api/feedback/admin/entries/{target}', json={'handled': False},
                       headers=auth()).json()['handled'] is False

        assert c.delete(f'/api/feedback/admin/entries/{target}', headers=auth()).status_code == 200
        assert c.delete(f'/api/feedback/admin/entries/{target}', headers=auth()).status_code == 404
        assert c.patch('/api/feedback/admin/entries/not-an-id', json={'handled': True},
                       headers=auth()).status_code == 404
        assert c.get('/api/feedback/admin/entries', headers=auth()).json()['total'] == 22


def test_maintenance_keeps_entries_and_clears_old_feedback_budgets():
    text = '보관 확인 ' + uuid.uuid4().hex
    with client() as c:
        assert c.post('/api/feedback', json=body(message=text)).status_code == 200
    old_day = int(time.time() // 86400) - 5
    with store.connect() as db:
        db.execute('INSERT INTO request_budgets VALUES(?,?,1)', ('feedback:day:old-' + uuid.uuid4().hex, old_day))
        db.execute('UPDATE feedback_entries SET created=? WHERE message=?', (time.time() - 400 * 86400, text))
    maintenance.maintain()
    assert len(find(text)) == 1
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM request_budgets WHERE scope LIKE 'feedback:%' AND bucket=?",
                          (old_day,)).fetchone()[0] == 0


def test_delete_my_data_does_not_touch_feedback():
    text = '세션 무관 ' + uuid.uuid4().hex
    with client() as c:
        assert c.post('/api/feedback', json=body(message=text)).status_code == 200
        assert c.delete('/api/me/data').status_code == 200
    assert len(find(text)) == 1


# --- 마이그레이션 ---------------------------------------------------------------

def sqlite_connect(path):
    def connect():
        db = sqlite3.connect(path, factory=store.ClosingConnection)
        db.row_factory = sqlite3.Row
        return db
    return connect


def columns(connect):
    with connect() as db:
        return {row[1] for row in db.execute('PRAGMA table_info(feedback_entries)')}


EXPECTED_COLUMNS = {'id', 'created', 'message', 'screen', 'contact', 'viewport_width', 'browser', 'handled'}


def test_migration_on_an_empty_database(tmp_path):
    connect = sqlite_connect(tmp_path / 'empty.sqlite')
    upgrade(connect, 'sqlite')
    assert columns(connect) == EXPECTED_COLUMNS
    with connect() as db:
        assert db.execute('SELECT 1 FROM schema_migrations WHERE version=?',
                          (v0004_user_feedback.VERSION,)).fetchone()


def test_migration_on_an_existing_database_keeps_data(tmp_path):
    connect = sqlite_connect(tmp_path / 'existing.sqlite')
    assert MIGRATIONS[-1] is v0004_user_feedback
    upgrade(connect, 'sqlite', MIGRATIONS[:-1])
    with connect() as db:
        db.execute('INSERT INTO sessions(token,created,last_used) VALUES(?,?,?)', ('a' * 64, 1.0, 1.0))
    assert columns(connect) == set()
    upgrade(connect, 'sqlite')
    upgrade(connect, 'sqlite')  # 두 번 돌려도 그대로
    assert columns(connect) == EXPECTED_COLUMNS
    with connect() as db:
        assert db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 1


def test_current_backend_has_the_table():
    # PostgreSQL 로 테스트를 돌리면(DATEMATE_TEST_DATABASE_URL) 그쪽 스키마도 확인한다.
    with store.connect() as db:
        db.execute('SELECT id,created,message,screen,contact,viewport_width,browser,handled FROM feedback_entries LIMIT 1').fetchall()
