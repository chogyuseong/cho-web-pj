"""QA-19 첫 화면 JS 나눠 받기(2026-11-28, 브랜치 feat/js-split-qa19).

첫 화면(static/index.html)의 스크립트를 둘로 나눴다: 바로 받는 첫 묶음(bundles/index.js)과, template#later-scripts 안에 적혀
later-scripts.js(전역 DatemateLater)가 DOMContentLoaded 뒤에 붙이는 나중 묶음(bundles/index-2.js — 결과 화면·둘러보기·지도·장소 정보 창).
모듈이 아니라 전역을 함께 쓰는 일반 스크립트 그대로라, 첫 묶음이 나중 묶음의 이름을 쓰는 곳은 DatemateLater 를 먼저 기다려야 한다.

여기서 보는 것
  1. 구조: 덩어리 둘, 두 번째는 template 안, 두 묶음의 첫 파일에 'use strict' 없음, 로더가 app.js 보다 앞, 첫 묶음 크기.
  2. 정적 허용 목록: 첫 묶음 파일이 나중 묶음 이름을 쓰는 곳 전부(파일·맨 위 문장별) = 아래 ENTRY. 새 참조가 생기면 실패한다.
  3. 브라우저: 나중 묶음을 붙잡아 두거나(느린 회선) 끊어도(받기 실패) 모든 진입 버튼·경로가 기다렸다 동작하거나 안내를 띄운다.
     페이지 오류(ReferenceError 등) 0, 받기 실패 때 서버에 추천 작업(POST /api/plan-jobs) 0, 다시 누르면 동작.
  4. 묶음이 없거나 오래돼 원본 태그를 쓰는 개발 중에도 같은 길로 동작하고, 받기에 실패한 파일만 다시 받는다.
  5. CSP(인라인 없음, script-src 'self') 위반 0, 동적으로 붙인 나중 묶음이 load 이벤트 전에 실행된다(기존 화면 테스트가 기대는 성질).
묶음 내용·?v=·앱과 엣지의 같은 페이지는 tests/test_js_bundle.py, 엣지 캐시는 cloudflare/edge.test.mjs. 측정은 tests/js_split_measure.py(수동).
"""

import json
import os
import re
import shutil
import socket
import threading
import time
from urllib.parse import parse_qs, urlsplit

import pytest
import uvicorn

import js_globals
from app import static_pages
from app.config import ROOT
from app.main import app

STATIC = ROOT / "static"
BUNDLE_BUILT = bool(
    shutil.which("node") and (ROOT.parent / "cloudflare" / "build-edge-pages.mjs").is_file()
)
LOAD_FAILED = "코스 화면을 불러오지 못했어요. 연결을 확인하고 다시 시도해 주세요."
BROKEN = "화면 일부를 불러오지 못했어요. 새로고침해 주세요."
WAITING = "화면을 준비하고 있어요. 준비되면 바로 이어 갈게요."


# ── 1. 구조 ─────────────────────────────────────────────────────────────────────────────────────


def test_index_has_two_script_chunks_and_the_second_is_inert():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    first, later = js_globals.page_scripts()
    runs = [
        js_globals.SCRIPT_TAG.findall(run.group(0))
        for run in static_pages._SCRIPT_RUN.finditer(html)
    ]
    assert runs == [first, later]
    assert len(first) >= 20 and len(later) >= 20
    assert not set(first) & set(later)
    # 로더는 첫 묶음에서 자기 뒤 파일이 맨 위 실행 중에 쓸 수 있게 앞쪽에(묶음 맨 앞은 ko-text.js 그대로).
    assert first[:2] == ["ko-text.js", "later-scripts.js"]
    # template 안의 script 는 브라우저가 받지도 실행하지도 않는다. 그 안에는 script 태그와 공백뿐이다.
    inside = js_globals.LATER_TEMPLATE.search(html).group(1)
    assert js_globals.SCRIPT_TAG.sub("", inside).strip() == ""
    assert html.count("<template") == 1 and "<script>" not in html  # 인라인 스크립트 없음(CSP)


def test_first_file_of_each_bundle_is_not_strict():
    """묶음의 첫 파일이 'use strict' 로 시작하면 그 묶음 전체가 엄격 모드가 된다(build-edge-pages.mjs 'JS 묶기')."""
    for names in js_globals.page_scripts():
        code = js_globals.file_code(names[0]).lstrip()
        assert not re.match(r"""['"]\s*['"]\s*;?""", code[:20]), names[0]
        assert (
            "use strict"
            not in (STATIC / names[0]).read_text(encoding="utf-8").split("*/")[-1].lstrip()[:20]
        )


