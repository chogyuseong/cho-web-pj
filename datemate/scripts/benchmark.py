import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import store
from app.rag import ask
from app.config import ROOT

store.init()
with store.connect() as db:db.execute("DELETE FROM cache WHERE key LIKE 'answer:%'")
first=ask(['Q494407'],'가격은 얼마인가요?','real')
cached=ask(['Q494407'],'가격은 얼마인가요?','real')
result={'mode':'키 없는 규칙 기반 응답 / 로컬 Chroma 문자 해시 검색','first_ms':first['elapsed_ms'],
        'cache_ms':cached['elapsed_ms'],'first_cache_hit':first['cache_hit'],'second_cache_hit':cached['cache_hit'],
        'note':'동일 질문·근거·빈 대화 이력. 검색은 재실행하고 생성 결과만 SQLite 캐시에서 읽음. 실제 외부 API 성능 아님.'}
(ROOT/'docs'/'benchmark.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=True))
