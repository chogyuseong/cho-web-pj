import sys,json
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from app.restaurants import restaurants

food=next(p for p in restaurants() if p['id']=='food:myeongdong-kyoja')
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.wait_for_function('Boolean(statusData)')
    page.evaluate('food=>document.querySelector("#results").replaceChildren(restaurantCard(food))',food)
    page.locator('.restaurant-menu').scroll_into_view_if_needed()
    page.locator('.menu-price-row').first.wait_for(timeout=25000)
    assert page.locator('.menu-price-row b').first.inner_text()
    data=page.request.get('http://127.0.0.1:8000/api/places/'+food['id']+'/menu?mode=real').json()
    assert data['status']=='available' and data['source_kind']=='naver_public_menu'
    assert data['matched_name']==food['name']
    assert data['source_url'].startswith('https://map.naver.com/p/entry/place/')
    page.locator('.meal-photo img').first.wait_for()
    page.wait_for_function('document.querySelector(".meal-photo img")?.naturalWidth>0',timeout=20000)
    page.locator('#results .meal-card').screenshot(path=str(root/'docs/screenshots/restaurant-menu.png'))
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.locator('#results .meal-card').screenshot(path=str(root/'docs/screenshots/restaurant-menu-mobile.png'))
    assert not errors,errors
    print(json.dumps({'live_menu_count':len(data['items']),'matched_business':data['matched_name'],'menus':[(r['name'],r['display_price']) for r in data['items'][:4]],'mobile_overflow':False,'page_errors':errors},ensure_ascii=True))
    browser.close()
