import json,time,sys
sys.path.insert(0,str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from pathlib import Path
import httpx
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=30) as client:
    deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        data=client.get('/api/explore?limit=1').json()
        print(json.dumps({k:data.get(k) for k in ['status','collected','queries_done','queries_max','duplicates_removed','failed_queries']},ensure_ascii=True),flush=True)
        if data['status']!='collecting':break
        time.sleep(4)
    assert data['collected']==500,data
    rows=[]
    for offset in range(0,500,60):rows.extend(client.get('/api/explore',params={'offset':offset,'limit':60}).json()['places'])
    assert len(rows)==500 and len({p['id'] for p in rows})==500
    assert all(p['address'].startswith('서울') and p['source'] and p['lat'] and p['lon'] for p in rows)
    assert client.get('/api/places/'+rows[0]['id'],params={'mode':'real'}).status_code==200
    Path('docs/explore-500-audit.json').write_text(json.dumps({k:v for k,v in data.items() if k!='places'},ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS: actual 500 unique sourced Seoul venues; pagination; details API')
