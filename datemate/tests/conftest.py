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
# 로컬 단위 테스트가 사용자 실제 검색 키로 외부 API를 호출하지 않게 한다.
os.environ['NAVER_SEARCH_CLIENT_ID']=''
os.environ['NAVER_SEARCH_CLIENT_SECRET']=''
os.environ['TMAP_APP_KEY']=''
os.environ['TMAP_TRANSIT_APP_KEY']=''
os.environ['DATEMATE_OPERATING_EVIDENCE_FILE']=''
os.environ['DATEMATE_EXTERNAL_CALLS_PER_RECOMMENDATION']='60'
os.environ['DATEMATE_HTTP_USD_PER_1000']='{}'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from app import store

@pytest.fixture(autouse=True)
def storage():
    store.init()
