import json
import os
import secrets
import time
import mimetypes
import hashlib
import re
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import FastAPI, HTTPException, Request, Response, Query
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from . import store
from .catalog import places,get_place
from .config import ROOT,REGION
from .models import Conditions,ReviewInput,ChatInput,THEMES
from .planner import recommend,replacements
from .indexing import collections,embedding_mode,search_places
from .rag import ask
from .geocoding import search_address
from .taxonomy import DATE_CATEGORIES
from .media import media_info
from .blog_search import place_blogs

# Windows 레지스트리의 .js=text/plain 매핑에서도 nosniff와 호환되도록 고정한다.
mimetypes.add_type('text/javascript', '.js')
mimetypes.add_type('text/css', '.css')

@asynccontextmanager
async def lifespan(app):
    store.init()
    yield

app=FastAPI(title='서울 데이트메이트 · 서울 데이트 코스 추천',version='0.1.0',lifespan=lifespan)

@app.get('/healthz',include_in_schema=False)
def health():
    return {'status':'ok'}

@app.middleware('http')
async def safety(request:Request,call_next):
    if request.url.path=='/healthz':return await call_next(request)
    started=time.perf_counter()
    # 전체 요청 본문 2 MiB. Content-Length가 없는 요청도 스트림을 읽으며 제한한다.
    if request.method in ('POST','PUT','PATCH','DELETE'):
        origin=request.headers.get('origin')
        if origin and origin.rstrip('/')!=str(request.base_url).rstrip('/'):
            return JSONResponse({'detail':'다른 사이트에서 보낸 변경 요청은 허용하지 않습니다.'},status_code=403)
        body=bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body)>2*1024*1024:return JSONResponse({'detail':'요청은 2 MiB 이하로 보내주세요.'},status_code=413)
        request._body=bytes(body)
    token=request.cookies.get('dm_session','')
    with store.connect() as db:
        exists=db.execute('SELECT 1 FROM sessions WHERE token=?',(token,)).fetchone()
        if not exists:
            token=secrets.token_urlsafe(32)
            db.execute('INSERT INTO sessions VALUES(?,?)',(token,time.time()))
    request.state.owner=token
    try:
        response=await call_next(request)
    except Exception:
        response=JSONResponse({'detail':'요청 처리 중 오류가 발생했습니다. 입력이나 서버 상태를 확인하세요.'},status_code=500)
    if not exists:response.set_cookie('dm_session',token,httponly=True,samesite='strict',secure=request.url.scheme=='https',max_age=2592000)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Server-Timing']=f'total;dur={(time.perf_counter()-started)*1000:.2f}'
    return response

def plan_row(id,owner=None):
    row=store.get_plan(id)
    if not row:raise HTTPException(404,'일정을 찾을 수 없습니다.')
    if owner is not None and row['owner']!=owner:raise HTTPException(403,'이 브라우저에서 만든 일정만 수정할 수 있습니다.')
    from .condition_audit import audit_plan
    return row,audit_plan(json.loads(row['payload']))

@app.get('/api/status')
def status():
    counts={}
    for mode in ('demo','real'):
        a,b=collections(mode)
        counts[mode]=dict(places=len(places(mode)),indexed=a.count(),chunks=b.count())
    return dict(region=REGION,temporary_region=False,counts=counts,llm='키 설정됨 · 실호출 결과 별도' if os.getenv('GMS_KEY') else 'GMS 키 없음',
        embedding=embedding_mode(),route='자동차 API 설정됨' if os.getenv('NAVER_MAPS_KEY') else '실제 경로 API 키 없음',
        themes=THEMES,date_categories=DATE_CATEGORIES,map_js_key=os.getenv('NAVER_MAPS_JS_KEY_ID',''),
        geocoding_available=bool(os.getenv('NAVER_MAPS_KEY_ID') and os.getenv('NAVER_MAPS_KEY')),
        map_tile_url=os.getenv('MAP_TILE_URL','https://tile.openstreetmap.org/{z}/{x}/{y}.png'),
        map_tile_attribution=os.getenv('MAP_TILE_ATTRIBUTION','© OpenStreetMap contributors'))

