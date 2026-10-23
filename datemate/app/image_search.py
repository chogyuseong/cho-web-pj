"""NAVER API HUB 이미지 검색. 2026-07-31 이후 신규 신청 경로를 사용한다."""
import html
import os
import re
import threading
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit, unquote
import httpx
from .search_address_text import place_query,street_address

_lock=threading.Lock()
_image_slots=threading.BoundedSemaphore(3)

def search_enabled():
    return bool(os.getenv('NAVER_SEARCH_CLIENT_ID') and os.getenv('NAVER_SEARCH_CLIENT_SECRET'))

def safe_https(url):
    try:
        parsed=urlsplit(url)
        return parsed.scheme=='https' and bool(parsed.hostname) and not parsed.username and not parsed.password
    except (TypeError,ValueError):return False

def safe_web_url(url):
    try:
        p=urlsplit(url)
        return p.scheme in ('http','https') and bool(p.hostname) and not p.username and not p.password
    except (TypeError,ValueError):return False

def usable_image(item):
    thumb=item.get('thumbnail','');original=item.get('link','')
    if safe_https(thumb):return thumb
    if (not thumb or safe_web_url(thumb)) and safe_https(original):return original
    return None

def plain(value):return html.unescape(re.sub(r'<[^>]*>',' ',str(value))).strip()[:300]

def image_aliases(place):
    aliases=list(place.get('image_aliases') or [])
    wiki=urlsplit(place.get('wikipedia') or '')
    if wiki.hostname=='ko.wikipedia.org':
        name=unquote(wiki.path.rsplit('/',1)[-1]).replace('_',' ')
        name=re.sub(r'\s*\([^)]*\)$','',name).strip()
        if name and name!=place['name']:aliases.append(name)
    return list(dict.fromkeys(aliases))

def title_matches(place,title,aliases):
    def compact(s):return re.sub(r'[\W_]+','',s).casefold()
    value=compact(title)
    keys=place.get('image_keywords')
    if keys:return all(compact(w) in value for w in keys)
    for name in [place['name'],*aliases]:
        if compact(name) and compact(name) in value:return True
        words=[compact(w) for w in name.split() if compact(w)]
        # Keep every name/branch token; tolerate intervening words and punctuation.
        if len(words)>1 and all(w in value for w in words):return True
    return False

def _search_place_images(place):
    if place.get('demo'):return {'status':'demo','photos':[]}
    if not search_enabled():return {'status':'key_missing','photos':[]}
    # Local listing uses 'SAAN 2'; published photos use SAAN / 산 을지로점.
    # Scope the alias by its verified street address to avoid other SAAN branches.
    if re.sub(r'\s+','',place['name']).casefold()=='saan2' and re.search(r'충무로4길\s*3(?:\s|$)',(place.get('address') or '')):
        place=dict(place,image_aliases=['SAAN 을지로 카페','산 을지로점','SAAN2'],image_keywords=['SAAN','을지로'],image_queries=['SAAN 을지로 카페 서울','SAAN2 카페'])
    aliases=image_aliases(place)
    query=f'{aliases[0] if aliases else place["name"]} 서울'
    try:
        with _image_slots, httpx.Client(timeout=7) as client:
            items=[]
            district=re.search(r'서울(?:특별시|시)?\s+([가-힣]+구)',(place.get('address') or ''))
            queries=place.get('image_queries') or list(dict.fromkeys([query,*([place_query(place)] if street_address(place.get('address')) else []),*([place['name']+' '+district[1]+' 사진'] if district else [])]))
            for search_query in queries[:3]:
                response=client.get('https://naverapihub.apigw.ntruss.com/search/v1/image',params={'query':search_query,'display':30,'start':1,'sort':'sim','filter':'all','format':'json'},
                    headers={'X-NCP-APIGW-API-KEY-ID':os.environ['NAVER_SEARCH_CLIENT_ID'],'X-NCP-APIGW-API-KEY':os.environ['NAVER_SEARCH_CLIENT_SECRET']})
                response.raise_for_status();batch=response.json()
                if not isinstance(batch,dict) or not isinstance(batch.get('items',[]),list):raise ValueError('invalid_response')
                items.extend(batch.get('items',[]))
                if not place.get('image_queries') and any(isinstance(i,dict) and title_matches(place,plain(i.get('title','')),aliases) and usable_image(i) and safe_web_url(i.get('link','')) for i in items):break
            data={'items':items}
        if not isinstance(data,dict) or not isinstance(data.get('items',[]),list):raise ValueError('invalid_response')
        photos=[];seen=set()
        for rank,item in enumerate(data.get('items',[]),1):
            if not isinstance(item,dict):continue
            title=plain(item.get('title',''));image=usable_image(item);original=item.get('link','')
            # 이름이 다른 이미지·중복·실행 가능한 URL을 제외한다. 제목 일치는 검수 완료와 다르다.
            matched=title_matches(place,title,aliases)
            if not matched or not image or not safe_web_url(original) or original in seen:continue
            seen.add(original)
            photos.append(dict(id=f'naver-{rank}',kind='search_result',provider='네이버 이미지 검색',rank=rank,sort='sim',
                title=title,image_url=image,url=image,source=original,search_url='https://search.naver.com/search.naver?'+urlencode({'where':'image','query':query}),
                caption=f'{place["name"]} 서울 검색 결과의 참고 이미지입니다. 장소 일치 여부와 이용 조건은 원본에서 확인해 주세요.',
                author=None,license=None,license_url=None,taken_at=None,checked_at=datetime.now(timezone.utc).isoformat(),
                association='장소명+서울 검색 및 제목 문자 일치 · 별도 실물 검수 아님'))
            if len(photos)==5:break
        def role(photo):
            title=photo['title']
            if re.search(r'내부|인테리어|전경|공간|외관',title):return '공간 관련 제목'
            if re.search(r'메뉴|음식|디저트|커피|파스타|요리',title):return '음식·메뉴 관련 제목'
            return '장소 관련 검색 사진'
        for photo in photos:photo['image_role']=role(photo)
        photos.sort(key=lambda p:0 if p['image_role']=='공간 관련 제목' else 1)
        return {'status':'available' if photos else 'not_found','photos':photos}
    except (httpx.HTTPError,ValueError,TypeError,KeyError):return {'status':'unavailable','photos':[]}


def search_place_images(place,force=False):
    if not place.get('id') or place.get('demo') or not search_enabled():return _search_place_images(place)
    from . import store
    import hashlib,json
    key='image-search-v4:'+hashlib.sha256(json.dumps([place.get(k) for k in ('id','name','address','image_aliases','image_keywords','image_queries','wikipedia')],ensure_ascii=False).encode()).hexdigest()
    if not force:
        cached=store.cached(key)
        if cached:return cached
    result=_search_place_images(place)
    store.cache(key,result,3600 if result['photos'] else 60)
    return result
