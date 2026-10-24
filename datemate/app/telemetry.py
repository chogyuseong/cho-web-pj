"""Aggregate external HTTP latency and failures without queries or identifiers."""
import logging
import time
import os
from threading import BoundedSemaphore
from urllib.parse import urlsplit
import httpx
from . import store

_slots=BoundedSemaphore(6)


def observed_http(call,url,**kwargs):
    provider=urlsplit(url).hostname or 'unknown'
    start=time.perf_counter();failed=True;attempted=False
    if not _slots.acquire(blocking=False):
        raise httpx.PoolTimeout('External request capacity reached')
    try:
        if not store.reserve_budget([('provider:'+provider,int(os.getenv('DATEMATE_PROVIDER_CALLS_PER_HOUR','600')))],int(time.time()//3600)):
            raise httpx.PoolTimeout('Provider hourly request budget reached')
        attempted=True
        response=call(url,**kwargs)
        failed=response.status_code>=400
        return response
    finally:
        _slots.release()
        elapsed=round((time.perf_counter()-start)*1000)
        try:
            with store.connect() as db:
                if not attempted:
                    logging.getLogger(__name__).info('provider_budget_rejected provider=%s',provider)
                    # A rejected attempt is not a billed provider call.
                    elapsed=0
                db.execute('''INSERT INTO provider_metrics VALUES(?,?,?,?,?)
                    ON CONFLICT(hour,provider) DO UPDATE SET calls=calls+excluded.calls,
                    errors=errors+excluded.errors,elapsed_ms=elapsed_ms+excluded.elapsed_ms''',
                    (int(time.time()//3600),provider,int(attempted),int(failed and attempted),elapsed))
        except Exception:logging.getLogger(__name__).warning('provider_metric_write_failed')
