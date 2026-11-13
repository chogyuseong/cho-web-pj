"""Bounded recommendation workers with shared progress and cancellation.

The container must receive CPU outside requests. Heartbeats allow a different
instance to poll/cancel and detect an interrupted worker without sticky sessions.
Interrupted jobs are reported as failed, never silently rerun or billed twice.
"""

import asyncio
import time
import secrets
import logging
import hashlib
import json
from . import store
from contextvars import ContextVar, copy_context
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from fastapi import APIRouter, Request, HTTPException
from fastapi.concurrency import run_in_threadpool
from .models import Conditions

router = APIRouter()
_jobs = {}
_lock = Lock()
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="recommendation")
LEASE_SECONDS = 45


def _read(db, key):
    row = db.execute(
        "SELECT payload FROM cache WHERE key=? AND expires>?", ("plan-job:" + key, time.time())
    ).fetchone()
    return json.loads(row["payload"]) if row else None


def _write(db, key, job):
    """작업 상태를 저장하고 저장한 내용의 크기(문자 수)를 돌려준다."""
    payload = json.dumps(job, ensure_ascii=False)
    db.execute(
        "INSERT INTO cache VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,expires=excluded.expires",
        ("plan-job:" + key, payload, time.time() + 3600),
    )
    return len(payload)


def _alive(job):
    return (
        job.get("heartbeat", 0) > time.time() - LEASE_SECONDS
        and job.get("deadline", 0) > time.time()
    )


def _persist(key):
    job = dict(_jobs[key])
    job.pop("started", None)
    job.pop("finished", None)
    job["heartbeat"] = time.time()
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM revoked_sessions WHERE token=?", (job["owner"],)).fetchone():
            return
        previous = _read(db, key)
        # A cancellation issued on another instance wins over late progress/results.
        if previous and previous["status"] in ("cancelled", "failed", "complete"):
            _jobs[key].update(previous)
            return
        return _write(db, key, job)


_current = ContextVar("recommendation_progress", default=None)


def check_current():
    key = _current.get()
    if key:
        job = _jobs.get(key)
        if not job or job["status"] != "running" or store.revoked(job["owner"]):
            raise ValueError("검색이 취소됐어요.")
        persisted = store.cached("plan-job:" + key)
        if persisted and persisted["status"] != "running":
            raise ValueError("검색이 취소됐거나 중단됐어요.")
        if time.monotonic() - job["started"] > 300:
            raise ValueError("검색 제한 시간을 초과했어요.")


def forget_owner(owner):
    with _lock:
        for key in list(_jobs):
            if _jobs[key]["owner"] == owner:
                del _jobs[key]


def report(stage, message, preview=None):
    from .perf_trace import stage as traced_stage

    traced_stage(stage)
    check_current()
    key = _current.get()
    if key:
        with _lock:
            if key in _jobs:
                logging.getLogger(__name__).info(
                    "recommendation_stage id=%s stage=%s elapsed_ms=%.1f",
                    key,
                    stage,
                    (time.monotonic() - _jobs[key]["started"]) * 1000,
                )
                _jobs[key].update(stage=stage, message=message)
                if preview is not None:
                    _jobs[key]["preview"] = preview
                _persist(key)


def _run(key, data, owner):
    token = _current.set(key)
    try:
        check_current()
        from .recommendation_service import generate

        result = generate(data, owner)
        with _lock:
            if key in _jobs and _jobs[key]["status"] == "running":
                _jobs[key].update(
                    status="complete", result=result, stage="완료", message="코스를 준비했어요"
                )
    except Exception:
        logging.getLogger(__name__).exception("recommendation_job_failed id=%s", key)
        with _lock:
            if key in _jobs and _jobs[key]["status"] == "running":
                _jobs[key].update(
                    status="failed",
                    message=f"{_jobs[key].get('stage', '검색')} 단계에서 처리 오류가 발생했어요. 다시 시도해 주세요. 오류 번호: {key[:8]}",
                    error_id=key[:8],
                )
    finally:
        _current.reset(token)
        saved = None
        with _lock:
            if key in _jobs:
                _jobs[key]["finished"] = time.monotonic()
                saving = time.perf_counter()
                size = _persist(key)
                saved = (_jobs[key]["status"], (time.perf_counter() - saving) * 1000, size)
        # 기록은 잠금 밖에서, 실패해도 작업 상태 저장과 무관하게 넘어간다. 크기는 저장할 때 만든 내용을 다시 쓴다.
        if saved:
            try:
                logging.getLogger(__name__).info(
                    "recommendation_job_saved id=%s status=%s persist_ms=%.1f stored_chars=%s",
                    key,
                    *saved,
                )
            except Exception:
                pass