class AddressInput(BaseModel):
    query:str=Field(min_length=2,max_length=200)

@app.post('/api/locations/search')
def location_search(data:AddressInput,request:Request):
    if len(data.query.strip())<2:raise HTTPException(422,'주소를 두 글자 이상 입력하세요.')
    # 단일 로컬 서버의 사용자별 연속 요청 제한. 자동완성/일괄 지오코딩은 하지 않는다.
    key='geocode-rate:'+request.state.owner
    if store.cached(key):raise HTTPException(429,'주소 검색은 잠시 후 다시 시도하세요.')
    store.cache(key,True,1)
    return search_address(data.query.strip())

@app.get('/api/places')
def catalog(mode:Literal['demo','real']='demo',q:str=Query(default='',max_length=500)):
    rows=places(mode)
    if q:
        matches=[p for p in rows if q.lower() in (p['name']+' '+p['category']+' '+' '.join(p['tags'])).lower()]
        if matches:return dict(places=matches,search='문자 일치')
        ids=search_places(q,mode)
        rows=sorted([p for p in rows if p['id'] in ids],key=lambda p:ids.index(p['id']))
    return dict(places=rows,search='해시 데모 검색' if embedding_mode()=='demo' else '의미 검색')

@app.get('/api/places/{id}')
def place(id:str,mode:Literal['demo','real']='demo'):
    p=get_place(id,mode)
    if p is None:raise HTTPException(404,'장소를 찾을 수 없습니다.')
    return p

class ParseInput(BaseModel):
    text:str=Field(max_length=4000)

@app.get('/api/places/{id}/media')
def place_media(id:str,mode:Literal['demo','real']='real'):
    p=get_place(id,mode)
    if p is None:raise HTTPException(404,'장소를 찾을 수 없습니다.')
    return media_info(p)

@app.get('/api/places/{id}/blogs')
def place_blog_results(id:str,mode:Literal['demo','real']='real'):
    p=get_place(id,mode)
    if p is None:raise HTTPException(404,'장소를 찾을 수 없습니다.')
    return place_blogs(p)

@app.post('/api/conditions/parse')
def parse(data:ParseInput):
    import re
    text=data.text; patch={}; warnings=[]
    aliases={'문화·예술':['전시','미술','박물관'],'카페·미식':['카페','커피','식사'],'산책·풍경':['산책','풍경'],
        '체험·제작':['공방','도자기'],'휴식·힐링':['휴식','힐링'],'오락·놀이':['게임','놀이'],'레저·활동':['운동','레저']}
    patch['themes']=[theme for theme,words in aliases.items() if any(w in text for w in words)]
    if re.search(r'싫|말고|제외|피하|안\s*가',text):
        patch.pop('themes',None);warnings.append('부정 표현은 자동 적용하지 않았습니다. 테마와 피할 활동을 직접 확인하세요.')
    match=re.search(r'(\d+)\s*만\s*원',text)
    if match:patch['budget']=int(match[1])*10000
    match=re.search(r'([2-5])\s*(?:곳|군데)',text)
    if match:patch['count']=int(match[1])
    patch['region']=REGION
    return dict(patch=patch,warnings=warnings+['추천 지역은 서울특별시로 고정됩니다. 서울 밖 장소는 추천하지 않습니다.', '키 없는 제한적 규칙 해석입니다. 날짜·출발지·시간·교통 및 미해석 요청을 직접 확인하세요.'],unparsed=text)

