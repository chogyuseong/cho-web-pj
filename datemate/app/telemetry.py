"""Aggregate external HTTP latency and failures without queries or identifiers."""
import logging
import time
import os
from threading import BoundedSemaphore
from urllib.parse import urlsplit
import httpx
from contextlib import contextmanager
from . import store

_slots=BoundedSemaphore(6)


def provider_limits(provider):
    """Hourly budget per provider, plus a share per client IP range.

    The share keeps one client from emptying the global budget for everyone.
    Calls outside a request (scripts, maintenance) only count against the global budget.
    """
    from .request_usage import client_range
    total=max(1,int(os.getenv('DATEMATE_PROVIDER_CALLS_PER_HOUR','600')))
    limits=[('provider:'+provider,total)]
    client=client_range()
    if client:
        share=max(1,int(os.getenv('DATEMATE_PROVIDER_CALLS_PER_IP_PER_HOUR',str(max(1,total//2)))))
        limits.append(('provider:ip:'+provider+':'+client,share))
    return limits


def _traced(provider,kind,started,attempted,failed):
    """추천 안이면 호출 종류별 기다린 시간을 남긴다(검색어·URL 경로는 남기지 않음)."""
    from .perf_trace import current as trace
    t=trace()
    if t:
        end=t.now();stage=t.stage
        t.add_call(provider,kind or 'other',stage,end-(time.perf_counter()-started)*1000,end,
                   'rejected' if not attempted else 'failed' if failed else 'ok')


@contextmanager
def operation(provider,kind=None):
    start=time.perf_counter();failed=True;attempted=False;sent=None
    from .request_usage import current
    usage=current();charged=False
    if not _slots.acquire(blocking=False):
        _traced(provider,kind,start,False,True)
        raise httpx.PoolTimeout('External request capacity reached')
    try:
        if usage:usage.reserve(provider);charged=True
        if not store.reserve_budget(provider_limits(provider),int(time.time()//3600)):
            raise httpx.PoolTimeout('Provider hourly request budget reached')
        attempted=True;sent=time.perf_counter()
        state={'failed':False}
        yield state
        failed=state['failed']
    finally:
        if charged and not attempted:usage.undo(provider)
        _slots.release()
        # 기다린 시간은 실제 요청 구간만 센다(요청 한도 확인·지표 기록의 DB 시간은 db 로 따로 셈).
        _traced(provider,kind,sent or start,attempted,failed)
        elapsed=round((time.perf_counter()-start)*1000)
        if not attempted:
            logging.getLogger(__name__).info('provider_budget_rejected provider=%s',provider)
            # A rejected attempt is not a billed provider call.
            elapsed=0
        row=(int(time.time()//3600),provider,int(attempted),int(failed and attempted),elapsed)
        # 추천·코스 변경 작업(request_usage.measure) 안에서는 작업이 끝날 때 한 번에 기록한다.
        # 호출마다 쓰면 운영 DB(PostgreSQL)에서 쓰기 잠금 왕복이 호출 수만큼 늘어난다.
        if not (usage and usage.defer_metric(row)):write_metrics([row])


def write_metrics(rows):
    """provider_metrics 에 (hour, provider, calls, errors, elapsed_ms) 행을 더한다. 같은 시간·제공자는 합쳐 한 번에."""
    if not rows:return
    merged={}
    for hour,provider,calls,errors,elapsed in rows:
        total=merged.setdefault((hour,provider),[0,0,0])
        total[0]+=calls;total[1]+=errors;total[2]+=elapsed
    try:
        with store.connect() as db:
            for (hour,provider),(calls,errors,elapsed) in merged.items():
                db.execute('''INSERT INTO provider_metrics VALUES(?,?,?,?,?)
                    ON CONFLICT(hour,provider) DO UPDATE SET calls=provider_metrics.calls+excluded.calls,
                    errors=provider_metrics.errors+excluded.errors,elapsed_ms=provider_metrics.elapsed_ms+excluded.elapsed_ms''',
                    (hour,provider,calls,errors,elapsed))
    except Exception:logging.getLogger(__name__).warning('provider_metric_write_failed')


def observed_http(call,url,**kwargs):
    from .perf_trace import call_kind
    with operation(urlsplit(url).hostname or 'unknown',call_kind(url)) as state:
        response=call(url,**kwargs)
        state['failed']=response.status_code>=400
        return response


@contextmanager
def observed_stream(client,method,url,**kwargs):
    from .perf_trace import call_kind
    with operation(urlsplit(url).hostname or 'unknown',call_kind(url)) as state:
        with client.stream(method,url,**kwargs) as response:
            state['failed']=response.status_code>=400
            yield response


def invoke_model(model, messages):
    # Count logical SDK calls (SDK retries may make additional HTTP requests).
    with operation('sdk:llm','llm'):
        result=model.invoke(messages)
    usage=getattr(result,'usage_metadata',None) or {}
    if usage:
        try:
            from .experience import event
            # No prompt, completion, address, token or user identity is stored.
            event('','','model_usage',{k:int(usage.get(k,0)) for k in ('input_tokens','output_tokens','total_tokens')})
        except Exception:logging.getLogger(__name__).warning('model_usage_metric_write_failed')
    return result
