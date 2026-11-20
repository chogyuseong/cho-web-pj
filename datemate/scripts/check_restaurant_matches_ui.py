"""Real local search plus deterministic SDK marker/circle rendering checks."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(bypass_csp=True,viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8001',wait_until='networkidle')
    result=page.evaluate('''async()=>await api('/plans',{mode:'real',allow_estimates:true,visit_date:'2026-10-24',
      count:3,origin:{name:'광화문',lat:37.575,lon:126.977},area_center:{name:'종로',lat:37.575,lon:126.985},budget:150000})''')
    plan=result['plans'][0]
    page.goto('http://127.0.0.1:8001/?plan='+plan['id'],wait_until='domcontentloaded')
    page.wait_for_function('Boolean(selected)',timeout=30000)
    data=page.evaluate('async()=>await fetchRestaurantMatches(selected)')
    assert len(data['groups'])==len(plan['places'])
    # 주변 식당은 우리 식당 자료와 공공 자료에서 500m → 1,000m → 1,500m 순으로 찾는다(2026-11-20, app/restaurants.py).
    # 구 단위 '유명 맛집 TOP 5'(네이버 리뷰순)는 없앴다.
    assert all(f['distance_m']<=1500 for g in data['groups'] for f in g['restaurants'])
    assert 'popular' not in data and page.locator('.regional-restaurants').count()==0
    assert page.locator('.meal-suggestions').count()==len(plan['places'])
    page.set_viewport_size({'width':390,'height':844})
    page.wait_for_timeout(400)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),'real mobile layout overflow'
    page.set_viewport_size({'width':1440,'height':1000})
    # 지도 공급자 연결 상태와 별도로 SDK에 전달하는 좌표·반경·클릭 동작을 확인한다.
    page.evaluate('''()=>{
      window.__mapTest={markers:[],circles:[],infos:[],events:[]};
      window.naver={maps:{
        LatLng:class{constructor(lat,lon){this.lat=lat;this.lon=lon;}},Point:class{},
        LatLngBounds:class{extend(){}},Map:class{fitBounds(){}},Polyline:class{},
        Marker:class{constructor(o){Object.assign(this,o);__mapTest.markers.push(this);}},
        Circle:class{constructor(o){__mapTest.circles.push(o);}},
        InfoWindow:class{constructor(o){this.content=o.content;__mapTest.infos.push(this);}open(){this.opened=true;}},
        Event:{addListener:(marker,name,handler)=>__mapTest.events.push({marker,name,handler})}
      }};window.naverMapAuthFailed=false;statusData.map_js_key='sdk-test';
      document.querySelector('.plan-map').replaceWith(drawPlanMap(selected));
    }''')
    page.wait_for_function('__mapTest.markers.some(m=>m.icon.content.includes("restaurant-marker"))')
    assert page.evaluate('__mapTest.circles.length')==len(plan['places'])
    assert page.evaluate('__mapTest.circles.every(c=>c.radius===500)')
    assert page.evaluate('__mapTest.events.every(e=>e.name==="click")')
    page.evaluate('__mapTest.events[0].handler()')
    assert page.evaluate('__mapTest.infos[0].opened')
    page.set_viewport_size({'width':390,'height':844})
    page.wait_for_timeout(400)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert not errors,errors
    print(json.dumps({'stop_groups':len(data['groups']),'within_1500m':True,'food_markers_and_clicks':True,'radius_circles':True,'mobile_overflow':False,'page_errors':errors}))
    browser.close()
