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
