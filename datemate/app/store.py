import hashlib
import json
import sqlite3
import time
import uuid
from .config import RUNTIME
from .database import postgres_enabled

# Compatibility export; schema history lives in immutable migration files.
from .migrations.v0001_baseline import SCHEMA


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def connect():
    if postgres_enabled():
        from .database import PostgresConnection

        return PostgresConnection()
    db = sqlite3.connect(RUNTIME / "datemate.sqlite", timeout=20, factory=ClosingConnection)
    db.row_factory = sqlite3.Row
    return db


def init():
    from .migrations import upgrade

    if not postgres_enabled():
        with connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
    upgrade(connect, "postgres" if postgres_enabled() else "sqlite")


def revoked(owner):
    with connect() as db:
        return (
            db.execute("SELECT 1 FROM revoked_sessions WHERE token=?", (owner,)).fetchone()
            is not None
        )


def reserve_budget(limits, bucket):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        for scope, limit in limits:
            row = db.execute(
                "SELECT calls FROM request_budgets WHERE scope=? AND bucket=?", (scope, bucket)
            ).fetchone()
            if row and row[0] >= limit:
                return False
        for scope, limit in limits:
            db.execute(
                "INSERT INTO request_budgets VALUES(?,?,1) ON CONFLICT(scope,bucket) DO UPDATE SET calls=request_budgets.calls+1",
                (scope, bucket),
            )
    return True


def aggregate_key(ids):
    # 시간과 예산은 집계 키에서 제외하고 방문 순서만 보존한다.
    return hashlib.sha256(json.dumps(ids, ensure_ascii=False).encode()).hexdigest()


def save_plan(plan, owner, parent=None):
    plan = dict(plan, id=uuid.uuid4().hex, parent=parent)
    plan["aggregate_key"] = aggregate_key([p["id"] for p in plan["places"]])
    with connect() as db:
        db.execute(
            "INSERT INTO plans VALUES(?,?,?,?,?)",
            (
                plan["id"],
                owner,
                parent,
                plan["aggregate_key"],
                json.dumps(plan, ensure_ascii=False),
            ),
        )
    return plan


def get_plan(plan_id):
    with connect() as db:
        row = db.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
    return dict(row) if row else None


def cached(key):
    with connect() as db:
        row = db.execute(
            "SELECT payload FROM cache WHERE key=? AND expires>?", (key, time.time())
        ).fetchone()
    return json.loads(row[0]) if row else None


def cache(key, value, ttl=86400):
    with connect() as db:
        db.execute(
            "INSERT INTO cache VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,expires=excluded.expires",
            (key, json.dumps(value, ensure_ascii=False), time.time() + ttl),
        )


def history(owner, scope):
    with connect() as db:
        return [
            dict(x)
            for x in db.execute(
                "SELECT role,content,created FROM chats WHERE owner=? AND scope=? ORDER BY created",
                (owner, scope),
            )
        ]


def chat_save(owner, scope, question, answer):
    with connect() as db:
        db.executemany(
            "INSERT INTO chats VALUES(?,?,?,?,?)",
            [
                (owner, scope, "user", question, time.time()),
                (owner, scope, "assistant", answer, time.time() + 0.001),
            ],
        )


def reviews(key, owner=""):
    with connect() as db:
        rows = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM reviews WHERE aggregate_key=? AND valid=1 ORDER BY updated DESC",
                (key,),
            )
        ]
    count = len(rows)
    for row in rows:
        row["mine"] = row.pop("author") == owner
    return dict(
        count=count,
        average=round(sum(r["rating"] for r in rows) / count, 2) if count >= 10 else None,
        label=f"평가 집계 중 · {count}건" if count < 10 else f"유효 후기 {count}건",
        rows=rows,
        verification="자기 신고 · 브라우저 세션 데모 식별 (실제 이용 및 다중 계정 방지 미검증)",
    )


def put_review(key, owner, data):
    now = time.time()
    with connect() as db:
        previous = db.execute(
            "SELECT updated FROM reviews WHERE author=? ORDER BY updated DESC LIMIT 1", (owner,)
        ).fetchone()
        if previous and now - previous[0] < 3:
            raise ValueError("연속 작성은 3초 후 다시 시도하세요.")
        db.execute(
            """INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?,?,1)
            ON CONFLICT(aggregate_key,author) DO UPDATE SET nickname=excluded.nickname,rating=excluded.rating,
            body=excluded.body,visited=excluded.visited,updated=excluded.updated,valid=1""",
            (
                uuid.uuid4().hex,
                key,
                owner,
                data.nickname,
                data.rating,
                data.body,
                str(data.visited),
                now,
                now,
            ),
        )
