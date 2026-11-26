"""사용자가 확인한 변경만 적용하며, 공유 방문자는 원본을 수정하지 않는다."""
import json
import logging
import time
import uuid
from typing import Literal
from fastapi import APIRouter,Request,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from . import store
from . import experience as service
from .models import PlaceId

router=APIRouter(prefix='/api')

def load(pid,owner):
    # 만든 브라우저(owner)의 코스만 연다(app/main.py plan_row 와 같은 기준). 상대방 의견은 공유 토큰 경로(app/sharing.py)로만 받는다.
    # 남의 코스와 없는 코스를 구별하지 않고 둘 다 404 로 답한다.
    row=store.get_plan(pid)
    if not row or not owner or row['owner']!=owner:raise HTTPException(404,'일정을 찾을 수 없습니다.')
    from .condition_audit import audit_plan
    return row,audit_plan(json.loads(row['payload']))

def run(action):
    try:return action()
    except PermissionError as e:raise HTTPException(403,str(e))
    except service.VotesChanged as e:raise HTTPException(409,dict(code='votes_changed',message=str(e),changed=e.changed))
    except ValidationError:
        # pydantic 검증 오류도 ValueError 다. 그 글은 내부 필드 이름·오류 주소가 든 원문이라 화면에 내지 않는다(2026-11-24 점검 A4:
        # 'count Input should be greater than or equal to 2 … errors.pydantic.dev'). 원인은 서버 기록에 남긴다.
        logging.getLogger(__name__).exception('plan_change_validation_failed')
        raise HTTPException(409,'이 코스의 조건으로는 변경을 계산하지 못했어요. 코스를 다시 열어 다시 시도해 주세요.')
    except ValueError as e:raise HTTPException(409,str(e))

class MealChange(BaseModel):
    restaurant_id:str=Field(min_length=1,max_length=150)
    after_index:int=Field(default=0,ge=-1,le=4)
    replace_index:int|None=Field(default=None,ge=0,le=4)
    locked:list[int]=Field(default_factory=list,max_length=5)
    menu_index:int=Field(default=0,ge=0,le=11)

class DraftApply(BaseModel):
    token:str=Field(pattern=r'^[a-f0-9]{32}$')

class Locks(BaseModel):
    locked:list[int]=Field(default_factory=list,max_length=5)

@router.post('/plans/{pid}/locks')
def update_locks(pid:str,data:Locks,request:Request):
    _,plan=load(pid,request.state.owner)
    if any(i<0 or i>=len(plan['places']) for i in data.locked):raise HTTPException(422,'고정 장소 번호가 잘못됐어요.')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        current=db.execute('SELECT payload FROM plans WHERE id=? AND owner=?',(pid,request.state.owner)).fetchone()
        plan=json.loads(current['payload'])
        updated={str(i):plan['places'][i]['id'] for i in set(data.locked)}
        if plan['conditions'].get('locked',{})!=updated:plan['lock_version']=plan.get('lock_version',0)+1
        plan['conditions']['locked']=updated
        db.execute('UPDATE plans SET payload=? WHERE id=?',(json.dumps(plan,ensure_ascii=False),pid))
    from .condition_audit import audit_plan
    plan=audit_plan(plan);plan['verification']=service.verification_summary(plan)
    return plan

@router.post('/plans/{pid}/meal-preview')
def meal_preview(pid:str,data:MealChange,request:Request):
    _,plan=load(pid,request.state.owner)
    # 21일이 지나 좌표를 지운 네이버 검색 장소가 있으면 경로를 다시 계산할 수 없다(app/naver_terms.ensure_changeable).
    from .naver_terms import ensure_changeable
    ensure_changeable(plan)
    return run(lambda:service.meal_draft(plan,request.state.owner,data.restaurant_id,data.after_index,data.replace_index,data.locked,data.menu_index))

class FestivalAdd(BaseModel):
    model_config=ConfigDict(extra='forbid')
    # 축제 id 만 받는다. 제목·좌표·기간·운영 시간은 서버가 축제 목록·상세에서 정한다(app/festival_add.py).
    festival_id:str=Field(min_length=1,max_length=240)

@router.post('/plans/{pid}/festival-preview')
def festival_preview(pid:str,data:FestivalAdd,request:Request):
    """결과 화면 축제 카드의 「+ 내 코스에 추가」 미리보기(app/festival_add.py). 확정은 draft-apply."""
    _,plan=load(pid,request.state.owner)
    from .naver_terms import ensure_changeable
    ensure_changeable(plan)
    from .festival_add import festival_draft
    return run(lambda:festival_draft(plan,request.state.owner,data.festival_id))

