from .service_time import today
"""요청 시 가격 검색. 공식 단가 / 웹 참고 단가 / 계획용 가정을 구분한다."""
import copy
import os
import re
from urllib.parse import unquote,urlsplit
from datetime import datetime,timezone,date
from concurrent.futures import ThreadPoolExecutor
import httpx
from .telemetry import observed_http
from . import store
from .image_search import plain,safe_https,search_enabled
from .request_usage import context_map,cache_hit

# 조회 가격이 아닌 예산 계획용 1인 범위. 사용자가 허용한 경우에만 사용한다.
ASSUMPTIONS={'문화·예술':[0,10000],'카페·미식':[6000,15000],'체험·제작':[15000,40000],
    '오락·놀이':[10000,30000],'레저·활동':[10000,30000],'휴식·힐링':[0,15000],'산책·풍경':[0,5000]}

def price_name(place):
    wiki=urlsplit(place.get('wikipedia') or '')
    if wiki.hostname=='ko.wikipedia.org':
        name=re.sub(r'\s*\([^)]*\)$','',unquote(wiki.path.rsplit('/',1)[-1]).replace('_',' '))
        if name and re.search(r'[가-힣]',name):return name
    return place['name']

def extract_quote(place,item):
    title=plain(item.get('title',''));description=plain(item.get('description',''));text=title+' '+description
    compact=re.sub(r'\s+','',text).casefold()
    if place.get('image_keywords'):
        if not all(re.sub(r'\s+','',word).casefold() in compact for word in place['image_keywords']):return None
    elif not any(re.sub(r'\s+','',name).casefold() in compact for name in [price_name(place),place['name']]):return None
    url=item.get('link','')
    if not safe_https(url):return None
    posted=str(item.get('postdate',''))
    try:posted_date=datetime.strptime(posted,'%Y%m%d').date()
    except ValueError:return None
    if not 0<=(today()-posted_date).days<=365:return None
    category=place['category']
    keywords=r'성인(?:\s*입장료)?|일반(?:\s*관람료)?|입장료|관람료|1인\s*이용료'
    if category=='카페·미식':keywords=r'아메리카노|칼국수|국밥|냉면|돈까스|돈가스|파스타|보이차|우롱차|녹차|홍차|말차|대추차|유자차|쌍화차'
    elif category in ('체험·제작','레저·활동','오락·놀이'):keywords+=r'|1인\s*체험비|1인\s*체험료|1인\s*이용권'
    free=re.search(r'(상설전시(?:\s*관람료)?|입장료|관람료)\s*(?:은|는|:|：|이|가)?\s*무료(?!\s*(?:아니|아닌|아닙))',text)
    if free and category!='카페·미식':return dict(amount=0,item=free[1],source=url,posted_at=posted_date.isoformat(),evidence=text[max(0,free.start()-30):free.end()+40])
    match=re.search(r'('+keywords+r')\s*(?:은|는|:|：|이|가)?\s*(?:1인(?:당)?\s*)?(\d[\d,]*(?:\.\d+)?)\s*(만|천)?\s*원',text)
    if not match:return None
    value=int(float(match[2].replace(',',''))*({'만':10000,'천':1000}.get(match[3],1)))
    if not 500<=value<=300000:return None
    return dict(amount=value,item=match[1],source=url,posted_at=posted_date.isoformat(),evidence=text[max(0,match.start()-30):match.end()+40])

def lookup_price(place,force=False):
    key='price-search-v2:'+place['id']
    if not force:
        cached=store.cached(key)
        if cached and not (cached['status']=='key_missing' and search_enabled()):cache_hit();return cached
    result=dict(status='key_missing',quotes=[],checked_at=datetime.now(timezone.utc).isoformat())
    if search_enabled():
        try:
            keys=place.get('image_keywords') or []
            search_name=' '.join(keys) if len(keys)>=2 else price_name(place)
            if len(keys)<2 and ' ' in search_name:search_name='"'+search_name+'"'
            query=search_name+' '+('메뉴 가격' if place['category']=='카페·미식' else '입장료')
            response=observed_http(httpx.get,'https://naverapihub.apigw.ntruss.com/search/v1/blog',params=dict(query=query,display=30,start=1,sort='sim',format='json'),
                headers={'X-NCP-APIGW-API-KEY-ID':os.environ['NAVER_SEARCH_CLIENT_ID'],'X-NCP-APIGW-API-KEY':os.environ['NAVER_SEARCH_CLIENT_SECRET']},timeout=7)
            response.raise_for_status();quotes=[];seen=set()
            for item in response.json().get('items',[]):
                if not isinstance(item,dict):continue
                quote=extract_quote(place,item)
                if quote and quote['source'] not in seen:quotes.append(quote);seen.add(quote['source'])
                if len(quotes)==3:break
            result.update(status='available' if quotes else 'not_found',quotes=quotes)
        except (httpx.HTTPError,ValueError,TypeError,KeyError):result['status']='unavailable'
    store.cache(key,result,3600 if result['status']=='available' else 300)
    return result

