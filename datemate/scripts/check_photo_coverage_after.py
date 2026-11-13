# [예전 기준 점검 스크립트] 예전 사진 점검 자료(docs/photo-audit-before.json)를 실제 이미지 검색으로 다시 검사하고 docs 의 결과 파일을 덮어씁니다.
# 그대로 실행하면 실패할 수 있습니다. 자동 테스트(pytest)가 기준이며, 같은 내용은 tests/test_image_search.py, tests/test_media.py 에서 확인합니다.
print('[예전 기준 점검 스크립트] 예전 사진 점검 자료(docs/photo-audit-before.json)를 실제 이미지 검색으로 다시 검사하고 docs 의 결과 파일을 덮어씁니다. 그대로 실행하면 실패할 수 있습니다. 대신 볼 테스트: tests/test_image_search.py, tests/test_media.py', flush=True)
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