def test_first_bundle_stays_small():
    """퇴행 방지: 첫 화면에 필요 없는 코드가 첫 묶음으로 돌아오면 느린 회선의 DOMContentLoaded 가 다시 늦어진다.
    나누기 전 한 묶음은 약 724KB, 나눈 직후 첫 묶음은 약 285KB. 넘으면 새 코드를 나중 묶음(template#later-scripts)에 둘 수 있는지 본다."""
    first, later = js_globals.page_scripts()
    size = sum((STATIC / name).stat().st_size for name in first)
    assert size < 320_000, size
    assert sum((STATIC / name).stat().st_size for name in later) > size


def test_later_files_do_not_wait_for_domcontentloaded():
    """나중 묶음은 DOMContentLoaded 뒤에 실행되므로, 그 이벤트를 기다리는 코드는 영영 돌지 않는다."""
    for name in js_globals.page_scripts()[1]:
        assert "DOMContentLoaded" not in js_globals.file_code(name), name


# ── 2. 정적 허용 목록 ────────────────────────────────────────────────────────────────────────────
# 첫 묶음 파일이 나중 묶음의 전역 이름을 쓰는 곳 전부: (파일, 맨 위 문장 이름) → (종류, 쓰는 이름들).
#   gate   그 문장 안에서 DatemateLater.need()/ready()/whenReady() 를 기다린 뒤에 쓴다(진입점).
#   inner  기다리지 않는다. 대신 이 이름을 부르는 첫 묶음 코드가 모두 이 표의 문장 안에 있다
#          (gate 를 지난 뒤에만 불리거나, 결과 화면처럼 나중 묶음 코드에서만 불린다) — 아래 테스트가 호출 지점을 확인한다.
#   check  로더가 약속한 이름이 다 생겼는지 typeof 로 보는 곳.
# 새 참조를 더하면 이 표와 달라져 실패한다: 진입점이면 DatemateLater 를 기다리게 하고 여기에 적는다.
RESULTS = {"renderResults", "renderDetail"}
ENTRY = {
    ("later-scripts.js", "DatemateLater"): (
        "check",
        RESULTS
        | {"renderPlanMapCard", "openDialog", "loadNaverMaps", "loadLeaflet"}
        | {"ExploreView", "FestivalPanel", "PopupView", "PopupCourse"},
    ),
    # G1 둘러보기: 메뉴·검색 단추·Enter·주소 # 이동·처음 주소(#explore-section)·빠른 검색(#nav-explore 클릭)
    ("app.js", "search"): ("gate", {"ExploreView"}),
    # G2 코스 추천 제출(테마 카드 '이 조건으로 바로 추천받기'·바구니도 form.requestSubmit 으로 여기를 거친다)
    ("app.js", "form.addEventListener('submit', async e => {"): (
        "gate",
        RESULTS | {"FestivalPanel", "PopupCourse"},
    ),
    # G3 ?plan= 직접 열기, G4 팝업 전환 그리기(whenReady)
    ("app.js", "init"): ("gate", RESULTS | {"FestivalPanel", "PopupCourse", "PopupView"}),
    # G5 코스 종류(실제 장소·체험 코스) 전환 뒤 빈 결과 다시 그리기(whenReady)
    ("app.js", "form.elements.mode.addEventListener('change', ()"): ("gate", RESULTS),
    # G6 남은 검색 이어보기
    ("plan-progress.js", "resumeOnce"): ("gate", RESULTS | {"FestivalPanel", "PopupCourse"}),
    # G7 지도에서 고르기
    ("location-picker.js", "openLocationPicker"): (
        "gate",
        {"openDialog", "loadNaverMaps", "loadLeaflet"},
    ),
    # G8 내가 결정한 코스 다시 보기(PlanningStudy.showDecisions)
    ("planning-outcomes.js", "PlanningStudy"): ("gate", {"openDialog"}),
    # gate 를 지난 뒤에만 불린다(제출 처리, resumeOnce).
    ("app.js", "values"): ("inner", {"FestivalPanel", "includedPlaces"}),
    ("app.js", "beginPlanSearch"): ("inner", {"renderPlanMapCard"}),
    # 결과 화면·장소 정보 창(나중 묶음 코드)에서만 불린다.
    ("app.js", "rememberVerifiedMapTarget"): ("inner", {"markIdentity", "markTourHours"}),
    ("recommendation-feedback.js", "conditionDifferences"): ("inner", {"mealRescuePanel"}),
    ("experience.js", "togglePlanLock"): ("inner", {"commitPlanChange"}),
    ("experience.js", "showPlaceReport"): (
        "inner",
        {"commitPlanChange", "dialogGeneration", "openDialog"},
    ),
    ("experience.js", "showMealChange"): (
        "inner",
        {"dialogGeneration", "openDialog", "restaurantMenuRequests"},
    ),
    ("experience.js", "showDraft"): (
        "inner",
        {"commitNewPlan", "dialogGeneration", "festivalMiddleAfter", "openDialog", "runPlanChange"},
    ),
    ("experience.js", "partnerAgreementPanel"): ("inner", {"dialogGeneration"}),
    ("experience.js", "experiencePanel"): ("inner", {"openDialog"}),
    ("api-client.js", "copyPlanShare"): ("inner", {"openDialog"}),
    ("api-client.js", "kakaoItineraryText"): ("inner", {"dayOfSteps", "legModeLabel"}),
    ("api-client.js", "copyKakaoItinerary"): ("inner", {"openDialog"}),
    ("course-search.js", "courseSearchPanel"): ("inner", {"naverBlogBlock"}),
}
# inner 함수를 부르지만 나중 묶음 이름을 직접 쓰지는 않는 첫 묶음 함수: 이들도 결과 화면(나중 묶음 코드)에서만 불려야 한다.
INNER_CALLERS = {
    # 결정 패널(결과 상세 안): copyPlanShare·partnerAgreementPanel 을 부른다.
    ("planning-outcomes.js", "decisionPanel"),
}
# 같은 이름의 지역 변수라 참조가 아닌 곳(분석이 지역 변수를 가리지 못한다): (파일, 이름)
SHADOWED = {("theme-cards.js", "values")}


