"""CSS 정리 전후 계산값 비교 장치 (docs/css-consolidation-plan-2026-11-18.md 의 5-0 단계).

CSS 를 고치기 전(before)과 후(after)에 같은 장면을 같은 폭으로 열어, 모든 요소·가상 요소의 getComputedStyle 전 속성과
getBoundingClientRect, 전체 스크린샷, 상태 표본(Tab 포커스·hover)을 모으고 두 결과를 허용 오차 0 으로 비교한다.
캡처하는 동안 CDP CSS.startRuleUsageTracking 으로 규칙 사용 여부를 모아 '한 번도 맞지 않은 규칙' 목록을 낸다.

datemate 폴더에서 실행한다(Docker 에서는 DATEMATE_BROWSER_CHANNEL=chromium):
    python tests/css_snapshot.py capture --out runtime/css-snapshots/before
    python tests/css_snapshot.py capture --out runtime/css-snapshots/after
    python tests/css_snapshot.py compare runtime/css-snapshots/before runtime/css-snapshots/after
줄이는 옵션(설계 범위를 바꾸지 않고 빨리 볼 때만): --scenes home,results --widths 390,1440 --jobs 4 --no-states --no-screenshots.
runtime/ 은 Git 에 들어가지 않는다. 캡처 산출물은 커밋하지 않는다.

외부 API 는 부르지 않는다: 서버는 tests/conftest.py 가 키를 비운 상태로 뜨고, 브라우저는 우리 서버 밖 요청을 모두 끊으며,
사진·블로그·둘러보기·팝업·검색 진행·지역 확인 응답은 기존 화면 테스트의 가짜 응답을 그대로 가져다 쓴다.
같은 입력이면 같은 출력이 나오도록 시계를 고정하고(장면마다 2026-10-20 10:00 KST 에서 시작), 글꼴·네트워크·DOM 이 조용해질 때까지
기다리고, 애니메이션·전환을 끝내거나 멈춘다. hover 표본은 실제 마우스 대신 CDP CSS.forcePseudoState 로 요소와 조상에 :hover 를 건다.
지도 타일 칸(.leaflet-tile-pane) 안의 타일은 넣지 않는다(바깥 타일이라 끊기고, 남는 타일이 Leaflet 의 시간 경쟁으로 달라짐).

이 파일 이름은 test_*.py 가 아니라서 일반 pytest 전체 실행에 수집되지 않는다. capture 명령이 이 파일을 직접 지정해
pytest 로 돌리고(기존 audit_page 고정물·tests/conftest.py 의 격리 환경을 그대로 쓰기 위해), CSS_SNAPSHOT_OUT 이 없으면 건너뛴다.
"""
import argparse
import base64
import gzip
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

if os.getenv('PYTEST_VERSION'):
    # pytest 안에서만(tests/conftest.py 가 키·저장소를 격리한 뒤). 명령줄 부모 프로세스(capture·compare)는 app 을 불러오지 않는다.
    from test_functional_audit import audit_page, generate, open_origin_picker, wait_for_selected_detail  # noqa: F401
    from test_popup_ui import Api as PopupApi, open_popups
    from test_results_extras_ui import POSTS, mount_photo_routes, real_results

ROOT = Path(__file__).resolve().parents[1]
WIDTHS = (320, 390, 450, 560, 700, 740, 780, 900, 1050, 1200, 1440, 1600)
HEIGHT = 900
FIXED_TIME = '2026-10-20T10:00:00+09:00'
TAB_LIMIT = 60
HOVER_LIMIT = 40
QUIET_MS = 800
ADMIN_KEY = 'css-snapshot-only-' + uuid.uuid4().hex
# 1×1 PNG(지도 타일 대신, test_functional_audit 의 축제 사진 가짜 응답과 같은 그림). 지도 칸은 스크린샷에서 가린다.
BLANK_TILE = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
READY ="typeof statusData!=='undefined'&&!!statusData&&document.querySelector('.simple-plan-form')"


# ---------------------------------------------------------------- 브라우저 쪽 수집 코드

