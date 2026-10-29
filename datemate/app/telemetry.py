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


@contextmanager
def operation(provider):
    start=time.perf_counter();failed=True;attempted=False
    from .request_usage import current
    usage=current();charged=False
    if not _slots.acquire(blocking=False):
        raise httpx.PoolTimeout('External request capacity reached')
    try:
        if usage:usage.reserve(provider);charged=True
        if not store.reserve_budget([('provider:'+provider,int(os.getenv('DATEMATE_PROVIDER_CALLS_PER_HOUR','600')))],int(time.time()//3600)):
            raise httpx.PoolTimeout('Provider hourly request budget reached')
        attempted=True
        state={'failed':False}
        yield state
        failed=state['failed']
    finally:
        if charged and not attempted:usage.undo(provider)
        _slots.release()
        elapsed=round((time.perf_counter()-start)*1000)
        try:
            with store.connect() as db:
                if not attempted:
                    logging.getLogger(__name__).info('provider_budget_rejected provider=%s',provider)
                    # A rejected attempt is not a billed provider call.
                    elapsed=0
                db.execute('''INSERT INTO provider_metrics VALUES(?,?,?,?,?)
                    ON CONFLICT(hour,provider) DO UPDATE SET calls=provider_metrics.calls+excluded.calls,
                    errors=provider_metrics.errors+excluded.errors,elapsed_ms=provider_metrics.elapsed_ms+excluded.elapsed_ms''',
                    (int(time.time()//3600),provider,int(attempted),int(failed and attempted),elapsed))
        except Exception:logging.getLogger(__name__).warning('provider_metric_write_failed')


def observed_http(call,url,**kwargs):
    with operation(urlsplit(url).hostname or 'unknown') as state:
        response=call(url,**kwargs)
        state['failed']=response.status_code>=400
        return response


@contextmanager
def observed_stream(client,method,url,**kwargs):
    with operation(urlsplit(url).hostname or 'unknown') as state:
        with client.stream(method,url,**kwargs) as response:
            state['failed']=response.status_code>=400
            yield response


def invoke_model(model, messages):
    # Count logical SDK calls (SDK retries may make additional HTTP requests).
    with operation('sdk:llm'):
        result=model.invoke(messages)
    usage=getattr(result,'usage_metadata',None) or {}
    if usage:
        try:
            from .experience import event
            # No prompt, completion, address, token or user identity is stored.
            event('','','model_usage',{k:int(usage.get(k,0)) for k in ('input_tokens','output_tokens','total_tokens')})
        except Exception:logging.getLogger(__name__).warning('model_usage_metric_write_failed')
    return result
