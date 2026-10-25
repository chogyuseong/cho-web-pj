import json
import os
import secrets
import time
import mimetypes
import logging
import uuid
import hashlib
import re
import asyncio
from contextlib import suppress
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import FastAPI, HTTPException, Request, Response, Query
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from . import store
from .catalog import places,get_place
from .config import ROOT,REGION,production,public_origin,validate_runtime
from . import web_security
from .models import Conditions,ReviewInput,ChatInput,THEMES
from .planner import recommend,replacements
from .indexing import collections,embedding_mode,search_places
from .rag import ask
from .geocoding import search_address
from .taxonomy import DATE_CATEGORIES
from .media import media_info
from .blog_search import place_blogs
from .execution import bounded_recommendation

# Windows 레지스트리의 .js=text/plain 매핑에서도 nosniff와 호환되도록 고정한다.
mimetypes.add_type('text/javascript', '.js')
mimetypes.add_type('text/javascript', '.mjs')
mimetypes.add_type('text/css', '.css')

@asynccontextmanager
async def lifespan(app):
    validate_runtime()
    await run_in_threadpool(store.init)
    from .maintenance import loop
    from .plan_jobs import heartbeat_loop
    task=asyncio.create_task(loop())
    heartbeat_task=asyncio.create_task(heartbeat_loop())
    try:yield
    finally:
        task.cancel()
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):await task
        with suppress(asyncio.CancelledError):await heartbeat_task

app=FastAPI(title='서울 데이트메이트 · 서울 데이트 코스 추천',version='0.2.0',lifespan=lifespan,
            docs_url=None if production() else '/docs',
            redoc_url=None if production() else '/redoc',
            openapi_url=None if production() else '/openapi.json')
from .experience_api import router as experience_router
app.include_router(experience_router)
from .plan_jobs import router as jobs_router
app.include_router(jobs_router)
from .inspiration import router as inspiration_router
app.include_router(inspiration_router)
from .explore import router as explore_router
app.include_router(explore_router)
from .sharing import router as sharing_router
app.include_router(sharing_router)

@app.get('/healthz',include_in_schema=False)
def health():
    return {'status':'ok'}

@app.get('/readyz',include_in_schema=False)
def readiness():
    try:
        with store.connect() as db:
            db.execute('SELECT 1 FROM sessions LIMIT 1').fetchone()
        return {'status':'ready','scope':'database_only','external_services_verified':False}
    except Exception:
        return JSONResponse({'status':'not_ready'},status_code=503)

@app.middleware('http')
async def safety(request:Request,call_next):
    started=time.perf_counter()
    request_id=uuid.uuid4().hex
    def finish(response):
        response.headers['Server-Timing']=f'total;dur={(time.perf_counter()-started)*1000:.2f}'
        return web_security.headers(response,request,request_id)
    token=None;exists=True
    try:
        if not web_security.allowed_host(request):
            return finish(JSONResponse({'detail':'허용되지 않은 사이트 주소입니다.'},status_code=400))
        if request.url.path in ('/healthz','/readyz') or request.url.path.startswith('/static/'):
            return finish(await call_next(request))
        if request.method in ('POST','PUT','PATCH','DELETE'):
            origin=request.headers.get('origin')
            expected=public_origin() or str(request.base_url).rstrip('/')
            if (origin and origin.rstrip('/')!=expected) or request.headers.get('sec-fetch-site')=='cross-site':
                return finish(JSONResponse({'detail':'다른 사이트에서 보낸 변경 요청은 허용하지 않습니다.'},status_code=403))
            body=bytearray()
            try:
                async with asyncio.timeout(15):
                    async for chunk in request.stream():
                        body.extend(chunk)
                        if len(body)>2*1024*1024:
                            return finish(JSONResponse({'detail':'요청은 2 MiB 이하로 보내주세요.'},status_code=413))
            except TimeoutError:
                return finish(JSONResponse({'detail':'요청 전송 시간이 초과됐어요.'},status_code=408))
            request._body=bytes(body)
        if not await run_in_threadpool(web_security.api_budget,request):
            return finish(JSONResponse({'detail':'요청이 많아요. 잠시 후 다시 시도해 주세요.'},status_code=429,headers={'Retry-After':'60'}))
        def identify():
            token=request.cookies.get('dm_session','')[:128]
            with store.connect() as db:
                exists=db.execute('SELECT 1 FROM sessions WHERE token=?',(token,)).fetchone()
                if not exists:
                    token=secrets.token_urlsafe(32)
                    db.execute('INSERT INTO sessions VALUES(?,?)',(token,time.time()))
            return token,bool(exists)
        token,exists=await run_in_threadpool(identify)
        request.state.owner=token
        match=re.match(r'^/api/(?:plans/|chat/plan/)([^/]+)',request.url.path)
        if match:
            row=await run_in_threadpool(store.get_plan,match.group(1))
            if not row or row['owner']!=token:
                response=JSONResponse({'detail':'일정을 찾을 수 없습니다. 공유 링크로 접속해 주세요.'},status_code=404)
            else:response=await call_next(request)
        else:response=await call_next(request)
    except Exception:
        logging.getLogger(__name__).exception('request_failed id=%s method=%s path=%s',request_id,request.method,request.url.path)
        response=JSONResponse({'detail':'요청 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.'},status_code=500)
    if token and not exists and request.url.path!='/api/me/data':
        response.set_cookie('dm_session',token,httponly=True,samesite='strict',secure=production() or request.url.scheme=='https',max_age=2592000)
    return finish(response)


