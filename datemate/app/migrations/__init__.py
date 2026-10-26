"""Ordered, transactional migrations for SQLite and PostgreSQL.

Never edit an applied migration. Add a new module and append it to MIGRATIONS.
The startup lock prevents two instances from applying the same migration.
"""

import time
from . import v0001_baseline, v0002_operational_indexes

MIGRATIONS = (v0001_baseline, v0002_operational_indexes)


def upgrade(connect, backend, migrations=None):
    migrations = MIGRATIONS if migrations is None else migrations
    versions = [migration.VERSION for migration in migrations]
    if versions != sorted(set(versions)):
        raise ValueError("Migration versions must be unique and ordered")
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        timestamp_type = "DOUBLE PRECISION" if backend == "postgres" else "REAL"
        db.execute(
            f"CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, applied {timestamp_type})"
        )
        for migration in migrations:
            if db.execute(
                "SELECT 1 FROM schema_migrations WHERE version=?", (migration.VERSION,)
            ).fetchone():
                continue
            migration.upgrade(db, backend)
            db.execute(
                "INSERT INTO schema_migrations VALUES(?,?)", (migration.VERSION, time.time())
            )
