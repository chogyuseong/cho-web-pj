"""일정 변경 초안, 사용자 피드백, 장소 확인과 두 브라우저의 합의."""
import copy
import json
import time
import uuid
from . import store
from .models import Conditions
from .preferences import hard_blocks,operating_source_current,selection_notes

def event(owner,plan_id,kind,payload):
    with store.connect() as db:db.execute('INSERT INTO experience_events VALUES(?,?,?,?,?,?)',(uuid.uuid4().hex,owner,plan_id,kind,json.dumps(payload,ensure_ascii=False),time.time()))

def feedback_exclusions(owner):
    with store.connect() as db:rows=db.execute("SELECT payload FROM experience_events WHERE owner=? AND kind='replace_reason' ORDER BY created DESC LIMIT 50",(owner,)).fetchall()
    return list(dict.fromkeys(p['place_id'] for row in rows if (p:=json.loads(row[0])).get('reason') in ('visited','taste')))[:100]

def verification_summary(plan):
    with store.connect() as db:pending={r[0] for r in db.execute('SELECT DISTINCT place_id FROM place_reports WHERE resolved=0')}
    rows=[]
    for p in plan['places']:
        source=operating_source_current(p)
        label='제보 확인 필요' if p['id'] in pending else '최근 운영 자료 있음' if source else '주소 연결 · 운영 미확인' if p.get('discovery_verification') else '운영 정보 추가 확인'
        rows.append(dict(id=p['id'],name=p['name'],label=label,pending=p['id'] in pending,source=p.get('operations_source'),checked_at=p.get('operations_checked_at'),current_operating_source=source))
    return dict(places=rows,notes=selection_notes(Conditions.model_validate(plan['conditions'])))

def make_draft(plan,original,owner,kind,summary):
    c=Conditions.model_validate(plan['conditions'])
    if c.mode=='real' and c.transport=='car' and not all(r['status']=='api' for r in plan['legs']):
        from .planner import evaluate
        from .pricing import price_plans
        recalculated,error=evaluate(plan['places'],c,soft=True,verify_routes=True)
        if recalculated:
            plan.update(recalculated);plan=price_plans([plan])[0]
            plan['route_verification']='네이버 자동차 길찾기로 변경 동선을 재조회했어요.'
        else:plan['route_verification']='자동차 실제 경로 확인 실패 · 추정 동선이며 실제 이동은 길찾기로 확인해 주세요.'
    token=uuid.uuid4().hex;blocking=hard_blocks(plan)
    plan['verification']=verification_summary(plan)
    draft=dict(token=token,plan=plan,can_apply=not blocking,blocking=blocking,summary=summary,kind=kind,
               delta=dict(minutes=plan['minutes']-original['minutes'],cost=[plan['total'][i]-original['total'][i] for i in (0,1)]))
    draft['lock_version']=original.get('lock_version',0)
    if kind=='agreement':draft['vote_snapshot']=vote_status(original,owner)['places']
    store.cache('plan-draft:'+token,dict(owner=owner,parent=original['id'],draft=draft),600)
    return draft

def apply_draft(parent,token,owner):
    saved=store.cached('applied-draft:'+token)
    if saved:
        if saved['owner']!=owner or saved['parent']!=parent:raise PermissionError('본인의 변경 초안만 적용할 수 있어요.')
        return json.loads(store.get_plan(saved['id'])['payload'])
    cached=store.cached('plan-draft:'+token)
    if not cached:raise ValueError('변경 미리보기가 만료됐어요. 다시 계산해 주세요.')
    if cached['owner']!=owner or cached['parent']!=parent:raise PermissionError('본인의 변경 초안만 적용할 수 있어요.')
    draft=cached['draft'];plan=draft['plan']
    current=json.loads(store.get_plan(parent)['payload'])
    if current.get('lock_version',0)!=draft.get('lock_version',0):raise ValueError('미리보기 후 고정 장소가 바뀌었어요. 다시 계산해 주세요.')
    if draft.get('vote_snapshot') is not None:
        original=json.loads(store.get_plan(parent)['payload'])
        if vote_status(original,owner)['places']!=draft['vote_snapshot']:raise ValueError('미리보기 후 의견이 바뀌었어요. 합의 코스를 다시 계산해 주세요.')
    if hard_blocks(plan):raise ValueError('필수 조건을 충족하지 못해 적용할 수 없어요.')
    plan.update(delta=draft['delta'],change_reason=draft['summary'])
    # 동시 적용 요청도 동일한 일정 한 개만 생성한다 (SQLite 단일 트랜잭션).
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        previous=db.execute('SELECT payload FROM cache WHERE key=? AND expires>?',('applied-draft:'+token,time.time())).fetchone()
        if previous:
            info=json.loads(previous['payload'])
            if info['owner']!=owner or info['parent']!=parent:raise PermissionError('본인의 변경 초안만 적용할 수 있어요.')
            row=db.execute('SELECT payload FROM plans WHERE id=?',(info['id'],)).fetchone()
            if not row:raise ValueError('적용한 일정이 만료됐어요.')
            return json.loads(row['payload'])
        original_row=db.execute('SELECT payload FROM plans WHERE id=? AND owner=?',(parent,owner)).fetchone()
        if not original_row:raise PermissionError('원본 일정의 소유자를 확인할 수 없어요.')
        if json.loads(original_row['payload']).get('lock_version',0)!=draft.get('lock_version',0):raise ValueError('고정 장소가 바뀌었어요. 다시 계산해 주세요.')
        if draft.get('vote_snapshot') is not None and vote_status(json.loads(original_row['payload']),owner)['places']!=draft['vote_snapshot']:raise ValueError('의견이 바뀌었어요. 다시 계산해 주세요.')
        result=dict(plan,id=uuid.uuid4().hex,parent=parent)
        result['aggregate_key']=store.aggregate_key([p['id'] for p in result['places']])
        db.execute('INSERT INTO plans VALUES(?,?,?,?,?)',(result['id'],owner,parent,result['aggregate_key'],json.dumps(result,ensure_ascii=False)))
        db.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?)',('applied-draft:'+token,json.dumps(dict(id=result['id'],owner=owner,parent=parent)),time.time()+600))
    event(owner,parent,'apply_'+draft['kind'],dict(new_plan_id=result['id']))
    return result