COLLECT = r"""(() => {
  const GEO = new Set(['width','height','inline-size','block-size','transform-origin','perspective-origin']);
  const snap = window.__cssSnap = {styles: [], index: new Map()};
  const intern = s => {let i = snap.index.get(s); if (i === undefined) {i = snap.styles.length; snap.styles.push(s); snap.index.set(s, i);} return i;};
  // 지도 이동 칸(.leaflet-map-pane) 안 요소의 자리(상자·transform)는 앱이 정한다: 지도 칸 크기가 바뀔 때마다
  // ResizeObserver→fitBounds 애니메이션이 다시 시작되고, 끊긴 시점에 따라 소수점 자리만큼 달라진다(같은 입력 두 번에서 확인).
  // 그래서 자리 값(상자, transform, SVG 의 d·x·y·cx·cy)만 빼고 나머지 계산값(크기·색·테두리 등)은 그대로 비교한다.
  // 지도 칸(.leaflet-container) 자체의 크기·자리는 비교한다.
  const inMap = el => !!el.closest('.leaflet-map-pane');
  const MAP_PLACE = new Set(['transform', 'd', 'x', 'y', 'cx', 'cy']);  // 자리를 나타내는 속성(SVG 경로 d 포함)
  const read = (cs, map) => {const keep = [], geo = [];
    for (let i = 0; i < cs.length; i++) {const n = cs[i]; if (map && MAP_PLACE.has(n)) continue;
      const v = cs.getPropertyValue(n); (GEO.has(n) ? geo : keep).push(n + ':' + v);}
    return [intern(keep.join('\n')), geo.join('\n')];};
  const label = el => el.localName + (el.id ? '#' + el.id : '') +
    (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).slice(0, 3).join('.') : '');
  const box = el => {const r = el.getBoundingClientRect(); return [r.x + scrollX, r.y + scrollY, r.width, r.height];};
  const pseudos = (el, cs) => {
    const out = [];
    for (const p of ['::before', '::after']) {const c = getComputedStyle(el, p).content; if (c !== 'none' && c !== 'normal') out.push(p);}
    if (cs.display.includes('list-item')) out.push('::marker');
    if (el.hasAttribute('placeholder')) out.push('::placeholder');
    if (el.localName === 'dialog' && el.matches(':modal')) out.push('::backdrop');
    if (el.localName === 'input' && el.type === 'file') out.push('::file-selector-button');
    return out;
  };
  const pathOf = el => {const p = []; while (el && el !== document.documentElement) {const parent = el.parentElement; if (!parent) return null;
    p.push(Array.prototype.indexOf.call(parent.children, el)); el = parent;} return p.reverse().join('.');};
  const record = (el, path) => {
    const map = inMap(el), cs = getComputedStyle(el), [s, g] = read(cs, map);
    const rows = [[path, label(el), s, g, ...(map ? [null, null, null, null] : box(el))]];
    for (const p of pseudos(el, cs)) {const [ps, pg] = read(getComputedStyle(el, p), map); rows.push([path + p, label(el) + p, ps, pg, null, null, null, null]);}
    return rows;
  };
  // 상태 표본: 그 요소와 조상 전부(:focus-within·:hover 는 조상에도 맞는다)와 그 가상 요소.
  const chain = el => {const rows = []; for (let e = el; e; e = e.parentElement) {const path = pathOf(e); if (path === null) break; rows.push(...record(e, path));} return rows;};
  snap.pathOf = pathOf; snap.chain = chain; snap.label = label; snap.box = el => inMap(el) ? null : box(el);
  snap.find = path => {let el = document.documentElement; if (path === '') return el;
    for (const i of path.split('.')) {el = el?.children[+i]; if (!el) return null;} return el;};
  const rows = [];
  // 지도 타일 칸(.leaflet-tile-pane) 안은 넣지 않는다: 바깥 타일은 끊기고, 지난 확대 단계 타일을 언제 치우는지가
  // Leaflet 의 시간 경쟁이라 같은 입력에서도 남았다 사라졌다 한다. 칸 자체와 지도 나머지(표시·버튼·출처)는 넣는다.
  const walk = (el, path) => {rows.push(...record(el, path)); if (el.classList.contains('leaflet-tile-pane')) return; let i = 0;
    for (const child of el.children) {walk(child, path === '' ? String(i) : path + '.' + i); i++;}};
  walk(document.documentElement, '');
  const d = document.documentElement;
  return {rows, meta: {url: location.pathname + location.search, scrollWidth: d.scrollWidth, scrollHeight: d.scrollHeight,
    innerWidth, innerHeight, title: document.title}};
})()"""

FREEZE = """(() => {
  void document.documentElement.getBoundingClientRect();
  for (const a of document.getAnimations()) {
    try {const t = a.effect && a.effect.getComputedTiming(); if (t && t.endTime === Infinity) {a.pause(); a.currentTime = 0;} else a.finish();}
    catch (e) {try {a.pause(); a.currentTime = 0;} catch (e2) {}}
  }
  void document.documentElement.getBoundingClientRect();
  return true;
})()"""

FRAMES = "new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => r(true))))"

SCROLL_THROUGH = """(async () => {
  const frames = () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const step = Math.max(200, Math.floor(innerHeight * 0.8));
  for (let y = 0; y < document.documentElement.scrollHeight; y += step) {scrollTo({top: y, left: 0, behavior: 'instant'}); await frames();}
  scrollTo({top: document.documentElement.scrollHeight, left: 0, behavior: 'instant'}); await frames();
  return document.documentElement.scrollHeight;
})()"""

TOP = """(async () => {scrollTo({top: 0, left: 0, behavior: 'instant'});
  for (let i = 0, last = -1; i < 60 && scrollY !== last; i++) {last = scrollY; await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));}
  return scrollY;})()"""

# DOM 이 QUIET_MS 동안 바뀌지 않을 때까지(최대 15초). 지도 타일 정리(Leaflet 의 250ms 뒤 prune)·늦은 렌더를 기다린다.
DOM_QUIET = """(() => new Promise(resolve => {
  let timer; const end = setTimeout(() => {observer.disconnect(); resolve(false);}, 15000);
  const observer = new MutationObserver(() => {clearTimeout(timer); timer = setTimeout(done, %d);});
  const done = () => {observer.disconnect(); clearTimeout(end); resolve(true);};
  observer.observe(document, {subtree: true, childList: true, attributes: true, characterData: true});
  timer = setTimeout(done, %d);
}))()""" % (QUIET_MS, QUIET_MS)

# Tab 한 번 뒤: 두 프레임 동안 DOM 이 바뀌지 않으면 바로 끝, 바뀌면(예: Leaflet 표시에 포커스가 가면 지도가 그쪽으로
# 움직이는 애니메이션) 300ms 조용해질 때까지 기다린다(최대 5초). 매번 QUIET_MS 를 기다리면 너무 느리다.
AFTER_FOCUS = """(() => new Promise(resolve => {
  let changed = false, timer;
  const observer = new MutationObserver(() => {changed = true; if (timer !== undefined) {clearTimeout(timer); timer = setTimeout(done, 300);}});
  const done = () => {observer.disconnect(); clearTimeout(end); resolve(changed);};
  const end = setTimeout(done, 5000);
  observer.observe(document, {subtree: true, childList: true, attributes: true, characterData: true});
  requestAnimationFrame(() => requestAnimationFrame(() => {if (!changed) done(); else timer = setTimeout(done, 300);}));
}))()"""

IMAGES_DONE ="[...document.images].every(i => i.complete)"

HOVER_TARGETS = """(limit) => {
  const snap = window.__cssSnap, seen = new Set(), out = [];
  const sel = 'a[href],button,summary,input,select,textarea,label,[role=button],[role=tab],[tabindex]:not([tabindex="-1"])';
  for (const el of document.querySelectorAll(sel)) {
    if (!el.getClientRects().length || getComputedStyle(el).visibility !== 'visible') continue;
    const path = snap.pathOf(el); if (path === null) continue;
    const key = el.localName + '|' + (typeof el.className === 'string' ? el.className : '') + '|' + getComputedStyle(el).cssText.length;
    if (seen.has(key)) continue; seen.add(key); out.push(path);
    if (out.length >= limit) break;
  }
  return out;
}"""

