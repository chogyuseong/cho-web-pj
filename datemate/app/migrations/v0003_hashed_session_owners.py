"""Store session owners as SHA-256 digests and record activity for retention.

Before this version the raw cookie token was the database identity of a browser
(sessions.token and every owner column). Afterwards only sha256(token) is stored,
so existing cookies keep matching: sha256(cookie) == migrated value. Values that
already look like a digest (64 lowercase hex) or a retention marker are left
alone, so a forced re-run never hashes twice. Raw tokens are 43-character
token_urlsafe values and can never look like a digest.
"""

import hashlib
import json
import re
import time

VERSION = "0003-hashed-session-owners"

EXPIRED_AUTHOR = "expired:"  # same marker as store.EXPIRED_AUTHOR (frozen here)
_DIGEST = re.compile(r"[0-9a-f]{64}")

# Every column that holds a browser identity. revoked_sessions goes last: the
# revocation triggers compare NEW.<column> with it while the other tables change.
OWNER_COLUMNS = (
    ("plans", "owner"),
    ("chats", "owner"),
    ("reviews", "author"),
    ("reports", "author"),
    ("experience_events", "owner"),
    ("place_reports", "owner"),
    ("partner_votes", "owner"),
    ("plan_shares", "owner"),
    ("sessions", "token"),
    ("cache_owners", "owner"),
    ("revoked_sessions", "token"),
)

# Short-lived limiter keys with the raw owner appended; safe to drop.
OWNER_RATE_PREFIXES = (
    "geocode-rate:",
    "region-rate:",
    "menu-refresh:",
    "media-refresh:",
    "price-refresh:",
    "local-rate:",
)


def digest(value):
    if not isinstance(value, str) or _DIGEST.fullmatch(value) or value.startswith(EXPIRED_AUTHOR):
        return value
    return hashlib.sha256(value.encode()).hexdigest()


def _needs_digest(value):
    return 1 if isinstance(value, str) and digest(value) != value else 0


def _columns(db, backend, table):
    if backend == "postgres":
        rows = db.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name=?",
            (table,),
        ).fetchall()
    else:
        rows = db.execute(f"PRAGMA table_info({table})").fetchall()
        return {row[1] for row in rows}
    return {row[0] for row in rows}


def _add_column(db, backend, table, column):
    if column in _columns(db, backend, table):
        return
    kind = "DOUBLE PRECISION" if backend == "postgres" else "REAL"
    db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")


def upgrade(db, backend):
    now = time.time()
    if backend == "postgres":
        # The pooled connection's 20 s statement limit is for requests; a one-time
        # rewrite of every plan row may need longer. Scoped to this transaction.
        db.execute("SET LOCAL statement_timeout = '300s'")
        hashed = "encode(sha256(convert_to({0},'UTF8')),'hex')"
        needs = "{0} !~ '^[0-9a-f]{{64}}$' AND {0} NOT LIKE 'expired:%'"
    else:
        db.create_function("datemate_owner_digest", 1, digest, deterministic=True)
        db.create_function("datemate_needs_digest", 1, _needs_digest, deterministic=True)
        hashed = "datemate_owner_digest({0})"
        needs = "datemate_needs_digest({0})=1"

    # Rows that can no longer be used would only make the updates below fail on
    # PostgreSQL's plan-existence trigger (it also fires on UPDATE).
    db.execute("DELETE FROM partner_votes WHERE plan_id NOT IN (SELECT id FROM plans)")
    db.execute("DELETE FROM plan_shares WHERE plan_id NOT IN (SELECT id FROM plans)")
    db.execute("DELETE FROM cache WHERE expires<=?", (now,))
    for prefix in OWNER_RATE_PREFIXES:
        db.execute("DELETE FROM cache WHERE key LIKE ?", (prefix + "%",))
    db.execute(
        "DELETE FROM request_budgets WHERE scope LIKE 'recommendations:%' OR scope LIKE 'chat:%'"
    )

    # Owner-bound cache payloads carry the owner in JSON; rewriting them lets the
    # cache_owners triggers re-index each key under the digest.
    rows = db.execute(
        "SELECT c.key,c.payload FROM cache c JOIN cache_owners o ON o.key=c.key"
    ).fetchall()
    for key, payload in ((row[0], row[1]) for row in rows):
        try:
            value = json.loads(payload)
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict) and digest(value.get("owner")) != value.get("owner"):
            value["owner"] = digest(value["owner"])
            db.execute(
                "UPDATE cache SET payload=? WHERE key=?",
                (json.dumps(value, ensure_ascii=False), key),
            )

    for table, column in OWNER_COLUMNS:
        db.execute(
            f"UPDATE {table} SET {column}={hashed.format(column)} "
            f"WHERE {column} IS NOT NULL AND {needs.format(column)}"
        )

    # Activity for the retention job. Existing sessions count as used a day ago:
    # nothing is deleted after deploy and the next visit renews the cookie.
    _add_column(db, backend, "sessions", "last_used")
    _add_column(db, backend, "plans", "created")
    db.execute("UPDATE sessions SET last_used=? WHERE last_used IS NULL", (now - 86400,))
    db.execute("UPDATE plans SET created=? WHERE created IS NULL", (now,))
    if backend == "postgres":
        # Positional inserts from a previous release during a rolling deploy still
        # get a timestamp (PostgreSQL fills omitted trailing columns with defaults).
        db.execute(
            "ALTER TABLE sessions ALTER COLUMN last_used SET DEFAULT EXTRACT(EPOCH FROM now())"
        )
        db.execute("ALTER TABLE plans ALTER COLUMN created SET DEFAULT EXTRACT(EPOCH FROM now())")
    db.execute("CREATE INDEX IF NOT EXISTS sessions_last_used ON sessions(last_used)")
    db.execute("CREATE INDEX IF NOT EXISTS plans_created ON plans(created)")
