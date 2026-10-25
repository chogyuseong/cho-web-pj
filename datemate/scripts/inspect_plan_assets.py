"""Report asset availability without printing keys, private inputs or coordinates."""
import json
import os
import sys
from urllib.parse import quote,urlsplit
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import store
from app.config import RUNTIME

if __name__=='__main__':
    result={'map_client_configured':bool(os.getenv('NAVER_MAPS_JS_KEY_ID')),
            'map_id_matches_js':os.getenv('NAVER_MAPS_KEY_ID')==os.getenv('NAVER_MAPS_JS_KEY_ID'),
            'map_js_matches_secret':bool(os.getenv('NAVER_MAPS_JS_KEY_ID')) and os.getenv('NAVER_MAPS_JS_KEY_ID')==os.getenv('NAVER_MAPS_KEY'),
            'map_js_has_whitespace':os.getenv('NAVER_MAPS_JS_KEY_ID','')!=os.getenv('NAVER_MAPS_JS_KEY_ID','').strip(),
            'image_search_configured':bool(os.getenv('NAVER_SEARCH_CLIENT_ID') and os.getenv('NAVER_SEARCH_CLIENT_SECRET'))}
    if (RUNTIME/'datemate.sqlite').exists():
        with store.connect() as db:
            rows=db.execute('SELECT payload FROM plans ORDER BY rowid DESC LIMIT 1').fetchall()
        if rows:
            plan=json.loads(rows[0]['payload'])
            result['mode']=plan['conditions']['mode']
            result['places']=[{'name':p['name'],'category':p.get('category'),'meal':p.get('meal',False)} for p in plan['places']]
            if '--network' in sys.argv:
                from app.menus import restaurant_menu
                from app.media import media_info
                for summary,place in zip(result['places'],plan['places']):
                    dining=place.get('meal') or place.get('cuisine') or any(word in (place.get('category') or '') for word in ('카페','미식','식당','음식점','베이커리'))
                    menu=restaurant_menu(place,force='--refresh' in sys.argv) if dining else {'status':'not_applicable'}
                    media=media_info(place)
                    summary.update(menu_status=menu['status'],menu_items=len(menu.get('items',[])),
                                   menu_provider_status=menu.get('provider_status'),
                                   menu_images=len(menu.get('menu_images',[])),
                                   photo_status=media.get('status'),photos=len(media.get('photos',[])))
                    if '--probe' in sys.argv and media.get('photos'):
                        from playwright.sync_api import sync_playwright
                        with sync_playwright() as pw:
                            browser=pw.chromium.launch(channel='msedge',headless=True)
                            page=browser.new_page()
                            candidates=list(dict.fromkeys(url for p in media['photos'][:2] for url in (p.get('source'),p.get('image_url')) if url))
                            summary['image_probe']=page.evaluate('''async urls=>Promise.all(urls.map(url=>new Promise(resolve=>{
                              const img=new Image();img.referrerPolicy='no-referrer';
                              const timer=setTimeout(()=>{img.src='';resolve(false);},7000);
                              img.onload=()=>{clearTimeout(timer);resolve(img.naturalWidth>0);};
                              img.onerror=()=>{clearTimeout(timer);resolve(false);};img.src=url;
                            })))''',candidates)
                            browser.close()
    if '--map-probe' in sys.argv and os.getenv('NAVER_MAPS_JS_KEY_ID'):
        from playwright.sync_api import sync_playwright
        key=quote(os.environ['NAVER_MAPS_JS_KEY_ID'],safe='')
        document=('''<!doctype html><meta charset="utf-8"><div id="map" style="width:600px;height:400px"></div><script>
          window.__datemateMapProbe={loaded:false,created:false,auth_failed:false};
          window.navermap_authFailure=()=>window.__datemateMapProbe.auth_failed=true;
          window.startMap=()=>{window.__datemateMapProbe.loaded=!!window.naver?.maps;try{
            new naver.maps.Map(document.getElementById('map'),{center:new naver.maps.LatLng(37.56,126.98),zoom:14});window.__datemateMapProbe.created=true;
          }catch{window.__datemateMapProbe.error=true;}};
          </script><script onload="startMap()" onerror="window.__datemateMapProbe.network_error=true" src="https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId='''+key+'''"></script>''').encode()
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='msedge',headless=True)
            probes=[]
            for origin in ('http://127.0.0.1:8000','http://localhost:8000'):
                context=browser.new_context()
                page=context.new_page();messages=[];sdk_status=[]
                def collect(message):
                    text=message.text
                    if message.type!='error':return
                    for name,value in os.environ.items():
                        if value and name.startswith(('NAVER_','GMS_')):text=text.replace(value,'[redacted]')
                    messages.append(text[:1000])
                page.on('console',collect)
                page.on('response',lambda response:sdk_status.append(response.status) if '/openapi/v3/maps.js' in response.url else None)
                page.route(origin+'/__datemate-map-probe',lambda route:route.fulfill(body=document,content_type='text/html; charset=utf-8'))
                page.goto(origin+'/__datemate-map-probe',wait_until='domcontentloaded')
                try:page.wait_for_function('window.__datemateMapProbe.created||window.__datemateMapProbe.auth_failed||window.__datemateMapProbe.network_error',timeout=20000)
                except Exception:pass
                page.wait_for_timeout(1500)
                probes.append(dict(origin=origin,**(page.evaluate('window.__datemateMapProbe') or {}),errors=messages,sdk_http_status=sdk_status))
                context.close()
            browser.close()
            result['map_probe']=probes
    if '--live' in sys.argv:
        import httpx
        try:
            response=httpx.get('http://127.0.0.1:8000/api/status',timeout=10)
            response.raise_for_status();live=response.json()
            result['live_server']={'reachable':True,'client_configured':bool(live.get('map_js_key')),
                'key_matches_env':live.get('map_js_key')==os.getenv('NAVER_MAPS_JS_KEY_ID'),
                'maps_script_current':httpx.get('http://127.0.0.1:8000/static/maps.js',timeout=10).text.lstrip('\ufeff').replace('\r\n','\n')==(Path(__file__).resolve().parents[1]/'static'/'maps.js').read_text(encoding='utf-8-sig')}
        except Exception as error:
            result['live_server']={'reachable':False,'error_type':type(error).__name__}
    print(json.dumps(result,ensure_ascii=True,indent=2))
