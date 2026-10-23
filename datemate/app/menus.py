"""Read matched businesses' public menus; never substitute another branch or delivery price."""
import json
import re
import threading
from datetime import datetime,timezone
from urllib.parse import urlencode,urlsplit
import httpx
from . import store
from .routes import distance
from .image_search import plain,safe_https
from .search_address_text import place_query

_limit=threading.BoundedSemaphore(3)

def cost_menu_options(menu):
    items=[item for item in menu.get('items',[]) if item.get('amount') is not None and item.get('price_scope')!='delivery']
    return sorted(items,key=lambda item:(bool(re.search(r'냉동|밀키트|택배|선물|포장|\d+\s*(?:g|kg)',item['name'],re.I)),not item.get('representative',False)))

def compact(value):return re.sub(r'\s+','',str(value or '')).casefold()

def dictionaries(value,depth=0):
    if depth>25:return
    if isinstance(value,dict):
        yield value
        for child in value.values():yield from dictionaries(child,depth+1)
    elif isinstance(value,list):
        for child in value:yield from dictionaries(child,depth+1)

def states(html):
    decoder=json.JSONDecoder()
    for marker in re.finditer(r'__APOLLO_STATE__\s*=\s*',html):
        try:state,_=decoder.raw_decode(html,marker.end())
        except ValueError:continue
        if isinstance(state,dict):yield state

def identified(base,place,listing=False):
    names=[place['name'],*(place.get('search_aliases') or []),*(place.get('image_aliases') or [])]
    actual=compact(plain(base.get('name','')))
    if not actual or not any(len(compact(n))>=2 and compact(n)==actual for n in names):return False
    try:
        coord=base.get('coordinate') or base
        point=dict(lat=float(coord['y']),lon=float(coord['x']))
        if distance(place,point)>.4:return False
    except (KeyError,ValueError,TypeError):return False
    if not listing and not str(base.get('roadAddress') or base.get('address','')).startswith('서울'):return False
    return str(base.get('id','')).isdigit()

def price_row(name,value,representative=False):
    name=plain(name)
    if isinstance(value,dict):value=value.get('displayText') or value.get('price') or value.get('value')
    if value is None:return None
    display=plain(value)[:100]
    if not name or not display:return None
    amount=None
    if re.fullmatch(r'\d[\d,]*\s*원?',display):
        amount=int(re.sub(r'[^0-9]','',display))
        if not 0<amount<=5000000:return None
        display=f'{amount:,}원'
    return dict(name=name,display_price=display,amount=amount,representative=representative,price_scope='store')

def resolve(value,state):
    return state.get(value['__ref'],{}) if isinstance(value,dict) and '__ref' in value else value

def extract_menus(html,place):
    image_result=None
    for state in states(html):
        bases=[(key,base) for key,base in state.items() if isinstance(base,dict) and base.get('__typename')=='PlaceDetailBase' and identified(base,place)]
        if len(bases)==1:
            key,base=bases[0]
            for scope in dictionaries(state):
                if scope.get('base')!={'__ref':key}:continue
                menu=resolve(scope.get('placeMenus') or {},state)
                rows=[]
                if isinstance(menu,dict):
                    for ref in (menu.get('items') or [])[:20]:
                        item=resolve(ref,state)
                        if not isinstance(item,dict) or item.get('__typename')!='PlaceMenuItem':continue
                        row=price_row(item.get('name',''),item.get('price'),'repr' in (item.get('badges') or []))
                        if row:rows.append(row)
                images=[]
                for ref in scope.get('menuImages') or []:
                    item=resolve(ref,state)
                    url=item.get('imageUrl') if isinstance(item,dict) else None
                    if safe_https(url) and (urlsplit(url).hostname or '').endswith('.pstatic.net') and url not in images:images.append(url)
                result=dict(items=rows,menu_images=images[:10],place_id=str(base['id']),matched_name=plain(base['name']),
                    address=plain(base.get('roadAddress') or base.get('address','')),menu_updated_at=menu.get('updatedAt') if isinstance(menu,dict) else None,
                    menu_format='detail' if rows else 'image_only')
                if rows:return result
                if images:image_result=result
        # Search sometimes presents a business list rather than a PlaceDetailBase.
        listings=[];seen=set()
        for base in dictionaries(state):
            if base.get('__typename')=='PlaceListBusinessesItem' and identified(base,place,listing=True) and str(base['id']) not in seen:
                listings.append(base);seen.add(str(base['id']))
        if len(listings)==1:
            base=listings[0];rows=[]
            for item in (base.get('menus') or [])[:20]:
                if not isinstance(item,str):continue
                # Trailing explicit menu price only; digits in a dish name are not prices.
                m=re.fullmatch(r'(.+?)\s+(\d[\d,]*(?:\s*원)?|변동|시가)',plain(item))
                if m:
                    row=price_row(m[1],m[2])
                    if row:rows.append(row)
            if rows:return dict(items=rows,menu_images=[],place_id=str(base['id']),matched_name=plain(base['name']),
                address=plain(base.get('roadAddress') or base.get('address','')),menu_updated_at=None,menu_format='business_list')
    return image_result

