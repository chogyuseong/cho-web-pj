"""공식 안내에서 확인한 장소 주소를 지오코딩한다. 키와 개인 주소는 저장하지 않는다."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import ROOT
from app.geocoding import search_address

sources=json.loads((ROOT/'data/curated_place_sources.json').read_text('utf-8'))
template=json.loads((ROOT/'data/real_places.json').read_text('utf-8'))[0]
rows=[]
for entry in sources:
    response=search_address(entry['address'])
    if not response['results']:raise RuntimeError('좌표 확인 실패: '+entry['name'])
    point=response['results'][0]
    if not (37.4<point['lat']<37.75 and 126.7<point['lon']<127.3):raise ValueError('서울 좌표 범위 이탈')
    row=dict(template)
    row.update({k:None for k in ('price','price_unit','hours','closed_days','breaks','last_entry','reservation','reservation_url','stay','stay_basis','rating','atmosphere','wikipedia')})
    row.update(entry,lat=point['lat'],lon=point['lon'],region='서울',demo=False,tags=entry['themes'],activities=[],photos=[],videos=[],
        source_type='공식 관광·운영 안내의 장소 정보 / 운영 조건 별도 확인',license='장소 사실 정보만 요약 · 원문 권리 별도',
        checked_at=datetime.now(timezone.utc).isoformat(),classification_basis='공식 안내 활동 및 시설에 따른 복수 테마 분류',coordinate_source='NAVER Maps Geocoding')
    row['image_keywords']={
        'seoul:runningman-insadong':['런닝맨','인사동'],
        'seoul:dynamicmaze-insadong':['다이나믹메이즈','인사동'],
        'Q121406424':['하이커','그라운드'],
        'seoul:ssamziegil-workshop':['쌈지길','공방'],
        'seoul:bukchon-craft':['북촌','공예'],
        'seoul:osulloc-bukchon':['오설록','북촌'],
        'seoul:beautiful-tea-museum':['차박물관'],
        'seoul:kyungin-teahouse':['경인','다원'],
    }[entry['id']]
    rows.append(row)
(ROOT/'data/curated_places.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),'utf-8')
print('준비한 실제 장소:',len(rows))
