import hashlib
import json
import sqlite3
import time
import uuid
from .config import RUNTIME
from .database import postgres_enabled

SCHEMA = """
        CREATE TABLE IF NOT EXISTS plans(id TEXT PRIMARY KEY, owner TEXT, parent TEXT, aggregate_key TEXT, payload TEXT);
        CREATE TABLE IF NOT EXISTS reviews(id TEXT PRIMARY KEY, aggregate_key TEXT, author TEXT, nickname TEXT, rating INTEGER,
          body TEXT, visited TEXT, created REAL, updated REAL, valid INTEGER DEFAULT 1, UNIQUE(aggregate_key,author));
        CREATE TABLE IF NOT EXISTS reports(review_id TEXT, author TEXT, reason TEXT, created REAL, PRIMARY KEY(review_id,author));
        CREATE TABLE IF NOT EXISTS chats(owner TEXT, scope TEXT, role TEXT, content TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, payload TEXT, expires REAL);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, created REAL);
        CREATE TABLE IF NOT EXISTS experience_events(id TEXT PRIMARY KEY, owner TEXT, plan_id TEXT, kind TEXT, payload TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS place_reports(id TEXT PRIMARY KEY, owner TEXT, place_id TEXT, reason TEXT, note TEXT, created REAL, resolved INTEGER DEFAULT 0, resolution TEXT DEFAULT '', UNIQUE(owner,place_id,reason));
        CREATE TABLE IF NOT EXISTS partner_votes(plan_id TEXT, owner TEXT, payload TEXT, updated REAL, PRIMARY KEY(plan_id,owner));
        CREATE TABLE IF NOT EXISTS plan_shares(token_hash TEXT PRIMARY KEY, plan_id TEXT, owner TEXT, expires REAL);
        CREATE TABLE IF NOT EXISTS revoked_sessions(token TEXT PRIMARY KEY, created REAL);
        CREATE TABLE IF NOT EXISTS provider_metrics(hour INTEGER,provider TEXT,calls INTEGER,errors INTEGER,elapsed_ms INTEGER,PRIMARY KEY(hour,provider));
        CREATE TABLE IF NOT EXISTS request_budgets(scope TEXT,bucket INTEGER,calls INTEGER,PRIMARY KEY(scope,bucket));
        CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY,applied REAL);
        CREATE TABLE IF NOT EXISTS cache_owners(key TEXT PRIMARY KEY,owner TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS cache_owners_owner ON cache_owners(owner);
        CREATE INDEX IF NOT EXISTS plans_owner ON plans(owner);
        CREATE INDEX IF NOT EXISTS chats_scope ON chats(owner,scope,created);
        CREATE INDEX IF NOT EXISTS events_owner ON experience_events(owner,kind,created);
        CREATE INDEX IF NOT EXISTS reviews_aggregate ON reviews(aggregate_key,valid,updated);
        CREATE INDEX IF NOT EXISTS cache_expiry ON cache(expires);
        CREATE INDEX IF NOT EXISTS shares_plan ON plan_shares(plan_id);
"""

class ClosingConnection(sqlite3.Connection):
    def __exit__(self,*args):
        try:return super().__exit__(*args)
        finally:self.close()


def connect():
    if postgres_enabled():
        from .database import PostgresConnection
        return PostgresConnection()
    db = sqlite3.connect(RUNTIME / 'datemate.sqlite', timeout=20, factory=ClosingConnection)
    db.row_factory = sqlite3.Row
    return db

def init():
    if postgres_enabled():
        from .database import initialize
        return initialize(SCHEMA)
    with connect() as db:
        db.executescript('PRAGMA journal_mode=WAL;' + SCHEMA)
        if db.execute("INSERT OR IGNORE INTO schema_migrations VALUES('owned-answer-cache-v1',?)",(time.time(),)).rowcount:
            db.execute("DELETE FROM cache WHERE key LIKE 'answer:%' AND json_extract(payload,'$.owner') IS NULL")
        if db.execute("INSERT OR IGNORE INTO schema_migrations VALUES('cache-owner-index-v1',?)",(time.time(),)).rowcount:
            db.execute("INSERT OR REPLACE INTO cache_owners SELECT key,json_extract(payload,'$.owner') FROM cache WHERE json_extract(payload,'$.owner') IS NOT NULL")
        for operation in ('INSERT','UPDATE'):
            db.execute(f'''CREATE TRIGGER IF NOT EXISTS track_cache_owner_{operation}
                AFTER {operation} ON cache BEGIN
                DELETE FROM cache_owners WHERE key=NEW.key;
                INSERT INTO cache_owners SELECT NEW.key,json_extract(NEW.payload,'$.owner')
                    WHERE json_extract(NEW.payload,'$.owner') IS NOT NULL;
                END''')
        db.execute('''CREATE TRIGGER IF NOT EXISTS clear_cache_owner AFTER DELETE ON cache
            BEGIN DELETE FROM cache_owners WHERE key=OLD.key; END''')
        # A tombstone is committed in the same transaction as deletion. Late
        # writers are rejected even if they run on another connection/process.
        for table,column in (('plans','owner'),('chats','owner'),('reviews','author'),
                             ('reports','author'),('experience_events','owner'),
                             ('place_reports','owner'),('partner_votes','owner'),
                             ('plan_shares','owner'),('sessions','token')):
            for operation in ('INSERT','UPDATE'):
                db.execute(f'''CREATE TRIGGER IF NOT EXISTS reject_revoked_{table}_{operation}
                    BEFORE {operation} ON {table}
                    WHEN EXISTS(SELECT 1 FROM revoked_sessions WHERE token=NEW.{column})
                    BEGIN SELECT RAISE(ABORT,'session revoked'); END''')
        for operation in ('INSERT','UPDATE'):
            db.execute(f'''CREATE TRIGGER IF NOT EXISTS reject_revoked_cache_{operation}
                BEFORE {operation} ON cache
                WHEN EXISTS(SELECT 1 FROM revoked_sessions WHERE token=json_extract(NEW.payload,'$.owner'))
                BEGIN SELECT RAISE(ABORT,'session revoked'); END''')
        for table in ('partner_votes','plan_shares'):
            db.execute(f'''CREATE TRIGGER IF NOT EXISTS require_plan_{table}
                BEFORE INSERT ON {table} WHEN NOT EXISTS(SELECT 1 FROM plans WHERE id=NEW.plan_id)
                BEGIN SELECT RAISE(ABORT,'plan removed'); END''')


