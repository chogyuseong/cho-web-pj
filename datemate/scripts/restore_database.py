"""Restore into a NEW runtime directory. Never replace an active database."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.maintenance import snapshot

def restore(source,directory):
    directory=Path(directory)
    if directory.exists():raise ValueError('복구 대상은 존재하지 않는 새 디렉터리여야 합니다.')
    return snapshot(directory/'datemate.sqlite',source)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backup')
    parser.add_argument('new_runtime')
    args=parser.parse_args()
    print(restore(args.backup,args.new_runtime))
