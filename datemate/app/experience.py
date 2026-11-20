"""일정 변경 초안, 사용자 피드백, 장소 확인과 두 브라우저의 합의."""
import copy
import json
import time
import uuid
from . import store
from .models import Conditions
from .leg_modes import uses_car
from .preferences import hard_blocks,operating_source_current,selection_notes

def event(owner,plan_id,kind,payload):
    with store.connect() as db:db.execute('INSERT INTO experience_events VALUES(?,?,?,?,?,?)',(uuid.uuid4().hex,owner,plan_id,kind,json.dumps(payload,ensure_ascii=False),time.time()))

def feedback_exclusions(owner):
    with store.connect() as db:rows=db.execute("SELECT payload FROM experience_events WHERE owner=? AND kind='replace_reason' ORDER BY created DESC LIMIT 50",(owner,)).fetchall()
    return list(dict.fromkeys(p['place_id'] for row in rows if (p:=json.loads(row[0])).get('reason') in ('visited','taste')))[:100]

def verification_summary(plan):
    from .data_quality import place_coverage,plan_coverage
    with store.connect() as db:pending={r[0] for r in db.execute('SELECT DISTINCT place_id FROM place_reports WHERE resolved=0')}
    rows=[]
    for p in plan['places']:
        source=operating_source_current(p)
        label='제보 확인 필요' if p['id'] in pending else '최근 운영 자료 있음' if source else '주소 연결 · 운영 미확인' if p.get('discovery_verification') else '운영 정보 추가 확인'
        rows.append(dict(id=p['id'],name=p['name'],label=label,pending=p['id'] in pending,source=p.get('operations_source'),checked_at=p.get('operations_checked_at'),current_operating_source=source,coverage=place_coverage(p),field_sources=p.get('operations_evidence',{})))
    return dict(places=rows,coverage=plan_coverage(plan),notes=selection_notes(Conditions.model_validate(plan['conditions'])))

VOTE_LABELS=dict(must='꼭 가고 싶어요',yes='좋아요',neutral='상관없어요',no='빼주세요')

class VotesChanged(ValueError):
    """계산에 쓴 의견 집계와 지금 유효한 의견이 다르다. changed 는 화면에 보일 장소별 변화."""
    def __init__(self,message,changed):
        super().__init__(message);self.changed=changed

def vote_changes(plan,used,current):
    """장소별로 계산 때 집계(used)와 지금 집계(current)가 다른 항목을 사람이 읽을 문장으로 돌려준다(코스 순서대로)."""
    order=[p['id'] for p in plan['places']];names={p['id']:p['name'] for p in plan['places']}
    rows=[]
    for pid in sorted(set(used)|set(current),key=lambda x:order.index(x) if x in order else len(order)):
        before,after=used.get(pid,{}),current.get(pid,{})
        if before==after:continue
        parts=[f"{VOTE_LABELS[k]} {before.get(k,0)}→{after.get(k,0)}" for k in ('must','yes','no','neutral') if before.get(k,0)!=after.get(k,0)]
        rows.append(dict(place_id=pid,name=names.get(pid,pid),change=' · '.join(parts)))
    return rows

def ensure_votes_unchanged(original,owner,used):
    """적용 직전 검사. 계산에 쓴 의견과 지금 의견이 다르면 무엇이 바뀌었는지 담아 거절한다(계산 도중 변경·미리보기 후 변경 모두)."""
    current=vote_status(original,owner)['places']
    if current==used:return
    changed=vote_changes(original,used,current)
    detail=' / '.join(f"{r['name']}: {r['change']}" for r in changed) or '의견 집계'
    raise VotesChanged('합의 코스를 계산한 뒤 의견이 바뀌었어요('+detail+'). 최신 의견으로 다시 계산해 주세요.',changed)

