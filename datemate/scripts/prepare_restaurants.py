import json
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import ROOT
from app.geocoding import search_address

rows=[]
for entry in json.loads((ROOT/'data/restaurant_sources.json').read_text('utf-8')):
    response=search_address(entry['address'])
    if not response['results']:raise RuntimeError('식당 주소 확인 실패: '+entry['name'])
    point=response['results'][0]
    if not (37.4<point['lat']<37.75 and 126.7<point['lon']<127.3):raise ValueError('서울 범위 이탈')
    row={key:None for key in ['price','price_unit','hours','closed_days','breaks','last_entry','reservation','stay','stay_basis','rating']}
    row.update(entry,lat=point['lat'],lon=point['lon'],region='서울',category='카페·미식',setting='indoor',demo=False,
        tags=[entry['cuisine']],description=entry['cuisine']+' 식사를 할 수 있는 공식 가이드 소개 식당입니다.',
        source_type=entry['recognition'],checked_at=datetime.now(timezone.utc).isoformat(),photos=[],videos=[],
        license='장소 사실 정보 요약 · 원문 권리 별도',image_keywords=entry.get('image_keywords',[entry['name']]))
    rows.append(row)
(ROOT/'data/restaurants.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),'utf-8')
print('restaurants',len(rows))