def meal_draft(original,owner,food_id,after_index,replace_index,locked,menu_index):
    from .catalog import get_place
    from .quality import is_meal,in_area,same_place
    from .planner import evaluate
    from .pricing import price_plans
    from .condition_audit import audit_plan
    from .menus import restaurant_menu,cost_menu_options
    c=Conditions.model_validate(original['conditions']);food=get_place(food_id,c.mode)
    if not food or not is_meal(food):raise ValueError('확인된 음식점만 일정에 넣을 수 있어요.')
    if not in_area(food,c):raise ValueError('선택한 동네 범위 밖의 식당이에요. 이동 범위를 직접 조정해 주세요.')
    if any(w.casefold() in (food['name']+' '+str(food.get('cuisine',''))+' '+' '.join(food.get('tags',[]))).casefold() for w in c.avoid):raise ValueError('피할 활동에 해당하는 식당이에요.')
    chosen=copy.deepcopy(original['places']);protected=set(locked)|set(c.locked)
    if any(i<0 or i>=len(chosen) for i in protected):raise ValueError('고정 장소 번호를 확인하세요.')
    mapping={i:chosen[i]['id'] for i in protected};undo_locks=dict(mapping)
    if replace_index is not None:
        if not 0<=replace_index<len(chosen) or replace_index in protected:raise ValueError('교체 위치가 잘못됐거나 고정한 장소예요.')
        target=replace_index;chosen.pop(target)
        mapping={i-(i>target):pid for i,pid in mapping.items()}
    else:
        if len(chosen)>=5:raise ValueError('최대 5곳까지 가능해요. 추가 대신 장소 교체를 선택해 주세요.')
        if not -1<=after_index<len(chosen):raise ValueError('추가 위치를 확인하세요.')
        target=after_index+1
    if any(same_place(food,p) for p in chosen):raise ValueError('이미 일정에 있는 식당이에요.')
    food=copy.deepcopy(food);food.update(price_unit='person',meal=True,stay_assumed=not food.get('stay'),stay=food.get('stay') or 60,stay_basis='식사 체류 60분 가정' if not food.get('stay') else food.get('stay_basis'))
    menu=restaurant_menu(food) if c.mode=='real' else dict(items=[])
    options=cost_menu_options(menu)
    selected_menu=None
    if options:
        if not 0<=menu_index<len(options):raise ValueError('선택한 메뉴가 바뀌었어요. 메뉴를 다시 확인해 주세요.')
        selected_menu=options[menu_index];food.update(price=[selected_menu['amount']]*2,price_status='estimated')
        food['menu_pricing']=dict(price_kind='naver_menu',price_basis=selected_menu['name']+' 1개/인 가정 · 네이버 공개 메뉴 참고가',source=menu['source_url'],checked_at=menu['checked_at'])
    chosen.insert(target,food)
    mapping={i+(i>=target):pid for i,pid in mapping.items()}
    c=c.model_copy(update={'count':len(chosen),'locked':mapping,'include_meal':True})
    plan,error=evaluate(chosen,c,soft=True,verify_routes=c.mode=='real' and c.transport=='car')
    route_note=None
    if error and c.mode=='real' and c.transport=='car' and c.allow_estimates:
        plan,error=evaluate(chosen,c,soft=True);route_note='자동차 경로 조회 실패로 추정 동선을 유지했어요.'
    if error:raise ValueError(error)
    if selected_menu:
        row=plan['costs'][target]
        row.update(price_kind='naver_menu',price_basis=selected_menu['name']+' 1개/인 가정 · 네이버 공개 메뉴 참고가',source=menu['source_url'],checked_at=menu['checked_at'])
    if original.get('course_search'):plan['course_search']=original['course_search']
    plan=price_plans([plan])[0];plan=audit_plan(plan,c)
    plan['undo_locks']=undo_locks
    if any(d['state']=='unmet' for d in plan['deviations']):plan.update(best_effort=True,status='조건 차이가 있는 변경안')
    if route_note:plan['route_verification']=route_note
    elif c.mode=='real' and c.transport=='car':plan['route_verification']='네이버 자동차 길찾기 재조회 반영'
    action='교체' if replace_index is not None else '추가'
    summary=f"{food['name']} {action} · 방문 {len(original['places'])}→{len(chosen)}곳 · 식사 {food['stay']}분 및 비용·이동 재계산"
    return make_draft(plan,original,owner,'meal',summary)

