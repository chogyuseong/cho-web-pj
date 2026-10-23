"""Photos explicitly attached to the uniquely matched public business record."""
import hashlib
from datetime import datetime,timezone
from urllib.parse import urlsplit,urlencode
import httpx
from . import store
from .menus import states,dictionaries,identified,resolve,fetch_page,_limit
from .image_search import safe_https
from .search_address_text import place_query

def image_urls(node,state):
    node=resolve(node,state)
    if isinstance(node,list):
        for item in node:yield from image_urls(item,state)
    elif isinstance(node,dict):
        for key in ('origin','imageUrl','thumbUrl','thumbnailUrl','thumUrl','url'):
            value=node.get(key)
            if isinstance(value,str) and safe_https(value) and (urlsplit(value).hostname or '').endswith('.pstatic.net'):yield value
        for key in ('images','image','items'):
            value=node.get(key)
            if isinstance(value,(dict,list)):yield from image_urls(value,state)

def extract_place_photos(html,place):
    for state in states(html):
        bases=[(key,base) for key,base in state.items() if isinstance(base,dict) and base.get('__typename')=='PlaceDetailBase' and identified(base,place)]
        if len(bases)==1:
            key,base=bases[0];urls=[]
            for scope in dictionaries(state):
                if scope.get('base')!={'__ref':key}:continue
                urls.extend(image_urls(scope.get('images'),state))
                urls.extend(image_urls(scope.get('topPhotos'),state))
            urls=list(dict.fromkeys(urls))[:5]
            if urls:return urls,str(base['id'])
        rows=[];seen=set()
        for base in dictionaries(state):
            if base.get('__typename')=='PlaceListBusinessesItem' and identified(base,place,listing=True) and base['id'] not in seen:
                rows.append(base);seen.add(base['id'])
        if len(rows)==1:
            urls=list(dict.fromkeys(image_urls(rows[0],state)))[:5]
            if urls:return urls,str(rows[0]['id'])
    return [],None

def public_place_photos(place,force=False):
    if not place.get('name') or place.get('lat') is None or place.get('lon') is None or place.get('demo'):return dict(status='not_found',photos=[],photo_source='naver_public_place')
    fingerprint=hashlib.sha256(str([place['name'],place.get('address'),place.get('lat'),place.get('lon')]).encode()).hexdigest()
    key='public-place-photos-v2:'+fingerprint
    if not force:
        cached=store.cached(key)
        if cached:return cached
    result=dict(status='not_found',photos=[],photo_source='naver_public_place')
    if place.get('demo'):return result
    district=next((word for word in (place.get('address') or '').split() if word.endswith('구')),'서울')
    query=place_query(place)
    try:
        with _limit,httpx.Client(timeout=8,follow_redirects=False) as client:
            urls=[];pid=None
            for search_query in dict.fromkeys([query,place['name']+' '+district]):
                urls,pid=extract_place_photos(fetch_page(client,search_query),place)
                if urls:break
        source='https://map.naver.com/p/entry/place/'+pid if pid else None
        checked=datetime.now(timezone.utc).isoformat()
        for index,url in enumerate(urls):
            result['photos'].append(dict(id='public-'+str(index),kind='place_public',provider='네이버 공개 장소 사진',title=place['name']+' 장소 사진',
                image_url=url,url=url,source=source,search_url=source,caption='상호·주소 좌표로 연결한 해당 장소의 공개 사진입니다. 개별 이용 조건은 원문에서 확인해 주세요.',
                author=None,license=None,license_url=None,taken_at=None,checked_at=checked,association='공개 장소 정보의 고유 업체·좌표 대조',image_role='장소 연결 사진'))
        if result['photos']:result['status']='available'
    except (httpx.HTTPError,ValueError,TypeError,KeyError):result['status']='unavailable'
    store.cache(key,result,3600 if result['photos'] else 60)
    return result