SAMPLE = """(async ([kind, target, collect]) => {
  const frames = () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  for (let i = 0, last = -1; i < 60 && scrollY !== last; i++) {last = scrollY; await frames();}
  await frames();
  if (!collect) return true;
  const snap = window.__cssSnap, el = kind === 'hover' ? snap.find(target) : document.activeElement;
  if (!el || el === document.body || el === document.documentElement) return {path: null};
  // 포커스·hover 로 시작된 전환을 읽기 직전에 다시 끝낸다(스타일 재계산이 늦게 일어나 전환이 이 시점에 생기는 경우가 있었다).
  const finish = () => {for (let e = el; e; e = e.parentElement) {getComputedStyle(e).color; getComputedStyle(e, '::before').color; getComputedStyle(e, '::after').color;}
    void document.documentElement.getBoundingClientRect();
    for (const a of document.getAnimations()) {try {const t = a.effect && a.effect.getComputedTiming();
      if (t && t.endTime === Infinity) {a.pause(); a.currentTime = 0;} else a.finish();} catch (e) {try {a.pause(); a.currentTime = 0;} catch (e2) {}}}};
  finish(); await frames(); finish();
  return {path: snap.pathOf(el), label: snap.label(el), box: snap.box(el), rows: snap.chain(el)};
})"""


class ForcedHover:
    """CDP CSS.forcePseudoState 로 한 요소와 그 조상 모두(실제 마우스가 올라갔을 때 :hover 가 맞는 범위)에만 :hover 를 둔다.
    표본마다 바뀌는 노드만 걸고 풀어 CDP 호출을 줄인다. 끝나면 clear()."""

    def __init__(self, cdp):
        self.cdp, self.ids, self.forced = cdp, {}, set()
        cdp.send('DOM.getDocument', {'depth': 0})

    def node(self, path):
        if path not in self.ids:
            result = self.cdp.send('Runtime.evaluate', {'expression': f'window.__cssSnap.find({json.dumps(path)})'})['result']
            self.ids[path] = (self.cdp.send('DOM.requestNode', {'objectId': result['objectId']})['nodeId']
                              if 'objectId' in result else None)
        return self.ids[path]

    def set(self, path):
        parts = path.split('.') if path else []
        chain = {self.node('.'.join(parts[:i])) for i in range(len(parts) + 1)} - {None}
        for node in self.forced - chain:
            self.cdp.send('CSS.forcePseudoState', {'nodeId': node, 'forcedPseudoClasses': []})
        for node in chain - self.forced:
            self.cdp.send('CSS.forcePseudoState', {'nodeId': node, 'forcedPseudoClasses': ['hover']})
        self.forced = chain

    def clear(self):
        for node in self.forced:
            self.cdp.send('CSS.forcePseudoState', {'nodeId': node, 'forcedPseudoClasses': []})
        self.forced = set()


# ---------------------------------------------------------------- 안정화

class Network:
    """마지막 요청 시작·끝 뒤로 QUIET_MS 동안 아무 일도 없으면 조용하다고 본다(응답을 붙잡아 둔 요청은 그 뒤로 사건이 없다)."""

    def __init__(self, page):
        self.last = time.monotonic()
        self.count = 0
        for name in ('request', 'requestfinished', 'requestfailed'):
            page.on(name, self.touch)

    def touch(self, *_):
        self.last = time.monotonic()
        self.count += 1

    def quiet(self, page, limit=20):
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            page.wait_for_timeout(100)
            if time.monotonic() - self.last >= QUIET_MS / 1000:
                return True
        return False


def settle(page, net, scroll=True, open_details=False):
    """글꼴 → 화면 끝까지 내려 '화면 근처에서 받기' 부품을 모두 불러옴(늦게 그려진 details 도 다시 엶) → 맨 위 → 이미지 → 애니메이션 정지."""
    page.evaluate('document.fonts.ready.then(() => true)')
    net.quiet(page)
    if scroll:
        for _ in range(8):
            before = net.count
            height = page.evaluate(SCROLL_THROUGH)
            net.quiet(page)
            opened = page.evaluate(OPEN_DETAILS) if open_details else 0
            if opened:
                net.quiet(page)
            if not opened and net.count == before and page.evaluate('document.documentElement.scrollHeight') == height:
                break
    page.evaluate(TOP)
    net.quiet(page)
    page.evaluate(DOM_QUIET)
    for _ in range(50):
        if page.evaluate(IMAGES_DONE):
            break
        page.wait_for_timeout(100)
    page.evaluate('document.fonts.ready.then(() => true)')
    page.evaluate(FREEZE)
    page.evaluate(FRAMES)
    page.evaluate(FREEZE)


# ---------------------------------------------------------------- 장면

OPEN_DETAILS = "[...document.querySelectorAll('details:not([open])')].map(d => {d.open = true; return 1;}).length"


def open_all_details(page):
    page.evaluate(OPEN_DETAILS)


def results(page, base):
    """결과 화면: 실제 장소 코스처럼 다시 그려 사진·블로그 패널까지 나오게 하고(test_results_extras_ui 와 같은 가짜 응답), details 를 모두 연다."""
    mount_photo_routes(page, base, count=2)
    page.route('**/api/places/*/blogs?*', lambda route: route.fulfill(json={
        'posts': POSTS, 'search_url': 'https://search.naver.com/search.naver?query=x', 'message': ''}))
    real_results(page, base)
    wait_for_selected_detail(page)
    open_all_details(page)


def results_course2(page, base):
    results(page, base)
    page.locator('.plan-option-tabs button').nth(1).click()
    page.wait_for_function('document.querySelector(".plan-option-tabs button:nth-child(2)").getAttribute("aria-pressed")==="true"')
    wait_for_selected_detail(page)
    open_all_details(page)


