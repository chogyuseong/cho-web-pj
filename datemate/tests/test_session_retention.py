"""Hashed session owners, __Host- cookies, the owner-hash migration and retention."""
import hashlib
import json
import secrets
import sqlite3
import time
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import maintenance, store
from app.main import app
from app.migrations import MIGRATIONS, upgrade, v0003_hashed_session_owners as v0003
from app.catalog import places
from app.models import Conditions, ReviewInput
from app.planner import evaluate

DAY = 86400


def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def plan_payload():
    conditions = Conditions(visit_date='2026-10-24', count=2, budget=1000000, max_leg=180,
                            start='09:00', end='23:00')
    plan, error = evaluate(places('demo')[:2], conditions)
    assert not error
    return plan


def set_cookies(response):
    return [value for key, value in response.headers.multi_items() if key == 'set-cookie']


# --- session digest -----------------------------------------------------------

def test_database_stores_only_the_cookie_digest():
    with TestClient(app) as client:
        client.get('/api/status')
        cookie = client.cookies['dm_session']
        with store.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM sessions WHERE token=?', (cookie,)).fetchone()[0] == 0
            row = db.execute('SELECT token,last_used FROM sessions WHERE token=?', (sha(cookie),)).fetchone()
        assert row is not None and row[1] is not None
        plan = store.save_plan(plan_payload(), store.owner_of(cookie))
        assert client.get('/api/plans/' + plan['id']).json()['can_edit'] is True
        with store.connect() as db:
            assert db.execute('SELECT owner FROM plans WHERE id=?', (plan['id'],)).fetchone()[0] == sha(cookie)


def test_other_session_and_raw_digest_cookie_cannot_open_a_plan():
    with TestClient(app) as owner, TestClient(app) as other:
        owner.get('/api/status')
        plan = store.save_plan(plan_payload(), store.owner_of(owner.cookies['dm_session']))
        assert other.get('/api/plans/' + plan['id'] + '/reviews').status_code == 404
        # Knowing the stored digest (e.g. from a leaked database) is not a session.
        other.cookies.set('dm_session', store.owner_of(owner.cookies['dm_session']))
        assert other.get('/api/plans/' + plan['id'] + '/reviews').status_code == 404


def test_local_http_keeps_dm_session_name():
    with TestClient(app) as client:
        cookie = set_cookies(client.get('/api/status'))[0]
        assert cookie.startswith('dm_session=') and 'secure' not in cookie.lower()


def test_https_issues_host_prefixed_cookie_and_deletes_it():
    with TestClient(app, base_url='https://testserver') as client:
        cookie = set_cookies(client.get('/api/status'))[0]
        lowered = cookie.lower()
        assert cookie.startswith('__Host-dm_session=')
        assert 'secure' in lowered and 'path=/' in lowered and 'domain' not in lowered
        assert 'httponly' in lowered and 'samesite=lax' in lowered
        token = client.cookies['__Host-dm_session']
        with store.connect() as db:
            assert db.execute('SELECT 1 FROM sessions WHERE token=?', (sha(token),)).fetchone()
        response = client.delete('/api/me/data', headers={'Origin': 'https://testserver'})
        assert response.status_code == 200
        removed = set_cookies(response)
        assert any(c.startswith('__Host-dm_session=') and 'max-age=0' in c.lower() for c in removed)
        assert any(c.startswith('dm_session=') and 'max-age=0' in c.lower() for c in removed)
        with store.connect() as db:
            assert db.execute('SELECT 1 FROM sessions WHERE token=?', (sha(token),)).fetchone() is None


def test_https_carries_over_legacy_cookie_without_losing_the_session():
    with TestClient(app) as old:
        old.get('/api/status')
        token = old.cookies['dm_session']
    plan = store.save_plan(plan_payload(), store.owner_of(token))
    with TestClient(app, base_url='https://testserver') as client:
        client.cookies.set('dm_session', token)
        response = client.get('/api/plans/' + plan['id'])
        assert response.status_code == 200 and response.json()['can_edit'] is True
        cookies = set_cookies(response)
        assert any(c.startswith('__Host-dm_session=' + token) and 'secure' in c.lower() for c in cookies)
        assert any(c.startswith('dm_session=') and 'max-age=0' in c.lower() for c in cookies)
        with store.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM sessions WHERE token=?', (sha(token),)).fetchone()[0] == 1
    # The next request with only the new cookie needs no cookie changes.
    with TestClient(app, base_url='https://testserver') as client:
        client.cookies.set('__Host-dm_session', token)
        response = client.get('/api/plans/' + plan['id'])
        assert response.status_code == 200 and not set_cookies(response)


