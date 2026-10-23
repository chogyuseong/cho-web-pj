import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import store
from app.image_search import search_place_images
from app.config import ROOT
store.init();seen=set();rows=[]
with store.connect() as db:plans=db.execute('SELECT payload FROM plans ORDER BY rowid DESC LIMIT 8').fetchall()
for row in plans:
    for p in json.loads(row[0])['places']:
        if p['id'] in seen or p.get('demo'):continue
        seen.add(p['id']);r=search_place_images(p);rows.append({'place':p,'status':r['status'],'count':len(r['photos'])});print(json.dumps({'name':p['name'],'status':r['status'],'photos':len(r['photos'])},ensure_ascii=True),flush=True)
        if len(rows)>=9:break
    if len(rows)>=9:break
Path('docs/photo-audit-before.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
