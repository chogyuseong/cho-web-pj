"""Indexes for retention cleanup and aggregate operational reporting."""

VERSION = "0002-operational-indexes"


def upgrade(db, backend):
    db.execute("CREATE INDEX IF NOT EXISTS shares_expiry ON plan_shares(expires)")
    db.execute("CREATE INDEX IF NOT EXISTS budgets_bucket ON request_budgets(bucket)")
    db.execute("CREATE INDEX IF NOT EXISTS events_kind_created ON experience_events(kind, created)")