def test_last_use_is_written_at_most_daily_and_renews_the_cookie():
    with TestClient(app) as client:
        client.get('/api/status')
        owner = store.owner_of(client.cookies['dm_session'])
        with store.connect() as db:
            first = db.execute('SELECT last_used FROM sessions WHERE token=?', (owner,)).fetchone()[0]
        response = client.get('/api/status')
        assert not set_cookies(response)
        with store.connect() as db:
            assert db.execute('SELECT last_used FROM sessions WHERE token=?', (owner,)).fetchone()[0] == first
            db.execute('UPDATE sessions SET last_used=? WHERE token=?', (time.time() - DAY - 60, owner))
        renewed = set_cookies(client.get('/api/status'))
        assert renewed and 'max-age=2592000' in renewed[0].lower()
        with store.connect() as db:
            assert db.execute('SELECT last_used FROM sessions WHERE token=?', (owner,)).fetchone()[0] > time.time() - 60


# --- migration ----------------------------------------------------------------

def rerun_owner_migration():
    with store.connect() as db:
        db.execute('DELETE FROM schema_migrations WHERE version=?', (v0003.VERSION,))
    store.init()


def test_migration_hashes_legacy_rows_once_and_keeps_access():
    token = secrets.token_urlsafe(32)
    other = secrets.token_urlsafe(32)
    revoked = secrets.token_urlsafe(32)
    plan_id = uuid.uuid4().hex
    review_key = 'legacy-' + uuid.uuid4().hex
    payload = json.dumps(dict(plan_payload(), id=plan_id, parent=None, aggregate_key=review_key))
    with store.connect() as db:
        # Pre-migration format: the raw cookie token everywhere.
        db.execute('INSERT INTO sessions(token,created) VALUES(?,?)', (token, time.time()))
        db.execute('INSERT INTO plans(id,owner,parent,aggregate_key,payload) VALUES(?,?,?,?,?)',
                   (plan_id, token, None, review_key, payload))
        db.execute('INSERT INTO chats VALUES(?,?,?,?,?)', (token, 'demo:plan:' + plan_id, 'user', 'q', 1))
        db.execute('INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?,?,1)',
                   (uuid.uuid4().hex, review_key, token, '닉', 5, '좋아요', '2026-10-01', 1, 1))
        db.execute('INSERT INTO partner_votes VALUES(?,?,?,?)', (plan_id, other, '{}', 1))
        db.execute('INSERT INTO plan_shares VALUES(?,?,?,?)', ('share-' + plan_id, plan_id, token, time.time() + 600))
        db.execute('INSERT INTO experience_events VALUES(?,?,?,?,?,?)', (uuid.uuid4().hex, token, plan_id, 'visit', '{}', 1))
        db.execute('INSERT INTO place_reports(id,owner,place_id,reason,note,created) VALUES(?,?,?,?,?,?)',
                   (uuid.uuid4().hex, token, 'sample', 'closed', '', 1))
        db.execute('INSERT INTO revoked_sessions VALUES(?,?)', (revoked, 1))
        db.execute("INSERT INTO cache VALUES(?,?,?)",
                   ('plan-job:legacy-' + plan_id, json.dumps({'owner': token, 'status': 'complete'}), time.time() + 600))
        db.execute("INSERT INTO cache VALUES(?,?,?)", ('geocode-rate:' + token, 'true', time.time() + 600))
    rerun_owner_migration()

    def snapshot():
        with store.connect() as db:
            return dict(
                session=db.execute('SELECT COUNT(*) FROM sessions WHERE token=?', (sha(token),)).fetchone()[0],
                raw=sum(db.execute(f'SELECT COUNT(*) FROM {t} WHERE {c}=?', (token,)).fetchone()[0]
                        for t, c in v0003.OWNER_COLUMNS),
                plan=db.execute('SELECT owner FROM plans WHERE id=?', (plan_id,)).fetchone()[0],
                chat=db.execute('SELECT owner FROM chats WHERE scope=?', ('demo:plan:' + plan_id,)).fetchone()[0],
                review=db.execute('SELECT author FROM reviews WHERE aggregate_key=?', (review_key,)).fetchone()[0],
                vote=db.execute('SELECT owner FROM partner_votes WHERE plan_id=?', (plan_id,)).fetchone()[0],
                share=db.execute('SELECT owner FROM plan_shares WHERE plan_id=?', (plan_id,)).fetchone()[0],
                event=db.execute('SELECT owner FROM experience_events WHERE plan_id=?', (plan_id,)).fetchone()[0],
                revoked=db.execute('SELECT COUNT(*) FROM revoked_sessions WHERE token=?', (sha(revoked),)).fetchone()[0],
                cache_owner=db.execute('SELECT owner FROM cache_owners WHERE key=?', ('plan-job:legacy-' + plan_id,)).fetchone()[0],
                rate=db.execute('SELECT COUNT(*) FROM cache WHERE key=?', ('geocode-rate:' + token,)).fetchone()[0],
                last_used=db.execute('SELECT last_used FROM sessions WHERE token=?', (sha(token),)).fetchone()[0],
            )

    after = snapshot()
    assert after['session'] == 1 and after['raw'] == 0 and after['revoked'] == 1 and after['rate'] == 0
    assert {after[k] for k in ('plan', 'chat', 'review', 'share', 'event', 'cache_owner')} == {sha(token)}
    assert after['vote'] == sha(other)
    # Existing sessions count as used about a day ago, never as expired.
    assert time.time() - 2 * DAY < after['last_used'] < time.time()
    assert store.cached('plan-job:legacy-' + plan_id)['owner'] == sha(token)
    # The browser still holding the old cookie reaches its own plan and chat.
    with TestClient(app) as client:
        client.cookies.set('dm_session', token)
        response = client.get('/api/plans/' + plan_id)
        assert response.status_code == 200 and response.json()['can_edit'] is True
        assert client.get('/api/chat/plan/' + plan_id + '?mode=demo').json()['messages'][0]['content'] == 'q'
        assert any(row['mine'] for row in client.get('/api/plans/' + plan_id + '/reviews').json()['rows'])
    # Re-running never hashes twice.
    rerun_owner_migration()
    again = snapshot()
    again.pop('last_used'), after.pop('last_used')
    assert again == after


