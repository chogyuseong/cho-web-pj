import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import RUNTIME
from app.menus import extract_menus,restaurant_menu
for i in [4,5]:
 place=json.loads((RUNTIME/'menu-debug'/f'{i}.json').read_text(encoding='utf-8'))
 parsed=extract_menus((RUNTIME/'menu-debug'/f'{i}.html').read_text(encoding='utf-8'),place)
 print(json.dumps({'name':place['name'],'format':parsed.get('menu_format') if parsed else None,'items':len(parsed['items']) if parsed else 0,'images':len(parsed.get('menu_images',[])) if parsed else 0},ensure_ascii=True),flush=True)
 result=restaurant_menu(place,force=True)
 print(json.dumps({'live_status':result['status'],'items':len(result['items']),'images':len(result['menu_images'])},ensure_ascii=True),flush=True)
