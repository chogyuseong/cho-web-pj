# [예전 기준 점검 스크립트] 서울 500곳 수집 결과(docs/explore-photos-*.json)를 실제 공급자로 다시 검사하는 일회성 점검입니다.
# 그대로 실행하면 실패할 수 있습니다. 자동 테스트(pytest)가 기준이며, 같은 내용은 tests/test_public_place_photos.py, tests/test_search_address_text.py 에서 확인합니다.
print('[예전 기준 점검 스크립트] 서울 500곳 수집 결과(docs/explore-photos-*.json)를 실제 공급자로 다시 검사하는 일회성 점검입니다. 그대로 실행하면 실패할 수 있습니다. 대신 볼 테스트: tests/test_public_place_photos.py, tests/test_search_address_text.py', flush=True)
import sys,json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.public_place_photos import public_place_photos
from app.search_address_text import place_query
before={r['place']['id']:r['place'] for r in json.loads(Path('docs/explore-photos-before.json').read_text(encoding='utf-8'))}
missing=[before[r['place_id']] for r in json.loads(Path('docs/explore-photos-after.json').read_text(encoding='utf-8')) if not r['count']]
def check(p):
 r=public_place_photos(p,True);return dict(name=p['name'],query=place_query(p),status=r['status'],photos=len(r['photos']))
with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(check,missing))
Path('docs/road-photo-recheck.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
for r in rows:print(json.dumps(r,ensure_ascii=True),flush=True)
