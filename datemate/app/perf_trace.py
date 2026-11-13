"""추천 1회의 소요 시간 기록: 단계, 주요 구간, 외부 호출, 캐시 적중, DB 사용.

운영에도 남기는 가벼운 장치다. 검색어·주소·장소 이름·URL 경로·키·세션은 남기지 않는다.
외부 호출은 호스트 이름과 고정된 호출 종류(블로그 검색, 지역 검색 등)로만 묶는다.
추천 밖(스크립트, 다른 API)에서는 기록하지 않고 아무 일도 하지 않는다.
"""

import time
from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock
from urllib.parse import urlsplit

_current = ContextVar("recommendation_trace", default=None)
# 한 추천에서 외부 호출 구간을 이 수까지만 보관한다(상한 60건의 여유분).
MAX_INTERVALS = 400

# 경로에 사용자·글 식별자가 없는 고정 API 경로만 이름으로 남긴다.
KNOWN_PATHS = {
    "/search/v1/blog": "blog_search",
    "/search/v1/local": "local_search",
    "/search/v1/image": "image_search",
    "/map-direction/v1/driving": "driving_route",
    "/map-reversegeocode/v2/gc": "reverse_geocode",
    "/map-geocode/v2/geocode": "geocode",
}
BLOG_HOSTS = ("blog.naver.com", "m.blog.naver.com")


def call_kind(url):
    parts = urlsplit(url)
    if parts.hostname in BLOG_HOSTS:
        return "blog_body"
    return KNOWN_PATHS.get(parts.path, "other")


class Trace:
    def __init__(self):
        self.started = time.perf_counter()
        self.lock = Lock()
        self.stage = "준비"
        self.stages = [("준비", 0.0)]
        self.spans = {}
        self.calls = {}
        self.intervals = []
        self.cache = Counter()
        self.db_count = 0
        self.db_ms = 0.0
        self.db_stages = {}
        self.counts = Counter()

    def now(self):
        return (time.perf_counter() - self.started) * 1000

    def enter_stage(self, name):
        with self.lock:
            if name != self.stage:
                self.stage = name
                self.stages.append((name, self.now()))

    def add_span(self, name, ms):
        with self.lock:
            row = self.spans.setdefault(name, [0, 0.0])
            row[0] += 1
            row[1] += ms

    def add_call(self, provider, kind, stage, start, end, outcome, connection=None):
        with self.lock:
            row = self.calls.setdefault(
                (stage, provider, kind),
                dict(count=0, failed=0, rejected=0, ms=0.0, max_ms=0.0, observed=0, new_connections=0, connect_ms=0.0),
            )
            if outcome == "rejected":
                row["rejected"] += 1
                return
            row["count"] += 1
            row["failed"] += outcome == "failed"
            row["ms"] += end - start
            row["max_ms"] = max(row["max_ms"], end - start)
            if connection is not None:
                # httpx.Client 로 보낸 호출만 안다(httpx.get 처럼 호출마다 새 클라이언트를 만드는 호출은 세지 않음).
                row["observed"] += 1
                row["new_connections"] += connection[0]
                row["connect_ms"] += connection[1]
            if len(self.intervals) < MAX_INTERVALS:
                self.intervals.append((start, end, stage))

    def add_cache_hit(self, kind):
        with self.lock:
            self.cache[kind or "other"] += 1

    def add_count(self, name, n):
        with self.lock:
            self.counts[name] += n

    def add_db(self, ms):
        with self.lock:
            self.db_count += 1
            self.db_ms += ms
            row = self.db_stages.setdefault(self.stage, [0, 0.0])
            row[0] += 1
            row[1] += ms

    def summary(self):
        with self.lock:
            total = self.now()
            stages = list(self.stages)
            intervals = sorted(self.intervals)
            calls = {k: dict(v) for k, v in self.calls.items()}
            spans = {k: list(v) for k, v in self.spans.items()}
            cache = dict(self.cache)
            counts = dict(sorted(self.counts.items()))
            db = dict(
                count=self.db_count,
                ms=round(self.db_ms),
                by_stage={k: dict(count=v[0], ms=round(v[1])) for k, v in self.db_stages.items()},
            )
        rows = []
        for i, (name, start) in enumerate(stages):
            end = stages[i + 1][1] if i + 1 < len(stages) else total
            rows.append(dict(name=name, start_ms=round(start), ms=round(end - start)))
        wall, peak = _overlap([(s, e) for s, e, _ in intervals])
        # 단계별로도 같은 값(가격 확인의 동시 3건이 실제로 겹치는지 등). 단계 이름은 화면 진행 문구와 같은 고정 문자열.
        by_stage = {}
        for s, e, name in intervals:
            by_stage.setdefault(name, []).append((s, e))
        stage_overlap = {}
        for name, spans_of_stage in by_stage.items():
            stage_wall, stage_peak = _overlap(spans_of_stage)
            stage_overlap[name] = dict(
                calls=len(spans_of_stage),
                wait_ms_sum=round(sum(e - s for s, e in spans_of_stage)),
                wall_ms=round(stage_wall),
                peak_parallel=stage_peak,
            )
        by_kind = [
            dict(
                stage=stage,
                provider=provider,
                kind=kind,
                count=v["count"],
                failed=v["failed"],
                rejected=v["rejected"],
                ms=round(v["ms"]),
                max_ms=round(v["max_ms"]),
                connection_observed=v["observed"],
                new_connections=v["new_connections"],
                connect_ms=round(v["connect_ms"]),
            )
            for (stage, provider, kind), v in calls.items()
        ]
        for row in by_kind:
            # 단계별 요약에 연결 재사용 여부를 더한다(알 수 있는 호출만: connection_observed).
            target = stage_overlap.get(row["stage"])
            if target is not None and row["connection_observed"]:
                target["connection_observed"] = target.get("connection_observed", 0) + row["connection_observed"]
                target["new_connections"] = target.get("new_connections", 0) + row["new_connections"]
                target["connect_ms"] = target.get("connect_ms", 0) + row["connect_ms"]
        return dict(
            total_ms=round(total),
            stages=rows,
            spans={k: dict(count=v[0], ms=round(v[1])) for k, v in sorted(spans.items())},
            external=dict(
                calls=sum(r["count"] for r in by_kind),
                failed=sum(r["failed"] for r in by_kind),
                rejected=sum(r["rejected"] for r in by_kind),
                wait_ms_sum=sum(r["ms"] for r in by_kind),
                wall_ms=round(wall),
                peak_parallel=peak,
                by_kind=by_kind,
            ),
            external_by_stage=stage_overlap,
            cache_hits=cache,
            counts=counts,
            db=db,
            scope="추천 작업 안의 시간(ms). 작업 저장·폴링·화면 표시는 포함하지 않음. 외부 호출 ms 는 호출마다 기다린 시간의 합.",
        )


