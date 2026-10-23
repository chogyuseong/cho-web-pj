import json
from pathlib import Path
from check_10000_inputs import preferences

root=Path(__file__).resolve().parents[1]
rows=[];parts=[]
for offset in (0,1250,2500,3750):
    base=root/'docs'/f'recommendation-matrix-1250-offset{offset}'
    parts.append(json.loads(base.with_suffix('.json').read_text('utf-8')))
    rows.extend(json.loads(line) for line in base.with_suffix('.jsonl').read_text('utf-8').splitlines())
assert len(rows)==5000 and len({row['input'] for row in rows})==5000
assert {row['input'] for row in rows}=={text for text,_ in preferences()}
summary=dict(total=len(rows),passed=sum(row['passed'] for row in rows),failed=sum(not row['passed'] for row in rows),
    resumed_rows=sum(part['resumed_rows'] for part in parts),scope=parts[0]['scope'],parts=parts)
(root/'docs/recommendation-matrix-5000.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),'utf-8')
with (root/'docs/recommendation-matrix-5000.jsonl').open('w',encoding='utf-8') as output:
    for row in rows:output.write(json.dumps(row,ensure_ascii=False)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k!='parts'}))
