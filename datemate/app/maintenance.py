"""Periodic backups and expired-cache cleanup; no silent user-data expiry."""
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
        raise ValueError('PostgreSQL은 Cloud SQL 백업 또는 pg_dump로 백업하세요.')
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
        db.execute("DELETE FROM request_budgets WHERE (scope LIKE 'http:%' OR scope LIKE 'chat:%') AND bucket<?",(int(time.time()//60)-2,))
        db.execute('DELETE FROM provider_metrics WHERE hour<?',(int(time.time()//3600)-24*30,))
    directory=os.getenv('DATEMATE_BACKUP_DIR','')
    if directory and not postgres_enabled():
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        snapshot(Path(directory)/f'datemate-{stamp}.sqlite')


async def loop():
    interval=max(60,int(os.getenv('DATEMATE_BACKUP_INTERVAL_SECONDS','3600')))
    while True:
        try:await asyncio.to_thread(maintain)
        except Exception:logging.getLogger(__name__).exception('maintenance_failed')
        await asyncio.sleep(interval)
