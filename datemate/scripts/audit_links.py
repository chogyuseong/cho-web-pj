import sys,json,re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import store
from app.config import ROOT
from urllib.parse import urlsplit
with store.connect() as db:rows=db.execute('SELECT payload FROM plans ORDER BY rowid DESC LIMIT 4').fetchall()
urls=[]
for row in rows:
 p=json.loads(row[0])
 for place in p['places']:
  for k in ['source','place_source','operations_source']:
   u=place.get(k)
   if isinstance(u,str) and u.startswith('https://') and u not in urls:urls.append(u)
 for cost in p['costs']:
  for q in cost.get('price_evidence') or []:
   if q['source'] not in urls:urls.append(q['source'])
def check(u):
 try:
  r=httpx.get(u,timeout=7,follow_redirects=True);return {'url':u,'status':r.status_code,'final':str(r.url)}
 except httpx.HTTPError as e:return {'url':u,'error':type(e).__name__}
results=list(ThreadPoolExecutor(max_workers=3).map(check,urls[:15]))
Path('docs/link-audit.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
for row in results:print(json.dumps(row,ensure_ascii=True))
