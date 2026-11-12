from .search_address_text import place_query
"""Supplement requested venue types with verified public local-search coordinates."""
import hashlib
import re
from datetime import datetime,timezone
from urllib.parse import quote
from . import store
from .request_intent import intent,INTENTS
from .image_search import search_enabled,plain
from .discovery import local_lookup
from .quality import in_area
from .regions import region_from_address, korean_coordinates, same_region


def reach_km(c):
    """한 구간 이동 제한 안에서 닿는 대략적인 직선 반경. routes.leg 의 추정 속도·보정과 같은 값."""
    if c.area_center:return c.neighborhood_radius_km
    speed={'walk':4,'bicycle':12,'car':25,'transit':18}[c.transport]
    return max(1.0,speed*c.max_leg/60/1.35)


def nearby(place,c):
    from .routes import distance
    return in_area(place,c) and distance((c.area_center or c.origin).model_dump(),place)<=reach_km(c)


def search_area(name,region):
    """출발지 이름에서 검색어에 쓸 시·군·구(읍·면) 표기를 고른다. ' · ' 뒤는 설명이라 쓰지 않는다."""
    from .regions import normalize_region
    head=name.split(' · ')[0]
    district=re.search(r'[가-힣]{1,8}구(?:\s|$)',head)
    if district:return district[0].strip()
    words=[w for w in head.split() if not normalize_region(w)]
    admin=[w for w in words if re.fullmatch(r'[가-힣]{1,8}(?:시|군)',w)][:1]
    admin+=[w for w in words if re.fullmatch(r'[가-힣0-9]{1,8}(?:읍|면|동)',w)][:1]
    return ' '.join(admin or words)


def discover_requested_places(c):
    keys=intent(c)['intents']
    if c.mode!='real' or not search_enabled():return dict(status='not_available',resolved=0)
    supplement=False
    if not keys:
        from .catalog import places
        # 같은 시·도라도 출발지에서 닿지 않는 장소는 후보로 치지 않는다.
        if sum(same_region(p,c.region) and nearby(p,c) for p in places('real',c.visit_date))>=c.count:return dict(status='not_needed',resolved=0)
        keys=['cafe','walk','culture'];supplement=True
    area=(c.area_center or c.origin).name.replace(' 지역 중심','').replace(' 중심','')
    if area.startswith('지도에서 선택'):
        from .geocoding import district_at
        area=district_at(c.origin.lat,c.origin.lon) or c.region
    area=search_area(area,c.region)
    fingerprint=hashlib.sha256(str([area,(c.area_center or c.origin).model_dump(),c.neighborhood_radius_km,keys]).encode()).hexdigest()
    cachekey='intent-local-v5:'+fingerprint
    cached=store.cached(cachekey)
    if cached:return cached
    count=0;statuses=[];resolved_ids=set()
    variations={'cafe':['카페','로스터리','디저트 카페'],'culture':['전시','미술관','갤러리'],
                'walk':['공원','산책','정원'],'workshop':['공방','도자기 공방','체험 공방']}
    queries=[(key,term) for key in keys[:4] for term in variations.get(key,[INTENTS[key][1][0]])]
    for key,term in queries:
        items,status=local_lookup(term,(c.region+' '+area).strip());statuses.append(status)
        for item in items:
            category=plain(item.get('category',''));name=plain(item.get('title',''))
            address=plain(item.get('roadAddress') or item.get('address',''))
            if not name or region_from_address(address)!=c.region:continue
            if any(word in category for word in ('자동차','주차장','부동산','병원','의원')):continue
            checks={'cafe':['카페','디저트','베이커리'],'meal':['음식점','한식','양식','일식','중식'],
                'cinema':['영화관','극장','시네마'],'performance':['공연','연극','뮤지컬','극장'],
                'jazz':['재즈','라이브'],
                'culture':['미술','박물관','전시','갤러리'],'museum':['박물관','문화재','유적'],
                'book':['서점','도서관','북카페','책방'],'walk':['공원','정원','산책','숲'],
                'game':['방탈출','보드','오락','게임','만화'],'workshop':['공방','공예','체험'],
                'activity':['스포츠','레저','볼링','클라이밍'],'view':['전망','공원','관광'],'shopping':['쇼핑','소품','편집']}
            sport_keys={'climbing','bowling','table_tennis','badminton','skating','screen_golf'}
            named_sport=key in sport_keys and any(word in category for word in ('스포츠시설','체육시설','체육관','골프연습장')) and any(word in name for word in INTENTS[key][1])
            if not any(word in category for word in checks.get(key,INTENTS[key][1])) and not named_sport:continue
            if key=='meal' and ('카페' in category or '디저트' in category):continue
            try:
                lon,lat=float(item['mapx']),float(item['mapy'])
                if abs(lon)>180:lon/=10000000
                if abs(lat)>90:lat/=10000000
                if not korean_coordinates(lat,lon):continue
            except (KeyError,ValueError,TypeError):continue
            if not in_area(dict(lat=lat,lon=lon),c):continue
            pid='discovered:'+hashlib.sha256((name+address).encode()).hexdigest()[:20]
            if pid in resolved_ids:continue
            resolved_ids.add(pid)
            source='https://map.naver.com/p/search/'+quote(place_query({'name':name,'address':address}))
            row=dict(id=pid,name=name,address=address,lat=lat,lon=lon,region=c.region,demo=False,
                category=INTENTS[key][0],themes=[INTENTS[key][0]],tags=[key,category],meal=key=='meal',
                description=category,source=source,source_type='네이버 지역 검색 · 요청 활동 유형 연결',
                checked_at=datetime.now(timezone.utc).isoformat(),discovery_verification='네이버 업체 분류·상호·주소·좌표 연결 · 영업 여부 별도 확인',
                price=None,price_unit='person',hours=None,closed_days=None,breaks=None,last_entry=None,
                reservation=None,stay=None,stay_basis=None,rating=None,setting=None,photos=[],videos=[],license='검색 결과')
            # Preserve richer blog evidence for a previously resolved venue.
            if not store.cached('discovered-place:'+pid):store.cache('discovered-place:'+pid,row,604800)
            count+=1
    result=dict(status='available' if count else 'not_found',resolved=count,query_area=area,coverage_supplement=supplement,
                permission_required='permission_required' in statuses,search_unavailable=bool(statuses) and all(s=='unavailable' for s in statuses))
    store.cache(cachekey,result,900 if count else 30)
    return result