def plan_row(id,owner=None):
    row=store.get_plan(id)
    if not row:raise HTTPException(404,'일정을 찾을 수 없습니다.')
    if owner is not None and row['owner']!=owner:raise HTTPException(403,'이 브라우저에서 만든 일정만 수정할 수 있습니다.')
    from .condition_audit import audit_plan
    plan=audit_plan(json.loads(row['payload']))
    from .experience import verification_summary
    plan['verification']=verification_summary(plan)
    from .recommendation_summary import enrich
    enrich(plan)
    return row,plan

@app.delete('/api/me/data')
def delete_my_data(request:Request,response:Response):
    owner=request.state.owner
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT INTO revoked_sessions VALUES(?,?) ON CONFLICT(token) DO NOTHING',(owner,time.time()))
        db.execute('DELETE FROM plan_shares WHERE owner=?',(owner,))
        db.execute('DELETE FROM request_budgets WHERE scope=?',('recommendations:'+owner,))
        # Remove related records before removing the user's plans and reviews.
        db.execute('DELETE FROM partner_votes WHERE plan_id IN (SELECT id FROM plans WHERE owner=?)',(owner,))
        db.execute('DELETE FROM reports WHERE review_id IN (SELECT id FROM reviews WHERE author=?)',(owner,))
        for table,column in (('plans','owner'),('chats','owner'),('reviews','author'),
                             ('reports','author'),('experience_events','owner'),
                             ('place_reports','owner'),('partner_votes','owner')):
            db.execute(f'DELETE FROM {table} WHERE {column}=?',(owner,))
        db.execute('DELETE FROM cache WHERE key IN (SELECT key FROM cache_owners WHERE owner=?)',(owner,))
        for prefix in ('geocode-rate:','menu-refresh:','price-refresh:','local-rate:'):
            db.execute('DELETE FROM cache WHERE key=?',(prefix+owner,))
        db.execute('DELETE FROM sessions WHERE token=?',(owner,))
    response.delete_cookie('dm_session')
    from .plan_jobs import forget_owner
    forget_owner(owner)
    return {'deleted':True,'notice':'현재 브라우저에 연결된 저장 데이터를 삭제했습니다. 별도 백업과 외부 서비스 기록은 포함되지 않습니다.'}

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
def place_media(id:str,mode:Literal['demo','real']='real',fallback:Literal['','place']='',refresh:bool=False):
    p=get_place(id,mode)
    if p is None:raise HTTPException(404,'장소를 찾을 수 없습니다.')
    return media_info(p,prefer_public=fallback=='place',force=refresh)

@app.get('/api/places/{id}/blogs')
def place_blog_results(id:str,mode:Literal['demo','real']='real'):
    p=get_place(id,mode)
    if p is None:raise HTTPException(404,'장소를 찾을 수 없습니다.')
    return place_blogs(p)

@app.get('/api/places/{id}/menu')
def place_menu(id:str,request:Request,mode:Literal['demo','real']='real',refresh:bool=False):
    p=get_place(id,mode)
    if p is None:raise HTTPException(404,'장소를 찾을 수 없습니다.')
    from .menus import restaurant_menu
    if refresh:
        key='menu-refresh:'+request.state.owner
        if store.cached(key):raise HTTPException(429,'메뉴 새로 조회는 잠시 후 다시 시도해 주세요.')
        store.cache(key,True,5)
    return restaurant_menu(p,force=refresh)

