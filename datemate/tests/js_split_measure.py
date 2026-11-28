"""첫 화면 로딩 측정(QA-19 JS 나눠 받기 전후 비교용 수동 도구, 2026-11-28).

이름이 test_*.py 가 아니라 일반 pytest 실행에는 수집되지 않는다(tests/photo_layout_capture.py 와 같은 방식). datemate 폴더에서:
    python -m pytest tests/js_split_measure.py -q -s
조건(docs/QA-19-js-split-design.ko.md 3.8): Playwright Chromium, 시도마다 새 context, 402×874, 캐시 없음, 지연 150ms·내려받기 1.6Mbps·
올리기 750kbps, CPU 4배, 5회 중앙값.

환경 변수
    MEASURE_URL     재는 주소. 없으면 이 저장소 앱을 로컬에 띄운다(conftest 가 묶음을 만든 상태 = 운영과 같은 묶음 태그).
                    로컬 앱은 압축 없이 보내므로(운영은 Cloudflare 가 압축) 이 도구가 gzip 으로 감싸서 띄운다 — 느린 회선에서 전송량이 운영과 비슷해지게.
                    MEASURE_GZIP=0 이면 감싸지 않는다. 로컬은 HTTP/1.1, 운영은 HTTP/2·brotli 라 절대값은 다르다(전후 비교에 쓴다).
    MEASURE_RUNS    횟수(기본 5)
    MEASURE_FAST=1  느린 조건 없이(회선·CPU 그대로) 잰다.
    MEASURE_ABORT   이 정규식에 맞는 주소 요청을 끊는다(원인 나누기: '\\.js' = JS 없이, '\\.css' = CSS 없이).
    MEASURE_EXPLORE=1  DOMContentLoaded 100ms 뒤 '장소 둘러보기'를 눌러 목록·안내가 뜰 때까지 시간도 잰다(따로 3회).
    MEASURE_COVERAGE=1 느린 조건 없이 한 번 더 열어 첫 화면에서 실행된 JS 비율(CDP precise coverage)을 잰다.
    MEASURE_LABEL   결과에 적을 이름(예: before, after)
    MEASURE_OUT     결과 JSON 을 쓸 파일(없으면 화면에만)

지표(ms): dcl·load(navigation timing), fcp·lcp, ready(statusData 와 .simple-plan-form 이 생긴 때 = 첫 화면 준비),
later_start·later_ready(나중 묶음 로더 표시, 없으면 null), css_end(마지막 CSS 응답 끝), js_end(DCL 전에 끝난 마지막 JS 응답 끝),
long_before_dcl(DCL 전 긴 작업 합), long_total(FCP~max(later_ready, load)+2초 사이 긴 작업 합), 전송 크기(B)는 CSS 합·JS 주소별.
글꼴(2026-11-28 perf/font-loading 에서 더함): font_first_end·font_early_end(load 전에 시작한 글꼴 가운데 첫·마지막 응답 끝 = 글자가 바뀌는 구간),
font_bytes_early·font_count_early(load 전에 시작한 글꼴 전송 합·수), font_bytes·font_count(전체 글꼴을 나중에 받는 것까지 모두),
fonts_full(static/full-fonts.js 가 전체 글꼴로 바꾼 때, 없으면 null), cls(레이아웃 밀림 합, 사용자 입력 직후 것은 빼고)·cls_after_ready(첫 화면 준비 뒤의 몫).
"""

import json
import os
import re
import socket
import statistics
import threading
import time

import pytest
import uvicorn

from app.main import app

RUNS = int(os.getenv("MEASURE_RUNS", "5"))
FAST = os.getenv("MEASURE_FAST") == "1"
ABORT = os.getenv("MEASURE_ABORT", "")