def first_bundle_references():
    first, later = js_globals.page_scripts()
    later_names = js_globals.declared(later)
    seen = {}
    for name in first:
        found = js_globals.units(name)
        for word, _, _, offset in js_globals.references(name, set(later_names)):
            seen.setdefault((name, js_globals.unit_of(found, offset)), set()).add(word)
    return seen


def test_no_global_name_is_declared_in_both_bundles():
    """같은 이름을 두 묶음이 선언하면 나중 묶음이 SyntaxError 로 통째로 멈춘다(const·let·function 중복 선언)."""
    first, later = js_globals.page_scripts()
    first_names, later_names = js_globals.declared(first), js_globals.declared(later)
    assert len(first_names) > 100 and len(later_names) > 200
    assert not set(first_names) & set(later_names)


def test_first_bundle_uses_later_names_only_at_listed_entry_points():
    seen = first_bundle_references()
    expected = {key: names for key, (_, names) in ENTRY.items()}
    assert seen == expected, {
        "새 참조(진입점이면 DatemateLater 를 기다리게 하고 ENTRY 에 적는다)": {
            str(key): sorted(names - expected.get(key, set()))
            for key, names in seen.items()
            if names - expected.get(key, set())
        },
        "없어진 참조(ENTRY 에서 지운다)": {
            str(key): sorted(names - seen.get(key, set()))
            for key, names in expected.items()
            if names - seen.get(key, set())
        },
    }


def test_gates_wait_and_inner_functions_are_only_called_behind_them():
    first, _ = js_globals.page_scripts()
    listed = set(ENTRY) | INNER_CALLERS
    for (name, label), (kind, _) in ENTRY.items():
        found = js_globals.units(name)
        code = js_globals.file_code(name)
        text = "".join(code[start:end] for start, end, unit in found if unit == label)
        assert text, (name, label)
        if kind == "gate":
            assert re.search(r"DatemateLater\.(need|ready|whenReady)\(", text), (name, label)
    inner = {label for (_, label), (kind, _) in ENTRY.items() if kind == "inner"}
    inner |= {label for _, label in INNER_CALLERS}
    for name in first:
        found = js_globals.units(name)
        for word, line, text, offset in js_globals.references(name, inner):
            unit = js_globals.unit_of(found, offset)
            if unit == word or (name, word) in SHADOWED:
                continue
            assert (name, unit) in listed, (
                f"{name}:{line} {word} 를 부르는 곳이 진입점 표 밖이다 — {text}"
            )


# ── 3~5. 브라우저 ────────────────────────────────────────────────────────────────────────────────
FIRST_SCREEN = "()=>typeof statusData!=='undefined'&&!!statusData&&!!document.querySelector('.simple-plan-form')"
DEMO = """()=>{form.elements.mode.value='demo';form.elements.mode.dispatchEvent(new Event('change',{bubbles:true}));
  form.elements.visit_date.value='2026-10-24';form.elements.max_leg.value=180;form.elements.budget.value=1000000;}"""
