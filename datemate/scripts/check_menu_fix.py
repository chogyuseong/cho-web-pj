# [예전 기준 점검 스크립트] 예전 진단 파일(runtime/menu-debug)이 있어야 하고 실제 메뉴 공급자에 접속하는 일회성 점검입니다.
# 그대로 실행하면 실패할 수 있습니다. 자동 테스트(pytest)가 기준이며, 같은 내용은 tests/test_menus.py 에서 확인합니다.
print('[예전 기준 점검 스크립트] 예전 진단 파일(runtime/menu-debug)이 있어야 하고 실제 메뉴 공급자에 접속하는 일회성 점검입니다. 그대로 실행하면 실패할 수 있습니다. 대신 볼 테스트: tests/test_menus.py', flush=True)
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