OBSERVE = """(()=>{const m=window.__measure={long:[],fcp:null,lcp:null,ready:null,shifts:[]};
try{new PerformanceObserver(l=>{for(const e of l.getEntries())if(!e.hadRecentInput)m.shifts.push([e.startTime,e.value]);}).observe({type:'layout-shift',buffered:true});}catch(e){}
try{new PerformanceObserver(l=>{for(const e of l.getEntries())m.long.push([e.startTime,e.duration]);}).observe({type:'longtask',buffered:true});}catch(e){}
try{new PerformanceObserver(l=>{for(const e of l.getEntries())if(e.name==='first-contentful-paint')m.fcp=e.startTime;}).observe({type:'paint',buffered:true});}catch(e){}
try{new PerformanceObserver(l=>{for(const e of l.getEntries())m.lcp=e.startTime;}).observe({type:'largest-contentful-paint',buffered:true});}catch(e){}
const timer=setInterval(()=>{let ok=false;try{ok=typeof statusData!=='undefined'&&!!statusData&&!!document.querySelector('.simple-plan-form');}catch(e){}
  if(ok){m.ready=performance.now();clearInterval(timer);}},50);})();"""

COLLECT = """()=>{const m=window.__measure,nav=performance.getEntriesByType('navigation')[0];
const res=performance.getEntriesByType('resource').map(e=>({name:new URL(e.name).pathname,end:e.responseEnd,start:e.startTime,size:e.transferSize,body:e.encodedBodySize,raw:e.decodedBodySize}));
const mark=n=>{const e=performance.getEntriesByName(n)[0];return e?e.startTime:null;};
return {dcl:nav.domContentLoadedEventStart,dcl_end:nav.domContentLoadedEventEnd,load:nav.loadEventStart,html_end:nav.responseEnd,html_size:nav.transferSize,
  fcp:m.fcp,lcp:m.lcp,ready:m.ready,later_start:mark('later:start'),later_ready:mark('later:ready'),fonts_full:mark('fonts:full'),long:m.long,shifts:m.shifts,res};}"""


