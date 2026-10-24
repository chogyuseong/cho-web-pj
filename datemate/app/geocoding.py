"""도로명·지번 주소를 네이버 공식 Geocoding으로 검색한다."""
import os
import re
import httpx
from .telemetry import observed_http
from .models import Point


def district_at(lat,lon):
    """지도에서 선택한 좌표의 행정구역을 공식 Reverse Geocoding으로 확인."""
    if not os.getenv('NAVER_MAPS_KEY_ID') or not os.getenv('NAVER_MAPS_KEY'):return ''
    try:
        r=observed_http(httpx.get,'https://maps.apigw.ntruss.com/map-reversegeocode/v2/gc',
                    params={'coords':f'{lon},{lat}','orders':'admcode','output':'json'},
                    headers={'x-ncp-apigw-api-key-id':os.environ['NAVER_MAPS_KEY_ID'],'x-ncp-apigw-api-key':os.environ['NAVER_MAPS_KEY']},timeout=5)
        r.raise_for_status()
        region=r.json().get('results',[{}])[0].get('region',{})
        if not region.get('area1',{}).get('name','').startswith('서울'):return ''
        return ' '.join(region.get(k,{}).get('name','') for k in ('area2','area3')).strip()
    except (httpx.HTTPError,ValueError,IndexError,KeyError,TypeError):return ''

def search_address(query):
    district=re.fullmatch(r'(?:서울(?:특별시)?\s*)?([가-힣]{1,6}구)',query.strip())
    from .seoul_districts import DISTRICT_ADDRESSES
    if district and district[1] in DISTRICT_ADDRESSES:query='서울 '+district[1]+' '+DISTRICT_ADDRESSES[district[1]]
    key_id=os.getenv('NAVER_MAPS_KEY_ID')
    key=os.getenv('NAVER_MAPS_KEY')
    if not key_id or not key:
        return dict(status='key_missing',results=[],message='주소 검색에는 네이버 Maps 키 설정이 필요합니다. 지금은 지도에서 위치를 선택해 주세요.')
    # 개인 주소를 로그·영구 캐시에 남기지 않으며, 버튼으로 요청할 때만 호출한다.
    try:
        with httpx.Client(timeout=10) as client:
            response=observed_http(client.get,'https://maps.apigw.ntruss.com/map-geocode/v2/geocode',
                params={'query':query,'count':5},headers={'Accept':'application/json',
                'x-ncp-apigw-api-key-id':key_id,'x-ncp-apigw-api-key':key})
            response.raise_for_status()
            data=response.json()
        if data.get('status')!='OK':raise ValueError('provider_error')
        results=[]
        for row in data.get('addresses',[]):
            name=row.get('roadAddress') or row.get('jibunAddress')
            if not name:continue
            try:
                point=Point(name=name,lat=float(row['y']),lon=float(row['x']))
            except (ValueError,KeyError,TypeError):continue
            if district:point=point.model_copy(update={'name':district[1]+' 대표 위치 · '+name})
            results.append(dict(**point.model_dump(),road_address=row.get('roadAddress'),jibun_address=row.get('jibunAddress')))
        return dict(status='ok',results=results,provider='NAVER Maps',message='' if results else '주소를 찾지 못했습니다. 시·군·구와 도로명 또는 지번을 함께 입력하거나 지도에서 선택해 주세요.')
    except (httpx.HTTPError,ValueError,KeyError,TypeError):
        return dict(status='unavailable',results=[],message='주소 검색에 연결하지 못했습니다. 잠시 후 다시 시도하거나 지도에서 위치를 선택해 주세요.')