SEARCH_JOB = 'css-snapshot-job'
SEARCH_STATE = {
    'status': 'running', 'stage': '코스 구성', 'message': '찾은 장소로 코스를 짜고 있어요.',
    'preview_options': [
        {'purpose': '가까운 동선', 'places': [{'id': 'p1', 'name': '성수 카페 하루'}, {'id': 'p2', 'name': '서울숲 산책길'}, {'id': 'p3', 'name': '성수 식당 이틀'}]},
        {'purpose': '실내 위주', 'places': [{'id': 'p4', 'name': '성수 전시관'}, {'id': 'p5', 'name': '성수 공방'}]},
        {'purpose': None, 'places': [{'id': 'p6', 'name': '뚝섬 한강공원'}, {'id': 'p7', 'name': '성수 서점'}]}]}


def searching(page, base):
    """검색 중: 작업 시작은 받아 주고 첫 진행 상태(확정 전 후보 포함)를 준 뒤, 긴 폴링은 응답하지 않고 붙잡아 둔다."""
    page.route('**/api/plan-jobs', lambda route: route.fulfill(status=202, json={'id': SEARCH_JOB}))
    held = []

    def poll(route):
        if 'wait=' in route.request.url:
            held.append(route)
            return
        route.fulfill(json=SEARCH_STATE)
    page.route(f'**/api/plan-jobs/{SEARCH_JOB}*', poll)
    page.evaluate("form.elements.mode.value='demo';form.elements.mode.dispatchEvent(new Event('change',{bubbles:true}));"
                  "form.elements.visit_date.value='2026-10-24';form.elements.max_leg.value=180;form.elements.budget.value=1000000;")
    page.locator('#submit-plan').click()
    page.wait_for_function("document.querySelector('#results .plan-preview')&&document.querySelector('#progress .search-progress-copy strong')")
    for _ in range(100):
        if held:
            break
        page.wait_for_timeout(50)


def conditions(page, base):
    page.locator('.condition-toggle').click()
    page.locator('#condition-details').wait_for(state='visible')


def explore(page, base):
    mount_photo_routes(page, base)
    page.get_by_role('button', name='장소 둘러보기', exact=True).click()
    page.locator('#catalog .place-card').first.wait_for()
    page.wait_for_function("[...document.querySelectorAll('#catalog .place-photo img')].some(i=>!i.hidden&&i.complete&&i.naturalWidth>0)")


def popups(page, base):
    PopupApi(page)
    open_popups(page)
    page.wait_for_selector('.popup-post')


def location_dialog(page, base):
    page.route('**/api/locations/region', lambda route: route.fulfill(json={
        'status': 'ok', 'region': '부산', 'label': '부산 해운대구 우동', 'message': ''}))
    open_origin_picker(page)
    page.locator('#dialog').get_by_role('button', name='지도 중심을 선택', exact=True).click()
    page.wait_for_function("!document.querySelector('#dialog .location-footer .primary').disabled")


def photo_viewer(page, base):
    explore(page, base)
    page.locator('#catalog .place-card').first.get_by_role('button', name='사진 1 사진 크게 보기', exact=True).click()
    page.wait_for_function("document.querySelector('#photo-viewer').open")
    page.wait_for_function("(()=>{const i=document.querySelector('#photo-viewer img');return !i.hidden&&i.complete&&i.naturalWidth===400})()")


def shared(page, base):
    generate(page)
    url = page.evaluate("api('/plans/'+encodeURIComponent(selected.id)+'/shares',{}).then(r=>r.url)")
    page.goto(base + url, wait_until='networkidle')
    page.wait_for_function("!document.getElementById('shared-form').hidden")


def feedback(page, base):
    page.goto(base + '/feedback', wait_until='networkidle')
    page.locator('#feedback-message').wait_for()


def feedback_admin(page, base):
    from app import store
    with store.connect() as db:
        db.execute('DELETE FROM feedback_entries')
        for i, (message, screen, handled) in enumerate((('결과 화면 사진이 작게 보여요. 휴대폰에서 확인했어요.', 'results', 0),
                                                        ('장소 둘러보기에서 지역을 바꾸면 목록이 늦게 바뀌어요.', 'explore', 1))):
            db.execute('INSERT INTO feedback_entries(id,created,message,screen,contact,viewport_width,browser,handled) '
                       'VALUES(?,?,?,?,?,?,?,?)', (f'css-snapshot-{i}', 1792800000 - i * 3600, message, screen,
                                                   'me@example.com' if i == 0 else '', 390, 'Chrome', handled))
    page.goto(base + '/feedback/admin', wait_until='networkidle')
    page.locator('#admin-key').fill(ADMIN_KEY)
    page.locator('#admin-open').click()
    page.wait_for_selector('.admin-entry.handled')


# 이름 → (준비 함수, 열 때 매체 에뮬레이션, 준비 뒤 매체 에뮬레이션, 상태 표본 여부)
SCENES = {
    'home': (None, {}, None, True),
    'conditions': (conditions, {}, None, True),
    'searching': (searching, {}, None, True),
    'results': (results, {}, None, True),
    'results-course2': (results_course2, {}, None, True),
    'results-print': (results, {}, {'media': 'print'}, False),
    'results-reduced-motion': (results, {'reduced_motion': 'reduce'}, None, True),
    'results-forced-colors': (results, {'forced_colors': 'active'}, None, True),
    'explore': (explore, {}, None, True),
    'popups': (popups, {}, None, True),
    'location-dialog': (location_dialog, {}, None, True),
    'photo-viewer': (photo_viewer, {}, None, True),
    'shared': (shared, {}, None, True),
    'feedback': (feedback, {}, None, True),
    'feedback-admin': (feedback_admin, {}, None, True),
}
SCREEN = {'media': 'screen', 'color_scheme': 'light', 'reduced_motion': 'no-preference', 'forced_colors': 'none'}


# ---------------------------------------------------------------- 규칙 사용률(CDP)

GROUPING_AT_RULES = {'media', 'supports', 'layer', 'container', 'scope', 'document', 'starting-style'}


