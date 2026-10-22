"""실제 장소로 오인하지 않도록 모든 이름과 운영 조건을 가상으로 표시."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
themes = ['문화·예술','카페·미식','산책·풍경','체험·제작','휴식·힐링','오락·놀이','레저·활동']
names = ['작은 전시실','느린 커피','초록 산책길','도자기 작업실','책과 쉼','보드게임 라운지','클라이밍 스튜디오']
rows = []
for i in range(28):
    cat = i%7
    price = [8000,6500,0,18000,4000,10000,15000][cat]
    rows.append(dict(id=f'demo-{i+1:02}',name=f'가상 {names[cat]} {i//7+1}',region='서울',category=themes[cat],
        tags=[themes[cat], '산책' if cat==2 else '실내'],address='가상 시연 구역 (실제 주소 아님)',
        lat=37.573+(i%7)*.0012,lon=126.982+(i//7)*.002,
        description=f'{themes[cat]} 일정 계산용 가상 장소입니다. 실제 방문할 수 없습니다.', activities=[themes[cat]],
        price=[price,price+2000] if cat==1 else [price,price],price_unit='person',price_status='estimated',
        hours=[600,1260],closed_days=[0] if cat==0 else [],breaks=[[900,930]] if cat==1 else [],last_entry=1200,
        reservation=cat==3,reservation_url=None,stay=[60,50,45,70,50,60,60][cat],
        stay_basis='시연용 설계 가정',setting='outdoor' if cat==2 else 'indoor',source='demo:fixture',
        checked_at='2026-10-21',source_type='가상 시연 데이터',license='프로젝트 자체 생성 가상 데이터',
        photos=[],videos=[],rating=None,atmosphere=None,demo=True))
(ROOT/'data').mkdir(exist_ok=True)
(ROOT/'data'/'demo_places.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
docs=[dict(id='demo-guide-'+p['id'],place_id=p['id'],title=p['name']+' 가상 이용 안내',
    body=f'{p["name"]}은 실제로 존재하지 않는 가상 시연 장소입니다. 분류는 {p["category"]}입니다. '
         f'시연용 체류 시간은 {p["stay"]}분입니다. 운영시간과 가격은 테스트 조건으로만 사용합니다. '
         '실제 방문, 실제 예약, 실제 외부 평점으로 사용할 수 없습니다. 사진과 영상은 확보하지 않았습니다.',
    source='demo:guide:'+p['id'],type='가상 안내 문서',collected_at='2026-10-21',license='프로젝트 자체 생성 데모',own=True,page=None) for p in rows]
(ROOT/'data'/'demo_documents.json').write_text(json.dumps(docs,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'Demo fixtures: {len(rows)} (not real places)')
