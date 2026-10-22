"""Check cloud bootstrap against an empty temporary runtime without API keys."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='datemate-cloud-check-') as runtime:
    env=os.environ.copy()
    env.update(DATEMATE_RUNTIME=runtime,DATEMATE_ENV_FILE=str(Path(runtime)/'absent.env'),
               DATEMATE_BOOTSTRAP_INDEX='1',EMBEDDING_MODE='demo',PYTHONIOENCODING='utf-8')
    for key in ['GMS_KEY','NAVER_MAPS_KEY','NAVER_SEARCH_CLIENT_SECRET']:env.pop(key,None)
    code='''
from app.cloud_start import prepare_runtime
prepare_runtime()
from app.indexing import collections
assert collections('real')[0].count()>0
assert collections('demo')[0].count()>0
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as client:
    response=client.get('/healthz')
    assert response.status_code==200 and response.json()=={'status':'ok'}
    assert 'set-cookie' not in response.headers
print({'empty_runtime_bootstrap':True,'health_check':True,'no_session_for_probe':True,'real_places_indexed':collections('real')[0].count()})
'''
    subprocess.run([sys.executable,'-c',code],cwd=root,env=env,check=True,timeout=90)