def style_rules(text):
    """CSS 원문에서 스타일 규칙의 (시작, 여는 괄호, 끝) 위치를 찾는다(@media 등 묶음 안까지, @keyframes·@font-face 안은 제외).
    CDP 의 규칙 사용 정보는 실제로 맞은 규칙만 주므로, 전체 규칙 목록은 원문에서 얻는다. 위치는 파이썬 문자 단위."""
    rules, stack = [], []  # stack: 'group' | ('style', start, brace) | 'skip'
    i, n, start = 0, len(text), None
    while i < n:
        c = text[i]
        if c == '/' and text.startswith('/*', i):
            end = text.find('*/', i + 2)
            i = n if end < 0 else end + 2
            continue
        if c in '"\'':
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == '\\' else 1
            if start is None:
                start = i
            i = j + 1
            continue
        top = stack[-1] if stack else 'group'
        if c == '{':
            if top == 'group':
                prelude = text[start:i].strip() if start is not None else ''
                if prelude.startswith('@'):
                    name = prelude[1:].split(None, 1)[0].split('(', 1)[0].lower() if len(prelude) > 1 else ''
                    stack.append('group' if name in GROUPING_AT_RULES else 'skip')
                else:
                    stack.append(('style', start if start is not None else i, i))
            else:
                stack.append('skip')
            start = None
        elif c == '}':
            if stack:
                item = stack.pop()
                if isinstance(item, tuple):
                    rules.append((item[1], item[2], i + 1))
            start = None
        elif c == ';' and top == 'group':
            start = None
        elif start is None and not c.isspace() and top == 'group':
            start = i
        i += 1
    return rules


def utf16_index(text):
    """파이썬 문자 위치 → UTF-16 위치(CDP 위치 단위). BMP 밖 글자가 없으면 그대로."""
    if all(ord(ch) < 0x10000 for ch in text):
        return lambda i: i
    offsets, total = [], 0
    for ch in text:
        offsets.append(total)
        total += 2 if ord(ch) >= 0x10000 else 1
    offsets.append(total)
    return lambda i: offsets[i]


class RuleUsage:
    """CDP CSS.startRuleUsageTracking → stopRuleUsageTracking 은 그동안 맞은 규칙의 위치만 준다. 시트 원문과 함께 모은다."""

    def __init__(self):
        self.sheets = {}  # 이름 → {'text': 원문, 'used': {(start, end)}}

    def tracker(self, page):
        cdp = page.context.new_cdp_session(page)
        names = {}

        def added(event):
            header = event['header']
            url = header.get('sourceURL') or ''
            if not url and not header.get('isInline'):
                return  # 주소 없는 시트(브라우저가 details 등에 쓰는 내부 시트). 우리 CSS 가 아니다.
            path = url.split('://', 1)[-1].split('/', 1)[-1].split('?', 1)[0].split('#', 1)[0]
            if header.get('isInline') or header.get('origin') != 'regular':
                path = f"inline:{path or '?'}:{header.get('startLine', 0)}:{header.get('origin')}"
            names[header['styleSheetId']] = path
        cdp.on('CSS.styleSheetAdded', added)
        cdp.send('DOM.enable')
        cdp.send('CSS.enable')
        return cdp, names

    def start(self, cdp):
        cdp.send('CSS.startRuleUsageTracking')

    def stop(self, cdp, names):
        usage = cdp.send('CSS.stopRuleUsageTracking')['ruleUsage']
        for sid, name in names.items():
            if name not in self.sheets:
                try:
                    text = cdp.send('CSS.getStyleSheetText', {'styleSheetId': sid})['text']
                except Exception:
                    continue  # 문서에서 빠진 시트
                self.sheets[name] = {'text': text, 'used': set()}
        for rule in usage:
            name = names.get(rule['styleSheetId'])
            if name in self.sheets and rule.get('used', True):
                self.sheets[name]['used'].add((int(rule['startOffset']), int(rule['endOffset'])))

    def dump(self, path):
        data = {name: {'text': s['text'], 'used': sorted(s['used'])} for name, s in self.sheets.items()}
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')


def merge_usage(files):
    sheets = {}
    for file in files:
        for name, data in json.loads(file.read_text(encoding='utf-8')).items():
            sheet = sheets.setdefault(name, {'text': data['text'], 'used': set()})
            sheet['used'].update(tuple(pair) for pair in data['used'])
    return sheets


def usage_report(sheets):
    """규칙 사용률 표와 한 번도 맞지 않은 규칙 목록(파일:줄 선택자). 규칙은 원문에서 찾고, CDP 가 준 맞은 범위(UTF-16 위치)가
    그 규칙의 여는 괄호를 품으면 맞은 것으로 본다."""
    table, unused = [], []
    total_used = total = 0
    for name in sorted(sheets):
        text, used_ranges = sheets[name]['text'], sorted(sheets[name]['used'])
        to16 = utf16_index(text)
        rules = style_rules(text)
        used = 0
        for start, brace, end in rules:
            b = to16(brace)
            if any(a <= b < e for a, e in used_ranges):
                used += 1
                continue
            selector = ' '.join(text[start:brace].split())[:200]
            unused.append(f'{name}:{text.count(chr(10), 0, start) + 1}  {selector}')
        total_used += used
        total += len(rules)
        table.append(f'{name}: {used}/{len(rules)} ({used / len(rules) * 100 if rules else 0:.1f}%)')
    table.append(f'전체: {total_used}/{total} ({total_used / total * 100 if total else 0:.1f}%), 한 번도 맞지 않은 규칙 {total - total_used}개')
    return table, unused


# ---------------------------------------------------------------- 캡처

