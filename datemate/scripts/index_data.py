import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.catalog import places
from app.indexing import index_places,index_documents,embedding_mode
from app.config import ROOT

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['demo','real'],default='demo');args=parser.parse_args()
    count=index_places(places(args.mode),args.mode)
    path=ROOT/'data'/f'{args.mode}_documents.json'
    docs=index_documents(json.loads(path.read_text(encoding='utf-8')),args.mode) if path.exists() else 0
    print(json.dumps(dict(mode=args.mode,embedding=embedding_mode(),places=count,chunks=docs)))
