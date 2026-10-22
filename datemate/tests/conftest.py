import os
import sys
import tempfile
from pathlib import Path
os.environ['DATEMATE_RUNTIME']=tempfile.mkdtemp(prefix='datemate-tests-')
os.environ['EMBEDDING_MODE']='demo'
os.environ['GMS_KEY']=''
# 로컬 단위 테스트가 사용자 실제 검색 키로 외부 API를 호출하지 않게 한다.
os.environ['NAVER_SEARCH_CLIENT_ID']=''
os.environ['NAVER_SEARCH_CLIENT_SECRET']=''
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from app import store

@pytest.fixture(autouse=True)
def storage():
    store.init()