def make_draft(plan,original,owner,kind,summary,vote_snapshot=None):
    if original.get('recommendation_group_id'):plan['recommendation_group_id']=original['recommendation_group_id']
    c=Conditions.model_validate(plan['conditions'])
    if c.mode=='real' and uses_car(c) and not all(r['status']=='api' for r in plan['legs'] if r.get('mode',c.transport)=='car'):
        from .planner import evaluate
        from .pricing import price_plans
        recalculated,error=evaluate(plan['places'],c,soft=True,verify_routes=True)
        if recalculated:
            plan.update(recalculated);plan=price_plans([plan])[0]
            plan['route_verification']='연결된 경로 공급자로 변경 동선을 재조회했어요. 조회 시점 기준입니다.'
        else:plan['route_verification']='실제 경로 확인 실패 · 추정 동선이며 실제 이동은 길찾기로 확인해 주세요.'
    from .plan_changes import change_delta
    token=uuid.uuid4().hex;blocking=hard_blocks(plan)
    plan['verification']=verification_summary(plan)
    from .recommendation_summary import enrich
    enrich(plan)
    draft=dict(token=token,plan=plan,can_apply=not blocking,blocking=blocking,summary=summary,kind=kind,
               delta=change_delta(original,plan))
    draft['lock_version']=original.get('lock_version',0)
    # 합의 초안은 '계산에 실제로 쓴' 집계를 기록한다. 여기서 다시 읽으면 계산 도중 바뀐 의견이 스냅샷에 들어가
    # 적용 검사가 변경을 놓친다(2026-11-19 재현). 호출한 쪽(agreement_draft)이 쓴 집계를 넘긴다.
    if kind=='agreement':draft['vote_snapshot']=vote_snapshot if vote_snapshot is not None else vote_status(original,owner)['places']
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
        ensure_votes_unchanged(current,owner,draft['vote_snapshot'])
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
        # 트랜잭션 안에서 한 번 더 확인한다(첫 검사와 이 줄 사이에 의견이 바뀌는 경우). 다르면 아무것도 저장하지 않는다.
        if draft.get('vote_snapshot') is not None:ensure_votes_unchanged(json.loads(original_row['payload']),owner,draft['vote_snapshot'])
        result=dict(plan,id=uuid.uuid4().hex,parent=parent)
        result['aggregate_key']=store.aggregate_key([p['id'] for p in result['places']])
        db.execute('INSERT INTO plans(id,owner,parent,aggregate_key,payload,created) VALUES(?,?,?,?,?,?)',(result['id'],owner,parent,result['aggregate_key'],store.plan_payload(result),time.time()))
        db.execute('INSERT INTO cache VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,expires=excluded.expires',('applied-draft:'+token,json.dumps(dict(id=result['id'],owner=owner,parent=parent)),time.time()+600))
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
        # 운영자가 확인한 제공 메뉴(operating_evidence)는 operator_menu. naver_menu 는 네이버 화면에서 읽던 메뉴로, 지금은 꺼져 있다(naver_pages).
        menu_kind='operator_menu' if menu.get('source_kind')=='operator_reviewed_menu' else 'naver_menu'
        food['menu_pricing']=dict(price_kind=menu_kind,price_basis=selected_menu['name']+' 1개/인 가정 · '+menu.get('source_label','공개 메뉴')+' 참고가',source=menu['source_url'],checked_at=menu['checked_at'])
    chosen.insert(target,food)
    mapping={i+(i>=target):pid for i,pid in mapping.items()}
    c=c.model_copy(update={'count':len(chosen),'locked':mapping,'include_meal':True})
    plan,error=evaluate(chosen,c,soft=True,verify_routes=c.mode=='real' and uses_car(c))
    route_note=None
    if error and c.mode=='real' and uses_car(c) and c.allow_estimates:
        plan,error=evaluate(chosen,c,soft=True);route_note='자동차 경로 조회 실패로 추정 동선을 유지했어요.'
    if error:raise ValueError(error)
    if original.get('course_search'):plan['course_search']=original['course_search']
    plan=price_plans([plan])[0];plan=audit_plan(plan,c)
    plan['undo_locks']=undo_locks
    if any(d['state']=='unmet' for d in plan['deviations']):plan.update(best_effort=True,status='조건 차이가 있는 변경안')
    if route_note:plan['route_verification']=route_note
    elif c.mode=='real' and uses_car(c):plan['route_verification']='네이버 자동차 길찾기 재조회 반영'
    action='교체' if replace_index is not None else '추가'
    summary=f"{food['name']} {action} · 방문 {len(original['places'])}→{len(chosen)}곳 · 식사 {food['stay']}분 및 비용·이동 재계산"
    return make_draft(plan,original,owner,'meal',summary)