def capture_one(page, base, scene, width, out, usage, options):
    prepare, initial_media, later_media, with_states = SCENES[scene]
    # 장면·폭마다 새 브라우저 문맥(쿠키·저장소·서버 세션이 비어 있음). 옵션과 막기는 audit_page 의 탭과 같게 둔다:
    # bypass_csp(Playwright 의 wait_for_function 이 eval 을 쓴다), 우리 서버 밖 요청은 끊음.
    context = page.context.browser.new_context(viewport={'width': width, 'height': HEIGHT}, bypass_csp=True)

    def guard(route):
        url = route.request.url
        if url.startswith(base):
            return route.continue_()
        # 지도 배경 타일(…/{z}/{x}/{y}.png)은 끊지 않고 빈 그림으로 답한다. 끊으면 tileerror 가 오는지·언제 오는지에 따라
        # 지도 아래 안내 글(maps.js mapCaption)이 바뀌어 같은 입력에서도 화면이 달라졌다. 바깥으로는 여전히 나가지 않는다.
        if route.request.resource_type == 'image' and re.search(r'/\d+/\d+/\d+\.png(\?|$)', url):
            return route.fulfill(status=200, content_type='image/png', body=BLANK_TILE)
        return route.abort()
    context.route('**/*', guard)
    # 시계 고정: 날짜는 늘 FIXED_TIME 에서 시작해 실제 속도로 흐른다. Date 를 한 순간에 멈추면(set_fixed_time) Leaflet 타일의
    # 서서히 나타나기(+new Date 로 계산)가 끝나지 않아 지난 확대 단계 타일이 남았다 사라졌다 해서, 멈추지는 않는다.
    context.clock.install(time=FIXED_TIME)
    view = context.new_page()
    errors = []
    view.on('pageerror', lambda error: errors.append(str(error)))
    net = Network(view)
    phases, mark = {}, [time.monotonic()]

    def phase(label):
        now = time.monotonic()
        phases[label] = round(now - mark[0], 1)
        mark[0] = now
    try:
        view.emulate_media(**{**SCREEN, **initial_media})
        cdp, names = usage.tracker(view)
        view.goto(base, wait_until='networkidle')
        view.wait_for_function(READY)
        if prepare:
            prepare(view, base)
        # 준비 중 누른 자리에 마우스가 남으면, 스크롤 뒤 그 아래 온 요소가 때에 따라 :hover 가 된다. 화면 밖으로 뺀다.
        view.mouse.move(-50, -50)
        phase('준비')
        settle(view, net, open_details=prepare in (results, results_course2))
        if later_media:
            view.emulate_media(**{**SCREEN, **initial_media, **later_media})
            settle(view, net, scroll=False)
        view.mouse.move(-40, -40)
        view.evaluate(FRAMES)
        phase('안정화')
        usage.start(cdp)
        data = view.evaluate(COLLECT)
        data['meta'].update(scene=scene, width=width, height=HEIGHT, hovered=view.evaluate("[...document.querySelectorAll(':hover')].map(e => window.__cssSnap.label(e))"))
        name = f'{scene}@{width}'
        phase('수집')
        if options.screenshots:
            # 지도 칸(.leaflet-container)은 단색으로 가린다: 안의 경로·표시 자리가 위 이유로 소수점만큼 흔들려 픽셀이 달라질 수 있다.
            # 지도 칸의 자리·크기와 안쪽 요소의 계산값은 위 수집 자료로 비교된다.
            # 연달아 찍은 두 장이 같아질 때까지 찍는다(최대 5장, Playwright toHaveScreenshot 과 같은 방식).
            # 모서리 몇 픽셀이 찍을 때마다 달라지는 경우가 있었다(위치 대화상자, 2026-11-19).
            # 모달 대화상자가 열린 장면은 보이는 화면만 찍는다: 전체 페이지로 찍으면 찍는 동안 화면 높이가 바뀌어
            # 가운데 놓인 대화상자의 둥근 모서리 몇 픽셀이 찍을 때마다 달라졌다(위치 대화상자·사진 뷰어, 2026-11-19).
            full = not view.evaluate("!!document.querySelector('dialog:modal')")
            data['meta']['full_page_screenshot'] = full
            shots = []
            for _ in range(5):
                shots.append(view.screenshot(full_page=full, animations='disabled', caret='hide',
                                             mask=[view.locator('.leaflet-container')], mask_color='#ff00ff'))
                if len(shots) >= 2 and shots[-1] == shots[-2]:
                    break
            data['meta']['screenshot_tries'] = len(shots)
            (out / f'{name}.png').write_bytes(shots[-1])
        phase('스크린샷')
        states = {'tab': [], 'hover': []}
        if with_states and options.states:
            view.evaluate(TOP)
            view.evaluate('document.activeElement&&document.activeElement.blur&&document.activeElement.blur()')
            seen = set()
            for _ in range(options.tab_limit):
                view.keyboard.press('Tab')
                view.evaluate(AFTER_FOCUS)
                view.evaluate(SAMPLE, ['tab', None, False])
                view.evaluate(FREEZE)
                sample = view.evaluate(SAMPLE, ['tab', None, True])
                if sample['path'] is None or sample['path'] in seen:
                    break
                seen.add(sample['path'])
                states['tab'].append(sample)
            view.evaluate('document.activeElement&&document.activeElement.blur&&document.activeElement.blur()')
            view.evaluate(TOP)
            view.evaluate(FREEZE)
            # hover 는 실제 마우스 대신 CDP 로 건다. 실제 마우스로 하면 스크롤 직후 브라우저가 hover 갱신을 미뤄
            # 같은 입력에서도 결과가 달라졌다(2026-11-18 확인).
            hover = ForcedHover(cdp)
            for path in view.evaluate(HOVER_TARGETS, options.hover_limit):
                hover.set(path)
                view.evaluate(SAMPLE, ['hover', path, False])
                view.evaluate(FREEZE)
                sample = view.evaluate(SAMPLE, ['hover', path, True])
                sample['target'] = path
                states['hover'].append(sample)
            hover.clear()
        phase('상태 표본')
        data['states'] = states
        data['styles'] = view.evaluate('window.__cssSnap.styles')
        usage.stop(cdp, names)
        data['meta']['errors'] = errors
        with gzip.open(out / f'{name}.json.gz', 'wt', encoding='utf-8', compresslevel=6) as file:
            json.dump(data, file, ensure_ascii=False)
        phase('저장')
        return len(data['rows']), errors, phases
    finally:
        context.close()