TOAST = "()=>document.querySelector('#toast').textContent"
CLICK_TEXT = (
    "text=>[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===text).click()"
)
SCRIPT_NAME = re.compile(r"/static/(?:bundles/)?([^/?]+\.js)")


class Later:
    """나중 묶음 요청을 붙잡거나(hold) 끊거나(abort) 빈 파일로 바꾼다(empty). release() 하면 붙잡은 요청을 보내고 그 뒤로는 통과."""

    def __init__(self, page, names, mode):
        self.mode = mode
        self.only = None  # 이름 집합이면 그 파일만 mode 를 적용
        self.held = []
        self.requests = []
        wanted = set(names)

        def handle(route):
            name = SCRIPT_NAME.search(route.request.url).group(1)
            if name not in wanted:
                return route.continue_()
            self.requests.append(name)
            mode = self.mode if self.only is None or name in self.only else "pass"
            if mode == "hold":
                self.held.append(route)
            elif mode == "abort":
                route.abort()
            elif mode == "empty":
                route.fulfill(body="/* empty */", content_type="text/javascript")
            else:
                route.continue_()

        page.route(re.compile(r"/static/(?:bundles/)?[^/?]+\.js(\?|$)"), handle)

    def release(self):
        self.mode = "pass"
        held, self.held = self.held, []
        for route in held:
            route.continue_()


class Session:
    def __init__(self, browser, base, later_names):
        self.browser, self.base, self.later_names = browser, base, later_names
        self.context = browser.new_context(viewport={"width": 1280, "height": 900})
        self.pages = []

    def open(self, path="/", mode="pass", popups=False, wait="domcontentloaded"):
        """CSP 를 끄지 않은 페이지(bypass_csp 없음). (page, later, seen) — seen: errors·console·posts·explore·csp."""
        page = self.context.new_page()
        seen = {"errors": [], "console": [], "posts": [], "explore": []}
        page.on("pageerror", lambda error: seen["errors"].append(str(error)))
        page.on(
            "console",
            lambda message: message.type == "error" and seen["console"].append(message.text),
        )

        def request(req):
            url = urlsplit(req.url)
            if req.method == "POST" and url.path == "/api/plan-jobs":
                seen["posts"].append(req.url)
            if url.path == "/api/explore":
                seen["explore"].append(parse_qs(url.query))

        page.on("request", request)
        page.add_init_script(
            "window.__csp=[];document.addEventListener('securitypolicyviolation',e=>window.__csp.push(e.violatedDirective+' '+e.blockedURI));"
        )
        if popups:
            # 팝업 전환은 서버 스위치가 켜져 있을 때만 그린다. 상태 응답의 그 값만 켠다.
            def status(route):
                data = route.fetch().json()
                data["popups_enabled"] = True
                route.fulfill(json=data)

            page.route("**/api/status", status)
        later = Later(page, self.later_names, mode)
        page.goto(self.base + path, wait_until=wait)
        page.wait_for_function(FIRST_SCREEN)
        self.pages.append((page, seen))
        return page, later, seen

    def close(self):
        self.context.close()


@pytest.fixture(scope="module")
def served():
    playwright = pytest.importorskip("playwright.sync_api")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    base = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        assert server.started
        with playwright.sync_playwright() as pw:
            browser = pw.chromium.launch(
                channel=os.getenv("DATEMATE_BROWSER_CHANNEL", "msedge"), headless=True
            )
            try:
                yield browser, base
            finally:
                browser.close()
    finally:
        server.should_exit = True
        thread.join(10)
        sock.close()


@pytest.fixture
def session(served):
    """묶음을 쓰는 평소 페이지(나중 묶음 = bundles/index-2.js 하나)."""
    if not BUNDLE_BUILT:
        pytest.skip("needs node and cloudflare/ (conftest builds the bundles)")
    browser, base = served
    current = Session(browser, base, ["index-2.js"])
    yield current
    for page, seen in current.pages:
        assert not seen["errors"], seen["errors"]
        assert page.evaluate("window.__csp") == []
    current.close()


@pytest.fixture
def source_session(served, monkeypatch):
    """묶음이 없거나 오래된 개발 중처럼 원본 태그를 그대로 쓰는 페이지(나중 묶음 = 원본 파일들)."""
    monkeypatch.setattr(static_pages, "bundled_page", lambda name, html: html)
    browser, base = served
    current = Session(browser, base, js_globals.page_scripts()[1])
    yield current
    for page, seen in current.pages:
        assert not seen["errors"], seen["errors"]
        assert page.evaluate("window.__csp") == []
    current.close()


