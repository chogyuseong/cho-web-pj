import json
from app.menus import extract_menus


def page(name='테스트식당',lat=37.56,price='12,000원',scope='PlaceDetailBase:1'):
    state={'PlaceDetailBase:1':{'__typename':'PlaceDetailBase','id':'1','name':name,'roadAddress':'서울 마포구 테스트로 1','coordinate':{'x':'126.925','y':str(lat)}},
           'PlaceMenuItem:m':{'__typename':'PlaceMenuItem','name':'칼국수','price':{'displayText':price},'badges':['repr']},
           'ROOT_QUERY':{'detail':{'base':{'__ref':scope},'placeMenus':{'items':[{'__ref':'PlaceMenuItem:m'}],'updatedAt':'26.10.01'}}}}
    return '<script>naver.search.ext.__APOLLO_STATE__ = '+json.dumps(state)+';</script>'


def test_menu_matches_exact_business_and_menu_ownership():
    place=dict(name='테스트식당',lat=37.56,lon=126.925)
    parsed=extract_menus(page(),place)
    assert parsed['items'][0]['amount']==12000
    assert parsed['items'][0]['display_price']=='12,000원'
    assert parsed['menu_updated_at']=='26.10.01'
    assert extract_menus(page(name='다른 식당'),place) is None
    assert extract_menus(page(lat=37.65),place) is None
    assert extract_menus(page(scope='PlaceDetailBase:2'),place) is None


def test_variable_prices_are_not_fabricated_numbers():
    place=dict(name='테스트식당',lat=37.56,lon=126.925)
    item=extract_menus(page(price='변동'),place)['items'][0]
    assert item['amount'] is None and item['display_price']=='변동'
    assert extract_menus('window.__APOLLO_STATE__ = invalid;',place) is None


def test_menu_rejects_ambiguous_same_name_branches():
    place=dict(name='테스트식당',lat=37.56,lon=126.925)
    html=page();start=html.index(' = ')+3
    state,_=json.JSONDecoder().raw_decode(html,start)
    state['PlaceDetailBase:2']={**state['PlaceDetailBase:1'],'id':'2'}
    assert extract_menus('window.__APOLLO_STATE__ = '+json.dumps(state),place) is None

def test_business_list_menu_has_verified_name_and_location():
    state={'ROOT_QUERY':{'businesses':[{'__typename':'PlaceListBusinessesItem','id':'21','name':'<mark>테스트식당</mark>',
        'x':'126.925','y':'37.56','roadAddress':'테스트로 1','menus':['칼국수 12,000','세트 2인 32,000원','가격 변동']}]}}
    html='window.__APOLLO_STATE__ = '+json.dumps(state)
    place=dict(name='테스트식당',lat=37.56,lon=126.925)
    result=extract_menus(html,place)
    assert result['menu_format']=='business_list'
    assert result['items'][0]['amount']==12000 and result['items'][1]['amount']==32000
    assert result['items'][2]['amount'] is None
    assert extract_menus(html,place|{'name':'다른식당'}) is None
    assert extract_menus(html,place|{'lat':37.65}) is None

def test_menu_images_are_scoped_and_delivery_not_dine_in():
    state,_=json.JSONDecoder().raw_decode(page(),page().index(' = ')+3)
    scope=state['ROOT_QUERY']['detail'];scope['placeMenus']=None
    scope['menuImages']=[{'imageUrl':'https://ldb-phinf.pstatic.net/menu.jpg'},{'imageUrl':'https://unrelated.example/menu.jpg'}]
    state['PlaceDetail_BaeminMenu:1']={'__typename':'PlaceDetail_BaeminMenu','name':'배달 전용','price':'9900'}
    result=extract_menus('window.__APOLLO_STATE__ = '+json.dumps(state),dict(name='테스트식당',lat=37.56,lon=126.925))
    assert result['menu_format']=='image_only' and not result['items']
    assert result['menu_images']==['https://ldb-phinf.pstatic.net/menu.jpg']

def test_price_formats_and_ranges():
    from app.menus import price_row,cost_menu_options
    assert price_row('칼국수',{'displayText':'12000'})['amount']==12000
    assert price_row('가격범위','10,000~20,000원')['amount'] is None
    assert price_row('시가','시가')['amount'] is None
    assert not cost_menu_options({'items':[{'name':'배달 메뉴','amount':10000,'price_scope':'delivery'}]})

def test_menu_retry_and_cache_upgrade(monkeypatch):
    from app import menus
    calls=[]
    def fetch(client,query):
        calls.append(query)
        return 'empty' if len(calls)==1 else page()
    monkeypatch.setattr(menus,'fetch_page',fetch)
    place=dict(id='menu-retry-fixture',name='테스트식당',lat=37.56,lon=126.925,address=None)
    result=menus.restaurant_menu(place)
    assert result['status']=='available' and len(calls)==2
    assert menus.restaurant_menu(place)['items'] and len(calls)==2
    menus.restaurant_menu(place,force=True)
    assert len(calls)==3


def test_menu_keeps_images_when_prices_are_also_available():
    state,_=json.JSONDecoder().raw_decode(page(),page().index(' = ')+3)
    state['ROOT_QUERY']['detail']['menuImages']=[{'imageUrl':'https://ldb-phinf.pstatic.net/menu.jpg'}]
    result=extract_menus('window.__APOLLO_STATE__ = '+json.dumps(state),dict(name='테스트식당',lat=37.56,lon=126.925))
    assert result['items'][0]['amount']==12000
    assert result['menu_images']==['https://ldb-phinf.pstatic.net/menu.jpg']


def test_listing_prices_keep_same_business_menu_image():
    state,_=json.JSONDecoder().raw_decode(page(),page().index(' = ')+3)
    state['ROOT_QUERY']['detail']['placeMenus']=None
    state['ROOT_QUERY']['detail']['menuImages']=[{'imageUrl':'https://ldb-phinf.pstatic.net/menu.jpg'}]
    state['ROOT_QUERY']['businesses']=[{'__typename':'PlaceListBusinessesItem','id':'1','name':'테스트식당','x':'126.925','y':'37.56','menus':['칼국수 12,000']}]
    result=extract_menus('window.__APOLLO_STATE__ = '+json.dumps(state),dict(name='테스트식당',lat=37.56,lon=126.925))
    assert result['items'] and result['menu_images']
