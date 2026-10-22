"""서울 25개 자치구 대표 주소에서 같은 조건으로 추천 범위를 점검한다."""
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import ROOT
from app.geocoding import search_address
from app.models import Conditions
from app.planner import recommend, candidates
from app.routes import leg

ADDRESSES={
    '종로구':'종로1길 36','중구':'창경궁로 17','용산구':'녹사평대로 150','성동구':'고산자로 270',
    '광진구':'자양로 117','동대문구':'천호대로 145','중랑구':'봉화산로 179','성북구':'보문로 168',
    '강북구':'도봉로89길 13','도봉구':'마들로 656','노원구':'노해로 437','은평구':'은평로 195',
    '서대문구':'연희로 248','마포구':'월드컵로 212','양천구':'목동동로 105','강서구':'화곡로 302',
    '구로구':'가마산로 245','금천구':'시흥대로73길 70','영등포구':'당산로 123','동작구':'장승배기로 161',
    '관악구':'관악로 145','서초구':'남부순환로 2584','강남구':'학동로 426','송파구':'올림픽로 326','강동구':'성내로 25',
}
SCENARIOS={
    '도보·전체':dict(transport='walk'),
    '대중교통·전체':dict(transport='transit'),
    '대중교통·비 오는 날':dict(transport='transit',date_category='날씨별',date_subcategory='비 오는 날'),
    '대중교통·카페':dict(transport='transit',themes=['카페·미식']),
    '대중교통·즐거운 데이트':dict(transport='transit',date_category='콘셉트별',date_subcategory='즐거운 데이트'),
}

def write_report(report):
    lines=['# 서울 25개 구 추천 범위 점검','',
        '각 구의 대표 도로명 주소 1곳을 네이버 Maps로 지오코딩하여 실제 장소 추천 로직을 점검했습니다. 각 구 전체 또는 모든 주소를 검증한 것은 아닙니다. 사진 API는 이 점검에 포함하지 않았습니다.','',
        '공통 조건: 2026-10-24, 11~19시, 2명, 예산 10만원, 3곳, 장소당 60분, 구간 이동 제한 30분. 이동·체류 추정을 허용했습니다. 실제 대중교통 시간표나 영업 여부를 검증한 결과는 아닙니다.','',
        '| 조건 | 코스 제공 / 대표 출발지 | 조건 차이가 있는 대안 |','|---|---|---|']
    for label,result in report['summary'].items():lines.append(f"| {label} | {result['passed']} / {result['total']} | {result.get('best_effort',0)} |")
    lines += ['', '| 구 | 도보·전체 | 대중교통·전체 | 비 오는 날 | 카페 | 즐거운 데이트 |', '|---|---|---|---|---|---|']
    for district in ADDRESSES:
        rows=[r for r in report['rows'] if r['district']==district]
        cells=[('대안 제공' if r.get('best_effort') else '기존 검증 통과') if r['plans'] else f"실패 (최근접 {r['nearest_minutes']}분)" for r in rows]
        lines.append('| '+district+' | '+' | '.join(cells)+' |')
    lines += ['', '## 판단','',
        '조건을 모두 만족하는 코스가 없으면 가까운 대안 코스를 제공합니다. 원래 입력 조건은 보존하며 이동 제한·테마·실내외·종료시간 등의 차이는 결과에 표시합니다. 대안 제공은 원래 조건을 만족했다는 뜻이 아닙니다. 미확인 가격·운영정보도 그대로 남겨둡니다.','',
        '다음 보강 대상은 실패 구의 주변 카페·실내 전시·놀이·공방 데이터입니다. 지역 검색 API의 권한 및 장소 운영정보를 확보해야 주변 실제 업체 검색을 확장할 수 있습니다.','',
        '상세 좌표: `seoul-district-origins.json`. 개별 결과·최근접 시간·실패 사유: `seoul-coverage.json`. 재실행: `python scripts/check_seoul_coverage.py`.']
    (ROOT/'docs/seoul-coverage.md').write_text('\n'.join(lines)+'\n','utf-8')

def main():
    origin_file=ROOT/'docs/seoul-district-origins.json'
    if origin_file.exists():origins=json.loads(origin_file.read_text('utf-8'))
    else:
        origins={}
        for district,address in ADDRESSES.items():
            response=search_address('서울 '+district+' '+address)
            if not response['results']:raise RuntimeError(district+' 대표 주소 좌표 확인 실패')
            origins[district]=response['results'][0]
        origin_file.write_text(json.dumps(origins,ensure_ascii=False,indent=2),'utf-8')
    rows=[];started=time.perf_counter()
    for district,origin in origins.items():
        for label,patch in SCENARIOS.items():
            c=Conditions(mode='real',allow_estimates=True,origin={k:origin[k] for k in ('name','lat','lon')},
                visit_date=date(2026,10,24),**patch)
            pool=candidates(c)
            times=[leg(c.origin.model_dump(),p,c)['minutes'] for p in pool]
            result=recommend(c)
            rows.append(dict(district=district,scenario=label,status=result['status'],plans=len(result['plans']),
                best_effort=result['status']=='best_effort',deviations=result['plans'][0].get('deviations',[]) if result['plans'] else [],
                nearest_minutes=min(times) if times else None,reachable_candidates=sum(t<=c.max_leg for t in times),
                reasons=result.get('reasons',[]),places=[p['name'] for p in result['plans'][0]['places']] if result['plans'] else []))
        print(district+': '+str(sum(r['plans']>0 for r in rows if r['district']==district))+'/5',flush=True)
    summary={label:dict(passed=sum(r['plans']>0 for r in rows if r['scenario']==label),
        best_effort=sum(r['best_effort'] for r in rows if r['scenario']==label),total=25) for label in SCENARIOS}
    report=dict(checked_at=datetime.now(timezone.utc).isoformat(),scope='25개 구의 대표 주소 각 1곳 · 구 전체 위치 보장 아님',
        conditions=dict(visit_date='2026-10-24',start='11:00',end='19:00',people=2,budget=100000,count=3,max_leg=30,stay_minutes=60,allow_estimates=True),
        summary=summary,rows=rows,elapsed_seconds=round(time.perf_counter()-started,2))
    (ROOT/'docs/seoul-coverage.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    write_report(report)
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
