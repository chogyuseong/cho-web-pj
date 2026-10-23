import sys,json,httpx,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import RUNTIME
from app.menus import restaurant_menu
from app.search_address_text import place_query
from app.public_place_photos import public_place_photos
from app import store
rows=store.cached('explore-seoul-500-v1')['places']
for name in ['브리즈밀','우지커피 불광중앙점']:
 p=next(p for p in rows if p['name']==name);r=public_place_photos(p,True)
 print(json.dumps({'name':name,'query':place_query(p),'photos':len(r['photos'])},ensure_ascii=True),flush=True)
for i in [4,5]:
 p=json.loads((RUNTIME/'menu-debug'/f'{i}.json').read_text(encoding='utf-8'));r=restaurant_menu(p,force=True)
 print(json.dumps({'name':p['name'],'query':r.get('query_used'),'status':r['status'],'items':len(r['items']),'menu_images':len(r['menu_images'])},ensure_ascii=True),flush=True)
r=httpx.get('https://naverapihub.apigw.ntruss.com/search/v1/local',params={'query':'코델 서울특별시 강서구 양천로 401','display':5,'format':'json'},headers={'X-NCP-APIGW-API-KEY-ID':os.environ['NAVER_SEARCH_CLIENT_ID'],'X-NCP-APIGW-API-KEY':os.environ['NAVER_SEARCH_CLIENT_SECRET']},timeout=8)
for item in r.json().get('items',[]):
 if '코델' not in item['title'] or '양천로 401' not in item.get('roadAddress',''):continue
 p={'id':'road-query-codel','name':'코델','address':item['roadAddress'],'lat':float(item['mapy'])/(10000000 if abs(float(item['mapy']))>90 else 1),'lon':float(item['mapx'])/(10000000 if abs(float(item['mapx']))>180 else 1)}
 r=restaurant_menu(p,force=True);print(json.dumps({'name':'코델','query':r.get('query_used'),'status':r['status'],'items':len(r['items']),'menu_images':len(r['menu_images'])},ensure_ascii=True),flush=True)