def fetch_page(client,query):
    with client.stream('GET','https://search.naver.com/search.naver',params={'query':query}) as response:
        response.raise_for_status()
        if response.status_code!=200:raise ValueError('redirect')
        body=bytearray()
        for chunk in response.iter_bytes():
            body.extend(chunk)
            if len(body)>4*1024*1024:raise ValueError('page_too_large')
    return body.decode('utf-8',errors='replace')

def restaurant_menu(place,force=False):
    empty=dict(status='not_found',items=[],menu_images=[],checked_at=datetime.now(timezone.utc).isoformat(),source_kind='naver_public_menu')
    if place.get('demo'):return dict(empty,status='demo',message='가상 장소는 실제 메뉴를 조회하지 않아요.')
    # New parser must not reuse old false-negative entries.
    key='restaurant-menu-v3:'+place['id']
    if not force:
        cached=store.cached(key)
        if cached:return cached
    address=(place.get('address') or '').split();district=next((s for s in address if s.endswith('구')),'서울')
    queries=list(dict.fromkeys([place_query(place),place_query(place,'메뉴'),place['name']+' '+district+' 메뉴']))
    source='https://search.naver.com/search.naver?'+urlencode({'query':queries[0]})
    result=dict(empty,search_url=source,message='공개 자료에서 같은 식당의 숫자 메뉴 가격을 확인하지 못했어요.',reason='not_published')
    try:
        with _limit,httpx.Client(timeout=8,follow_redirects=False) as client:
            for query in queries:
                html=fetch_page(client,query);parsed=extract_menus(html,place)
                if not parsed:continue
                has_prices=bool(parsed['items'])
                result.update(parsed,query_used=query,status='available' if has_prices else 'image_only',message='' if has_prices else '이 매장은 메뉴판 이미지로 가격을 제공하고 있어요. 아래 메뉴판을 눌러 확대해 주세요.',
                    source_url='https://map.naver.com/p/entry/place/'+parsed['place_id']+'?placePath=%2Fmenu',
                    source_label='네이버 공개 메뉴' if has_prices else '네이버 공개 메뉴판 이미지',reason=None,
                    note='조회 시 공개된 메뉴 정보예요. 현재 매장 가격·수량·세트 구성은 원문과 확인해 주세요. 배달 메뉴 가격은 매장 가격으로 사용하지 않아요.')
                if has_prices:break
    except (httpx.HTTPError,ValueError,TypeError):
        if not result.get('menu_images') and not result['items']:result.update(status='unavailable',reason='provider_unavailable',message='공개 메뉴 조회가 일시적으로 제한됐어요. 다시 조회하거나 지도 메뉴를 확인해 주세요.')
    store.cache(key,result,3600 if result['status'] in ('available','image_only') else 60)
    return result
