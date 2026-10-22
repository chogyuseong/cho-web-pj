import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import store

parser=argparse.ArgumentParser();parser.add_argument('--clear',choices=['expired','answers','all'],default='expired');args=parser.parse_args()
store.init()
with store.connect() as db:
    if args.clear=='expired':cursor=db.execute("DELETE FROM cache WHERE expires < strftime('%s','now')")
    elif args.clear=='answers':cursor=db.execute("DELETE FROM cache WHERE key LIKE 'answer:%'")
    else:cursor=db.execute('DELETE FROM cache')
    print(f'Removed cache rows: {cursor.rowcount}')
