"""Feedback written on the /feedback page during the test period.

Rows are not tied to a browser session (no owner column) and no raw IP is stored,
so they are kept until an administrator deletes them.
"""

VERSION = "0004-user-feedback"


def upgrade(db, backend):
    real = "DOUBLE PRECISION" if backend == "postgres" else "REAL"
    db.execute(
        "CREATE TABLE IF NOT EXISTS feedback_entries("
        "id TEXT PRIMARY KEY, "
        f"created {real} NOT NULL, "
        "message TEXT NOT NULL, "
        "screen TEXT NOT NULL DEFAULT '', "
        "contact TEXT NOT NULL DEFAULT '', "
        "viewport_width INTEGER, "
        "browser TEXT NOT NULL DEFAULT '', "
        "handled INTEGER NOT NULL DEFAULT 0)"
    )
    db.execute("CREATE INDEX IF NOT EXISTS feedback_entries_created ON feedback_entries(created)")