def later_state(page):
    return page.evaluate(
        "()=>({state:DatemateLater.state,loaded:DatemateLater.loaded,results:typeof renderResults})"
    )


def assert_waiting(page, seen):
    """나중 묶음이 아직 없는 첫 화면: 오류 없이 다 그려졌고, 나중 묶음 이름은 아직 없다."""
    assert later_state(page) == {"state": "loading", "loaded": False, "results": "undefined"}
    assert not seen["errors"] and not seen["console"], seen


def wait_ready(page):
    page.wait_for_function("()=>DatemateLater.loaded")


def wait_toast(page, text):
    page.wait_for_function(
        "text=>document.querySelector('#toast').textContent.includes(text)", arg=text
    )


def no_reference_errors(seen):
    """받기를 끊거나 서버가 4xx 를 주면(테스트의 지난 방문일에 축제·팝업 조회가 422 — 나누기 전에도 같다) 브라우저가 '받지 못함'을 콘솔에 적는다.
    그 밖의 콘솔 오류(ReferenceError 등)와 페이지 오류는 없어야 한다."""
    other = [text for text in seen["console"] if "Failed to load resource" not in text]
    assert not other and not seen["errors"], seen


def test_later_bundle_runs_before_load_event_under_the_real_csp(session):
    """동적으로 붙인 나중 묶음도 load 이벤트를 늦춘다 — goto(기본 load)·networkidle 로 여는 기존 화면 테스트는 그대로 나중 묶음까지 실행된 화면을 받는다."""
    page, later, seen = session.open(wait="load")
    assert later_state(page) == {"state": "ready", "loaded": True, "results": "function"}
    assert later.requests == ["index-2.js"]
    tags = page.evaluate(
        "()=>[...document.scripts].map(s=>new URL(s.src).pathname+(s.closest('template')?' template':''))"
    )
    assert tags == ["/static/bundles/index.js", "/static/bundles/index-2.js"]
    marks = page.evaluate(
        "()=>['later:start','later:ready'].map(n=>performance.getEntriesByName(n).length)"
    )
    assert marks == [1, 1]
    timing = page.evaluate(
        """()=>{const nav=performance.getEntriesByType('navigation')[0];
          const later=performance.getEntriesByType('resource').find(e=>e.name.includes('index-2.js'));
          return {dcl:nav.domContentLoadedEventStart,asked:later.startTime,ready:performance.getEntriesByName('later:ready')[0].startTime,load:nav.loadEventStart};}"""
    )
    # 나중 묶음은 DOMContentLoaded 뒤에 받기 시작하고, load 전에 실행이 끝난다.
    assert timing["dcl"] <= timing["asked"] + 1 and timing["ready"] <= timing["load"] + 1, timing
    no_reference_errors(seen)


def test_slow_later_bundle_explore_waits_then_searches(session):
    page, later, seen = session.open(mode="hold")
    assert_waiting(page, seen)
    page.locator("#nav-explore").click()
    assert page.locator("#explore-section").is_visible()
    wait_toast(page, WAITING)  # 0.4초 넘게 걸리면 준비 중 안내
    # 기다리는 동안 시·도를 바꾸면(explore.js 의 change 처리가 아직 없다) 그 선택으로 찾는다 — 조건 화면 지역으로 덮어쓰지 않는다.
    page.locator("#explore-region").select_option("부산")
    assert not seen["explore"]
    assert_waiting(page, seen)
    later.release()
    page.wait_for_function(
        "()=>document.querySelector('#search-info').textContent.trim()||document.querySelector('#catalog .hint')"
    )
    assert [query["region"] for query in seen["explore"]] == [["부산"]]
    assert page.locator("#explore-region").input_value() == "부산"
    assert page.evaluate("()=>ExploreView.regionTouched") is True
    no_reference_errors(seen)


def test_slow_later_bundle_first_address_hash_opens_explore(session):
    page, later, seen = session.open("/#explore-section", mode="hold")
    assert page.locator("#explore-section").is_visible()
    assert_waiting(page, seen)
    later.release()
    page.wait_for_function(
        "()=>document.querySelector('#search-info').textContent.trim()||document.querySelector('#catalog .hint')"
    )
    assert len(seen["explore"]) == 1 and page.locator("#status").is_hidden()
    no_reference_errors(seen)


