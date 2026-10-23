import sys,json,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import store
from app.image_search import search_place_images
from app.config import ROOT
snapshot=store.cached('explore-seoul-500-v1');rows=snapshot['places'];started=time.monotonic()
def check(p):
 r=search_place_images(p);return dict(place=p,status=r['status'],count=len(r['photos']))
results=[]
with ThreadPoolExecutor(max_workers=3) as pool:
 for i,r in enumerate(pool.map(check,rows),1):
  results.append(r)
  if not r['count']:print(json.dumps({'missing':r['place']['name'],'status':r['status']},ensure_ascii=True),flush=True)
  if i%50==0:print('checked',i,flush=True)
Path('docs/explore-photos-before.json').write_text(json.dumps(results,ensure_ascii=False),encoding='utf-8')
print(json.dumps({'checked':len(results),'available':sum(bool(r['count']) for r in results),'seconds':round(time.monotonic()-started,1)}),flush=True)
