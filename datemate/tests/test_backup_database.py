import sqlite3
import pytest
from scripts.backup_database import backup
from app import store

pytestmark = pytest.mark.skipif(store.postgres_enabled(), reason='SQLite backup; PostgreSQL uses managed backups')


def test_backup_preserves_committed_rows(tmp_path):
    with store.connect() as db:
        db.execute('INSERT OR REPLACE INTO sessions VALUES(?,?)', ('backup-test', 123))
    destination = backup(tmp_path / 'backup.sqlite')
    with sqlite3.connect(destination) as db:
        assert db.execute('SELECT created FROM sessions WHERE token=?', ('backup-test',)).fetchone()[0] == 123
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'


def test_backup_never_overwrites_existing_file(tmp_path):
    destination = tmp_path / 'existing.sqlite'
    destination.write_bytes(b'keep me')
    with pytest.raises(ValueError):
        backup(destination)
    assert destination.read_bytes() == b'keep me'
