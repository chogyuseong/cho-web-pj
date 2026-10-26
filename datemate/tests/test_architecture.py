"""Upgrade safety and service boundaries, exercised on both database backends."""

import json
import time
import uuid
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor

import pytest
from app import store, recommendation_service as service
from app.migrations import upgrade, MIGRATIONS
from app.models import Conditions


def backend():
    return "postgres" if store.postgres_enabled() else "sqlite"


def test_legacy_database_is_adopted_without_losing_data():
    owner = "migration-" + uuid.uuid4().hex
    store.cache(owner, {"owner": owner, "proof": "retained"})
    with store.connect() as db:
        for migration in MIGRATIONS:
            db.execute("DELETE FROM schema_migrations WHERE version=?", (migration.VERSION,))
    with ThreadPoolExecutor(max_workers=2) as workers:
        list(workers.map(lambda _: store.init(), range(2)))
    assert store.cached(owner)["proof"] == "retained"
    with store.connect() as db:
        for migration in MIGRATIONS:
            assert (
                db.execute(
                    "SELECT COUNT(*) FROM schema_migrations WHERE version=?", (migration.VERSION,)
                ).fetchone()[0]
                == 1
            )


def test_failed_migration_rolls_back_schema_and_version():
    version = "test-" + uuid.uuid4().hex
    table = "migration_" + uuid.uuid4().hex

    def fail(db, backend):
        db.execute(f"CREATE TABLE {table}(proof TEXT)")
        raise RuntimeError("migration interrupted")

    with pytest.raises(RuntimeError, match="migration interrupted"):
        upgrade(store.connect, backend(), [SimpleNamespace(VERSION=version, upgrade=fail)])
    with store.connect() as db:
        assert (
            db.execute("SELECT 1 FROM schema_migrations WHERE version=?", (version,)).fetchone()
            is None
        )
        # This would fail if the failed migration's CREATE TABLE had committed.
        db.execute(f"CREATE TABLE {table}(proof TEXT)")
        db.execute(f"DROP TABLE {table}")


def test_service_failure_is_measured_and_preserves_original_error(monkeypatch):
    owner = "service-failure-" + uuid.uuid4().hex

    def fail(data):
        raise ValueError("original failure")

    monkeypatch.setattr(service, "_research", fail)
    with pytest.raises(ValueError, match="original failure"):
        service.generate(Conditions(visit_date="2026-10-31"), owner)
    with store.connect() as db:
        row = db.execute("SELECT payload FROM experience_events WHERE owner=?", (owner,)).fetchone()
    assert json.loads(row[0])["status"] == "failed"
    assert "original failure" not in row[0]


def test_metrics_failure_does_not_discard_successful_result(monkeypatch):
    from app import experience

    def fail(*args):
        raise RuntimeError("metrics unavailable")

    monkeypatch.setattr(service, "_research", lambda data: (data, {"plans": []}))
    monkeypatch.setattr(service, "_finish", lambda data, result, owner: result)
    monkeypatch.setattr(experience, "event", fail)
    assert service.generate(Conditions(visit_date="2026-10-31"), uuid.uuid4().hex) == {"plans": []}


def test_report_distinguishes_failures_from_empty_results():
    from app.experience import event
    from scripts.operations_report import report

    since = time.time()
    owner = uuid.uuid4().hex
    event(owner, "", "recommendation", {"plans": 0, "elapsed_ms": 10})  # Legacy success.
    event(owner, "", "recommendation", {"status": "failed", "elapsed_ms": 999})
    event(
        owner,
        "",
        "recommendation",
        {"status": "complete", "plans": 2, "best_effort_plans": 1, "elapsed_ms": 20},
    )
    result = report(since)
    assert (result["completed"], result["failed"], result["empty_results"]) == (2, 1, 1)
    assert result["failure_rate"] == pytest.approx(1 / 3)
    assert result["p95_ms"] == 20
    assert result["quality_sample_size"] == 1
    assert result["best_effort_plans"] == 1
