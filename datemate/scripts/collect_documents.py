import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import store
from app.catalog import places
from app.collection import collect
from app.config import ROOT

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int,default=5);parser.add_argument('--refresh',action='store_true');parser.add_argument('--llm',action='store_true');args=parser.parse_args()
    store.init();path=ROOT/'data'/'real_documents.json'
    old=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    merged={(d['place_id'],d['id']):d for d in old};ok=0;failed=0
    for p in [p for p in places('real') if p.get('wikipedia')][:args.limit]:
        try:
            docs,_=collect(p,refresh=args.refresh,use_llm=args.llm)
            for d in docs:merged[(d['place_id'],d['id'])]=d
            ok+=1
        except Exception:
            failed+=1
        path.write_text(json.dumps(list(merged.values()),ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(dict(place=p['id'],succeeded=ok,failed=failed,documents=len(merged))),flush=True)
