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

def leg(a,b,conditions,force_api=False):
    # Candidate combinations use cheap estimates; verify only the selected plans.
    if _candidate_search.get() and conditions.mode=='real' and not force_api:conditions=conditions.model_copy(update={'allow_estimates':True})
    base=dict(origin=a['name'],destination=b['name'],link=app_link(a,b,conditions.transport),
              status='unavailable',minutes=None,walking=None,distance_km=None,cost=None,source=None,
              toll=None,fuel=None,transfers=None,checked_at=None,path=[])
    if conditions.mode=='real' and conditions.transport in ('walk','transit') and (force_api or not conditions.allow_estimates):
        from .route_providers import route
        return dict(base,**route(a,b,conditions.transport,conditions.people))
    if conditions.mode=='demo' or (conditions.allow_estimates and not force_api):
        km=distance(a,b) * (1 if conditions.mode=='demo' else 1.35)
        speed={'walk':4,'bicycle':12,'car':25,'transit':18}[conditions.transport]
        minutes=max(1,math.ceil(km/speed*60))+ (8 if conditions.transport=='transit' else 0)
        costs={'walk':0,'bicycle':None,'car':round(km*200),'transit':1500*conditions.people}
        return dict(base,status='estimated',minutes=minutes,walking=minutes if conditions.transport=='walk' else (6 if conditions.transport=='transit' else 0),
            distance_km=round(km,3),cost=costs[conditions.transport],source='가상 시연: 직선거리 ÷ 가정 속도. 실제 경로 아님' if conditions.mode=='demo' else '직선거리 × 1.35 기반 이동 추정 · 실제 길찾기 미반영',
            planning_minutes_range=[minutes,math.ceil(minutes*1.5)+5],
            planning_note='여유시간 시나리오: 추정 시간의 1.5배 + 5분. 통계적 예측 범위가 아니며 횡단보도·대기·주차는 길찾기로 확인해 주세요.',
            assumption=f'속도 {speed}km/h'+(' + 대기 8분, 도보 6분 포함 가정' if conditions.transport=='transit' else ''),
            fuel=costs['car'] if conditions.transport=='car' else None,toll=None)
    if conditions.transport!='car' or not (os.getenv('NAVER_MAPS_KEY_ID') and os.getenv('NAVER_MAPS_KEY')):
        return dict(base,source='실제 경로 공급자 미연결 또는 키 누락')
    key=f'route-v2:{a["lat"]},{a["lon"]}:{b["lat"]},{b["lon"]}:car'
    hit=store.cached(key)
    if hit:
        from .request_usage import cache_hit
        cache_hit();return hit
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