@app.post('/api/conditions/parse')
def parse(data:ParseInput):
    from .request_intent import interpret
    parsed=interpret(data.text)
    patch=dict(parsed['patch'],region=REGION)
    warnings=['입력 글에서 확인한 활동·인원·예산·이동수단을 적용했어요. 폼에서 확인하고 수정할 수 있어요.', '추천 지역은 서울특별시로 고정됩니다. 서울 밖 장소는 추천하지 않습니다.']
    if parsed['excluded']:warnings.append('제외 요청은 코스 추천 시 장소 유형과 대조해 적용해요.')
    return dict(patch=patch,warnings=warnings,unparsed=data.text)

@app.post('/api/plans')
@bounded_recommendation
def create(data:Conditions,request:Request):
    calculation_started=time.perf_counter()
    from .plan_jobs import report
    report("장소 검색", "선택 지역의 후기와 실제 장소를 찾고 있어요")
    from .request_intent import normalize
    data=normalize(data)
    if data.use_feedback:
        from .experience import feedback_exclusions
        data=data.model_copy(update={'excluded_place_ids':list(set(data.excluded_place_ids)|set(feedback_exclusions(request.state.owner)))[:100]})
    from .course_search import search_courses,priority
    evidence=search_courses(data) if data.mode=='real' else None
    if data.mode=='real':
        from .quality import configure
        data=configure(data,evidence['query'])
        from .intent_discovery import discover_requested_places
        evidence['intent_discovery']=discover_requested_places(data)
    report("코스 구성", "취향·필수 조건·이동 동선을 비교하고 있어요")
    result=recommend(data,evidence)
    if data.mode=='real' and (not result['plans'] or any(p.get('search_adjustments') for p in result['plans'])):
        # Retry live research without taste keywords before accepting a wider-area fallback.
        local=data.model_copy(update={'course_query':'','request':'','themes':[],
            'date_category':'','date_subcategory':'','setting':'any','trust_mode':'balanced'})
        broad=search_courses(local)
        discover_requested_places(local)
        if broad['status']=='available' and (broad['query']!=evidence['query'] or not result['plans']):
            original_query=evidence['query']
            broad['search_history']=[*evidence.get('search_history',[]),*broad.get('search_history',[])]
            broad['requested_query']=original_query
            broad['search_relaxed']=broad['query']!=original_query
            broad['relaxation_note']='위치는 유지하고 취향 검색어를 줄여 같은 지역의 일반 데이트 후기를 다시 검색했어요.'
            retried=recommend(data,broad)
            if retried['plans']:
                result=retried;evidence=broad
                for p in result['plans']:
                    adjustments=p.setdefault('search_adjustments',dict(stage='same_location',origin_unchanged=True,
                        original_radius_km=data.neighborhood_radius_km,effective_radius_km=data.neighborhood_radius_km,
                        messages=[],differences=[dict(label=r['label'],message=r['message']) for r in p.get('condition_checks',[]) if r['state']=='unmet']))
                    if original_query!=broad['query']:adjustments['messages'].insert(0,f'후기 검색어를 ‘{original_query}’ → ‘{broad["query"]}’로 넓혔어요.')
    if not result['plans'] and data.area_center:
        result.setdefault('suggestions',[]).insert(0,f'{data.area_center.name} 반경 {data.neighborhood_radius_km:g}km 안에서 찾고 있어요. 동네 이동 범위나 방문 수를 조정해 주세요.')
    if evidence:
        result['course_search']=evidence
        for plan in result['plans']:
            plan['course_search']=evidence
            plan['blog_score']=priority(plan,evidence)
            plan['recommendation_method']='naver_blog_selected5' if plan['blog_score'] else 'conditions_fallback'
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
    report('가격 확인', '코스 후보를 찾았어요. 가격과 필수 조건을 마지막으로 확인해요',preview=[[p['name'] for p in plan['places']] for plan in result['plans']])
    result['plans']=price_plans(result['plans'])
    from .preferences import filter_required,hard_blocks
    blocked=[p for p in result['plans'] if hard_blocks(p)]
    result['plans']=filter_required(result['plans'])
    if blocked and not result['plans']:
        result.update(status='required_unmet',reasons=['선택한 필수 조건을 충족하는 코스를 확인하지 못했어요.'],suggestions=['필수 조건 또는 입력 범위를 직접 조정해 주세요. 미확인 조건을 충족으로 처리하지 않습니다.'])
    if data.mode=='real':
        from .option_diversity import select_options
        result['plans']=select_options(result['plans'],data)
    if result['plans'] and all(p.get('best_effort') for p in result['plans']):result['status']='best_effort'
    from .experience import verification_summary
    for p in result['plans']:p['verification']=verification_summary(p)
    from .recommendation_summary import enrich
    for p in result['plans']:enrich(p)
    from .plan_jobs import check_current
    check_current()
    result['plans']=[store.save_plan(p,request.state.owner) for p in result['plans']]
    from .experience import event
    event(request.state.owner,'','recommendation',dict(plans=len(result['plans']),elapsed_ms=round((time.perf_counter()-calculation_started)*1000),api_cost_status='not_measured'))
    return result

