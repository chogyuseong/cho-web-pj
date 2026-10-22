"""Create a consistent SQLite backup, including committed WAL transactions."""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import RUNTIME


def backup(destination):
    source = RUNTIME / 'datemate.sqlite'
    destination = Path(destination).resolve()
    if not source.exists():
        raise ValueError('원본 데이터베이스가 없습니다.')
    if destination == source.resolve() or destination.exists():
        raise ValueError('기존 파일을 덮어쓸 수 없습니다. 새 백업 경로를 지정하세요.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the destination exclusively before SQLite opens it.
    with destination.open('xb'):
        pass
    try:
        with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('백업 무결성 검사에 실패했습니다.')
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', help='새 백업 파일 경로 (개인정보 포함, 접근 제한 필요)')
    print(backup(parser.parse_args().destination))
