"""Test two disposable Cloud Run-like containers sharing PostgreSQL.

Start from repository root: docker compose -f compose.test.yaml up -d --build
Run this script, then docker compose -f compose.test.yaml down.
Only the fixed local test Compose project is restarted; no production resources.
"""
import json
import subprocess
import time
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[2]
FIRST='http://127.0.0.1:18080'
SECOND='http://127.0.0.1:18081'
HEADERS={'Host':'datemate.test','X-Forwarded-Proto':'https','Origin':'https://datemate.test'}


def ready(base):
    deadline=time.monotonic()+90
    while time.monotonic()<deadline:
        try:
            if httpx.get(base+'/readyz',timeout=3).status_code==200:return
        except httpx.HTTPError:pass
        time.sleep(.5)
    raise AssertionError('test container did not become ready')


def main():
    ready(FIRST);ready(SECOND)
    checks={}
    with httpx.Client(headers=HEADERS,timeout=30) as client:
        home=client.get(FIRST+'/')
        assert home.status_code==200
        assert 'Secure' in home.headers['set-cookie']
        # This local harness emulates the managed TLS ingress. The application
        # correctly issues Secure cookies; explicitly forward one over loopback.
        token=home.cookies['dm_session']
        client.headers['Cookie']='dm_session='+token
        assert client.get(FIRST+'/docs').status_code==404
        assert client.get(FIRST+'/openapi.json').status_code==404
        checks['production_headers_and_private_docs']=True
        status=client.get(FIRST+'/api/status').json()
        assert all(status['counts'][mode]['chunks']>0 for mode in ('demo','real'))
        checks['places_and_documents_bootstrapped']=True
        payload={'mode':'demo','visit_date':'2026-10-31','budget':1000000,'max_leg':180}
        response=client.post(FIRST+'/api/plan-jobs',json=payload)
        assert response.status_code==202,response.text
        job=response.json()['id']
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            state=client.get(SECOND+'/api/plan-jobs/'+job).json()
            assert state['status'] not in ('failed','cancelled'),state
            if state['status']=='complete':break
            time.sleep(.2)
        assert state['status']=='complete'
        plan=state['result']['plans'][0];pid=plan['id']
        assert client.get(SECOND+'/api/plans/'+pid).status_code==200
        checks['cross_instance_job_poll_and_plan_read']=True
        share=client.post(SECOND+'/api/plans/'+pid+'/shares').json()['url'].split('#')[1]
        shared=httpx.get(FIRST+'/api/shared-plan',headers=HEADERS|{'Authorization':'Bearer '+share})
        assert shared.status_code==200 and 'conditions' not in shared.json()
        assert httpx.get(SECOND+'/api/plans/'+pid,headers=HEADERS).status_code==404
        checks['sharing_and_owner_isolation']=True
        chat=client.post(SECOND+'/api/chat/plan/'+pid,json={'question':'총비용은 얼마야?','mode':'demo'})
        assert chat.status_code==200
        review=client.put(FIRST+'/api/plans/'+pid+'/review',json={'nickname':'배포점검','rating':5,'body':'격리 환경 검사','visited':'2026-01-01'})
        assert review.status_code==200
        checks['chat_and_review']=True
        subprocess.run(['docker','compose','-f','compose.test.yaml','restart','web','web2'],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
        ready(FIRST);ready(SECOND)
        assert client.get(FIRST+'/api/plans/'+pid).status_code==200
        assert client.get(SECOND+'/api/plans/'+pid+'/reviews').json()['count']>=1
        assert client.get(SECOND+'/api/chat/plan/'+pid+'?mode=demo').json()['messages']
        checks['data_survives_both_container_restarts']=True
        assert client.delete(SECOND+'/api/me/data').status_code==200
        assert client.get(FIRST+'/api/plans/'+pid).status_code==404
        assert httpx.get(FIRST+'/api/shared-plan',headers=HEADERS|{'Authorization':'Bearer '+share}).status_code==404
        checks['deletion_and_share_revocation_across_instances']=True
    print(json.dumps(checks,indent=2))


if __name__=='__main__':main()
