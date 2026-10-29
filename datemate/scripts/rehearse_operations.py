"""Offline startup -> plan -> backup -> restore -> delete drill in temporary storage."""

import json, os, subprocess, sys, tempfile
from pathlib import Path


def rehearse():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="datemate-rehearsal-") as temporary:
        env = os.environ.copy()
        env.update(
            DATEMATE_RUNTIME=str(Path(temporary) / "runtime"),
            DATEMATE_ENV_FILE=str(Path(temporary) / "no.env"),
            DATABASE_URL="",
            DATEMATE_ENV="development",
            DATEMATE_BACKUP_DIR="",
            DATEMATE_PUBLIC_ORIGIN="",
            DATEMATE_ALLOWED_HOSTS="",
            DATEMATE_OPERATING_EVIDENCE_FILE="",
            DATEMATE_EXTERNAL_CALLS_PER_RECOMMENDATION="60",
            EMBEDDING_MODE="demo",
            PYTHONIOENCODING="utf-8",
        )
        for key in (
            "K_SERVICE",
            "GMS_KEY",
            "NAVER_MAPS_KEY_ID",
            "NAVER_MAPS_KEY",
            "NAVER_SEARCH_CLIENT_ID",
            "NAVER_SEARCH_CLIENT_SECRET",
            "TMAP_APP_KEY",
            "TMAP_TRANSIT_APP_KEY",
        ):
            env.pop(key, None)
        code = """
import json,sqlite3
from pathlib import Path
from fastapi.testclient import TestClient
from app.config import RUNTIME
from app.main import app
from app.maintenance import snapshot
from app.service_time import today
from scripts.restore_database import restore
from scripts.operations_check import report
with TestClient(app) as client:
    assert client.get('/healthz').status_code==200
    response=client.post('/api/plans',json={'visit_date':today().isoformat(),'max_leg':180,'budget':1000000,'count':2})
    assert response.status_code==200 and response.json()['plans']
    pid=response.json()['plans'][0]['id']
    assert client.post('/api/plans/'+pid+'/decision',json={}).status_code==200
    backup=snapshot(RUNTIME.parent/'backup.sqlite')
    recovered=restore(backup,RUNTIME.parent/'restored')
    with sqlite3.connect(recovered) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('SELECT 1 FROM plans WHERE id=?',(pid,)).fetchone()
    assert report()['ok']
    assert client.delete('/api/me/data').status_code==200
    assert client.get('/api/plans/'+pid).status_code==404
print(json.dumps({'startup':True,'recommendation':True,'decision':True,'sqlite_backup_restore':True,'delete':True,'operator_check':True,'storage':'temporary SQLite','external_api_verified':False}))
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=90,
        )
        if result.returncode:
            raise RuntimeError(
                "격리 운영 훈련 실패. 테스트 환경에서 재현해 확인하세요: " + result.stderr[-2000:]
            )
        return json.loads(result.stdout.strip().splitlines()[-1])


if __name__ == "__main__":
    print(json.dumps(rehearse(), ensure_ascii=False, indent=2))
