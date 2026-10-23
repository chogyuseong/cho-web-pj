import sys,json,re
from pathlib import Path
from urllib.parse import urlencode
from collections import Counter
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import store
from app.config import RUNTIME
from app.menus import restaurant_menu,dictionaries
with store.connect() as db:rows=db.execute("SELECT payload FROM cache WHERE key LIKE 'restaurant:food:%' ORDER BY rowid DESC LIMIT 6").fetchall()
places=[json.loads(r[0]) for r in rows]
out=RUNTIME/'menu-debug';out.mkdir(exist_ok=True)
for i,p in enumerate(places):
 result=restaurant_menu(p)
 print(json.dumps({'name':p['name'],'status':result['status'],'count':len(result['items'])},ensure_ascii=True),flush=True)
 if result['items']:continue
 query=p['name']+' '+((p.get('address') or '').split()[1] if len((p.get('address') or '').split())>1 else '서울')+' 메뉴'
 r=httpx.get('https://search.naver.com/search.naver',params={'query':query},timeout=10)
 (out/f'{i}.html').write_text(r.text,encoding='utf-8');(out/f'{i}.json').write_text(json.dumps(p,ensure_ascii=False),encoding='utf-8')
 markers=list(re.finditer(r'__APOLLO_STATE__\s*=\s*',r.text));summary={'http':r.status_code,'bytes':len(r.content),'apollo':len(markers)}
 if markers:
  try:
   state,_=json.JSONDecoder().raw_decode(r.text,markers[0].end());summary['types']=Counter(d.get('__typename','') for d in dictionaries(state)).most_common(10)
   summary['bases']=[{k:d.get(k) for k in ('__typename','name','id','coordinate','roadAddress')} for d in dictionaries(state) if d.get('__typename')=='PlaceDetailBase'][:3]
  except ValueError:pass
 print(json.dumps(summary,ensure_ascii=True),flush=True)