class ConnectionProbe:
    """httpx 의 trace 확장으로 이 호출이 새 연결(TCP·TLS)을 맺었는지와 그 시간을 잰다. 주소·인증서 정보는 남기지 않는다."""

    def __init__(self):
        self.started = None
        self.connect_ms = 0.0
        self.new = False
        self.seen = False

    def __call__(self, event, info):
        if event.startswith(("http11.", "http2.")):
            self.seen = True
        elif event == "connection.connect_tcp.started":
            self.new = True
            self.started = time.perf_counter()
        elif event in ("connection.connect_tcp.complete", "connection.start_tls.complete") and self.started:
            self.connect_ms = (time.perf_counter() - self.started) * 1000

    def result(self):
        # 실제 연결을 거치지 않은 호출(시험용 가짜 전송 등)은 모른다고 둔다.
        return (int(self.new), self.connect_ms) if self.seen else None


def connection_probe(client, kwargs):
    """추천 안에서 httpx.Client 로 보내는 호출이면 kwargs 에 trace 확장을 넣고 probe 를 돌려준다. 그 밖에는 아무것도 하지 않는다."""
    if _current.get() is None or "extensions" in kwargs:
        return None
    import httpx

    if not isinstance(client, httpx.Client):
        return None
    probe = ConnectionProbe()
    kwargs["extensions"] = {"trace": probe}
    return probe


def _overlap(intervals):
    """구간 목록이 실제로 차지한 시간(겹친 구간은 한 번만)과 가장 많이 겹친 수."""
    wall, peak, edge = 0.0, 0, None
    for start, end in sorted(intervals):
        if edge is None or start > edge:
            wall += end - start
            edge = end
        elif end > edge:
            wall += end - edge
            edge = end
    events = sorted([(s, 1) for s, _ in intervals] + [(e, -1) for _, e in intervals])
    running = 0
    for _, step in events:
        running += step
        peak = max(peak, running)
    return wall, peak


def current():
    return _current.get()


@contextmanager
def recording():
    trace = Trace()
    token = _current.set(trace)
    try:
        yield trace
    finally:
        _current.reset(token)


def stage(name):
    trace = _current.get()
    if trace:
        trace.enter_stage(name)


@contextmanager
def span(name):
    trace = _current.get()
    if not trace:
        yield
        return
    start = time.perf_counter()
    try:
        yield
    finally:
        trace.add_span(name, (time.perf_counter() - start) * 1000)


def cache_hit(kind):
    trace = _current.get()
    if trace:
        trace.add_cache_hit(kind)


def count(name, n=1):
    """구간 안의 개수(예: 가격 조회 수, 가격 확인 뒤 바뀐 안 수). 이름은 고정 문자열만 쓴다(검색어·장소 이름 금지)."""
    trace = _current.get()
    if trace and n:
        trace.add_count(name, int(n))


class TimedConnection:
    """store.connect() 결과를 감싸 with 블록 안의 시간을 잰다. 추천 안에서만 쓰인다."""

    def __init__(self, connection, trace):
        self.connection = connection
        self.trace = trace

    def __enter__(self):
        self.start = time.perf_counter()
        return self.connection.__enter__()

    def __exit__(self, *args):
        try:
            return self.connection.__exit__(*args)
        finally:
            self.trace.add_db((time.perf_counter() - self.start) * 1000)


def timed_connection(connection):
    trace = _current.get()
    return TimedConnection(connection, trace) if trace else connection