def apply_prices(plan,lookups):
    plan=copy.deepcopy(plan)
    if plan['conditions']['mode']!='real':return plan
    allow=plan['conditions'].get('allow_price_estimates',True);people=plan['conditions']['people'];updates=[]
    for index,place in enumerate(plan['places']):
        row=plan['costs'][index]
        if row.get('price_kind')=='naver_menu':continue
        if row['unit'] is not None and not row.get('price_kind'):
            row['price_basis']=('업체 제공 단가 · 확인일 기준' if row.get('source_kind')=='merchant' else '등록 출처 단가 · 확인일 기준') if row['status']=='confirmed' else '기존 단가 · 현재가 별도 확인';continue
        result=lookups.get(place['id'],{});quotes=result.get('quotes',[])
        if quotes:
            # 서로 다른 메뉴를 섞어 단가 범위로 만들지 않는다.
            item=quotes[0]['item'];quotes=[q for q in quotes if q['item']==item]
            unit=[min(q['amount'] for q in quotes),max(q['amount'] for q in quotes)]
            basis='웹 참고 단가 · '+item+' 기준/인 (공식 현재가 미검증)';source=quotes[0]['source'];kind='web_reference'
        elif allow:
            unit=ASSUMPTIONS.get(place['category'],[0,20000]);basis='계획용 1인 범위 · 검색에서 가격을 확보하지 못해 사용한 가정 (실제 단가 아님)';source='서비스 예산 계획용 가정';kind='planning_assumption'
        else:
            row.update(price_basis='검색에서 단가를 확보하지 못했어요.',price_lookup_status=result.get('status','not_found'),checked_at=result.get('checked_at'));continue
        amount=[v*people for v in unit]
        row.update(unit=unit,quantity=people,formula=f'1인 기준 × {people}',amount=amount,status='estimated',source=source,
            checked_at=result.get('checked_at'),price_basis=basis,price_kind=kind,price_evidence=quotes,
            price_lookup_status=result.get('status','not_found'))
        updates.append(place['name']+' 가격')
    plan['unknown']=[u for u in plan['unknown'] if u not in updates]
    total=[sum(r['amount'][i] for r in plan['costs'] if r['amount'] is not None) for i in (0,1)]
    known=[sum(r['amount'][i] for r in plan['costs'] if r['amount'] is not None and r['status']=='confirmed') for i in (0,1)]
    budget=plan['conditions']['budget']
    plan.update(total=total,confirmed=known,estimated=[total[i]-known[i] for i in (0,1)],remaining=[budget-total[1],budget-total[0]],
        pricing_checked_at=datetime.now(timezone.utc).isoformat())
    if total[1]>budget:plan.update(best_effort=True,status='예산을 넘는 대안 · 비용 확인 필요')
    from .condition_audit import audit_plan
    plan=audit_plan(plan)
    if total[1]<=budget and plan['status'].startswith('예산을 넘는'):
        if not any(d['state']=='unmet' for d in plan['deviations']):plan['best_effort']=False
        plan['status']='조건에 가까운 대안 · 차이 확인 필요'
        plan=audit_plan(plan)
    return plan

def price_plans(plans,force=False):
    needed={p['id']:p for plan in plans if plan['conditions']['mode']=='real' for p in plan['places'] if p['price'] is None}
    with ThreadPoolExecutor(max_workers=3) as executor:
        data=dict(zip(needed,context_map(executor,lambda p:lookup_price(p,force),needed.values())))
    return [apply_prices(p,data) for p in plans]