@pytest.mark.skipif(store.postgres_enabled(), reason='fresh SQLite file adoption')
def test_migration_adopts_a_pre_hash_sqlite_file(tmp_path):
    path = tmp_path / 'legacy.sqlite'

    def connect():
        db = sqlite3.connect(path, factory=store.ClosingConnection)
        db.row_factory = sqlite3.Row
        return db

    upgrade(connect, 'sqlite', MIGRATIONS[:2])
    token = secrets.token_urlsafe(32)
    with connect() as db:
        db.execute('INSERT INTO sessions VALUES(?,?)', (token, 5.0))
        db.execute('INSERT INTO plans VALUES(?,?,?,?,?)', ('p1', token, None, 'k', '{}'))
    upgrade(connect, 'sqlite')
    with connect() as db:
        assert db.execute('SELECT token,created,last_used FROM sessions').fetchall()[0][:2] == (sha(token), 5.0)
        assert db.execute('SELECT owner,created FROM plans').fetchone()[0] == sha(token)
        assert db.execute('SELECT created FROM plans').fetchone()[0] is not None
        assert db.execute('SELECT COUNT(*) FROM schema_migrations WHERE version=?', (v0003.VERSION,)).fetchone()[0] == 1


# --- retention ----------------------------------------------------------------

def make_owner(days_idle, review=True):
    token = secrets.token_urlsafe(32)
    owner = store.owner_of(token)
    used = time.time() - days_idle * DAY
    with store.connect() as db:
        db.execute('INSERT INTO sessions(token,created,last_used) VALUES(?,?,?)', (owner, used, used))
    plan = store.save_plan(plan_payload(), owner)
    with store.connect() as db:
        db.execute('UPDATE plans SET created=? WHERE id=?', (used, plan['id']))
        db.execute('INSERT INTO partner_votes VALUES(?,?,?,?)', (plan['id'], 'guest-' + owner[:8], '{}', used))
    store.chat_save(owner, 'demo:plan:' + plan['id'], 'question', 'answer')
    plan['review_id'] = None
    if review:
        store.put_review(plan['aggregate_key'], owner,
                         ReviewInput(rating=5, body='좋았어요', nickname='익명', visited=date(2026, 10, 1)))
        with store.connect() as db:
            plan['review_id'] = db.execute('SELECT id FROM reviews WHERE author=?', (owner,)).fetchone()[0]
    return owner, plan


