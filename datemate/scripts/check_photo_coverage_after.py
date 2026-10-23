import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import ROOT
from app.image_search import search_place_images
rows=json.loads(Path('docs/photo-audit-before.json').read_text(encoding='utf-8'))
for row in rows:
    result=search_place_images(row['place']);row['after_status']=result['status'];row['after_count']=len(result['photos'])
    print(json.dumps({'name':row['place']['name'],'before':row['count'],'after':row['after_count']},ensure_ascii=True),flush=True)
Path('docs/photo-audit-after.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
