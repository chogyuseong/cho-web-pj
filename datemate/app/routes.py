import math
import os
from contextvars import ContextVar
from contextlib import contextmanager
from urllib.parse import urlencode
from . import store

_candidate_search=ContextVar('candidate_route_search',default=False)


@contextmanager
def candidate_routes():
    token=_candidate_search.set(True)
    try:yield
    finally:_candidate_search.reset(token)

def distance(a,b):
    lat1,lat2=map(math.radians,[a['lat'],b['lat']])
    delta=math.radians(b['lon']-a['lon'])
    return 6371*2*math.asin(min(1,math.sqrt(math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(delta/2)**2)))

def app_link(a,b,mode):
    route={'car':'car','transit':'public','walk':'walk','bicycle':'bicycle'}[mode]
    return 'nmap://route/'+route+'?'+urlencode(dict(slat=a['lat'],slng=a['lon'],sname=a['name'],dlat=b['lat'],dlng=b['lon'],dname=b['name'],appname='datemate.local'))

# 대중교통 구간 추정의 가정값. 실제 대중교통 길찾기(지하철·버스 노선)는 연결돼 있지 않다 — 네이버 지도 API 에는 공개된
# 대중교통 길찾기가 없고(자동차 Directions 만), 다른 공급자(예: ODsay)는 키·약관이 필요해 2026-11-18 사용자가 '추정임을 표시'로 정했다.
# 그래서 지하철인지 버스인지 구분하지 않고, 아래 값으로 시간·요금을 만든다. 값을 바꾸면 화면 설명(TRANSIT_BASIS)도 저절로 따라간다.
#   시간 = 직선거리 × 1.35 ÷ TRANSIT_SPEED_KMH + TRANSIT_WAIT_MINUTES,  도보 = TRANSIT_WALK_MINUTES(대기 시간 안에 포함된 걷기로 셈)
#   요금 = TRANSIT_FARE_PER_PERSON × 인원(구간마다 새로 타는 것으로 보고 환승 할인은 넣지 않음)
# 실제 노선을 붙이려면 여기서 공급자를 불러 status='api', transit_basis 에 노선 요약을 넣으면 된다(화면은 status 로 '추정' 표시를 뗀다).
TRANSIT_SPEED_KMH=18
TRANSIT_WAIT_MINUTES=8
TRANSIT_WALK_MINUTES=6
TRANSIT_FARE_PER_PERSON=1500
# 화면(plan-detail.js renderDetail)이 대중교통 구간이 있는 일정 위에 그대로 보여 주는 문장.
TRANSIT_BASIS=(f'지하철·버스를 구분하지 않은 추정이에요. 평균 시속 {TRANSIT_SPEED_KMH}km, 구간마다 대기 {TRANSIT_WAIT_MINUTES}분'
               f'(그중 도보 {TRANSIT_WALK_MINUTES}분), 요금 1인 {TRANSIT_FARE_PER_PERSON:,}원(환승 할인 없음)으로 계산했어요.')


def leg(a,b,conditions,force_api=False):
    # Candidate combinations use cheap estimates; verify only the selected plans.
    if _candidate_search.get() and conditions.mode=='real' and not force_api:conditions=conditions.model_copy(update={'allow_estimates':True})
    base=dict(origin=a['name'],destination=b['name'],mode=conditions.transport,link=app_link(a,b,conditions.transport),
              status='unavailable',minutes=None,walking=None,distance_km=None,cost=None,source=None,
              toll=None,fuel=None,transfers=None,checked_at=None,path=[])
    if conditions.mode=='demo' or (conditions.allow_estimates and not force_api):
        km=distance(a,b) * (1 if conditions.mode=='demo' else 1.35)
        transit=conditions.transport=='transit'
        speed={'walk':4,'bicycle':12,'car':25,'transit':TRANSIT_SPEED_KMH}[conditions.transport]
        minutes=max(1,math.ceil(km/speed*60))+(TRANSIT_WAIT_MINUTES if transit else 0)
        costs={'walk':0,'bicycle':None,'car':round(km*200),'transit':TRANSIT_FARE_PER_PERSON*conditions.people}
        estimate=dict(base,status='estimated',minutes=minutes,walking=minutes if conditions.transport=='walk' else (TRANSIT_WALK_MINUTES if transit else 0),
            distance_km=round(km,3),cost=costs[conditions.transport],source='가상 시연: 직선거리 ÷ 가정 속도. 실제 경로 아님' if conditions.mode=='demo' else '직선거리 × 1.35 기반 이동 추정 · 실제 길찾기 미반영',
            planning_minutes_range=[minutes,math.ceil(minutes*1.5)+5],
            planning_note='여유시간 시나리오: 추정 시간의 1.5배 + 5분. 통계적 예측 범위가 아니며 횡단보도·대기·주차는 길찾기로 확인해 주세요.',
            assumption=f'속도 {speed}km/h'+(f' + 대기 {TRANSIT_WAIT_MINUTES}분, 도보 {TRANSIT_WALK_MINUTES}분 포함 가정' if transit else ''),
            fuel=costs['car'] if conditions.transport=='car' else None,toll=None)
        # 대중교통 구간에만: 지하철·버스 구분 없는 추정이라는 설명(화면이 일정 위에 한 번 보여 줌). 다른 수단 구간에는 키 자체가 없다.
        if transit:estimate['transit_basis']=TRANSIT_BASIS
        return estimate
    if conditions.transport!='car' or not (os.getenv('NAVER_MAPS_KEY_ID') and os.getenv('NAVER_MAPS_KEY')):
        return dict(base,source='실제 경로 공급자 미연결 또는 키 누락')
    key=f'route-v2:{a["lat"]},{a["lon"]}:{b["lat"]},{b["lon"]}:car'
    hit=store.cached(key)
    if hit:
        from .request_usage import cache_hit
        cache_hit('driving_route');return dict(hit,mode='car')
    from .collection import fetch_json
    try:
        data=fetch_json('https://maps.apigw.ntruss.com/map-direction/v1/driving',
            params=dict(start=f'{a["lon"]},{a["lat"]}',goal=f'{b["lon"]},{b["lat"]}'),
            headers={'x-ncp-apigw-api-key-id':os.getenv('NAVER_MAPS_KEY_ID'),'x-ncp-apigw-api-key':os.getenv('NAVER_MAPS_KEY')})
        route=next(iter(data['route'].values()))[0]
        summary=route['summary']
        path=route.get('path') or []  # Directions 좌표 순서: [경도, 위도].
        path=[xy for xy in path if isinstance(xy,list) and len(xy)==2
              and all(isinstance(v,(int,float)) and math.isfinite(v) for v in xy)
              and -180<=xy[0]<=180 and -90<=xy[1]<=90]
        fuel,toll=summary.get('fuelPrice'),summary.get('tollFare')
        result=dict(base,status='api',minutes=math.ceil(summary['duration']/60000),walking=None,
            distance_km=summary['distance']/1000,cost=fuel+toll if fuel is not None and toll is not None else None,
            fuel=fuel,toll=toll,path=path,source='네이버 Directions 5 (조회 시점 교통, 미래 예측 아님)',checked_at=data.get('currentDateTime'))
        store.cache(key,result,300)
        return result
    except Exception:
        return dict(base,source='경로 API 호출 실패. 키·사용 권한을 확인하세요.')
