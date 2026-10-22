"""운영자가 출처를 직접 확인한 뒤 제보 확인 대기를 해제하는 로컬 도구."""
import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import store

p=argparse.ArgumentParser();p.add_argument('--resolve-id');p.add_argument('--source');p.add_argument('--note');args=p.parse_args()
store.init()
with store.connect() as db:
    if args.resolve_id:
        if not args.source or urlsplit(args.source).scheme!='https' or not args.note:p.error('확인한 HTTPS 출처와 --note가 필요합니다.')
        row=db.execute('SELECT id FROM place_reports WHERE id=?',(args.resolve_id,)).fetchone()
        if not row:p.error('제보를 찾을 수 없습니다.')
        db.execute('UPDATE place_reports SET resolved=1,resolution=? WHERE id=?',(json.dumps(dict(source=args.source,note=args.note),ensure_ascii=False),args.resolve_id))
        print('제보 검토를 기록했습니다. 공식 운영 정보 원본은 자동 변경하지 않습니다.')
    else:
        for row in db.execute('SELECT id,place_id,reason,note,created FROM place_reports WHERE resolved=0 ORDER BY created DESC'):
            print(json.dumps(dict(row),ensure_ascii=False))
