"""Bounded, owner-scoped background recommendation jobs for a single server."""
import time
import secrets
import logging
import hashlib
import json
from . import store
from contextvars import ContextVar
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from types import SimpleNamespace
from fastapi import APIRouter, Request, HTTPException
from .models import Conditions

router=APIRouter()
_jobs={}
_lock=Lock()
_pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='recommendation')
def _persist(key):
    job=dict(_jobs[key]);job.pop('started',None);job.pop('finished',None)
    if store.revoked(job['owner']):return
    store.cache('plan-job:'+key,job,3600)

_current=ContextVar('recommendation_progress',default=None)

def check_current():
    key=_current.get()
    if key:
        job=_jobs.get(key)
        if not job or job['status']!='running' or store.revoked(job['owner']):
            raise ValueError('검색이 취소됐어요.')
        if time.monotonic()-job['started']>300:
            raise ValueError('검색 제한 시간을 초과했어요.')

def forget_owner(owner):
    with _lock:
        for key in list(_jobs):
            if _jobs[key]['owner']==owner:del _jobs[key]

def report(stage,message,preview=None):
    check_current()
    key=_current.get()
    if key:
        with _lock:
            if key in _jobs:
                logging.getLogger(__name__).info('recommendation_stage id=%s stage=%s elapsed_ms=%.1f',key,stage,(time.monotonic()-_jobs[key]['started'])*1000)
                _jobs[key].update(stage=stage,message=message)
                if preview is not None:_jobs[key]['preview']=preview
                _persist(key)

def _run(key,data,owner):
    token=_current.set(key)
    try:
        check_current()
        from .main import create
        result=create(data,SimpleNamespace(state=SimpleNamespace(owner=owner)))
        with _lock:
            if key in _jobs and _jobs[key]['status']=='running':
                _jobs[key].update(status='complete',result=result,stage='완료',message='코스를 준비했어요')
    except Exception:
        logging.getLogger(__name__).exception('recommendation_job_failed id=%s',key)
        with _lock:
            if key in _jobs and _jobs[key]['status']=='running':
                _jobs[key].update(status='failed',message=f"{_jobs[key].get('stage','검색')} 단계에서 처리 오류가 발생했어요. 다시 시도해 주세요. 오류 번호: {key[:8]}",error_id=key[:8])
    finally:
        _current.reset(token)
        with _lock:
            if key in _jobs:
                _jobs[key]['finished']=time.monotonic()
                _persist(key)

@router.post('/api/plan-jobs',status_code=202)
def start(data:Conditions,request:Request):
    owner=request.state.owner
    fingerprint=hashlib.sha256(json.dumps(data.model_dump(mode='json'),sort_keys=True).encode()).hexdigest()
    with _lock:
        now=time.monotonic()
        if store.revoked(owner):raise HTTPException(410,'삭제된 세션입니다.')
        for key in list(_jobs):
            if _jobs[key].get('finished',now)>0 and now-_jobs[key].get('finished',now)>600:del _jobs[key]
        for key,j in _jobs.items():
            if j['owner']==owner and j['status']=='running':
                if j.get('fingerprint')==fingerprint:return {'id':key}
                raise HTTPException(429,'이미 코스를 찾고 있어요. 잠시 기다려 주세요.')
        if len(_jobs)>=100 or sum(j['status']=='running' for j in _jobs.values())>=6:raise HTTPException(429,'검색 요청이 많아요. 잠시 후 다시 시도해 주세요.')
        key=secrets.token_urlsafe(24)
        _jobs[key]=dict(fingerprint=fingerprint,started=now,owner=owner,status='running',stage='접수 완료',message='조건을 확인하고 있어요')
        _persist(key)
    _pool.submit(_run,key,data,owner)
    return {'id':key}

@router.get('/api/plan-jobs/{key}')
def poll(key:str,request:Request):
    with _lock:
        job=_jobs.get(key) or store.cached('plan-job:'+key)
        if job and key not in _jobs and job['status']=='running':
            job=dict(job,status='failed',message='서버 재시작으로 검색이 중단됐어요. 같은 조건으로 다시 검색해 주세요.')
        if not job or job['owner']!=request.state.owner:raise HTTPException(404,'검색 작업을 찾을 수 없습니다. 서버가 재시작되었다면 다시 검색해 주세요.')
        return {k:v for k,v in job.items() if k not in ('owner','finished','started','fingerprint')}

@router.delete('/api/plan-jobs/{key}')
def cancel(key:str,request:Request):
    with _lock:
        job=_jobs.get(key)
        if not job or job['owner']!=request.state.owner:raise HTTPException(404,'검색 작업을 찾을 수 없습니다.')
        if job['status']=='running':
            job.update(status='cancelled',message='검색을 취소했어요.',finished=time.monotonic())
            job.pop('preview',None)
            _persist(key)
    return {'cancelled':True}
