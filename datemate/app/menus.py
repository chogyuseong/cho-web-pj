"""공개 네이버 검색 화면의 해당 업체 메뉴 정보. 비공개 API/차단 우회 없음."""
import json
import re
import threading
from datetime import datetime,timezone
from urllib.parse import urlencode
import httpx
from . import store
from .routes import distance
from .image_search import plain

_limit=threading.BoundedSemaphore(3)

def cost_menu_options(menu):
    items=[item for item in menu.get('items',[]) if item.get('amount') is not None]
    return sorted(items,key=lambda item:(bool(re.search(r'냉동|밀키트|택배|선물|포장|\d+\s*(?:g|kg)',item['name'],re.I)),not item.get('representative',False)))

def compact(value):return re.sub(r'\s+','',value).casefold()

def dictionaries(value,depth=0):
    if depth>25:return
    if isinstance(value,dict):
        yield value
        for child in value.values():yield from dictionaries(child,depth+1)
    elif isinstance(value,list):
        for child in value:yield from dictionaries(child,depth+1)

def extract_menus(html,place):
    names=[place['name'],*(place.get('search_aliases') or []),*(place.get('image_aliases') or [])]
    decoder=json.JSONDecoder()
    for marker in re.finditer(r'__APOLLO_STATE__\s*=\s*',html):
        try:state,_=decoder.raw_decode(html,marker.end())
        except ValueError:continue
        if not isinstance(state,dict):continue
        bases=[]
        for key,base in state.items():
            if not isinstance(base,dict) or base.get('__typename')!='PlaceDetailBase':continue
            actual=compact(plain(base.get('name','')))
            if not actual or not any(len(compact(n))>=2 and compact(n)==actual for n in names):continue
            try:
                coord=base['coordinate'];point=dict(lat=float(coord['y']),lon=float(coord['x']))
                if distance(place,point)>.4:continue
            except (KeyError,ValueError,TypeError):continue
            if not str(base.get('roadAddress') or base.get('address','')).startswith('서울'):continue
            if not str(base.get('id','')).isdigit():continue
            bases.append((key,base))
        # 식별이 모호한 다른 지점의 메뉴는 표시하지 않는다.
        if len(bases)!=1:continue
        key,base=bases[0]
        for scope in dictionaries(state):
            if scope.get('base')!={'__ref':key}:continue
            menu=scope.get('placeMenus',{})
            if not isinstance(menu,dict):continue
            if '__ref' in menu:menu=state.get(menu['__ref'],{})
            if not isinstance(menu,dict):continue
            rows=[]
            for reference in menu.get('items',[])[:12]:
                if not isinstance(reference,dict):continue
                item=state.get(reference.get('__ref'),{}) if '__ref' in reference else reference
                if not isinstance(item,dict) or item.get('__typename')!='PlaceMenuItem':continue
                name=plain(item.get('name',''));price=item.get('price') or {}
                if not isinstance(price,dict):continue
                display=plain(price.get('displayText',''))[:100]
                if not name or not display:continue
                amount=None
                if re.fullmatch(r'\d[\d,]*\s*원',display):amount=int(re.sub(r'[^0-9]','',display))
                if amount is not None and not 0<amount<=5000000:continue
                rows.append(dict(name=name,display_price=display,amount=amount,representative='repr' in (item.get('badges') or [])))
            if rows:return dict(items=rows,place_id=str(base['id']),matched_name=plain(base['name']),address=plain(base.get('roadAddress') or base.get('address','')),menu_updated_at=menu.get('updatedAt'))
    return None


def restaurant_menu(place):
    empty=dict(status='not_found',items=[],checked_at=datetime.now(timezone.utc).isoformat(),source_kind='naver_public_menu')
    if place.get('demo'):return dict(empty,status='demo',message='가상 장소는 실제 메뉴를 조회하지 않아요.')
    key='restaurant-menu-v1:'+place['id']
    cached=store.cached(key)
    if cached:return cached
    query=place['name']+' '+(place.get('address','').split()[1] if len(place.get('address','').split())>1 else '서울')+' 메뉴'
    source='https://search.naver.com/search.naver?'+urlencode({'query':query})
    result=dict(empty,search_url=source,message='네이버 공개 화면에서 이 식당의 메뉴 가격을 확인하지 못했어요. 지도 메뉴에서 확인해 주세요.')
    try:
        with _limit,httpx.Client(timeout=8,follow_redirects=False) as client:
            with client.stream('GET','https://search.naver.com/search.naver',params={'query':query}) as response:
                response.raise_for_status()
                if response.status_code!=200:raise ValueError('redirect')
                body=bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body)>4*1024*1024:raise ValueError('page_too_large')
        parsed=extract_menus(body.decode('utf-8',errors='replace'),place)
        if parsed:result.update(parsed,status='available',message='',source_url='https://map.naver.com/p/entry/place/'+parsed['place_id']+'?placePath=%2Fmenu',source_label='네이버 플레이스 메뉴 · 공개 검색 화면 기준',note='조회 시 표시된 메뉴 가격이며 매장 변경·수량·세트 구성에 따라 달라질 수 있어요.')
    except (httpx.HTTPError,ValueError,TypeError):result.update(status='unavailable',message='메뉴 정보 조회가 제한되거나 연결되지 않았어요. 지도 메뉴에서 확인해 주세요.')
    store.cache(key,result,3600 if result['status']=='available' else 60)
    return result
