"""Run the 5,000 preference inputs through /api/plans with controlled venue fixtures."""
import os
import sys
import json
import time
import argparse
import tempfile
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from check_10000_inputs import preferences


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int,default=5000);parser.add_argument('--offset',type=int,default=0);parser.add_argument('--resume',action='store_true')
    args=parser.parse_args();limit=args.limit;offset=args.offset
    with tempfile.TemporaryDirectory(prefix='datemate-venue-matrix-') as temp:
        os.environ['DATEMATE_RUNTIME']=temp
        for key in ('GMS_KEY','NAVER_SEARCH_CLIENT_ID','NAVER_SEARCH_CLIENT_SECRET','NAVER_MAPS_KEY_ID','NAVER_MAPS_KEY'):os.environ[key]=''
        os.environ['EMBEDDING_MODE']='demo'
        from fastapi.testclient import TestClient
        from app.main import app
        from app import catalog,store
        from app.request_intent import INTENTS,matches
        prototype=json.loads((root/'data/demo_places.json').read_text('utf-8'))[0]
        original=catalog.places;current=[]
        def venues(mode='demo',visit_date=None):return current if mode=='real' else original(mode,visit_date)
        evidence=dict(query='가상 검증 지역',posts=[],matches={},status='not_found',rating_note='fixture',provider='controlled fixture',search_history=[])
        count=0;passed=0;failed=[];started=time.perf_counter()
        suffix=str(limit)+('-offset'+str(offset) if limit!=5000 else '')
        outfile=root/'docs'/('recommendation-matrix-'+suffix+'.jsonl')
        resumed=0
        if args.resume and outfile.exists():
            existing=[];lines=outfile.read_text('utf-8').splitlines()
            for index,line in enumerate(lines):
                if not line.strip():continue
                try:existing.append(json.loads(line))
                except json.JSONDecodeError:
                    if index!=len(lines)-1:raise
                    # A power loss may interrupt the final write; keep all complete cases.
                    outfile.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in existing),'utf-8')
            expected_inputs=list(preferences())[offset:offset+len(existing)]
            assert len(existing)<=limit and all(row['input']==case[0] for row,case in zip(existing,expected_inputs))
            count=len(existing);resumed=count;passed=sum(row['passed'] for row in existing)
            failed=[row for row in existing if not row['passed']][:20]
        with ExitStack() as stack,TestClient(app) as client,outfile.open('a' if args.resume else 'w',encoding='utf-8') as output:
            stack.enter_context(patch('app.catalog.places',side_effect=venues))
            stack.enter_context(patch('app.course_search.search_courses',return_value=evidence))
            stack.enter_context(patch('app.intent_discovery.discover_requested_places',return_value=dict(status='fixture',resolved=0)))
            stack.enter_context(patch('app.pricing.price_plans',side_effect=lambda plans,*args,**kwargs:plans))
            for ordinal,(text,expected) in enumerate(preferences()):
                if ordinal<offset+resumed:continue
                if count>=limit:break
                key=expected['intent'];current.clear()
                for i in range(5):
                    current.append(dict(prototype,id=f'fixture:{key}:{i}',name=f'가상 검증 {key} {i}',region='서울',demo=False,
                        lat=37.575+i*.0001,lon=126.985,category=INTENTS[key][0],themes=[INTENTS[key][0]],tags=[key],
                        address='서울 가상 검증로 '+str(i),meal=key=='meal',hours=[0,1440],closed_days=[],breaks=[],last_entry=None,
                        reservation=False,stay=30,setting=expected.get('setting','indoor'),price=[1000,1000],price_unit='person',
                        description='자동 테스트 전용 가상 장소',operations_source=None))
                excluded=expected.get('excluded')
                if excluded:current.append(dict(current[0],id='fixture:excluded',name='가상 제외 후보',category=INTENTS[excluded][0],themes=[INTENTS[excluded][0]],tags=[excluded],meal=excluded=='meal'))
                response=client.post('/api/plans',json=dict(mode='real',allow_estimates=True,visit_date='2026-10-24',
                    request=text,origin=dict(name='검증 위치',lat=37.575,lon=126.985)))
                issues=[];result=response.json();plans=result.get('plans',[])
                if response.status_code!=200:issues.append('http_'+str(response.status_code))
                if not plans:issues.append('no_plans')
                for plan in plans:
                    for field in ('people','budget','count'):
                        if plan['conditions'][field]!=expected[field]:issues.append('wrong_'+field)
                    if len(plan['places'])!=expected['count']:issues.append('wrong_venue_count')
                    if not all(matches(p,key) for p in plan['places']):issues.append('off_intent')
                    if excluded and any(matches(p,excluded) for p in plan['places']):issues.append('excluded_venue')
                count+=1;passed+=not issues
                row=dict(input=text,expected=expected,passed=not issues,issues=sorted(set(issues)),plans=len(plans),
                         venues=[[p['id'] for p in plan['places']] for plan in plans])
                output.write(json.dumps(row,ensure_ascii=False)+'\n')
                output.flush()
                if issues and len(failed)<20:failed.append(row)
                # Only the isolated test DB is cleared; no user plans are accessed.
                with store.connect() as db:
                    db.execute('DELETE FROM plans');db.execute('DELETE FROM experience_events')
                if count%250==0:print(json.dumps(dict(processed=count,passed=passed,seconds=round(time.perf_counter()-started,1))),flush=True)
        report=dict(total=count,offset=offset,resumed_rows=resumed,passed=passed,failed=count-passed,examples=failed,seconds=round(time.perf_counter()-started,2),
                    scope='local HTTP /api/plans, 5 known synthetic matching venues + excluded decoy; search/discovery/pricing mocked; real planner and persistence; no live venue availability validation')
        (root/'docs'/('recommendation-matrix-'+suffix+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
        print(json.dumps(report,ensure_ascii=True),flush=True)


if __name__=='__main__':main()
