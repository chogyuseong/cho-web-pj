"""사용자가 확인한 변경만 적용하며, 공유 방문자는 원본을 수정하지 않는다."""
import json
import time
import uuid
from typing import Literal
from fastapi import APIRouter,Request,HTTPException
from pydantic import BaseModel,Field
from . import store
from . import experience as service

router=APIRouter(prefix='/api')

def load(pid,owner=None):
    row=store.get_plan(pid)
    if not row:raise HTTPException(404,'일정을 찾을 수 없습니다.')
    if owner is not None and row['owner']!=owner:raise HTTPException(403,'이 브라우저에서 만든 일정만 변경할 수 있어요.')
    from .condition_audit import audit_plan
    return row,audit_plan(json.loads(row['payload']))

def run(action):
    try:return action()
    except PermissionError as e:raise HTTPException(403,str(e))
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
    return run(lambda:service.meal_draft(plan,request.state.owner,data.restaurant_id,data.after_index,data.replace_index,data.locked,data.menu_index))

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
    _,plan=load(pid)
    if data.kind=='replace_reason' and (data.place_id not in {p['id'] for p in plan['places']} or not data.reason):raise HTTPException(422,'장소와 변경 이유를 확인해 주세요.')
    if data.kind=='visit' and (not data.visited or not data.obstacle or not data.reuse):raise HTTPException(422,'세 가지 방문 피드백을 모두 선택해 주세요.')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM experience_events WHERE owner=? AND plan_id=? AND kind=?',(request.state.owner,pid,data.kind))
        db.execute('INSERT INTO experience_events VALUES(?,?,?,?,?,?)',(uuid.uuid4().hex,request.state.owner,pid,data.kind,json.dumps(data.model_dump(exclude_none=True)),time.time()))
    return dict(saved=True,verification='자기 신고 · 실제 방문 인증 아님')

@router.get('/plans/{pid}/feedback')
def my_plan_feedback(pid:str,request:Request):
    load(pid)
    with store.connect() as db:row=db.execute("SELECT payload FROM experience_events WHERE owner=? AND plan_id=? AND kind='visit' ORDER BY created DESC LIMIT 1",(request.state.owner,pid)).fetchone()
    return dict(visit=json.loads(row[0]) if row else None)

@router.delete('/plans/{pid}/feedback')
def delete_my_feedback(pid:str,request:Request):
    load(pid)
    with store.connect() as db:db.execute('DELETE FROM experience_events WHERE owner=? AND plan_id=?',(request.state.owner,pid))
    return dict(deleted=True)

class PlaceReport(BaseModel):
    place_id:str=Field(max_length=150)
    reason:Literal['closed','moved','hours','price','other']
    note:str=Field(default='',max_length=500)

@router.post('/plans/{pid}/place-report')
def place_report(pid:str,data:PlaceReport,request:Request):
    _,plan=load(pid)
    if data.place_id not in {p['id'] for p in plan['places']}:raise HTTPException(422,'코스에 있는 장소만 제보할 수 있어요.')
    with store.connect() as db:
        db.execute('INSERT INTO place_reports(id,owner,place_id,reason,note,created) VALUES(?,?,?,?,?,?) ON CONFLICT(owner,place_id,reason) DO UPDATE SET note=excluded.note,created=excluded.created,resolved=0,resolution=\'\'',(uuid.uuid4().hex,request.state.owner,data.place_id,data.reason,data.note,time.time()))
    return dict(saved=True,message='제보를 접수했어요. 사실 확정 없이 확인 대기 상태로 표시하고 추천 우선순위를 낮춥니다.')

class Votes(BaseModel):
    choices:dict[str,Literal['yes','no','neutral','must']]=Field(max_length=5)

@router.get('/plans/{pid}/agreement')
def agreement(pid:str,request:Request):
    row,plan=load(pid)
    return dict(**service.vote_status(plan,request.state.owner),can_replan=row['owner']==request.state.owner)

@router.post('/plans/{pid}/agreement')
def vote(pid:str,data:Votes,request:Request):
    row,plan=load(pid)
    return run(lambda:service.save_votes(plan,request.state.owner,row['owner'],data.choices))

@router.post('/plans/{pid}/agreement-preview')
def replan_agreement(pid:str,request:Request,data:dict|None=None):
    _,plan=load(pid,request.state.owner)
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
