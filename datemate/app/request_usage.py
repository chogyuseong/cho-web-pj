"""Bound external work per recommendation; counts are not provider invoices."""

import json
import math
import os
from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from threading import Lock
import httpx

_current = ContextVar("recommendation_usage", default=None)
# Hashed client IP range of the HTTP request being served (see web_security.client_key).
# Copied into worker threads by context_map and into queued recommendation jobs.
_client = ContextVar("client_range", default=None)


def client_range():
    return _client.get()


def bind_client(key):
    """Set the current client range; returns a token for ContextVar.reset."""
    return _client.set(key)


def unbind_client(token):
    _client.reset(token)


class Usage:
    def __init__(self, limit):
        self.limit = limit
        self.calls = Counter()
        self.hits = 0
        self.blocked = False
        self.lock = Lock()

    def reserve(self, provider):
        with self.lock:
            if sum(self.calls.values()) >= self.limit:
                self.blocked = True
                raise httpx.PoolTimeout("Recommendation external request budget reached")
            self.calls[provider] += 1

    def undo(self, provider):
        with self.lock:
            self.calls[provider] -= 1
            if not self.calls[provider]:
                del self.calls[provider]

    def snapshot(self):
        with self.lock:
            calls = dict(self.calls)
            hits = self.hits
            blocked = self.blocked
        try:
            prices = json.loads(os.getenv("DATEMATE_HTTP_USD_PER_1000", "{}"))
            if not isinstance(prices, dict) or any(
                isinstance(v, bool)
                or not isinstance(v, (int, float))
                or not math.isfinite(v)
                or v < 0
                for v in prices.values()
            ):
                prices = {}
        except (ValueError, TypeError):
            prices = {}
        http = {k: v for k, v in calls.items() if not k.startswith("sdk:")}
        missing = [k for k in http if k not in prices]
        return dict(
            calls=calls,
            total_calls=sum(calls.values()),
            cache_hits=hits,
            limit=self.limit,
            budget_exhausted=blocked,
            estimated_http_usd=None
            if missing
            else sum(v * prices[k] / 1000 for k, v in http.items()),
            unpriced_providers=missing,
            scope="Observed HTTP attempts and logical SDK calls within recommendation, including propagated worker tasks. Configured HTTP unit prices only; excludes SDK retry/token charges, later photos, DB, hosting and invoices.",
        )


def current():
    return _current.get()


def cache_hit():
    usage = current()
    if usage:
        with usage.lock:
            usage.hits += 1


@contextmanager
def measure(limit=None):
    """limit: 이 작업만의 더 작은 외부 호출 상한(예: 이동 수단 변경의 자동차 구간 수)."""
    usage = Usage(
        max(1, min(500, int(os.getenv("DATEMATE_EXTERNAL_CALLS_PER_RECOMMENDATION", "60"))))
        if limit is None
        else max(1, min(500, int(limit)))
    )
    token = _current.set(usage)
    try:
        yield usage
    finally:
        _current.reset(token)


def context_map(executor, action, values):
    futures = [executor.submit(copy_context().run, action, value) for value in values]
    return [future.result() for future in futures]
