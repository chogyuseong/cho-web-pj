"""One real recommendation in disposable storage, using a fixed public area."""
import json
import os
import sys
import tempfile
import subprocess
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    if '--worker' not in sys.argv:
        # Chroma keeps Windows memory-mapped files open until process exit.
        # Let a parent own cleanup after the worker releases those handles.
        with tempfile.TemporaryDirectory(prefix='datemate-real-course-') as runtime:
            env=os.environ.copy();env.update(DATEMATE_RUNTIME=runtime,DATABASE_URL='',DATEMATE_ENV='development',DATEMATE_PUBLIC_ORIGIN='',DATEMATE_ALLOWED_HOSTS='')
            env.pop('K_SERVICE',None)
            subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker'],env=env,check=True,timeout=240)
        return
    if os.environ.get('DATEMATE_RUNTIME'):
        runtime=os.environ['DATEMATE_RUNTIME']
        os.environ.update(DATEMATE_RUNTIME=runtime,DATEMATE_BACKUP_DIR='',EMBEDDING_MODE='demo')
        from app.main import app
        from app.catalog import places
        from app.indexing import index_places
        from app import store
        from fastapi.testclient import TestClient
        with TestClient(app) as client:
            index_places(places('real'),'real')
            payload=dict(mode='real',visit_date='2026-10-31',origin={'name':'연남동 공개 점검 지역','lat':37.562,'lon':126.925},
                         request='연남동에서 카페 보고 산책하고 식사하고 싶어요',count=3,people=2,budget=100000,
                         max_leg=45,transport='walk',allow_estimates=True,include_meal=True)
            started=time.monotonic()
            response=client.post('/api/plan-jobs',json=payload)
            if response.status_code!=202:
                print(json.dumps({'status':'rejected','http_status':response.status_code}));return
            key=response.json()['id'];deadline=time.monotonic()+150
            while time.monotonic()<deadline:
                state=client.get('/api/plan-jobs/'+key).json()
                if state['status']!='running':break
                time.sleep(.3)
            else:
                client.delete('/api/plan-jobs/'+key)
                state={'status':'timeout'}
            result=state.get('result',{});plans=result.get('plans',[])
            checks=[]
            for plan in plans:
                checks.append({'places':len(plan['places']),'real_places':all(not p.get('demo') for p in plan['places']),
                    'has_timeline':len(plan['timeline'])==len(plan['places']),
                    'has_costs':bool(plan.get('costs')),
                    'owner_can_read':client.get('/api/plans/'+plan['id']).status_code==200})
            report={'status':state['status'],'elapsed_ms':round((time.monotonic()-started)*1000),
                    'plans':len(plans),'checks':checks,'stage':state.get('stage'),
                    'semantic_embedding_tested':False,'production_storage_used':False}
            print(json.dumps(report,ensure_ascii=True,indent=2))
        from app.plan_jobs import _pool
        _pool.shutdown(wait=True)


if __name__=='__main__':main()