def test_css_snapshot_capture(audit_page, monkeypatch):
    out = os.getenv('CSS_SNAPSHOT_OUT')
    if not out:
        pytest.skip('css_snapshot.py capture 명령으로만 실행한다(CSS_SNAPSHOT_OUT).')
    options = argparse.Namespace(**json.loads(os.environ['CSS_SNAPSHOT_OPTIONS']))
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('FEEDBACK_ADMIN_KEY', ADMIN_KEY)
    page, base, errors = audit_page
    usage = RuleUsage()
    for scene in options.scenes:
        for width in options.widths:
            started = time.monotonic()
            count, page_errors, phases = capture_one(page, base, scene, width, out, usage, options)
            note = f' 화면 오류 {len(page_errors)}건: {page_errors[:2]}' if page_errors else ''
            detail = ' '.join(f'{k} {v}' for k, v in phases.items())
            print(f'[css_snapshot {options.job}] {scene}@{width}: 요소·가상 요소 {count}개, {time.monotonic() - started:.1f}초 ({detail}){note}',
                  flush=True)
    usage.dump(out / f'usage-{options.job}.json')


# ---------------------------------------------------------------- 명령

def run_capture(args):
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    for old in list(out.glob('*.json.gz')) + list(out.glob('*.png')) + list(out.glob('usage-*.json')):
        old.unlink()
    scenes = args.scenes.split(',') if args.scenes else list(SCENES)
    unknown = [s for s in scenes if s not in SCENES]
    if unknown:
        sys.exit(f'모르는 장면: {unknown}. 가능한 장면: {", ".join(SCENES)}')
    widths = [int(w) for w in args.widths.split(',')] if args.widths else list(WIDTHS)
    jobs = max(1, min(args.jobs, len(scenes)))
    # 무거운 장면(결과 화면 상태 표본)부터 가장 가벼운 작업에 나눠 준다. 무게는 2026-11-18 Docker 측정 비(결과 약 35초, 홈 14초, 나머지 7초).
    groups, loads = [[] for _ in range(jobs)], [0.0] * jobs
    weight = {'results': 5, 'results-course2': 5, 'results-reduced-motion': 5, 'results-forced-colors': 5,
              'results-print': 1.5, 'home': 2, 'conditions': 2}
    for scene in sorted(scenes, key=lambda s: -weight.get(s, 1)):
        i = loads.index(min(loads))
        groups[i].append(scene)
        loads[i] += weight.get(scene, 1)
    started = time.monotonic()
    processes = []
    for job, group in enumerate(groups):
        options = dict(scenes=group, widths=widths, job=job, states=not args.no_states, screenshots=not args.no_screenshots,
                       tab_limit=args.tab_limit, hover_limit=args.hover_limit)
        env = dict(os.environ, CSS_SNAPSHOT_OUT=str(out), CSS_SNAPSHOT_OPTIONS=json.dumps(options))
        command = [sys.executable, '-m', 'pytest', str(Path(__file__).resolve()) + '::test_css_snapshot_capture',
                   '-q', '-s', '-p', 'no:cacheprovider']
        processes.append(subprocess.Popen(command, cwd=ROOT, env=env))
    failed = [job for job, process in enumerate(processes) if process.wait() != 0]
    if failed:
        sys.exit(f'캡처 실패(작업 {failed}). 위 pytest 출력을 보세요.')
    sheets = merge_usage(sorted(out.glob('usage-*.json')))
    table, unused = usage_report(sheets)
    (out / 'rule-usage.txt').write_text('\n'.join(['규칙 사용률 (CDP CSS.startRuleUsageTracking, 캡처 중 한 번이라도 맞은 규칙)', *table, '',
                                                   f'한 번도 맞지 않은 규칙 {len(unused)}개', *unused]) + '\n', encoding='utf-8')
    (out / 'manifest.json').write_text(json.dumps(dict(scenes=scenes, widths=widths, height=HEIGHT, fixed_time=FIXED_TIME,
                                                       states=not args.no_states, screenshots=not args.no_screenshots,
                                                       tab_limit=args.tab_limit, hover_limit=args.hover_limit), ensure_ascii=False, indent=1),
                                       encoding='utf-8')
    print(f'캡처 {len(scenes)}장면 × {len(widths)}폭 = {len(scenes) * len(widths)}개, {time.monotonic() - started:.0f}초 → {out}')
    print('규칙 사용률')
    for line in table:
        print('  ' + line)
    print(f'한 번도 맞지 않은 규칙 {len(unused)}개 (전체 목록: {out / "rule-usage.txt"})')
    for line in unused[:args.show_unused]:
        print('  ' + line)
    if len(unused) > args.show_unused:
        print(f'  … {len(unused) - args.show_unused}개 더')


def load(path):
    with gzip.open(path, 'rt', encoding='utf-8') as file:
        return json.load(file)


def props(text):
    return dict(line.split(':', 1) for line in text.split('\n') if line)


def diff_rows(rows_a, styles_a, rows_b, styles_b, where, lines):
    """같은 경로의 요소끼리 계산값·위치·크기를 비교한다. 다르면 lines 에 사람이 읽을 줄을 더하고 다른 요소 수를 돌려준다."""
    a = {row[0]: row for row in rows_a}
    b = {row[0]: row for row in rows_b}
    changed = 0
    for path in a.keys() - b.keys():
        changed += 1
        lines.append(f'{where} {a[path][1]} [{path}]: 앞 캡처에만 있음')
    for path in b.keys() - a.keys():
        changed += 1
        lines.append(f'{where} {b[path][1]} [{path}]: 뒤 캡처에만 있음')
    for path in a.keys() & b.keys():
        ra, rb = a[path], b[path]
        notes = []
        if styles_a[ra[2]] != styles_b[rb[2]]:
            pa, pb = props(styles_a[ra[2]]), props(styles_b[rb[2]])
            notes += [f'{k}: {pa.get(k)} → {pb.get(k)}' for k in sorted(pa.keys() | pb.keys()) if pa.get(k) != pb.get(k)]
        if ra[3] != rb[3]:
            ga, gb = props(ra[3]), props(rb[3])
            notes += [f'{k}: {ga.get(k)} → {gb.get(k)}' for k in sorted(ga.keys() | gb.keys()) if ga.get(k) != gb.get(k)]
        if ra[4:8] != rb[4:8]:
            notes.append(f'상자 {ra[4:8]} → {rb[4:8]}')
        if notes:
            changed += 1
            lines.append(f'{where} {ra[1]} [{path}]: ' + '; '.join(notes[:8]) + (f' …(+{len(notes) - 8})' if len(notes) > 8 else ''))
    return changed