@router.post('/plans/{pid}/draft-apply')
def draft_apply(pid:str,data:DraftApply,request:Request):
    load(pid,request.state.owner)
    return run(lambda:service.apply_draft(pid,data.token,request.state.owner))

class Feedback(BaseModel):
    kind:Literal['selection','replace_reason','visit']
    place_id:str|None=Field(default=None,max_length=150)
    reason:Literal['budget','distance','taste','visited']|None=None
    visited:Literal['yes','no','planned']|None=None
    obstacle:Literal['none','closed','price','distance','waiting','taste','other']|None=None
    reuse:Literal['yes','no','unsure']|None=None

@router.post('/plans/{pid}/feedback')
def feedback(pid:str,data:Feedback,request:Request):
    _,plan=load(pid,request.state.owner)
    if data.kind=='replace_reason' and (data.place_id not in {p['id'] for p in plan['places']} or not data.reason):raise HTTPException(422,'장소와 변경 이유를 확인해 주세요.')
    if data.kind=='visit' and (not data.visited or not data.obstacle or not data.reuse):raise HTTPException(422,'세 가지 방문 피드백을 모두 선택해 주세요.')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM experience_events WHERE owner=? AND plan_id=? AND kind=?',(request.state.owner,pid,data.kind))
        db.execute('INSERT INTO experience_events VALUES(?,?,?,?,?,?)',(uuid.uuid4().hex,request.state.owner,pid,data.kind,json.dumps(data.model_dump(exclude_none=True)),time.time()))
    return dict(saved=True,verification='자기 신고 · 실제 방문 인증 아님')

@router.get('/plans/{pid}/feedback')
def my_plan_feedback(pid:str,request:Request):
    load(pid,request.state.owner)
    with store.connect() as db:row=db.execute("SELECT payload FROM experience_events WHERE owner=? AND plan_id=? AND kind='visit' ORDER BY created DESC LIMIT 1",(request.state.owner,pid)).fetchone()
    return dict(visit=json.loads(row[0]) if row else None)

@router.delete('/plans/{pid}/feedback')
def delete_my_feedback(pid:str,request:Request):
    load(pid,request.state.owner)
    with store.connect() as db:db.execute('DELETE FROM experience_events WHERE owner=? AND plan_id=?',(request.state.owner,pid))
    return dict(deleted=True)

class PlaceReport(BaseModel):
    place_id:str=Field(max_length=150)
    reason:Literal['closed','moved','hours','price','other']
    note:str=Field(default='',max_length=500)

@router.post('/plans/{pid}/place-report')
def place_report(pid:str,data:PlaceReport,request:Request):
    _,plan=load(pid,request.state.owner)
    if data.place_id not in {p['id'] for p in plan['places']}:raise HTTPException(422,'코스에 있는 장소만 제보할 수 있어요.')
    with store.connect() as db:
        db.execute('INSERT INTO place_reports(id,owner,place_id,reason,note,created) VALUES(?,?,?,?,?,?) ON CONFLICT(owner,place_id,reason) DO UPDATE SET note=excluded.note,created=excluded.created,resolved=0,resolution=\'\'',(uuid.uuid4().hex,request.state.owner,data.place_id,data.reason,data.note,time.time()))
    return dict(saved=True,message='제보를 접수했어요. 사실 확정 없이 확인 대기 상태로 표시하고 추천 우선순위를 낮춥니다.')

class Votes(BaseModel):
    choices:dict[PlaceId,Literal['yes','no','neutral','must']]=Field(max_length=5)

@router.get('/plans/{pid}/agreement')
def agreement(pid:str,request:Request):
    row,plan=load(pid,request.state.owner)
    return dict(**service.vote_status(plan,request.state.owner),can_replan=row['owner']==request.state.owner)

@router.post('/plans/{pid}/agreement')
def vote(pid:str,data:Votes,request:Request):
    row,plan=load(pid,request.state.owner)
    return run(lambda:service.save_votes(plan,request.state.owner,row['owner'],data.choices))

@router.delete('/plans/{pid}/agreement/partner')
def reset_partner(pid:str,request:Request):
    # 만든 브라우저만(load 가 소유자만 연다 — 상대방 브라우저는 404). 점검 S4: 엉뚱한 브라우저가 차지한 상대 자리를 비운다.
    row,plan=load(pid,request.state.owner)
    return dict(**service.clear_partner_votes(plan,row['owner']),can_replan=True)

