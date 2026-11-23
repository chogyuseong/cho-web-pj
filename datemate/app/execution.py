"""Common admission control for synchronous and queued recommendations."""

from functools import wraps
from contextlib import contextmanager
from threading import BoundedSemaphore, Lock
import os
import time
from fastapi import HTTPException
from . import store
from .request_usage import client_range
from .web_security import limit

_slots = BoundedSemaphore(2)
_owners = set()
_lock = Lock()


RECOMMENDATION_LIMIT_MESSAGE = "분당 검색 한도에 도달했어요. 잠시 후 다시 시도해 주세요."


def reserve_recommendation(owner):
    """분당 추천 한도(전체·사용자·IP 범위)에서 1회를 쓴다. 남은 한도가 없으면 False.

    새 추천(recommendation_slot)과 추천을 통째로 다시 돌리는 합의 코스 미리보기(web_security.RECOMMENDING)가 함께 쓴다.
    """
    limits = [
        ("recommendations", int(os.getenv("DATEMATE_RECOMMENDATIONS_PER_MINUTE", "30"))),
        (
            "recommendations:" + owner,
            int(os.getenv("DATEMATE_USER_RECOMMENDATIONS_PER_MINUTE", "6")),
        ),
    ]
    client = client_range()
    if client:
        # A fresh cookie per request must not reset the per-user allowance.
        limits.append(
            (
                "ip:recommendations:" + client,
                limit("DATEMATE_IP_RECOMMENDATIONS_PER_MINUTE", 12),
            )
        )
    return store.reserve_budget(limits, int(time.time() // 60))


@contextmanager
def recommendation_slot(owner):
    with _lock:
        if owner in _owners or not _slots.acquire(blocking=False):
            raise HTTPException(429, "검색 요청이 많아요. 잠시 후 다시 시도해 주세요.")
        _owners.add(owner)
    try:
        if store.revoked(owner):
            raise HTTPException(410, "삭제된 세션입니다.")
        if not reserve_recommendation(owner):
            raise HTTPException(429, RECOMMENDATION_LIMIT_MESSAGE)
        yield
    finally:
        with _lock:
            _owners.discard(owner)
            _slots.release()


def bounded_recommendation(function):
    """Compatibility adapter for request-based callers."""

    @wraps(function)
    def wrapped(data, request):
        with recommendation_slot(request.state.owner):
            return function(data, request)

    return wrapped