def compare_capture(a, b):
    lines, counts = [], {}
    counts['계산값·상자'] = diff_rows(a['rows'], a['styles'], b['rows'], b['styles'], '', lines)
    for key in ('scrollWidth', 'scrollHeight'):
        if a['meta'].get(key) != b['meta'].get(key):
            counts[key] = 1
            lines.append(f'문서 {key}: {a["meta"].get(key)} → {b["meta"].get(key)}')
    for kind in ('tab', 'hover'):
        sa, sb = a['states'][kind], b['states'][kind]
        n = 0
        if len(sa) != len(sb):
            n += 1
            lines.append(f'{kind} 표본 수 {len(sa)} → {len(sb)}')
        for i, (x, y) in enumerate(zip(sa, sb)):
            if x.get('path') != y.get('path') or x.get('target') != y.get('target'):
                n += 1
                lines.append(f'{kind} {i}번 표본 대상: {x.get("label") or x.get("target")} → {y.get("label") or y.get("target")}')
                continue
            if x.get('path') is None:
                continue
            here = f'{kind} {i}번({x["label"]})'
            if x['box'] != y['box']:
                n += 1
                lines.append(f'{here} 상자 {x["box"]} → {y["box"]}')
            n += diff_rows(x['rows'], a['styles'], y['rows'], b['styles'], here, lines)
        counts[f'{kind} 표본'] = n
    if a['meta'].get('errors') != b['meta'].get('errors'):
        counts['화면 오류'] = 1
        lines.append(f'화면 오류 {a["meta"].get("errors")} → {b["meta"].get("errors")}')
    return counts, lines


def compare_png(path_a, path_b):
    if not path_a.exists() and not path_b.exists():
        return None
    if not path_a.exists() or not path_b.exists():
        return '한쪽에만 스크린샷이 있음'
    if path_a.read_bytes() == path_b.read_bytes():
        return None
    from PIL import Image, ImageChops
    with Image.open(path_a) as ia, Image.open(path_b) as ib:
        if ia.size != ib.size:
            return f'스크린샷 크기 {ia.size} → {ib.size}'
        diff = ImageChops.difference(ia.convert('RGBA'), ib.convert('RGBA'))
        box = diff.getbbox(alpha_only=False)  # 기본값은 알파 채널만 본다(색만 달라도 None)
        if box is None:
            return None
        bands = diff.split()
        mask = bands[0]
        for band in bands[1:]:
            mask = ImageChops.lighter(mask, band)
        pixels = mask.point(lambda v: 255 if v else 0).histogram()[255]
        return f'스크린샷 픽셀 {pixels}개 다름(영역 {box})'


def run_compare(args):
    a, b = Path(args.a), Path(args.b)
    names_a = {p.name[:-len('.json.gz')] for p in a.glob('*.json.gz')}
    names_b = {p.name[:-len('.json.gz')] for p in b.glob('*.json.gz')}
    if not names_a and not names_b:
        sys.exit('비교할 캡처가 없습니다.')
    differing = 0
    for name in sorted(names_a | names_b, key=lambda n: (n.split('@')[0], int(n.split('@')[1]))):
        if name not in names_a or name not in names_b:
            differing += 1
            print(f'{name}: {"뒤" if name not in names_a else "앞"} 캡처에만 있음')
            continue
        counts, lines = compare_capture(load(a / f'{name}.json.gz'), load(b / f'{name}.json.gz'))
        shot = compare_png(a / f'{name}.png', b / f'{name}.png')
        if shot:
            counts['스크린샷'] = 1
            lines.append(shot)
        if any(counts.values()):
            differing += 1
            print(f'{name}: ' + ', '.join(f'{k} {v}' for k, v in counts.items() if v))
            for line in lines[:args.limit]:
                print('   ' + line)
            if len(lines) > args.limit:
                print(f'   … {len(lines) - args.limit}줄 더')
    total = len(names_a | names_b)
    print(f'비교 {total}개 캡처, 차이 있는 캡처 {differing}개' + (' — 차이 0' if not differing else ''))
    return 1 if differing else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    cap = sub.add_parser('capture', help='장면·폭마다 계산값·상자·스크린샷·상태 표본과 규칙 사용률을 모은다')
    cap.add_argument('--out', required=True)
    cap.add_argument('--scenes', help='쉼표로 구분(기본: 전부). ' + ','.join(SCENES))
    cap.add_argument('--widths', help='쉼표로 구분(기본: ' + ','.join(map(str, WIDTHS)) + ')')
    cap.add_argument('--jobs', type=int, default=1, help='장면을 나눠 동시에 돌릴 프로세스 수')
    cap.add_argument('--no-states', action='store_true', help='상태 표본(Tab·hover) 생략')
    cap.add_argument('--no-screenshots', action='store_true', help='스크린샷 생략')
    cap.add_argument('--tab-limit', type=int, default=TAB_LIMIT)
    cap.add_argument('--hover-limit', type=int, default=HOVER_LIMIT)
    cap.add_argument('--show-unused', type=int, default=40, help='화면에 보일 미사용 규칙 줄 수(전체는 rule-usage.txt)')
    cmp_ = sub.add_parser('compare', help='두 캡처 폴더를 허용 오차 0 으로 비교한다(차이가 있으면 종료 코드 1)')
    cmp_.add_argument('a')
    cmp_.add_argument('b')
    cmp_.add_argument('--limit', type=int, default=20, help='캡처마다 보일 차이 줄 수')
    args = parser.parse_args(argv)
    if args.command == 'capture':
        run_capture(args)
        return 0
    return run_compare(args)


if __name__ == '__main__':
    sys.exit(main())
