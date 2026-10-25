"""PostgreSQL storage with bounded pooling and SQLite-compatible result rows.

Writes are serialized with a transaction advisory lock, preserving the existing
SQLite transaction semantics across Cloud Run instances. No network calls belong
inside a database transaction. Local development can continue using SQLite.
"""
import os
import re
from functools import lru_cache

WRITE_LOCK = 731942601


def postgres_enabled():
    return bool(os.getenv('DATABASE_URL', '').strip())


class Record(dict):
    def __getitem__(self, key):
        return tuple(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


def row_factory(cursor):
    names = [column.name for column in cursor.description] if cursor.description else []
    return lambda values: Record(zip(names, values))


@lru_cache(maxsize=1)
def pool():
    from psycopg_pool import ConnectionPool
    schema=os.getenv('DATEMATE_DB_SCHEMA','public')
    if not re.fullmatch(r'[a-z_][a-z0-9_]*',schema):
        raise ValueError('Invalid database schema name')
    return ConnectionPool(os.environ['DATABASE_URL'], min_size=0,
                          max_size=int(os.getenv('DATEMATE_DB_POOL_SIZE', '12')),
                          timeout=15, max_waiting=32,
                          kwargs={'row_factory': row_factory, 'connect_timeout': 10,
                                  'options': f'-c statement_timeout=20000 -c lock_timeout=15000 -c search_path={schema}'},
                          open=True)


def parameters(sql):
    # Do not replace question marks in SQL string literals. Psycopg requires
    # literal percent signs to be escaped whenever parameters are supplied.
    sql = sql.replace('%', '%%')
    return re.sub(r"'(?:''|[^'])*'|\?", lambda m: '%s' if m[0] == '?' else m[0], sql)


class PostgresConnection:
    def __enter__(self):
        self.context = pool().connection()
        self.connection = self.context.__enter__()
        self.locked = False
        self.closed = False
        return self

    def __exit__(self, *args):
        self.closed = True
        return self.context.__exit__(*args)

    def lock(self):
        if not self.locked:
            self.connection.execute('SELECT pg_advisory_xact_lock(%s)', (WRITE_LOCK,))
            self.locked = True

    def execute(self, sql, args=None):
        if self.closed:
            raise RuntimeError('database connection context is closed')
        if sql.strip().upper() == 'BEGIN IMMEDIATE':
            self.lock()
            return self.connection.execute('SELECT 1')
        if re.match(r'\s*(INSERT|UPDATE|DELETE|CREATE|DROP|ALTER)\b', sql, re.I):
            self.lock()
        return self.connection.execute(parameters(sql) if args is not None else sql, args)

    def executemany(self, sql, rows):
        if self.closed:
            raise RuntimeError('database connection context is closed')
        self.lock()
        cursor = self.connection.cursor()
        cursor.executemany(parameters(sql), rows)
        return cursor


def initialize(schema):
    with PostgresConnection() as db:
        db.lock()
        for statement in schema.split(';'):
            if statement.strip():
                db.execute(re.sub(r'\bREAL\b', 'DOUBLE PRECISION',
                                 re.sub(r'\bINTEGER\b', 'BIGINT', statement)))
        if db.execute("SELECT 1 FROM schema_migrations WHERE version='postgres-v1'").fetchone():
            return
        db.execute('''CREATE OR REPLACE FUNCTION datemate_guard_owner() RETURNS trigger AS $$
            DECLARE owner_token text;
            BEGIN
                owner_token := to_jsonb(NEW)->>TG_ARGV[0];
                IF EXISTS(SELECT 1 FROM revoked_sessions WHERE token=owner_token) THEN
                    RAISE EXCEPTION 'session revoked' USING ERRCODE='23514';
                END IF;
                RETURN NEW;
            END; $$ LANGUAGE plpgsql''')
        for table, column in (('plans','owner'), ('chats','owner'), ('reviews','author'),
                              ('reports','author'), ('experience_events','owner'),
                              ('place_reports','owner'), ('partner_votes','owner'),
                              ('plan_shares','owner'), ('sessions','token')):
            db.execute(f'''CREATE TRIGGER reject_revoked BEFORE INSERT OR UPDATE ON {table}
                FOR EACH ROW EXECUTE FUNCTION datemate_guard_owner('{column}')''')
        db.execute('''CREATE OR REPLACE FUNCTION datemate_cache_owner() RETURNS trigger AS $$
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
            END; $$ LANGUAGE plpgsql''')
        db.execute('''CREATE TRIGGER track_cache_owner BEFORE INSERT OR UPDATE OR DELETE ON cache
            FOR EACH ROW EXECUTE FUNCTION datemate_cache_owner()''')
        db.execute('''CREATE OR REPLACE FUNCTION datemate_require_plan() RETURNS trigger AS $$
            BEGIN
                IF NOT EXISTS(SELECT 1 FROM plans WHERE id=NEW.plan_id) THEN
                    RAISE EXCEPTION 'plan removed' USING ERRCODE='23514';
                END IF;
                RETURN NEW;
            END; $$ LANGUAGE plpgsql''')
        for table in ('partner_votes', 'plan_shares'):
            db.execute(f'''CREATE TRIGGER require_plan BEFORE INSERT OR UPDATE ON {table}
                FOR EACH ROW EXECUTE FUNCTION datemate_require_plan()''')
        db.execute("INSERT INTO schema_migrations VALUES('postgres-v1',EXTRACT(EPOCH FROM now()))")
