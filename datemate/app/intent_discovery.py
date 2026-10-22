"""Supplement requested venue types with verified public local-search coordinates."""
import hashlib
from datetime import datetime,timezone
from urllib.parse import quote
from . import store
from .request_intent import intent,INTENTS
from .image_search import search_enabled,plain
from .discovery import local_lookup
from .quality import in_area


def discover_requested_places(c):
    keys=intent(c)['intents']
    if c.mode!='real' or not keys or not search_enabled():return dict(status='not_available',resolved=0)
    area=(c.area_center or c.origin).name.replace(' 중심','').replace(' 지역 중심','')
    fingerprint=hashlib.sha256(str([area,(c.area_center or c.origin).model_dump(),c.neighborhood_radius_km,keys]).encode()).hexdigest()
    cachekey='intent-local-v1:'+fingerprint
    cached=store.cached(cachekey)
    if cached:return cached
    count=0;statuses=[]
    for key in keys[:4]:
        term=INTENTS[key][1][0]
        items,status=local_lookup(term,'서울 '+area);statuses.append(status)
        for item in items:
            category=plain(item.get('category',''));name=plain(item.get('title',''))
            address=plain(item.get('roadAddress') or item.get('address',''))
            if not name or not address.startswith('서울'):continue
            checks={'cafe':['카페','디저트','베이커리'],'meal':['음식점','한식','양식','일식','중식'],
                'culture':['미술','박물관','전시','갤러리'],'museum':['박물관','문화재','유적'],
                'book':['서점','도서관','북카페','책방'],'walk':['공원','정원','산책','숲'],
                'game':['방탈출','보드','오락','게임','만화'],'workshop':['공방','공예','체험'],
                'activity':['스포츠','레저','볼링','클라이밍'],'view':['전망','공원','관광'],'shopping':['쇼핑','소품','편집']}
            if not any(word in category for word in checks.get(key,[])):continue
            if key=='meal' and ('카페' in category or '디저트' in category):continue
            try:
                lon,lat=float(item['mapx']),float(item['mapy'])
                if abs(lon)>180:lon/=10000000
                if abs(lat)>90:lat/=10000000
                if not (37.4<lat<37.75 and 126.7<lon<127.3):continue
            except (KeyError,ValueError,TypeError):continue
            if not in_area(dict(lat=lat,lon=lon),c):continue
            pid='discovered:'+hashlib.sha256((name+address).encode()).hexdigest()[:20]
            source='https://map.naver.com/p/search/'+quote(name+' '+address)
            row=dict(id=pid,name=name,address=address,lat=lat,lon=lon,region='서울',demo=False,
                category=INTENTS[key][0],themes=[INTENTS[key][0]],tags=[key,category],meal=key=='meal',
                description=category,source=source,source_type='네이버 지역 검색 · 요청 활동 유형 연결',
                checked_at=datetime.now(timezone.utc).isoformat(),discovery_verification='네이버 업체 분류·상호·주소·좌표 연결 · 영업 여부 별도 확인',
                price=None,price_unit='person',hours=None,closed_days=None,breaks=None,last_entry=None,
                reservation=None,stay=None,stay_basis=None,rating=None,setting=None,photos=[],videos=[],license='검색 결과')
            # Preserve richer blog evidence for a previously resolved venue.
            if not store.cached('discovered-place:'+pid):store.cache('discovered-place:'+pid,row,604800)
            count+=1
    result=dict(status='available' if count else 'not_found',resolved=count,query_area=area,
                permission_required='permission_required' in statuses)
    store.cache(cachekey,result,900 if count else 30)
    return result
