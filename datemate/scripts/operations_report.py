"""Local-only aggregate report. Never exports addresses, tokens or user text."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import store

def report():
    with store.connect() as db:
        providers=[dict(r) for r in db.execute('SELECT provider,SUM(calls) calls,SUM(errors) errors,ROUND(SUM(elapsed_ms)*1.0/NULLIF(SUM(calls),0),1) average_ms FROM provider_metrics GROUP BY provider')]
        rows=db.execute("SELECT payload FROM experience_events WHERE kind='recommendation'").fetchall()
    values=[json.loads(r['payload']) for r in rows]
    for provider in providers:
        for key in ('calls','errors'):provider[key]=int(provider[key])
        if provider['average_ms'] is not None:provider['average_ms']=float(provider['average_ms'])
    durations=sorted(v['elapsed_ms'] for v in values if 'elapsed_ms' in v)
    return {'providers':providers,'recommendations':len(values),
            'empty_results':sum(v.get('plans')==0 for v in values),
            'p95_ms':durations[min(len(durations)-1,int(len(durations)*.95))] if durations else None,
            'billing_cost':'not_measured','scope':'Instrumented HTTP and logical SDK calls; SDK retries, token charges and actual visits are not measured.'}

if __name__=='__main__':print(json.dumps(report(),ensure_ascii=False,indent=2))
