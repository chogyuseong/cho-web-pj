import sys,json,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.media import media_info
rows=json.loads(Path('docs/explore-photos-before.json').read_text(encoding='utf-8'))
started=time.monotonic();results=[]
def check(row):
 data=media_info(row['place']);return dict(place_id=row['place']['id'],name=row['place']['name'],before=row['count'],count=len(data['photos']),status=data['status'],provider=data.get('photo_source') or data.get('search_status'))
with ThreadPoolExecutor(max_workers=3) as pool:
 for i,r in enumerate(pool.map(check,rows),1):
  results.append(r)
  if not r['count'] or not r['before']:print(json.dumps({k:v for k,v in r.items() if k!='photos'},ensure_ascii=True),flush=True)
  if i%50==0:print('checked',i,flush=True)
Path('docs/explore-photos-after.json').write_text(json.dumps(results,ensure_ascii=False),encoding='utf-8')
print(json.dumps({'checked':len(results),'available':sum(bool(r['count']) for r in results),'before_available':sum(bool(r['count']) for r in rows),'seconds':round(time.monotonic()-started,1)}),flush=True)
