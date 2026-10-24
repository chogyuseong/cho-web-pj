"""Common admission control for synchronous and queued recommendations."""
from functools import wraps
from threading import BoundedSemaphore, Lock
import os
import time
from fastapi import HTTPException
from . import store

_slots=BoundedSemaphore(2)
_owners=set()
_lock=Lock()


def bounded_recommendation(function):
    @wraps(function)
    def wrapped(data,request):
        owner=request.state.owner
        with _lock:
            if owner in _owners or not _slots.acquire(blocking=False):
                raise HTTPException(429,'검색 요청이 많아요. 잠시 후 다시 시도해 주세요.')
            _owners.add(owner)
        try:
            if store.revoked(owner):raise HTTPException(410,'삭제된 세션입니다.')
            if not store.reserve_budget([
                ('recommendations',int(os.getenv('DATEMATE_RECOMMENDATIONS_PER_MINUTE','30'))),
                ('recommendations:'+owner,int(os.getenv('DATEMATE_USER_RECOMMENDATIONS_PER_MINUTE','6')))
            ],int(time.time()//60)):
                raise HTTPException(429,'분당 검색 한도에 도달했어요. 잠시 후 다시 시도해 주세요.')
            return function(data,request)
        finally:
            with _lock:
                _owners.discard(owner)
                _slots.release()
    return wrapped