@app.get('/api/plans/{id}')
def get_plan(id:str,request:Request):
    row,plan=plan_row(id)
    plan['can_edit']=row['owner']==request.state.owner
    return plan

@app.post('/api/plans/{id}/prices')
def refresh_prices(id:str,request:Request):
    _,plan=plan_row(id,request.state.owner)
    rate_key='price-refresh:'+request.state.owner
    if store.cached(rate_key):raise HTTPException(429,'단가 검색은 잠시 후 다시 시도해 주세요.')
    store.cache(rate_key,True,5)
    from .pricing import price_plans
    updated=price_plans([plan],force=True)[0]
    from .preferences import hard_blocks
    if hard_blocks(updated):raise HTTPException(409,'재조회 가격 또는 조건이 필수 조건을 넘어요. 필수 조건을 조정한 뒤 다시 추천해 주세요.')
    return store.save_plan(updated,request.state.owner,parent=id)

@app.get('/api/plans/{id}/restaurant-matches')
def matched_restaurants(id:str):
    _,plan=plan_row(id)
    from .restaurants import restaurant_matches
    return restaurant_matches(plan)

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
        from .preferences import filter_required
        options=filter_required(options)
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
    from .preferences import hard_blocks
    if hard_blocks(updated):raise HTTPException(409,'필수 조건을 충족하지 않아 교체할 수 없어요.')
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
        db.execute('INSERT INTO reports VALUES(?,?,?,?) ON CONFLICT(review_id,author) DO UPDATE SET reason=excluded.reason,created=excluded.created',(id,request.state.owner,data.reason,time.time()))
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
    if not store.reserve_budget([('chat:'+request.state.owner,int(os.getenv('DATEMATE_USER_CHATS_PER_MINUTE','6')))],int(time.time()//60)):
        raise HTTPException(429,'질문이 많아요. 잠시 후 다시 시도해 주세요.',headers={'Retry-After':'60'})
    ids=scope_ids(kind,id,data.mode);scope=f'{data.mode}:{kind}:{id}'
    from .plan_chat import answer_plan
    plan=plan_row(id)[1] if kind=='plan' else None
    result=answer_plan(plan,data.question) if plan else None
    if result is None:
        result=ask(ids,data.question,data.mode,store.history(request.state.owner,scope),plan=plan,owner=request.state.owner)
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
@app.post('/api/plans/{id}/leisure-options')
def leisure_options(id:str,data:ReplaceInput,request:Request):
    _,plan=plan_row(id,request.state.owner)
    from .leisure import options
    try:
        rows=options(plan,data.index,data.locked,discover=True)
        return {'options':[{'place':r['plan']['places'][data.index],'distance_m':r['distance_m'],'delta':r['plan']['delta']} for r in rows], 'message':'현재 코스 장소 반경 1.5km의 스포츠 후보예요. 선택하면 해당 순서의 장소를 교체합니다. 직선거리 기준이며 영업·예약은 별도 확인해 주세요.'}
    except ValueError as exc:raise HTTPException(422,str(exc))

@app.post('/api/plans/{id}/leisure-select')
def leisure_select(id:str,data:ReplaceInput,request:Request):
    _,plan=plan_row(id,request.state.owner)
    from .leisure import options
    try:rows=options(plan,data.index,data.locked)
    except ValueError as exc:raise HTTPException(422,str(exc))
    chosen=next((r['plan'] for r in rows if r['plan']['places'][data.index]['id']==data.replacement_id),None)
    if not chosen:raise HTTPException(409,'현재 조건에 맞지 않거나 후보가 바뀌었어요. 주변 레저를 다시 확인해 주세요.')
    from .pricing import price_plans
    from .preferences import hard_blocks
    updated=price_plans([chosen])[0]
    if hard_blocks(updated):raise HTTPException(409,'필수 조건에 맞지 않아 교체하지 않았어요.')
    from .recommendation_summary import enrich
    enrich(updated)
    return store.save_plan(updated,request.state.owner,parent=id)