@router.post("/api/plan-jobs", status_code=202)
def start(data: Conditions, request: Request):
    owner = request.state.owner
    from .service_time import past_visit_message

    # 새 추천만 지난 날짜·시각을 막는다(한국 시각). 만든 코스를 바꾸는 경로는 이 검사를 거치지 않는다.
    past = past_visit_message(data)
    if past:
        raise HTTPException(422, past)
    # 구간별 수단 예외는 만든 코스를 바꿀 때(/api/plans/{id}/transport)만 받는다.
    data = data.model_copy(update={"leg_modes": []})
    fingerprint = hashlib.sha256(
        json.dumps(data.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()
    with _lock:
        now = time.monotonic()
        if store.revoked(owner):
            raise HTTPException(410, "삭제된 세션입니다.")
        for key in list(_jobs):
            if _jobs[key].get("finished", now) > 0 and now - _jobs[key].get("finished", now) > 600:
                del _jobs[key]
        for key, j in _jobs.items():
            if j["owner"] == owner and j["status"] == "running":
                persisted = store.cached("plan-job:" + key)
                if persisted and persisted["status"] != "running":
                    j.update(persisted, finished=now)
                    continue
                if j.get("fingerprint") == fingerprint:
                    return {"id": key}
                raise HTTPException(429, "이미 코스를 찾고 있어요. 잠시 기다려 주세요.")
        if len(_jobs) >= 100 or sum(j["status"] == "running" for j in _jobs.values()) >= 6:
            raise HTTPException(429, "검색 요청이 많아요. 잠시 후 다시 시도해 주세요.")
        key = secrets.token_urlsafe(24)
        job = dict(
            fingerprint=fingerprint,
            owner=owner,
            status="running",
            stage="접수 완료",
            message="조건을 확인하고 있어요",
            heartbeat=time.time(),
            deadline=time.time() + 300,
        )
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM revoked_sessions WHERE token=?", (owner,)).fetchone():
                raise HTTPException(410, "삭제된 세션입니다.")
            active = db.execute(
                "SELECT c.key,c.payload FROM cache c JOIN cache_owners o ON o.key=c.key WHERE o.owner=? AND c.key LIKE 'plan-job:%' AND c.expires>?",
                (owner, time.time()),
            ).fetchall()
            for row in active:
                previous = json.loads(row["payload"])
                if previous["status"] == "running" and _alive(previous):
                    if previous.get("fingerprint") == fingerprint:
                        return {"id": previous["id"]}
                    raise HTTPException(429, "이미 코스를 찾고 있어요. 잠시 기다려 주세요.")
                if previous["status"] == "running":
                    # Fence the expired worker before accepting a retry. If it
                    # resumes later, it must not renew or publish its old job.
                    previous.update(
                        status="failed", message="이전 검색이 중단되어 새 검색을 시작했어요."
                    )
                    _write(db, row["key"].removeprefix("plan-job:"), previous)
            job["id"] = key
            _write(db, key, job)
        _jobs[key] = dict(job, started=now)
    # Carry the request context (the caller's IP range) so limits and provider
    # budgets in the worker are charged to the person who started the search.
    _pool.submit(copy_context().run, _run, key, data, owner)
    return {"id": key}


# 긴 폴링: 화면이 마지막으로 본 단계를 보내면, 이 인스턴스에서 도는 작업의 단계·상태가 바뀔 때까지 최대 이만큼 기다렸다 답한다.
# 기다리는 동안 DB를 읽지 않고 스레드도 잡지 않는다(메모리의 작업 상태만 0.1초마다 확인).
MAX_WAIT_SECONDS = 8.0
WAIT_STEP_SECONDS = 0.1


def _changed(key, owner, stage):
    job = _jobs.get(key)
    # 다른 인스턴스의 작업이거나 주인이 아니면 기다리지 않는다(아래 일반 조회가 404·저장 상태를 답함).
    return (
        not job or job["owner"] != owner or job["status"] != "running" or job.get("stage") != stage
    )


async def _wait_for_change(key, owner, stage, seconds, request):
    deadline = time.monotonic() + min(max(seconds, 0.0), MAX_WAIT_SECONDS)
    while time.monotonic() < deadline and not _changed(key, owner, stage):
        if await request.is_disconnected():
            return
        await asyncio.sleep(WAIT_STEP_SECONDS)


@router.get("/api/plan-jobs/{key}")
async def poll_route(key: str, request: Request, wait: float = 0, stage: str | None = None):
    if wait > 0 and stage is not None:
        await _wait_for_change(key, request.state.owner, stage[:40], wait, request)
    return await run_in_threadpool(poll, key, request)


def poll(key: str, request: Request):
    with _lock:
        job = store.cached("plan-job:" + key) or _jobs.get(key)
        if not job or job["owner"] != request.state.owner:
            raise HTTPException(
                404, "검색 작업을 찾을 수 없습니다. 서버가 재시작되었다면 다시 검색해 주세요."
            )
        if key not in _jobs and job["status"] == "running" and not _alive(job):
            with store.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                latest = _read(db, key)
                if latest and latest["status"] == "running" and not _alive(latest):
                    latest.update(
                        status="failed",
                        message="서버 재시작 또는 검색 제한 시간으로 중단됐어요. 같은 조건으로 다시 검색해 주세요.",
                    )
                    _write(db, key, latest)
                job = latest or job
        return {
            k: v
            for k, v in job.items()
            if k not in ("owner", "finished", "started", "fingerprint", "heartbeat", "deadline")
        }


@router.delete("/api/plan-jobs/{key}")
def cancel(key: str, request: Request):
    with _lock:
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            job = _read(db, key) or _jobs.get(key)
            if not job or job["owner"] != request.state.owner:
                raise HTTPException(404, "검색 작업을 찾을 수 없습니다.")
            if job["status"] == "running":
                job = dict(job, status="cancelled", message="검색을 취소했어요.")
                job.pop("preview", None)
                _write(db, key, job)
        if key in _jobs:
            _jobs[key].update(job, finished=time.monotonic())
    return {"cancelled": True}


def heartbeat():
    with _lock:
        for key, job in list(_jobs.items()):
            if job["status"] == "running":
                if time.monotonic() - job["started"] > 300:
                    job.update(
                        status="failed",
                        message="검색 제한 시간을 초과했어요. 다시 검색해 주세요.",
                        finished=time.monotonic(),
                    )
                _persist(key)


async def heartbeat_loop():
    while True:
        try:
            await asyncio.to_thread(heartbeat)
        except Exception:
            logging.getLogger(__name__).exception("job_heartbeat_failed")
        await asyncio.sleep(5)
