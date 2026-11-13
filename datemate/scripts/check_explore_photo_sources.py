# [예전 기준 점검 스크립트] 서울 500곳 수집 자료(docs/explore-photos-before.json)를 실제 사진 공급자로 다시 검사하고 docs 의 결과 파일을 덮어씁니다.
# 그대로 실행하면 실패할 수 있습니다. 자동 테스트(pytest)가 기준이며, 같은 내용은 tests/test_public_place_photos.py, tests/test_media.py 에서 확인합니다.
print('[예전 기준 점검 스크립트] 서울 500곳 수집 자료(docs/explore-photos-before.json)를 실제 사진 공급자로 다시 검사하고 docs 의 결과 파일을 덮어씁니다. 그대로 실행하면 실패할 수 있습니다. 대신 볼 테스트: tests/test_public_place_photos.py, tests/test_media.py', flush=True)
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
