"""도로명·지번 주소를 네이버 공식 Geocoding으로 검색한다."""
import os
import httpx
from .models import Point

def search_address(query):
    key_id=os.getenv('NAVER_MAPS_KEY_ID')
    key=os.getenv('NAVER_MAPS_KEY')
    if not key_id or not key:
        return dict(status='key_missing',results=[],message='주소 검색에는 네이버 Maps 키 설정이 필요합니다. 지금은 지도에서 위치를 선택해 주세요.')
    # 개인 주소를 로그·영구 캐시에 남기지 않으며, 버튼으로 요청할 때만 호출한다.
    try:
        with httpx.Client(timeout=10) as client:
            response=client.get('https://maps.apigw.ntruss.com/map-geocode/v2/geocode',
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
            results.append(dict(**point.model_dump(),road_address=row.get('roadAddress'),jibun_address=row.get('jibunAddress')))
        return dict(status='ok',results=results,provider='NAVER Maps',message='' if results else '주소를 찾지 못했습니다. 시·군·구와 도로명 또는 지번을 함께 입력하거나 지도에서 선택해 주세요.')
    except (httpx.HTTPError,ValueError,KeyError,TypeError):
        return dict(status='unavailable',results=[],message='주소 검색에 연결하지 못했습니다. 잠시 후 다시 시도하거나 지도에서 위치를 선택해 주세요.')
