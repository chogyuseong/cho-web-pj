"""Frozen baseline; adopts pre-migration databases without deleting user data."""

import re
import time

VERSION = "0001-baseline"

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


def upgrade(db, backend):
    for statement in SCHEMA.split(";"):
        if statement.strip():
            if backend == "postgres":
                statement = re.sub(
                    r"\bREAL\b", "DOUBLE PRECISION", re.sub(r"\bINTEGER\b", "BIGINT", statement)
                )
            db.execute(statement)
    if backend == "postgres":
        _postgres(db)
    else:
        _sqlite(db)


def _sqlite(db):
    if db.execute(
        "INSERT OR IGNORE INTO schema_migrations VALUES('owned-answer-cache-v1',?)", (time.time(),)
    ).rowcount:
        db.execute(
            "DELETE FROM cache WHERE key LIKE 'answer:%' AND json_extract(payload,'$.owner') IS NULL"
        )
    if db.execute(
        "INSERT OR IGNORE INTO schema_migrations VALUES('cache-owner-index-v1',?)", (time.time(),)
    ).rowcount:
        db.execute(
            "INSERT OR REPLACE INTO cache_owners SELECT key,json_extract(payload,'$.owner') FROM cache WHERE json_extract(payload,'$.owner') IS NOT NULL"
        )
    for operation in ("INSERT", "UPDATE"):
        db.execute(f"""CREATE TRIGGER IF NOT EXISTS track_cache_owner_{operation}
            AFTER {operation} ON cache BEGIN
            DELETE FROM cache_owners WHERE key=NEW.key;
            INSERT INTO cache_owners SELECT NEW.key,json_extract(NEW.payload,'$.owner')
                WHERE json_extract(NEW.payload,'$.owner') IS NOT NULL;
            END""")
    db.execute("""CREATE TRIGGER IF NOT EXISTS clear_cache_owner AFTER DELETE ON cache
        BEGIN DELETE FROM cache_owners WHERE key=OLD.key; END""")
    # A tombstone is committed in the same transaction as deletion. Late
    # writers are rejected even if they run on another connection/process.
    for table, column in (
        ("plans", "owner"),
        ("chats", "owner"),
        ("reviews", "author"),
        ("reports", "author"),
        ("experience_events", "owner"),
        ("place_reports", "owner"),
        ("partner_votes", "owner"),
        ("plan_shares", "owner"),
        ("sessions", "token"),
    ):
        for operation in ("INSERT", "UPDATE"):
            db.execute(f"""CREATE TRIGGER IF NOT EXISTS reject_revoked_{table}_{operation}
                BEFORE {operation} ON {table}
                WHEN EXISTS(SELECT 1 FROM revoked_sessions WHERE token=NEW.{column})
                BEGIN SELECT RAISE(ABORT,'session revoked'); END""")
    for operation in ("INSERT", "UPDATE"):
        db.execute(f"""CREATE TRIGGER IF NOT EXISTS reject_revoked_cache_{operation}
            BEFORE {operation} ON cache
            WHEN EXISTS(SELECT 1 FROM revoked_sessions WHERE token=json_extract(NEW.payload,'$.owner'))
            BEGIN SELECT RAISE(ABORT,'session revoked'); END""")
    for table in ("partner_votes", "plan_shares"):
        db.execute(f"""CREATE TRIGGER IF NOT EXISTS require_plan_{table}
            BEFORE INSERT ON {table} WHEN NOT EXISTS(SELECT 1 FROM plans WHERE id=NEW.plan_id)
            BEGIN SELECT RAISE(ABORT,'plan removed'); END""")


def _postgres(db):
    if db.execute("SELECT 1 FROM schema_migrations WHERE version='postgres-v1'").fetchone():
        return
    db.execute("""CREATE OR REPLACE FUNCTION datemate_guard_owner() RETURNS trigger AS $$
        DECLARE owner_token text;
        BEGIN
            owner_token := to_jsonb(NEW)->>TG_ARGV[0];
            IF EXISTS(SELECT 1 FROM revoked_sessions WHERE token=owner_token) THEN
                RAISE EXCEPTION 'session revoked' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql""")
    for table, column in (
        ("plans", "owner"),
        ("chats", "owner"),
        ("reviews", "author"),
        ("reports", "author"),
        ("experience_events", "owner"),
        ("place_reports", "owner"),
        ("partner_votes", "owner"),
        ("plan_shares", "owner"),
        ("sessions", "token"),
    ):
        db.execute(f"""CREATE TRIGGER reject_revoked BEFORE INSERT OR UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION datemate_guard_owner('{column}')""")
    db.execute("""CREATE OR REPLACE FUNCTION datemate_cache_owner() RETURNS trigger AS $$
        DECLARE owner_token text;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                DELETE FROM cache_owners WHERE key=OLD.key;
                RETURN OLD;
            END IF;
            owner_token := NEW.payload::jsonb->>'owner';
            IF EXISTS(SELECT 1 FROM revoked_sessions WHERE token=owner_token) THEN
                RAISE EXCEPTION 'session revoked' USING ERRCODE='23514';
            END IF;
            DELETE FROM cache_owners WHERE key=NEW.key;
            IF owner_token IS NOT NULL THEN
                INSERT INTO cache_owners VALUES(NEW.key,owner_token);
            END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql""")
    db.execute("""CREATE TRIGGER track_cache_owner BEFORE INSERT OR UPDATE OR DELETE ON cache
        FOR EACH ROW EXECUTE FUNCTION datemate_cache_owner()""")
    db.execute("""CREATE OR REPLACE FUNCTION datemate_require_plan() RETURNS trigger AS $$
        BEGIN
            IF NOT EXISTS(SELECT 1 FROM plans WHERE id=NEW.plan_id) THEN
                RAISE EXCEPTION 'plan removed' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql""")
    for table in ("partner_votes", "plan_shares"):
        db.execute(f"""CREATE TRIGGER require_plan BEFORE INSERT OR UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION datemate_require_plan()""")
    db.execute("INSERT INTO schema_migrations VALUES('postgres-v1',EXTRACT(EPOCH FROM now()))")