@router.post('/plans/{pid}/agreement-preview')
def replan_agreement(pid:str,request:Request,data:dict|None=None):
    _,plan=load(pid,request.state.owner)
    from .naver_terms import ensure_changeable
    ensure_changeable(plan)
    locked=(data or {}).get('locked',[])
    if not isinstance(locked,list) or len(locked)>5 or any(type(i) is not int for i in locked):raise HTTPException(422,'고정 장소 번호를 확인해 주세요.')
    return run(lambda:service.agreement_draft(plan,request.state.owner,locked))

@router.get('/my/feedback-summary')
def feedback_summary(request:Request):
    with store.connect() as db:rows=db.execute('SELECT kind,payload,owner,plan_id,created FROM experience_events WHERE owner=?',(request.state.owner,)).fetchall()
    from .planning_outcomes import study_summary
    study=study_summary([dict(r) for r in rows])
    visits=[json.loads(r['payload']) for r in rows if r['kind']=='visit']
    durations=[json.loads(r['payload'])['elapsed_ms'] for r in rows if r['kind']=='recommendation' and 'elapsed_ms' in json.loads(r['payload'])]
    return dict(recommendations=sum(r['kind']=='recommendation' for r in rows),selections=sum(r['kind']=='selection' for r in rows),self_reported_visits=sum(r.get('visited')=='yes' for r in visits),reuse_yes=sum(r.get('reuse')=='yes' for r in visits),average_elapsed_ms=round(sum(durations)/len(durations)) if durations else None,planning_study=study,api_cost_status='not_measured',verification='현재 브라우저 기준 · 자기 신고이며 실제 이용 인증이 아닙니다.')


@router.get('/plans/{pid}/delay-check')
def delay_check(pid:str,request:Request,index:int=0,minutes:int=10,stays:str=Query('',max_length=200)):
    """읽기 전용: 남은 첫 장소(index)에 minutes 분 늦게 도착하면 남은 일정이 어디서 처음 어긋나는지(app/delay_check.py).
    stays='장소 번호:분,…' 이면 그 장소들의 체류 시간을 바꿔 본다(2026-11-26 시안 '체류 -15분/+15분', 같은 규칙으로 다시 계산).
    만든 브라우저만 볼 수 있다(공유 범위는 그대로). 아무것도 저장하지 않는다."""
    _,plan=load(pid,request.state.owner)
    from .delay_check import delay_check as check,parse_stays
    from .delay_recovery import recovery_for
    def action():
        changed=parse_stays(stays,len(plan['places']))
        result=check(plan,index,minutes,changed)
        # 체류를 바꿔 본 시간표에서는 대신 갈 곳 안(지각 복구)을 만들지 않는다 — 복구는 저장된 체류 그대로 다시 계산해서 화면과 맞지 않는다.
        if changed:
            result['recovery']=None
            return result
        # 늦어서 맞출 수 없게 된 장소가 있으면 대신 갈 곳·빼고 진행 안(app/delay_recovery.py). 계산만 하고 저장하지 않는다.
        # 복구 안 계산이 예상 못 한 코스 모양에서 실패해도 지각 확인 자체는 그대로 답한다(복구 안만 빠진다).
        try:result['recovery']=recovery_for(plan,result)
        except Exception:
            logging.getLogger(__name__).exception('delay_recovery_options_failed')
            result['recovery']=None
        return result
    return run(action)

class DelayRecovery(BaseModel):
    model_config=ConfigDict(extra='forbid')
    index:int=Field(ge=0,le=4)
    minutes:int=Field(ge=0,le=180)
    target:int=Field(ge=0,le=4)
    # 없으면(None) 그 장소를 빼고 진행한다.
    replacement_id:str|None=Field(default=None,min_length=1,max_length=150)

@router.post('/plans/{pid}/delay-recovery')
def delay_recovery(pid:str,data:DelayRecovery,request:Request):
    """지각 확인에서 맞출 수 없게 된 장소(target)를 대신 갈 곳으로 바꾸거나 빼고, 지연을 반영해 새 코스로 저장한다(되돌리기는 /undo).
    화면이 본 결과와 지금 계산이 다르거나 축제 시각을 못 맞추면 409."""
    _,plan=load(pid,request.state.owner)
    from .naver_terms import ensure_changeable
    ensure_changeable(plan)
    from .delay_recovery import apply
    return run(lambda:apply(plan,data.index,data.minutes,data.target,data.replacement_id,request.state.owner))