def counts(owner, plan):
    with store.connect() as db:
        return dict(
            session=db.execute('SELECT COUNT(*) FROM sessions WHERE token=?', (owner,)).fetchone()[0],
            plan=db.execute('SELECT COUNT(*) FROM plans WHERE id=?', (plan['id'],)).fetchone()[0],
            chats=db.execute('SELECT COUNT(*) FROM chats WHERE owner=?', (owner,)).fetchone()[0],
            votes=db.execute('SELECT COUNT(*) FROM partner_votes WHERE plan_id=?', (plan['id'],)).fetchone()[0],
            reviews=db.execute('SELECT COUNT(*) FROM reviews WHERE id=?', (plan['review_id'],)).fetchone()[0],
            mine=db.execute('SELECT COUNT(*) FROM reviews WHERE author=?', (owner,)).fetchone()[0],
        )


def test_idle_owner_is_deleted_but_public_review_stays_detached():
    owner, plan = make_owner(91)
    maintenance.retention()
    assert counts(owner, plan) == dict(session=0, plan=0, chats=0, votes=0, reviews=1, mine=0)
    with store.connect() as db:
        author = db.execute('SELECT author FROM reviews WHERE id=?', (plan['review_id'],)).fetchone()[0]
    assert author == store.EXPIRED_AUTHOR + plan['review_id']
    assert plan['review_id'] in [row['id'] for row in store.reviews(plan['aggregate_key'])['rows']]


def test_owner_used_within_retention_is_kept():
    owner, plan = make_owner(89)
    maintenance.retention()
    assert counts(owner, plan) == dict(session=1, plan=1, chats=2, votes=1, reviews=1, mine=1)


def test_retention_days_come_from_environment(monkeypatch):
    monkeypatch.setenv('DATEMATE_RETENTION_DAYS', '10')
    assert maintenance.retention_days() == 10
    owner, plan = make_owner(11, review=False)
    maintenance.retention()
    assert counts(owner, plan)['plan'] == 0
    monkeypatch.setenv('DATEMATE_RETENTION_DAYS', 'not-a-number')
    assert maintenance.retention_days() == 90


def test_orphan_plans_follow_the_same_cutoff():
    old_owner, recent_owner = 'orphan-' + uuid.uuid4().hex, 'orphan-' + uuid.uuid4().hex
    old = store.save_plan(plan_payload(), old_owner)
    recent = store.save_plan(plan_payload(), recent_owner)
    with store.connect() as db:
        db.execute('UPDATE plans SET created=? WHERE id=?', (time.time() - 91 * DAY, old['id']))
        db.execute('UPDATE plans SET created=? WHERE id=?', (time.time() - 89 * DAY, recent['id']))
    maintenance.retention()
    assert store.get_plan(old['id']) is None
    assert store.get_plan(recent['id']) is not None


def test_two_expired_reviews_of_one_course_do_not_collide():
    first, plan = make_owner(91)
    second = store.owner_of(secrets.token_urlsafe(32))
    used = time.time() - 91 * DAY
    with store.connect() as db:
        db.execute('INSERT INTO sessions(token,created,last_used) VALUES(?,?,?)', (second, used, used))
    store.put_review(plan['aggregate_key'], second,
                     ReviewInput(rating=4, body='괜찮았어요', nickname='둘째', visited=date(2026, 10, 2)))
    with store.connect() as db:
        second_id = db.execute('SELECT id FROM reviews WHERE author=?', (second,)).fetchone()[0]
    maintenance.retention()
    with store.connect() as db:
        authors = {row[0]: row[1] for row in db.execute(
            'SELECT id,author FROM reviews WHERE id IN (?,?)', (plan['review_id'], second_id))}
    assert authors == {plan['review_id']: store.EXPIRED_AUTHOR + plan['review_id'],
                       second_id: store.EXPIRED_AUTHOR + second_id}