@app.post('/api/plans')
def create(data:Conditions,request:Request):
    from .course_search import search_courses,priority
    evidence=search_courses(data) if data.mode=='real' else None
    if data.mode=='real':
        from .quality import configure
        data=configure(data,evidence['query'])
    result=recommend(data,evidence)
    if not result['plans'] and data.area_center:
        result.setdefault('suggestions',[]).insert(0,f'{data.area_center.name} 반경 {data.neighborhood_radius_km:g}km 안에서 찾고 있어요. 동네 이동 범위나 방문 수를 조정해 주세요.')
    if evidence:
        result['course_search']=evidence
        for plan in result['plans']:
            plan['course_search']=evidence
            plan['blog_score']=priority(plan,evidence)
            plan['recommendation_method']='naver_blog_top3' if plan['blog_score'] else 'conditions_fallback'
            for i,place in enumerate(plan['places']):
                matched=evidence['matches'].get(place['id'])
                if matched:plan['reasons'][i]='네이버 코스 검색 '+', '.join(str(n)+'위 글' for n in matched['ranks'])+'에 등장 · '+plan['reasons'][i]
    from .pricing import price_plans
    if data.mode=='real' and data.transport=='car':
        from .planner import evaluate
        from .condition_audit import audit_plan
        for i,plan in enumerate(result['plans']):
            verified,error=evaluate(plan['places'],data,soft=bool(plan.get('best_effort')),verify_routes=True)
            if verified:
                plan.update(verified)
                result['plans'][i]=audit_plan(plan,data)
                plan['route_verification']='네이버 자동차 길찾기 조회 반영 (조회 시점 기준)'
            else:plan['route_verification']='자동차 실제 경로 확인 실패: '+str(error)+' · 추정 동선을 유지했어요.'
    result['plans']=price_plans(result['plans'])
    if data.mode=='real':result['plans'].sort(key=lambda p:(p['total'][1]>data.budget,max(0,p['total'][1]-data.budget)))
    if result['plans'] and all(p.get('best_effort') for p in result['plans']):result['status']='best_effort'
    result['plans']=[store.save_plan(p,request.state.owner) for p in result['plans']]
    return result

@app.get('/api/plans/{id}')
def get_plan(id:str):
    return plan_row(id)[1]

@app.post('/api/plans/{id}/prices')
def refresh_prices(id:str,request:Request):
    _,plan=plan_row(id,request.state.owner)
    rate_key='price-refresh:'+request.state.owner
    if store.cached(rate_key):raise HTTPException(429,'단가 검색은 잠시 후 다시 시도해 주세요.')
    store.cache(rate_key,True,5)
    from .pricing import price_plans
    updated=price_plans([plan],force=True)[0]
    return store.save_plan(updated,request.state.owner,parent=id)

@app.get('/api/plans/{id}/restaurants')
def nearby_restaurants(id:str,request:Request,after_index:int=Query(default=0,ge=0,le=4)):
    _,plan=plan_row(id)
    from .restaurants import search_nearby
    key='local-rate:'+request.state.owner
    if store.cached(key):raise HTTPException(429,'주변 식당 검색은 잠시 후 다시 시도해 주세요.')
    store.cache(key,True,1)
    try:return search_nearby(plan,after_index)
    except ValueError as exc:raise HTTPException(422,str(exc))

class ReplaceInput(BaseModel):
    index:int=Field(ge=0,le=4)
    locked:list[int]=Field(default_factory=list,max_length=5)
    replacement_id:str|None=None


@app.get('/api/plans/{id}/meal-rescue')
def recommend_meal_rescue(id:str):
    _,plan=plan_row(id)
    from .restaurants import meal_rescue
    return meal_rescue(plan)

@app.post('/api/plans/{id}/alternatives')
def alternatives(id:str,data:ReplaceInput,request:Request):
    _,plan=plan_row(id,request.state.owner)
    try:
        from .pricing import price_plans
        options=price_plans(replacements(plan,data.index,data.locked))
        for option in options:option['delta']['cost']=[option['total'][i]-plan['total'][i] for i in (0,1)]
        return {'alternatives':options}
    except ValueError as exc:raise HTTPException(422,str(exc))

@app.post('/api/plans/{id}/replace')
def replace(id:str,data:ReplaceInput,request:Request):
    _,plan=plan_row(id,request.state.owner)
    try:options=replacements(plan,data.index,data.locked)
    except ValueError as exc:raise HTTPException(422,str(exc))
    chosen=next((p for p in options if p['places'][data.index]['id']==data.replacement_id),None)
    if not chosen:raise HTTPException(422,'선택 조건을 만족하는 대체 장소가 없습니다.')
    from .pricing import price_plans
    updated=price_plans([chosen])[0]
    updated['delta']['cost']=[updated['total'][i]-plan['total'][i] for i in (0,1)]
    return store.save_plan(updated,request.state.owner,parent=id)