def vote_status(plan,viewer):
    with store.connect() as db:rows=db.execute('SELECT owner,payload FROM partner_votes WHERE plan_id=?',(plan['id'],)).fetchall()
    mine=next((json.loads(r['payload']) for r in rows if r['owner']==viewer),{})
    counts={p['id']:dict(yes=0,no=0,neutral=0) for p in plan['places']}
    for row in rows:
        for pid,value in json.loads(row['payload']).items():
            if pid in counts:counts[pid][value]+=1
    return dict(participants=len(rows),mine=mine,places=counts,verification='브라우저별 의견 · 실제 신원·방문 인증 아님')

def save_votes(plan,viewer,plan_owner,choices,share_token=None):
    ids={p['id'] for p in plan['places']}
    if set(choices)!=ids:raise ValueError('모든 장소의 의견을 선택해 주세요.')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if share_token is not None and not db.execute('SELECT 1 FROM plan_shares WHERE token_hash=? AND plan_id=? AND expires>?',(share_token,plan['id'],time.time())).fetchone():
            raise ValueError('공유 링크가 만료되었거나 취소됐어요.')
        others=[r[0] for r in db.execute('SELECT owner FROM partner_votes WHERE plan_id=?',(plan['id'],)) if r[0]!=plan_owner]
        if viewer!=plan_owner and viewer not in others and others:raise ValueError('이 코스에는 이미 다른 브라우저의 상대방 의견이 있어요. 두 브라우저까지만 참여할 수 있어요.')
        db.execute('INSERT INTO partner_votes VALUES(?,?,?,?) ON CONFLICT(plan_id,owner) DO UPDATE SET payload=excluded.payload,updated=excluded.updated',(plan['id'],viewer,json.dumps(choices),time.time()))
    event(viewer,plan['id'],'vote',dict(place_count=len(choices)))
    return vote_status(plan,viewer)

def agreement_draft(plan,owner,ui_locked=None):
    from .planner import recommend
    from .pricing import price_plans
    from .preferences import filter_required
    status=vote_status(plan,owner)
    if status['participants']<2:raise ValueError('두 브라우저에서 의견을 저장한 뒤 다시 계산할 수 있어요.')
    c=Conditions.model_validate(plan['conditions']);locked=dict(c.locked)
    for i in ui_locked or []:
        if not 0<=i<len(plan['places']):raise ValueError('고정 장소 번호를 확인해 주세요.')
        locked[i]=plan['places'][i]['id']
    undo_locks=dict(locked)
    disliked={pid for pid,counts in status['places'].items() if counts['no']}
    if disliked.intersection(locked.values()):raise ValueError('고정한 장소에 반대 의견이 있어요. 고정을 해제하거나 두 사람의 의견을 조정해 주세요.')
    for i,p in enumerate(plan['places']):
        if status['places'][p['id']]['yes']==2:locked[i]=p['id']
    c=c.model_copy(update={'locked':locked,'excluded_place_ids':list(set(c.excluded_place_ids)|disliked)})
    result=recommend(c,plan.get('course_search'))
    candidates=filter_required(price_plans(result['plans']))
    if not candidates:raise ValueError('두 사람의 의견과 필수 조건을 함께 만족하는 코스를 찾지 못했어요. 조건이나 반대 의견을 직접 조정해 주세요.')
    chosen=candidates[0]
    chosen['undo_locks']=undo_locks
    if plan.get('course_search'):chosen['course_search']=plan['course_search']
    return make_draft(chosen,plan,owner,'agreement','두 사람 모두 좋아하는 장소는 고정하고, 반대 의견이 있는 장소는 제외해 재계산했어요.')