def revoked(owner):
    with connect() as db:
        return db.execute('SELECT 1 FROM revoked_sessions WHERE token=?',(owner,)).fetchone() is not None


def reserve_budget(limits,bucket):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        for scope,limit in limits:
            row=db.execute('SELECT calls FROM request_budgets WHERE scope=? AND bucket=?',(scope,bucket)).fetchone()
            if row and row[0]>=limit:return False
        for scope,limit in limits:
            db.execute('INSERT INTO request_budgets VALUES(?,?,1) ON CONFLICT(scope,bucket) DO UPDATE SET calls=request_budgets.calls+1',(scope,bucket))
    return True

def aggregate_key(ids):
    # 시간과 예산은 집계 키에서 제외하고 방문 순서만 보존한다.
    return hashlib.sha256(json.dumps(ids, ensure_ascii=False).encode()).hexdigest()

def save_plan(plan, owner, parent=None):
    plan = dict(plan, id=uuid.uuid4().hex, parent=parent)
    plan['aggregate_key'] = aggregate_key([p['id'] for p in plan['places']])
    with connect() as db:
        db.execute('INSERT INTO plans VALUES(?,?,?,?,?)', (plan['id'], owner, parent, plan['aggregate_key'], json.dumps(plan, ensure_ascii=False)))
    return plan

def get_plan(plan_id):
    with connect() as db:
        row = db.execute('SELECT * FROM plans WHERE id=?', (plan_id,)).fetchone()
    return dict(row) if row else None

def cached(key):
    with connect() as db:
        row = db.execute('SELECT payload FROM cache WHERE key=? AND expires>?', (key, time.time())).fetchone()
    return json.loads(row[0]) if row else None

def cache(key, value, ttl=86400):
    with connect() as db:
        db.execute('INSERT INTO cache VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,expires=excluded.expires', (key, json.dumps(value, ensure_ascii=False), time.time()+ttl))

def history(owner, scope):
    with connect() as db:
        return [dict(x) for x in db.execute('SELECT role,content,created FROM chats WHERE owner=? AND scope=? ORDER BY created', (owner, scope))]

def chat_save(owner, scope, question, answer):
    with connect() as db:
        db.executemany('INSERT INTO chats VALUES(?,?,?,?,?)', [(owner, scope, 'user', question, time.time()), (owner, scope, 'assistant', answer, time.time()+.001)])

def reviews(key, owner=''):
    with connect() as db:
        rows = [dict(r) for r in db.execute('SELECT * FROM reviews WHERE aggregate_key=? AND valid=1 ORDER BY updated DESC', (key,))]
    count = len(rows)
    for row in rows:
        row['mine'] = row.pop('author') == owner
    return dict(count=count, average=round(sum(r['rating'] for r in rows)/count, 2) if count>=10 else None,
                label=f'평가 집계 중 · {count}건' if count<10 else f'유효 후기 {count}건', rows=rows,
                verification='자기 신고 · 브라우저 세션 데모 식별 (실제 이용 및 다중 계정 방지 미검증)')

def put_review(key, owner, data):
    now = time.time()
    with connect() as db:
        previous = db.execute('SELECT updated FROM reviews WHERE author=? ORDER BY updated DESC LIMIT 1', (owner,)).fetchone()
        if previous and now-previous[0]<3:
            raise ValueError('연속 작성은 3초 후 다시 시도하세요.')
        db.execute('''INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?,?,1)
            ON CONFLICT(aggregate_key,author) DO UPDATE SET nickname=excluded.nickname,rating=excluded.rating,
            body=excluded.body,visited=excluded.visited,updated=excluded.updated,valid=1''',
            (uuid.uuid4().hex, key, owner, data.nickname, data.rating, data.body, str(data.visited), now, now))