def test_slow_later_bundle_submit_waits_and_posts_once(session):
    page, later, seen = session.open(mode="hold")
    page.evaluate(DEMO)  # 코스 종류 전환(G5)도 나중 묶음 없이 오류 없이 지나간다
    assert_waiting(page, seen)
    page.locator("#submit-plan").click()
    wait_toast(page, WAITING)
    assert page.locator("#submit-plan").is_disabled() and not seen["posts"]
    assert_waiting(page, seen)
    later.release()
    page.wait_for_function(
        "()=>selected?.id&&!document.querySelector('#submit-plan').disabled", timeout=45000
    )
    assert len(seen["posts"]) == 1
    assert page.evaluate("()=>document.querySelector('#plan-detail').dataset.planId===selected.id")
    no_reference_errors(seen)


def test_slow_later_bundle_theme_card_submit_waits_and_posts_once(session):
    page, later, seen = session.open(mode="hold")
    page.locator("#curation-tab-areas").click()
    page.locator('#curation-areas [data-preset="서울 성수"]').click()
    go = page.locator(".preset-go")
    go.wait_for(state="visible")
    page.evaluate("()=>{form.elements.visit_date.value='2026-10-24';}")
    assert_waiting(page, seen)
    go.click()
    wait_toast(page, WAITING)
    assert not seen["posts"]
    with page.expect_request(
        lambda req: req.method == "POST" and urlsplit(req.url).path == "/api/plan-jobs"
    ):
        later.release()
    page.wait_for_function("()=>!document.querySelector('#submit-plan').disabled", timeout=45000)
    assert len(seen["posts"]) == 1


def test_slow_later_bundle_map_picker_and_saved_decisions_open_after_it_arrives(session):
    page, later, seen = session.open(mode="hold")
    page.evaluate(CLICK_TEXT, "지도에서 고르기")
    wait_toast(page, WAITING)
    assert not page.locator("#dialog").evaluate("d=>d.open")
    assert_waiting(page, seen)
    later.release()
    page.wait_for_function("()=>document.querySelector('#dialog').open")
    assert page.locator("#dialog").evaluate("d=>d.classList.contains('location-dialog')")
    assert "데이트할 지역 선택" in page.locator("#dialog").inner_text()
    page.locator("#close-dialog").click()

    page, later, seen = session.open(mode="hold")
    page.evaluate("()=>document.querySelector('.saved-decisions').click()")
    wait_toast(page, WAITING)
    assert_waiting(page, seen)
    later.release()
    page.wait_for_function("()=>document.querySelector('#dialog').open")
    assert "내가 결정한 코스" in page.locator("#dialog").inner_text()


def make_plan(session):
    page, _, _ = session.open(wait="load")
    page.evaluate(DEMO)
    page.locator("#submit-plan").click()
    page.wait_for_function(
        "()=>selected?.id&&!document.querySelector('#submit-plan').disabled", timeout=45000
    )
    return page, page.evaluate("()=>selected.id")


def test_slow_later_bundle_saved_plan_link_opens_after_it_arrives(session):
    _, plan_id = make_plan(session)
    page, later, seen = session.open("/?plan=" + plan_id, mode="hold")
    assert_waiting(page, seen)
    assert page.evaluate("()=>selected") is None
    later.release()
    page.wait_for_function(
        "id=>selected?.id===id&&document.querySelector('#plan-detail').dataset.planId===id",
        arg=plan_id,
    )
    assert page.locator(".results-area").is_visible() and page.locator("#status").is_hidden()
    no_reference_errors(seen)


def test_slow_later_bundle_resumes_the_remaining_search(session):
    page, later, seen = session.open(wait="load")
    page.evaluate(DEMO)
    # 화면을 거치지 않고 추천 작업만 만들고 '남은 검색'으로 적어 둔다(검색 중 새로고침한 것과 같은 상태).
    job = page.evaluate(
        """async()=>{const data=values();data.explicit_fields=[];
          data.origin={name:data.origin.name,lat:data.origin.lat,lon:data.origin.lon};
          const job=await api('/plan-jobs',data);PlanSearch.remember(job.id,null);return job.id;}"""
    )
    assert job and len(seen["posts"]) == 1
    later.mode = "hold"
    page.reload(wait_until="domcontentloaded")
    page.wait_for_function(FIRST_SCREEN)
    wait_toast(page, WAITING)
    assert_waiting(page, seen)
    # 이어보기를 기다리는 동안 새 검색을 겹쳐 시작하지 못한다(나누기 전에도 이어보기는 시작하자마자 단추를 껐다).
    assert page.locator("#submit-plan").is_disabled()
    later.release()
    page.wait_for_function(
        "()=>plans.length>0&&document.querySelector('#progress').textContent.includes('검색 복원 완료')",
        timeout=45000,
    )
    assert len(seen["posts"]) == 1  # 이어보기는 새 작업을 만들지 않는다
    assert page.evaluate("()=>document.querySelector('#plan-detail').dataset.planId===selected.id")