@app.post('/api/plans/{id}/undo')
def undo(id:str,request:Request):
    row,plan=plan_row(id,request.state.owner)
    if not row['parent']:raise HTTPException(422,'되돌릴 변경이 없습니다.')
    return plan_row(row['parent'],request.state.owner)[1]

@app.get('/api/plans/{id}/reviews')
def reviews(id:str,request:Request):
    row,_=plan_row(id)
    return store.reviews(row['aggregate_key'],request.state.owner)

@app.put('/api/plans/{id}/review')
def review(id:str,data:ReviewInput,request:Request):
    row,_=plan_row(id)
    try:store.put_review(row['aggregate_key'],request.state.owner,data)
    except ValueError as exc:raise HTTPException(429,str(exc))
    return store.reviews(row['aggregate_key'],request.state.owner)

@app.delete('/api/reviews/{id}')
def delete_review(id:str,request:Request):
    with store.connect() as db:
        row=db.execute('SELECT author FROM reviews WHERE id=?',(id,)).fetchone()
        if not row:raise HTTPException(404,'후기를 찾을 수 없습니다.')
        if row['author']!=request.state.owner:raise HTTPException(403,'본인의 후기만 삭제할 수 있습니다.')
        db.execute('DELETE FROM reviews WHERE id=?',(id,))
    return {'deleted':True}

class ReportInput(BaseModel):
    reason:str=Field(min_length=1,max_length=2000)

@app.post('/api/reviews/{id}/report')
def report(id:str,data:ReportInput,request:Request):
    with store.connect() as db:
        if not db.execute('SELECT 1 FROM reviews WHERE id=?',(id,)).fetchone():raise HTTPException(404,'후기를 찾을 수 없습니다.')
        db.execute('INSERT OR REPLACE INTO reports VALUES(?,?,?,?)',(id,request.state.owner,data.reason,time.time()))
    return {'reported':True,'notice':'신고 접수됨. 자동 삭제되지 않으며 관리자 검토가 필요합니다.'}

def scope_ids(kind,id,mode):
    if kind=='place':
        if not get_place(id,mode):raise HTTPException(404,'장소를 찾을 수 없습니다.')
        return [id]
    _,plan=plan_row(id)
    if plan['conditions']['mode']!=mode:raise HTTPException(422,'일정 데이터 모드가 일치하지 않습니다.')
    return [p['id'] for p in plan['places']]

@app.get('/api/chat/{kind}/{id}')
def chat_history(kind:Literal['place','plan'],id:str,request:Request,mode:Literal['demo','real']='demo'):
    scope_ids(kind,id,mode)
    return {'messages':store.history(request.state.owner,f'{mode}:{kind}:{id}')}

@app.post('/api/chat/{kind}/{id}')
def chat(kind:Literal['place','plan'],id:str,data:ChatInput,request:Request):
    ids=scope_ids(kind,id,data.mode);scope=f'{data.mode}:{kind}:{id}'
    result=ask(ids,data.question,data.mode,store.history(request.state.owner,scope))
    store.chat_save(request.state.owner,scope,data.question,result['answer'])
    return result

@app.get('/')
def home():
    html=(ROOT/'static'/'index.html').read_text(encoding='utf-8')
    # 파일 변경 시 URL도 바꿔 이전 maps.js와 새 app.js의 혼합 로딩을 방지한다.
    def versioned(match):
        url=match.group(1)
        path=ROOT/url.lstrip('/')
        if not path.is_file():return match.group(0)
        version=hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        return url+'?v='+version
    html=re.sub(r'(/static/[^\s"\'<>?]+\.(?:js|css))',versioned,html)
    return HTMLResponse(html,headers={'Cache-Control':'no-store'})

app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