@pytest.fixture(scope="module")
def target():
    url = os.getenv("MEASURE_URL")
    if url:
        yield url.rstrip("/")
        return
    served = app
    if os.getenv("MEASURE_GZIP", "1") != "0":
        from starlette.middleware.gzip import GZipMiddleware

        served = GZipMiddleware(app, minimum_size=500)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    server = uvicorn.Server(uvicorn.Config(served, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started
    try:
        yield f"http://127.0.0.1:{sock.getsockname()[1]}"
    finally:
        server.should_exit = True
        thread.join(10)
        sock.close()


def open_page(browser, base, slow=True):
    context = browser.new_context(viewport={"width": 402, "height": 874})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    cdp = context.new_cdp_session(page)
    cdp.send("Network.enable")
    cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
    if slow and not FAST:
        cdp.send(
            "Network.emulateNetworkConditions",
            {
                "offline": False,
                "latency": 150,
                "downloadThroughput": 1.6e6 / 8,
                "uploadThroughput": 750e3 / 8,
            },
        )
        cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
    if ABORT:
        pattern = re.compile(ABORT)
        page.route(
            "**/*",
            lambda route: (
                route.abort() if pattern.search(route.request.url) else route.continue_()
            ),
        )
    page.add_init_script(OBSERVE)
    return context, page, cdp, errors


def one_run(browser, base):
    context, page, _, errors = open_page(browser, base)
    try:
        page.goto(base + "/", wait_until="load", timeout=120000)
        if not ABORT:
            page.wait_for_function("()=>window.__measure.ready!==null", timeout=120000)
            page.wait_for_function(
                "()=>typeof DatemateLater==='undefined'||DatemateLater.loaded", timeout=120000
            )
            # 전체 글꼴을 나중에 받는 코드가 있으면 끝날 때까지(받는 양·바뀌는 때·그때의 레이아웃 밀림을 함께 잰다).
            page.evaluate(
                "()=>typeof DatemateFullFonts==='undefined'?null:DatemateFullFonts.done.then(()=>null)"
            )
        page.wait_for_timeout(2500)
        data = page.evaluate(COLLECT)
    finally:
        context.close()
    css = [r for r in data["res"] if r["name"].endswith(".css")]
    scripts = [r for r in data["res"] if r["name"].endswith((".js", ".mjs"))]
    before_dcl = [r for r in scripts if r["end"] <= data["dcl"]]
    until = max(data["later_ready"] or 0, data["load"]) + 2000
    row = {
        key: data[key]
        for key in (
            "dcl",
            "load",
            "fcp",
            "lcp",
            "ready",
            "later_start",
            "later_ready",
            "html_end",
            "fonts_full",
        )
    }
    fonts = [r for r in data["res"] if r["name"].endswith(".woff2")]
    early = [r for r in fonts if r["start"] < data["load"]]
    row["font_first_end"] = min((r["end"] for r in early), default=None)
    row["font_early_end"] = max((r["end"] for r in early), default=None)
    row["font_bytes_early"] = sum(r["size"] for r in early)
    row["font_count_early"] = len(early)
    row["font_bytes"] = sum(r["size"] for r in fonts)
    row["font_count"] = len(fonts)
    row["cls"] = round(sum(v for _, v in data["shifts"]), 4)
    row["shifts"] = [[round(t), round(v, 4)] for t, v in data["shifts"]]
    row["cls_after_ready"] = round(
        sum(v for t, v in data["shifts"] if data["ready"] is not None and t > data["ready"]), 4
    )
    row["css_end"] = max((r["end"] for r in css), default=None)
    row["js_end"] = max((r["end"] for r in before_dcl), default=None)
    row["css_bytes"] = sum(r["size"] for r in css)
    row["js_bytes"] = sum(r["size"] for r in scripts)
    row["js_bytes_before_dcl"] = sum(r["size"] for r in before_dcl)
    row["long_before_dcl"] = sum(d for s, d in data["long"] if s < data["dcl"])
    row["long_total"] = sum(d for s, d in data["long"] if (data["fcp"] or 0) <= s <= until)
    row["long_max"] = max((d for _, d in data["long"]), default=0)
    row["scripts"] = {r["name"]: [r["size"], r["raw"], round(r["end"])] for r in scripts}
    # 받은 순서 그대로의 전체 목록: [주소, 시작 ms, 응답 끝 ms, 전송 B] — 무엇이 회선을 나눠 쓰는지 본다.
    row["waterfall"] = [
        [r["name"], round(r["start"]), round(r["end"]), r["size"]]
        for r in sorted(data["res"], key=lambda r: r["start"])
    ]
    row["script_count"] = len(scripts)
    row["errors"] = errors
    return row


def explore_run(browser, base):
    """DOMContentLoaded 100ms 뒤 '장소 둘러보기' → 목록 카드나 안내 글이 뜰 때까지(ms, 누른 때부터)."""
    context, page, _, errors = open_page(browser, base)
    try:
        page.add_init_script(
            """document.addEventListener('DOMContentLoaded',()=>setTimeout(()=>{const t=performance.now();window.__explore={clicked:t,shown:null};
              document.querySelector('#nav-explore').click();
              const timer=setInterval(()=>{if(document.querySelector('#catalog')?.children.length||document.querySelector('#search-info')?.textContent.trim()){
                window.__explore.shown=performance.now();clearInterval(timer);}},30);},100));"""
        )
        page.goto(base + "/", wait_until="domcontentloaded", timeout=120000)
        page.wait_for_function(
            "()=>window.__explore&&window.__explore.shown!==null", timeout=120000
        )
        seen = page.evaluate("window.__explore")
    finally:
        context.close()
    return {"explore_click_to_list": seen["shown"] - seen["clicked"], "errors": errors}


def coverage_run(browser, base):
    context, page, cdp, _ = open_page(browser, base, slow=False)
    try:
        cdp.send("Profiler.enable")
        cdp.send("Profiler.startPreciseCoverage", {"callCount": False, "detailed": True})
        page.goto(base + "/", wait_until="load", timeout=120000)
        page.wait_for_function("()=>window.__measure.ready!==null", timeout=120000)
        page.wait_for_function(
            "()=>typeof DatemateLater==='undefined'||DatemateLater.loaded", timeout=120000
        )
        page.wait_for_timeout(1500)
        result = cdp.send("Profiler.takePreciseCoverage")["result"]
        sizes = page.evaluate(
            "Object.fromEntries(performance.getEntriesByType('resource').map(e=>[e.name.split('?')[0],e.decodedBodySize]))"
        )
    finally:
        context.close()
    out = {}
    for script in result:
        url = script["url"].split("?")[0]
        if "/static/" not in url or url not in sizes:
            continue
        # 함수별 구간: 가장 바깥(파일 전체)부터 안쪽으로 덮어쓴다 — count 0 인 구간이 실행되지 않은 글자.
        total = sizes[url] or max(
            (r["endOffset"] for f in script["functions"] for r in f["ranges"]), default=0
        )
        used = bytearray(total + 1)
        ranges = sorted(
            (r for f in script["functions"] for r in f["ranges"]),
            key=lambda r: (r["startOffset"], -r["endOffset"]),
        )
        for r in ranges:
            value = 1 if r["count"] else 0
            end = min(r["endOffset"], total)
            used[r["startOffset"] : end] = bytes([value]) * max(0, end - r["startOffset"])
        out[url.split("/static/")[1]] = [sum(used), total]
    return out


def median(rows, key):
    values = [row[key] for row in rows if row.get(key) is not None]
    return round(statistics.median(values)) if values else None


def test_measure_first_screen(target):
    playwright = pytest.importorskip("playwright.sync_api")
    report = {
        "label": os.getenv("MEASURE_LABEL", ""),
        "url": target,
        "slow": not FAST,
        "abort": ABORT,
        "runs": [],
    }
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(
            channel=os.getenv("DATEMATE_BROWSER_CHANNEL", "msedge"), headless=True
        )
        try:
            one_run(browser, target)  # 서버 데우기(첫 요청의 가져오기·색인 준비를 재지 않는다)
            for _ in range(RUNS):
                report["runs"].append(one_run(browser, target))
            if os.getenv("MEASURE_EXPLORE") == "1":
                report["explore"] = [explore_run(browser, target) for _ in range(3)]
            if os.getenv("MEASURE_COVERAGE") == "1":
                report["coverage"] = coverage_run(browser, target)
        finally:
            browser.close()
    keys = (
        "dcl",
        "load",
        "fcp",
        "lcp",
        "ready",
        "later_start",
        "later_ready",
        "html_end",
        "css_end",
        "js_end",
        "long_before_dcl",
        "long_total",
        "long_max",
        "css_bytes",
        "js_bytes",
        "js_bytes_before_dcl",
        "script_count",
        "font_first_end",
        "font_early_end",
        "font_bytes_early",
        "font_count_early",
        "font_bytes",
        "font_count",
        "fonts_full",
    )
    report["median"] = {key: median(report["runs"], key) for key in keys}
    for key in ("cls", "cls_after_ready"):  # 작은 소수라 반올림하지 않는다
        report["median"][key] = statistics.median(row[key] for row in report["runs"])
    if "explore" in report:
        report["median"]["explore_click_to_list"] = median(
            report["explore"], "explore_click_to_list"
        )
    if "coverage" in report:
        used = sum(v[0] for v in report["coverage"].values())
        total = sum(v[1] for v in report["coverage"].values())
        report["median"]["js_used_percent"] = round(100 * used / total, 1) if total else None
    report["scripts"] = report["runs"][-1]["scripts"]
    print("waterfall [path, start, end, transfer B] (last run):")
    for line in report["runs"][-1]["waterfall"]:
        print("  ", line)
    report["errors"] = [e for row in report["runs"] for e in row["errors"]]
    print("layout shifts [ms, value] (last run):", report["runs"][-1]["shifts"])
    print("\n==== first screen measure:", report["label"] or "(no label)", "====")
    print("each dcl:", [round(row["dcl"]) for row in report["runs"]])
    print(json.dumps(report["median"], ensure_ascii=False, indent=1))
    print(
        "scripts [transfer B, raw B, response end ms]:",
        json.dumps(report["scripts"], ensure_ascii=False),
    )
    if report.get("coverage"):
        print("coverage [used, total]:", json.dumps(report["coverage"], ensure_ascii=False))
    print("page errors:", report["errors"])
    out = os.getenv("MEASURE_OUT")
    if out:
        with open(out, "w", encoding="utf-8") as file:
            json.dump(report, file, ensure_ascii=False, indent=1)
