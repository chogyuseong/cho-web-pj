import os
import sys
import tempfile
from pathlib import Path
os.environ['DATEMATE_RUNTIME']=tempfile.mkdtemp(prefix='datemate-tests-')
# Never run tests against the application's database or credentials.
os.environ['DATABASE_URL']=os.getenv('DATEMATE_TEST_DATABASE_URL','')
if os.environ['DATABASE_URL']:
    import uuid
    import psycopg
    from psycopg import sql
    os.environ['DATEMATE_DB_SCHEMA']='datemate_test_'+uuid.uuid4().hex
    with psycopg.connect(os.environ['DATABASE_URL']) as db:
        db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(os.environ['DATEMATE_DB_SCHEMA'])))
os.environ['DATEMATE_ENV_FILE']=str(Path(os.environ['DATEMATE_RUNTIME'])/'absent.env')
os.environ['DATEMATE_IP_REQUESTS_PER_MINUTE']='100000'
os.environ['DATEMATE_USER_CHATS_PER_MINUTE']='10000'
os.environ['EMBEDDING_MODE']='demo'
os.environ['GMS_KEY']=''
os.environ['DATEMATE_BACKUP_DIR']=''
os.environ['DATEMATE_RECOMMENDATIONS_PER_MINUTE']='10000'
os.environ['DATEMATE_USER_RECOMMENDATIONS_PER_MINUTE']='10000'
os.environ['DATEMATE_PROVIDER_CALLS_PER_HOUR']='10000'
# Every test request comes from the same TestClient address within a few minutes,
# far beyond one real visitor; tests of these limits lower them with monkeypatch.
for _name in ('SESSIONS','EXPENSIVE_REQUESTS','RECOMMENDATIONS','CHATS','GEOCODE','REVERSE_GEOCODE',
              'LOCAL_SEARCHES','REFRESHES','REVIEWS','EXPLORE_SEARCHES'):
    os.environ[f'DATEMATE_IP_{_name}_PER_MINUTE']='100000'
# 로컬 단위 테스트가 사용자 실제 검색 키로 외부 API를 호출하지 않게 한다.
os.environ['NAVER_SEARCH_CLIENT_ID']=''
os.environ['NAVER_SEARCH_CLIENT_SECRET']=''
# 셸에 실제 키가 설정돼 있어도 축제·지도 API를 실제로 호출하지 않게 한다. 필요한 테스트는 monkeypatch로 넣는다.
for _name in ('TOUR_API_KEY','NAVER_MAPS_KEY_ID','NAVER_MAPS_KEY','NAVER_MAPS_JS_KEY_ID'):
    os.environ[_name]=''
os.environ['DATEMATE_OPERATING_EVIDENCE_FILE']=''
os.environ['DATEMATE_EXTERNAL_CALLS_PER_RECOMMENDATION']='60'
os.environ['DATEMATE_HTTP_USD_PER_1000']='{}'
# 테스트는 과거의 고정 방문일(2026-10-24 등)을 쓴다. 새 추천의 지난 날짜 검사만 이 시각(한국 시각) 기준으로 한다.
# 검사 자체를 확인하는 테스트는 monkeypatch 로 바꾼다(tests/test_past_visit.py).
os.environ['DATEMATE_PLANNING_NOW']='2026-01-01T00:00'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from app import store

@pytest.fixture(autouse=True)
def storage():
    store.init()
