"""Small live-provider acceptance sample; not a satisfaction survey."""
import json,time
from pathlib import Path
import httpx
cases=[('종로구',37.573,126.979,'카페 투어, 볼링 제외',100000),('은평구',37.603,126.929,'비 오는 날 실내에서 카페',50000),('구로구',37.495,126.887,'전시와 산책',80000),('성수동',37.5446,127.0559,'맛집 탐방',30000)]
results=[]
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=30) as client:
    for area,lat,lon,text,budget in cases:
        started=time.monotonic()
        payload=dict(mode='real',visit_date='2026-10-24',allow_estimates=True,allow_price_estimates=True,origin=dict(name=area,lat=lat,lon=lon),request=text,budget=budget)
        response=client.post('/api/plan-jobs',json=payload);response.raise_for_status();key=response.json()['id']
        stages=set()
        while time.monotonic()-started<240:
            response=client.get('/api/plan-jobs/'+key);response.raise_for_status();state=response.json();stages.add(state.get('stage'))
            if state['status']!='running':break
            time.sleep(1)
        assert state['status']=='complete',(area,state)
        plans=state['result']['plans'];assert plans,(area,state['result'].get('reasons'))
        for p in plans:
            assert p['conditions']['origin']==payload['origin']
            assert p['conditions']['budget']==budget
            assert len(p['place_evidence'])==len(p['places'])
            assert p['decision_summary']['travel_minutes']>=0
            assert not any(c['state'] in ('unmet','unknown') and c['condition'] in p['conditions'].get('hard_constraints',[]) for c in p.get('condition_checks',[]))
        results.append(dict(area=area,plans=len(plans),seconds=round(time.monotonic()-started,1),stages=sorted(x for x in stages if x),adjusted=sum(bool(p.get('search_adjustments')) for p in plans)))
        print(json.dumps(results[-1],ensure_ascii=True),flush=True)
Path('docs/live-acceptance.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