def test_slow_later_bundle_popup_switch_is_drawn_when_it_arrives(session):
    page, later, seen = session.open(mode="hold", popups=True)
    page.locator("#nav-explore").click()
    assert page.locator(".explore-switch-button").count() == 0
    assert_waiting(page, seen)
    later.release()
    wait_ready(page)
    page.wait_for_function("()=>document.querySelectorAll('.explore-switch-button').length===2")
    assert not seen["errors"], seen


def test_slow_later_bundle_mode_switches_end_in_the_same_screen(session):
    def switch(page):
        page.locator('#mode-switch [data-mode="travel"]').click()
        page.evaluate(DEMO)

    def shot(page):
        return page.evaluate(
            """()=>({results:document.querySelector('#results').innerHTML,count:document.querySelector('#result-count').textContent,
              badge:document.querySelector('#mode-badge').textContent,mode:document.documentElement.dataset.mode,
              detail:document.querySelector('#plan-detail')?.innerHTML??null})"""
        )

    control, _, _ = session.open(wait="load")
    switch(control)
    page, later, seen = session.open(mode="hold")
    switch(page)
    assert_waiting(page, seen)
    later.release()
    wait_ready(page)
    assert shot(page) == shot(control)
    no_reference_errors(seen)


def test_failed_later_bundle_tells_the_user_and_works_on_the_next_press(session):
    page, later, seen = session.open(mode="abort", popups=True)
    page.wait_for_function("()=>DatemateLater.state==='idle'")
    assert later.requests == ["index-2.js"]
    no_reference_errors(seen)
    # 둘러보기
    page.locator("#nav-explore").click()
    wait_toast(page, LOAD_FAILED)
    assert not seen["explore"] and page.locator(".explore-switch-button").count() == 0
    page.locator("#nav-plan").click()
    # 코스 추천: 서버에 추천 작업을 만들지 않고, 단추는 다시 누를 수 있다.
    page.evaluate(DEMO)
    page.evaluate("()=>{document.querySelector('#toast').textContent='';}")
    page.locator("#submit-plan").click()
    wait_toast(page, LOAD_FAILED)
    page.wait_for_function("()=>!document.querySelector('#submit-plan').disabled")
    assert not seen["posts"]
    # 지도에서 고르기, 내가 결정한 코스 다시 보기
    for press in (
        lambda: page.evaluate(CLICK_TEXT, "지도에서 고르기"),
        lambda: page.evaluate("()=>document.querySelector('.saved-decisions').click()"),
    ):
        page.evaluate("()=>{document.querySelector('#toast').textContent='';}")
        press()
        wait_toast(page, LOAD_FAILED)
        assert not page.locator("#dialog").evaluate("d=>d.open")
    assert len(later.requests) == 5 and later_state(page)["state"] == "idle"
    no_reference_errors(seen)
    # 연결이 돌아온 뒤 다시 누르면 된다.
    later.release()
    page.locator("#submit-plan").click()
    page.wait_for_function(
        "()=>selected?.id&&!document.querySelector('#submit-plan').disabled", timeout=45000
    )
    assert len(seen["posts"]) == 1 and len(later.requests) == 6
    # 처음에 못 그린 팝업 전환도 나중 묶음이 실행된 때 그려진다.
    page.locator("#nav-explore").click()
    page.wait_for_function("()=>document.querySelectorAll('.explore-switch-button').length===2")
    page.wait_for_function(
        "()=>document.querySelector('#search-info').textContent.trim()||document.querySelector('#catalog .hint')"
    )
    assert len(seen["explore"]) == 1 and len(later.requests) == 6
    no_reference_errors(seen)


def test_failed_later_bundle_on_direct_addresses_shows_the_notice(session):
    _, plan_id = make_plan(session)
    for path in ("/?plan=" + plan_id, "/#explore-section"):
        page, later, seen = session.open(path, mode="abort")
        page.wait_for_function("()=>!document.querySelector('#status').hidden")
        assert LOAD_FAILED in page.locator("#status").inner_text()
        assert page.evaluate("()=>selected") is None
        no_reference_errors(seen)


