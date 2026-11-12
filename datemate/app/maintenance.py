"""Periodic backups, expired-cache cleanup and the stated retention period.

Saved data of a browser that has not used the service for DATEMATE_RETENTION_DAYS
(default 90) is deleted with the same routine as "delete my data", except that
public reviews stay visible and are only detached from their former owner.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
import time
from . import store
from .config import RUNTIME
from .database import postgres_enabled


def snapshot(destination, source=None):
    if source is None and postgres_enabled():
        raise ValueError('PostgreSQL은 제공자의 백업 또는 pg_dump로 백업하세요.')
    source=Path(source or RUNTIME/'datemate.sqlite').resolve()
    destination=Path(destination).resolve()
    if not source.exists():raise ValueError('원본 데이터베이스가 없습니다.')
    if source==destination or destination.exists():raise ValueError('기존 파일을 덮어쓸 수 없습니다.')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('xb'):pass
    try:
        with store.ClosingConnection(str(source)) as src, store.ClosingConnection(str(destination)) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('무결성 검사 실패')
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


def maintain():
    with store.connect() as db:
        db.execute('DELETE FROM cache WHERE expires<=?',(time.time(),))
        db.execute('DELETE FROM plan_shares WHERE expires<=?',(time.time(),))
        db.execute("DELETE FROM request_budgets WHERE scope LIKE 'recommendations%' AND bucket<?",(int(time.time()//60)-2,))
        db.execute("DELETE FROM request_budgets WHERE scope LIKE 'provider:%' AND bucket<?",(int(time.time()//3600)-2,))
        db.execute("DELETE FROM request_budgets WHERE (scope LIKE 'http:%' OR scope LIKE 'chat:%' OR scope LIKE 'ip:%') AND bucket<?",(int(time.time()//60)-2,))
        db.execute('DELETE FROM provider_metrics WHERE hour<?',(int(time.time()//3600)-24*30,))
    retention()
    directory=os.getenv('DATEMATE_BACKUP_DIR','')
    if directory and not postgres_enabled():
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        snapshot(Path(directory)/f'datemate-{stamp}.sqlite')


RETENTION_BATCH = 500


def retention_days():
    try:
        return max(1, int(os.getenv('DATEMATE_RETENTION_DAYS', '90')))
    except ValueError:
        return 90


def retention(now=None):
    """Delete owners idle past the retention period; one short transaction each.

    Idle = a session whose last use is older than the cutoff, or plans whose owner has
    no session row (orphans) and whose newest plan is older than the cutoff.
    Returns the number of owners removed.
    """
    cutoff = (now if now is not None else time.time()) - retention_days() * 86400
    idle_session = 'SELECT 1 FROM sessions WHERE token=? AND COALESCE(last_used,created)<?'
    orphan = ('SELECT 1 FROM plans p WHERE p.owner=? AND NOT EXISTS(SELECT 1 FROM sessions s WHERE s.token=p.owner) '
              'GROUP BY p.owner HAVING MAX(p.created)<?')
    with store.connect() as db:
        candidates = [(row[0], idle_session) for row in db.execute(
            'SELECT token FROM sessions WHERE COALESCE(last_used,created)<? LIMIT ?', (cutoff, RETENTION_BATCH))]
        candidates += [(row[0], orphan) for row in db.execute(
            'SELECT p.owner FROM plans p WHERE p.owner IS NOT NULL '
            'AND NOT EXISTS(SELECT 1 FROM sessions s WHERE s.token=p.owner) '
            'GROUP BY p.owner HAVING MAX(p.created)<? LIMIT ?', (cutoff, RETENTION_BATCH))]
    from .plan_jobs import forget_owner
    removed = 0
    for owner, still_idle in candidates:
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            # Re-check under the write lock: the browser may have come back meanwhile.
            if not db.execute(still_idle, (owner, cutoff)).fetchone():
                continue
            store.purge_owner(db, owner, keep_public_reviews=True)
        forget_owner(owner)
        removed += 1
    if removed:
        logging.getLogger(__name__).info('retention_removed_owners=%s days=%s', removed, retention_days())
    return removed


async def loop():
    interval=max(60,int(os.getenv('DATEMATE_BACKUP_INTERVAL_SECONDS','3600')))
    while True:
        try:await asyncio.to_thread(maintain)
        except Exception:logging.getLogger(__name__).exception('maintenance_failed')
        await asyncio.sleep(interval)