def vote_status(plan,viewer):
    with store.connect() as db:rows=db.execute('SELECT owner,payload FROM partner_votes WHERE plan_id=?',(plan['id'],)).fetchall()
    mine=next((json.loads(r['payload']) for r in rows if r['owner']==viewer),{})
    counts={p['id']:dict(yes=0,no=0,neutral=0,must=0) for p in plan['places']}
    answered={}  # 브라우저별로 의견을 준 장소 수(무응답은 세지 않는다)
    for row in rows:
        for pid,value in json.loads(row['payload']).items():
            if pid in counts and value in counts[pid]:counts[pid][value]+=1;answered[row['owner']]=answered.get(row['owner'],0)+1
    conflicts=[p['name'] for p in plan['places'] if counts[p['id']]['must'] and counts[p['id']]['no']]
    # answered: 몇 곳에 의견을 줬는지(본인 mine, 다른 브라우저 others). 계산에는 쓰지 않는다(vote_snapshot 은 places 만 비교).
    return dict(participants=len(rows),mine=mine,places=counts,conflicts=conflicts,place_count=len(plan['places']),
                answered=dict(mine=answered.get(viewer,0),others=[v for k,v in answered.items() if k!=viewer]),
                verification='브라우저별 의견 · 실제 신원·방문 인증 아님')

def save_votes(plan,viewer,plan_owner,choices,share_token=None):
    ids={p['id'] for p in plan['places']}
    # 개선안 28: 고른 장소만 저장한다. 고르지 않은 장소는 '아직 안 정함'(무응답)으로 남고 '상관없어요'(neutral)와 섞이지 않는다.
    # 아무것도 고르지 않은 저장은 막는다. 이미 저장된 옛 의견(모든 장소가 채워진 값)은 그대로 두고 다시 분류하지 않는다.
    if not choices:raise ValueError('한 곳 이상 의견을 골라 주세요. 고르지 않은 곳은 아직 안 정한 것으로 남아요.')
    if not set(choices)<=ids:raise ValueError('이 코스에 없는 장소의 의견이 있어요. 화면을 새로고침해 주세요.')
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
    if status['conflicts']:raise ValueError('꼭 가고 싶은 곳과 빼고 싶은 곳이 겹쳐요: '+', '.join(status['conflicts'])+'. 두 사람의 의견을 조정해 주세요.')
    c=Conditions.model_validate(plan['conditions']);locked=dict(c.locked)
    for i in ui_locked or []:
        if not 0<=i<len(plan['places']):raise ValueError('고정 장소 번호를 확인해 주세요.')
        locked[i]=plan['places'][i]['id']
    undo_locks=dict(locked)
    disliked={pid for pid,counts in status['places'].items() if counts['no']}
    if disliked.intersection(locked.values()):raise ValueError('고정한 장소에 반대 의견이 있어요. 고정을 해제하거나 두 사람의 의견을 조정해 주세요.')
    for i,p in enumerate(plan['places']):
        votes=status['places'][p['id']]
        if votes['yes']+votes['must']==2 or votes['must'] and not votes['no']:locked[i]=p['id']
    c=c.model_copy(update={'locked':locked,'excluded_place_ids':list(set(c.excluded_place_ids)|disliked)})
    result=recommend(c)
    candidates=filter_required(price_plans(result['plans']))
    if not candidates:raise ValueError('두 사람의 의견과 필수 조건을 함께 만족하는 코스를 찾지 못했어요. 조건이나 반대 의견을 직접 조정해 주세요.')
    chosen=candidates[0]
    chosen['undo_locks']=undo_locks
    if plan.get('course_search'):chosen['course_search']=plan['course_search']
    preserved=[p['name'] for i,p in enumerate(plan['places']) if i in locked]
    removed=[p['name'] for p in plan['places'] if p['id'] in disliked]
    summary=('유지: '+', '.join(preserved)+' · ' if preserved else '')+('제외: '+', '.join(removed)+' · ' if removed else '')+'두 사람의 의견과 필수 조건으로 시간·동선·비용을 다시 계산했어요.'
    return make_draft(chosen,plan,owner,'agreement',summary,vote_snapshot=status['places'])