def test_failed_later_bundle_leaves_the_remaining_search_for_the_next_visit(session):
    page, later, seen = session.open(wait="load")
    page.evaluate(DEMO)
    job = page.evaluate(
        """async()=>{const data=values();data.explicit_fields=[];
          data.origin={name:data.origin.name,lat:data.origin.lat,lon:data.origin.lon};
          const job=await api('/plan-jobs',data);PlanSearch.remember(job.id,null);return job.id;}"""
    )
    later.mode = "abort"
    page.reload(wait_until="domcontentloaded")
    page.wait_for_function(FIRST_SCREEN)
    wait_toast(page, LOAD_FAILED)
    assert page.evaluate("()=>PlanSearch.pending()") == job
    assert not page.locator("#submit-plan").is_disabled()
    no_reference_errors(seen)
    later.mode = "pass"
    page.reload(wait_until="domcontentloaded")
    page.wait_for_function(
        "()=>plans.length>0&&document.querySelector('#progress').textContent.includes('검색 복원 완료')",
        timeout=45000,
    )
    assert len(seen["posts"]) == 1


def test_later_bundle_that_runs_without_its_names_asks_for_a_reload(session):
    """받기는 됐는데 약속한 이름이 없으면(실행 오류·잘못된 파일) 다시 받아도 같다 — 다시 받지 않고 새로고침을 안내한다."""
    page, later, seen = session.open(mode="empty")
    page.wait_for_function("()=>DatemateLater.state==='broken'")
    for _ in range(2):
        page.evaluate("()=>{document.querySelector('#toast').textContent='';}")
        page.locator("#nav-explore").click()
        wait_toast(page, BROKEN)
    page.evaluate(DEMO)
    page.locator("#nav-plan").click()
    page.locator("#submit-plan").click()
    page.wait_for_function("()=>!document.querySelector('#submit-plan').disabled")
    assert later.requests == ["index-2.js"] and not seen["posts"]
    assert not seen["errors"] and not seen["console"], seen


def test_source_tags_load_in_order_through_the_same_loader(source_session):
    """묶음이 없거나 오래되면(개발 중 JS 를 고친 직후) 페이지는 원본 태그 그대로다 — 로더가 template 안의 원본 파일들을 순서대로 붙인다."""
    _, later_names = js_globals.page_scripts()
    page, later, seen = source_session.open(wait="load")
    assert later_state(page) == {"state": "ready", "loaded": True, "results": "function"}
    assert sorted(later.requests) == sorted(later_names)
    order = page.evaluate(
        "()=>[...document.head.querySelectorAll('script')].map(s=>new URL(s.src).pathname.split('/').pop())"
    )
    assert order[-len(later_names) :] == later_names
    assert "bundles" not in json.dumps(page.evaluate("()=>[...document.scripts].map(s=>s.src)"))
    page.evaluate(DEMO)
    page.locator("#submit-plan").click()
    page.wait_for_function(
        "()=>selected?.id&&!document.querySelector('#submit-plan').disabled", timeout=45000
    )
    assert len(seen["posts"]) == 1
    no_reference_errors(seen)


def test_source_tags_retry_only_the_file_that_failed(source_session):
    _, later_names = js_globals.page_scripts()
    # 처음 여는 동안 한 파일만 끊는다(Session.open 은 파일을 가려 끊지 못해 직접 연다).
    page = source_session.context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    later = Later(page, later_names, "abort")
    later.only = {"plan-detail.js"}
    page.goto(source_session.base + "/", wait_until="domcontentloaded")
    page.wait_for_function(FIRST_SCREEN)
    page.wait_for_function("()=>DatemateLater.state==='idle'")
    assert sorted(later.requests) == sorted(later_names)
    assert page.evaluate("()=>[typeof renderResults,typeof renderDetail]") == [
        "function",
        "undefined",
    ]
    page.locator("#nav-explore").click()
    wait_toast(page, LOAD_FAILED)
    assert (
        later.requests.count("plan-detail.js") == 2 and len(later.requests) == len(later_names) + 1
    )
    later.release()
    page.evaluate("()=>{document.querySelector('#toast').textContent='';}")
    page.locator("#search-button").click()
    wait_ready(page)
    # 실패한 파일만 다시 받는다(실행된 파일을 다시 붙이면 중복 선언 오류).
    assert (
        later.requests.count("plan-detail.js") == 3 and len(later.requests) == len(later_names) + 2
    )
    assert page.evaluate("()=>typeof renderDetail") == "function"
    assert not errors, errors
    page.close()
