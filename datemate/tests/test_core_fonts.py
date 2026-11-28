"""첫 화면용 작은 글꼴(core)과 전체 글꼴 나중 받기(2026-11-28, 브랜치 perf/font-loading).

line.css 가 Pretendard 굵기마다 @font-face 를 둘 적는다: 전체 파일(*.subset.woff2, 범위 없음)과 그 뒤의 작은 core 파일(*.core.woff2, unicode-range).
브라우저는 core 를 먼저 쓰고 core 에 없는 글자가 나올 때만 전체 파일을 받는다. static/full-fonts.js(전역 DatemateFullFonts)는 모든 기능이 준비된 뒤
전체 파일 넷을 받아 모든 글자를 전체 파일로 그리게 한다 — 다 받은 뒤의 모양은 예전과 같다. core 는 scripts/build_core_fonts.py 가 만든다.

여기서 보는 것
  1. 파일·범위: core 네 파일이 진짜 woff2 이고 크기 예산 안, line.css 의 범위 = 파일 안 글자 집합, 전체 파일의 글자 집합은 예전 그대로(줄지 않음),
     @font-face 순서(전체가 앞, core 가 뒤), 저작권·라이선스 문구 유지와 글꼴 이름 변경(OFL 예약 이름).
  2. 화면 문구의 한글이 모두 core 에 있다(없으면 첫 화면이 전체 파일을 일찍 받아 느려진다 — 스크립트를 다시 돌리라는 안내),
     CSS·JS 가 켜는 글꼴 기능이 core 에 남긴 것(tnum)뿐이다.
  3. 브라우저: core 로 그린 글과 전체 파일로 그린 글이 픽셀까지 같다(core 의 모든 글자, 문장부호 문맥, 첫 화면 문구 — 네 굵기, tabular-nums 포함).
  4. 브라우저: 첫 화면·공유 화면은 전체 파일 없이 core 만으로 다 그려지고(전체 파일 요청을 붙잡아 둔 동안 요청은 스크립트가 보낸 하나뿐),
     전체 파일로 바뀌는 순간 화면이 한 픽셀도 달라지지 않는다. 전체 파일을 못 받아도 오류 없이 core 로 남는다.
     core 에 없는 글자는 스크립트가 없어도 전체 파일의 글리프로 그려진다(글자가 빠지지 않는다).
측정(수동): tests/js_split_measure.py.
"""

import os
import re
import socket
import sys
import threading
import time

import pytest
import uvicorn

from app.config import ROOT
from app.main import app

sys.path.insert(0, str(ROOT / "scripts"))
import build_core_fonts  # noqa: E402

STATIC = ROOT / "static"
FONT_DIR = STATIC / "fonts" / "pretendard"
WEIGHTS = build_core_fonts.WEIGHTS
# 예전(2026-11-24 ~ 11-28) 부분집합의 글자 수. 전체 파일을 바꾸면 여기와 fonts/LICENSE 를 함께 고친다 — 줄어들면 글자가 빠진다.
FULL_CODEPOINTS = 3728
FULL_HANGUL = 2780
CORE_BUDGET = 95_000  # 굵기마다(지금 약 84,000). 넘으면 첫 화면이 느려진다 — 담는 글자를 다시 본다.


def css_faces():
    """line.css 의 Pretendard @font-face 를 적힌 순서대로: (kind, 파일 이름 굵기, font-weight, unicode-range 또는 '')."""
    css = (STATIC / "line.css").read_text(encoding="utf-8")
    faces = []
    for body in re.findall(r"@font-face\s*\{([^}]*)\}", css):
        match = re.search(r"Pretendard-(\w+)\.(subset|core)\.woff2\)", body)
        assert match, body
        weight = re.search(r"font-weight:([^;]+);", body).group(1).strip()
        covered = re.search(r"unicode-range:([^;]+);", body)
        assert "font-display:swap" in body and "font-family:'Pretendard'" in body, body
        faces.append(
            (match.group(2), match.group(1), weight, covered.group(1).strip() if covered else "")
        )
    return faces


def core_range():
    ranges = build_core_fonts.css_core_ranges()
    assert set(ranges) == {name for name, _ in WEIGHTS}
    first = ranges[WEIGHTS[0][0]]
    assert all(value == first for value in ranges.values())
    return first


# ── 1. 파일·범위 ────────────────────────────────────────────────────────────────────────────────


def test_font_face_rules_list_full_files_first_then_core_with_a_range():
    faces = css_faces()
    weights = dict(WEIGHTS)
    # 전체 파일은 나중에 받는 순서(본문 → 제목 → 단추 → 칩)로 적는다: full-fonts.js 가 적힌 순서대로 하나씩 받는다.
    assert [(kind, name, weight) for kind, name, weight, _ in faces] == [
        ("subset", name, weights[name]) for name in ("Regular", "ExtraBold", "Bold", "SemiBold")
    ] + [("core", name, weight) for name, weight in WEIGHTS]
    # 전체 파일에는 범위가 없다(core 에 없는 모든 글자를 맡는다). 뒤에 적힌 core 가 자기 범위의 글자를 먼저 가져간다.
    assert all(not covered for kind, _, _, covered in faces if kind == "subset")
    assert all(covered for kind, _, _, covered in faces if kind == "core")


def test_core_files_match_the_css_range_and_the_full_files_keep_every_character():
    ttlib = pytest.importorskip("fontTools.ttLib")
    covered = core_range()
    for name, _ in WEIGHTS:
        core_path = FONT_DIR / f"Pretendard-{name}.core.woff2"
        data = core_path.read_bytes()
        assert data[:4] == b"wOF2", name
        assert len(data) < CORE_BUDGET, (name, len(data))
        full = ttlib.TTFont(FONT_DIR / f"Pretendard-{name}.subset.woff2")
        core = ttlib.TTFont(core_path)
        full_cmap, core_cmap = full.getBestCmap(), core.getBestCmap()
        assert len(full_cmap) == FULL_CODEPOINTS, (name, len(full_cmap))
        assert sum(1 for cp in full_cmap if 0xAC00 <= cp <= 0xD7A3) == FULL_HANGUL
        assert set(core_cmap) == covered, name
        assert covered < set(full_cmap), name
        # 줄 높이·굵기 판정에 쓰이는 값은 원본 그대로.
        for table, fields in (
            ("head", ("unitsPerEm",)),
            ("hhea", ("ascent", "descent", "lineGap")),
            (
                "OS/2",
                (
                    "sTypoAscender",
                    "sTypoDescender",
                    "sTypoLineGap",
                    "usWinAscent",
                    "usWinDescent",
                    "usWeightClass",
                    "fsSelection",
                    "sxHeight",
                    "sCapHeight",
                ),
            ),
        ):
            for field in fields:
                assert getattr(core[table], field) == getattr(full[table], field), (
                    name,
                    table,
                    field,
                )
        # 글자마다 나아가는 폭이 원본과 같다(줄바꿈이 같다).
        full_widths, core_widths = full["hmtx"].metrics, core["hmtx"].metrics
        assert all(
            core_widths[core_cmap[cp]][0] == full_widths[full_cmap[cp]][0] for cp in covered
        ), name
        # OFL: 저작권·라이선스 문구는 그대로, 고친 파일의 글꼴 이름은 예약 이름(Pretendard)을 쓰지 않는다.
        names = {
            r.nameID: r.toUnicode()
            for r in core["name"].names
            if r.platformID == 3 and r.langID == 0x409
        }
        assert "Kil Hyung-jin" in names[0]
        assert "SIL Open Font License" in names[13]
        assert names[1] == names[16] == build_core_fonts.CORE_FAMILY_NAME
        assert "Pretendard" not in names[4] and "Pretendard" not in names[6]
    # 문맥 대체에 걸리는 문장부호·화살표와 입력 중 낱자모는 core 에 있어야 한다.
    for ch in "~-:+→←↔·…()[]<>=@×÷–—•ㄱㅎㅏㅣ0123456789AZaz ":
        assert ord(ch) in covered, ch


def test_license_note_and_preloads_name_the_core_files():
    note = (STATIC / "fonts" / "LICENSE").read_text(encoding="utf-8")
    assert (
        "core.woff2" in note and "build_core_fonts.py" in note and "SIL Open Font License" in note
    )
    assert (FONT_DIR / "LICENSE.txt").read_text(encoding="utf-8").count("SIL OPEN FONT LICENSE")
    for name in ("index.html", "shared.html", "feedback.html", "feedback-admin.html"):
        html = (STATIC / name).read_text(encoding="utf-8")
        # 전체 파일은 미리 받지 않는다(첫 화면 CSS·JS 와 회선을 나눠 쓴다). 미리 받는 것이 있다면 core 뿐.
        assert not re.search(r'rel="preload"[^>]*\.subset\.woff2', html), name
        assert '<script src="/static/full-fonts.js" defer></script>' in html, name
        assert '<link rel="stylesheet" href="/static/line.css">' in html, name


# ── 2. 화면 문구·글꼴 기능 ──────────────────────────────────────────────────────────────────────


def test_every_hangul_syllable_in_the_ui_sources_is_in_the_core_files():
    covered = core_range()
    texts = [
        path.read_text(encoding="utf-8")
        for pattern in ("*.html", "*.js", "*.mjs", "*.css")
        for path in sorted(STATIC.glob(pattern))
    ] + [path.read_text(encoding="utf-8") for path in sorted((ROOT / "app").rglob("*.py"))]
    missing = sorted(build_core_fonts.source_hangul(texts) - covered)
    assert not missing, (
        "화면 문구에 core 글꼴에 없는 한글이 있습니다: "
        + "".join(map(chr, missing))
        + " — datemate 폴더에서 python scripts/build_core_fonts.py 를 돌리고 바뀐 woff2·line.css 를 함께 커밋하세요."
    )


def test_css_and_js_turn_on_only_the_font_features_kept_in_the_core_files():
    assert "tnum" in build_core_fonts.LAYOUT_FEATURES
    allowed = {"font-variant-numeric:tabular-nums"}
    found = set()
    for pattern in ("*.css", "*.js", "*.mjs", "*.html"):
        for path in STATIC.glob(pattern):
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(
                r"(font-variant(?:-[a-z]+)*|font-feature-settings)\s*:\s*([^;}\"'`]+)", text
            ):
                found.add(match.group(1) + ":" + match.group(2).strip())
            assert not re.search(r"fontVariant|fontFeatureSettings", text), path.name
    assert found <= allowed, (
        f"core 글꼴에 없는 글꼴 기능을 켭니다: {sorted(found - allowed)} — "
        "scripts/build_core_fonts.py 의 LAYOUT_FEATURES 에 더해 다시 만들고 여기 allowed 에 적으세요."
    )


# ── 3·4. 브라우저 ───────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def site():
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


def open_page(browser, base, width=402, height=874):
    page = browser.new_page(viewport={"width": width, "height": height})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: message.type == "error" and errors.append(message.text))
    page.route(
        "**/*",
        lambda route: (route.continue_() if route.request.url.startswith(base) else route.abort()),
    )
    return page, errors


def hold_full_fonts(page):
    """전체 파일(*.subset.woff2) 요청을 응답하지 않고 붙잡아 둔다. 붙잡힌 route 목록을 돌려준다."""
    held = []
    page.route("**/*.subset.woff2*", lambda route: held.append(route))
    return held


SAMPLE_PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>
%(faces)s
body{margin:0;background:#fff;color:#000}
#box{width:1180px;padding:8px;font-size:17px;line-height:1.6;word-break:keep-all;overflow-wrap:anywhere}
#box.nums{font-variant-numeric:tabular-nums}
#box p{margin:0 0 6px}
#box .small{font-size:12px}
#box .big{font-size:31px}
</style></head><body><div id="box"></div></body></html>"""

CONTEXT_LINES = [
    "성수 → 한남 → 이태원 ← 서울숲 ↔ 뚝섬",
    "10:00~12:30 · 오후 2:05–3:40 · 1,234,500원 · 12.5km · 35%",
    "서울-부산 A-B a-b 1-2 가~나 A~B a~b 3~4 (가) (A) (a) [1] <2> 가+나 1+1=2 A=B 가:나 A:B a:b",
    "TEL 02-123-4567 · http://example.com/path?a=1&b=2 · me@example.com · #태그 @이름",
    "AV To Ty Wa VA Yo LT fi fl ff 1/2 3/4 ×2 ÷3 ±4 ≤5 ≥6 ≈7 ≠8 −9",
    "‘작은따옴표’ “큰따옴표” 「낫표」 『겹낫표』 〈작은 화살〉 《겹화살》 … · • ※ ★ ☆ ♥ ♡ ✓ ① ② ③ ㈜ ℃ ₩ ￦ €",
    "가격은 12,000원~15,000원(1인), 주차 30분 무료! 정말? 네. 좋아요; 그리고, 끝.",
    "ㅋㅋㅋ ㅎㅎ ㅠㅠ ㄱㄴㄷ ㅏㅑㅓㅕ 한ㄱ 가ㅏ",
    "0123456789 1111 7777 00:00 11:11 2026-11-28 (토) 09:41",
]


def test_core_glyphs_and_shaping_render_like_the_full_files(site):
    """core 로만 그린 글과 전체 파일로만 그린 글의 화면이 픽셀까지 같다(같은 자리·같은 크기, 글꼴 가족만 바꿔 찍는다)."""
    browser, base = site
    covered = sorted(core_range())
    every = "".join(chr(cp) for cp in covered if cp > 0x20 and cp not in range(0x2002, 0x200B))
    rows = [every[i : i + 64] for i in range(0, len(every), 64)]
    # 첫 화면의 실제 문장(태그·스크립트·주석을 뺀 글).
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    html = re.sub(r"<!--.*?-->|<script\b.*?</script>|<style\b.*?</style>", " ", html, flags=re.S)
    sentences = [
        text.strip()
        for text in re.sub(r"<[^>]+>", "\n", html).split("\n")
        if re.search(r"[가-힣]", text)
    ]
    assert len(sentences) > 40
    faces = "".join(
        f"@font-face{{font-family:'{family}';src:url(/static/fonts/pretendard/Pretendard-{name}.{kind}.woff2) format('woff2');"
        f"font-weight:{weight};font-style:normal}}"
        for family, kind in (("OnlyCore", "core"), ("OnlyFull", "subset"))
        for name, weight in WEIGHTS
    )
    page, errors = open_page(browser, base, 1200, 900)
    try:
        page.route(
            base + "/sample",
            lambda route: route.fulfill(
                content_type="text/html; charset=utf-8", body=SAMPLE_PAGE % {"faces": faces}
            ),
        )
        page.goto(base + "/sample")
        box = page.locator("#box")
        fill = """([lines, family, weight, nums]) => {
            const box = document.getElementById('box');
            box.className = nums ? 'nums' : '';
            box.style.fontFamily = `'${family}', monospace`;
            box.style.fontWeight = weight;
            box.replaceChildren(...lines.map((line, i) => {
                const p = document.createElement('p');
                p.className = i % 5 === 3 ? 'small' : i % 5 === 4 ? 'big' : '';
                p.textContent = line;
                return p;
            }));
            return document.fonts.load(`${weight} 17px '${family}'`, lines.join('')).then(() => document.fonts.ready).then(() => box.getBoundingClientRect().height);
        }"""
        compared = 0
        # 비교하는 글은 모두 core 에 있는 글자여야 한다(없는 글자는 한쪽만 대체 글꼴로 떨어져 비교가 뜻을 잃는다).
        for lines in (rows, CONTEXT_LINES):
            assert {ord(ch) for line in lines for ch in line} <= set(covered), lines
        sentences = [line for line in sentences if {ord(ch) for ch in line} <= set(covered)]
        assert len(sentences) > 40
        for label, lines in (("every", rows), ("context", CONTEXT_LINES), ("sentences", sentences)):
            for weight in ("400", "600", "700", "800"):
                for nums in (False, True):
                    if nums and label != "context":
                        continue
                    shots = {}
                    for family in ("OnlyCore", "OnlyFull"):
                        height = page.evaluate(fill, [lines, family, weight, nums])
                        shots[family] = (height, box.screenshot(animations="disabled"))
                    assert shots["OnlyCore"][0] == shots["OnlyFull"][0], (label, weight, nums)
                    assert shots["OnlyCore"][1] == shots["OnlyFull"][1], (label, weight, nums)
                    compared += 1
        assert (
            compared == 4 + 4 * 2 + 4
        )  # 모든 글자 4 굵기 + 문맥 4 굵기×(보통·tabular-nums) + 첫 화면 문장 4 굵기
        assert not errors, errors
    finally:
        page.close()


READY = "typeof statusData!=='undefined'&&!!statusData&&!!document.querySelector('.simple-plan-form')&&DatemateLater.loaded"
FONT_STATES = """() => [...document.fonts].filter(f => f.family.replace(/["']/g, '') === 'Pretendard')
    .map(f => [/U\\+0-10FFFF/i.test(f.unicodeRange) ? 'full' : 'core', f.weight, f.status])"""


def settle(page):
    page.evaluate("document.fonts.ready.then(() => true)")
    page.wait_for_timeout(400)
    page.evaluate(
        "new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => r(true))))"
    )


@pytest.mark.parametrize("width,height", [(402, 874), (1440, 900)])
def test_first_screen_needs_only_core_and_does_not_change_when_full_fonts_take_over(
    site, width, height
):
    browser, base = site
    page, errors = open_page(browser, base, width, height)
    try:
        held = hold_full_fonts(page)
        page.goto(base + "/", wait_until="load")
        page.wait_for_function("() => " + READY)
        page.wait_for_function("() => DatemateFullFonts.state === 'loading'")
        settle(page)
        # 붙잡힌 요청은 스크립트가 보낸 첫 굵기 하나뿐이다: 첫 화면 글자는 모두 core 에 있어 CSS 가 전체 파일을 부르지 않았다.
        assert len(held) == 1, [route.request.url for route in held]
        states = page.evaluate(FONT_STATES)
        assert sorted(s for kind, _, s in states if kind == "core") == ["loaded"] * 4, states
        assert all(s == "unloaded" for kind, _, s in states if kind == "full"), states
        assert len(states) == 8
        before = page.screenshot(full_page=True, animations="disabled", caret="hide")
        # 놓아 주면 넷을 차례로 받고 한 번에 바꾼다.
        page.unroute("**/*.subset.woff2*")
        for route in held:
            route.continue_()
        assert page.evaluate("DatemateFullFonts.done") == "full"
        settle(page)
        states = page.evaluate(FONT_STATES)
        added = [s for s in states if s[0] == "full" and s[2] == "loaded"]
        assert sorted(w for _, w, _ in added) == ["400", "500 600", "700", "800 900"], states
        assert page.evaluate("performance.getEntriesByName('fonts:full').length") == 1
        after = page.screenshot(full_page=True, animations="disabled", caret="hide")
        assert before == after
        assert not errors, errors
    finally:
        page.close()


def test_shared_page_text_is_in_core_and_full_fonts_follow_after_load(site):
    browser, base = site
    page, errors = open_page(browser, base)
    try:
        held = hold_full_fonts(page)
        # 없는 공유 주소의 안내 화면: 공유 화면의 틀·문구가 core 만으로 그려지는지 본다.
        page.goto(base + "/shared#none", wait_until="load")
        page.wait_for_function("() => DatemateFullFonts.state === 'loading'")
        settle(page)
        assert len(held) == 1, [route.request.url for route in held]
        states = page.evaluate(FONT_STATES)
        assert all(s == "unloaded" for kind, _, s in states if kind == "full"), states
        assert any(s == "loaded" for kind, _, s in states if kind == "core"), states
        page.unroute("**/*.subset.woff2*")
        for route in held:
            route.continue_()
        assert page.evaluate("DatemateFullFonts.done") == "full"
        # 없는 공유 주소라 API 가 404 를 준다(브라우저가 콘솔에 적는다) — 그것 말고 오류는 없다.
        assert not [e for e in errors if "404" not in e], errors
    finally:
        page.close()


def test_full_font_failure_keeps_core_and_reports_no_error(site):
    browser, base = site
    page, errors = open_page(browser, base)
    try:
        page.route("**/*.subset.woff2*", lambda route: route.abort())
        page.goto(base + "/", wait_until="load")
        page.wait_for_function("() => " + READY)
        assert page.evaluate("DatemateFullFonts.done") == "failed"
        states = page.evaluate(FONT_STATES)
        assert len(states) == 8, states  # 아무것도 더하지 않았다
        assert sorted(s for kind, _, s in states if kind == "core") == ["loaded"] * 4, states
        assert page.evaluate("document.fonts.check(\"400 16px 'Pretendard'\", '데이트 코스 추천')")
        # 요청이 끊긴 것은 브라우저가 콘솔에 적는다(ERR_FAILED) — 그것 말고 페이지 오류는 없다.
        assert not [e for e in errors if "ERR_FAILED" not in e and "net::" not in e], errors
    finally:
        page.close()


def test_characters_outside_core_use_the_full_file_even_without_the_script(site):
    """core 에 없는 글자(드문 한글·악센트 라틴)는 CSS 만으로 전체 파일의 글리프로 그려진다 — 글자 범위가 줄지 않았다."""
    browser, base = site
    covered = core_range()
    rare = [
        chr(cp) for cp in (0xAC02, 0xB618, 0xD4B8, 0xC42C, 0xE9, 0x3A9, 0x42F)
    ]  # 갂 똘 풸 쐬 é Ω Я
    ttlib = pytest.importorskip("fontTools.ttLib")
    full = set(ttlib.TTFont(FONT_DIR / "Pretendard-Regular.subset.woff2").getBestCmap())
    rare = [ch for ch in rare if ord(ch) in full and ord(ch) not in covered]
    assert len(rare) >= 4, rare
    page, errors = open_page(browser, base)
    try:
        # 스크립트는 못 받게 하고(전체 파일로 바꾸는 코드 없이) line.css 만으로 본다.
        page.route("**/static/full-fonts.js*", lambda route: route.abort())
        page.route("**/static/bundles/**", lambda route: route.abort())
        requested = []
        page.on(
            "request",
            lambda request: ".subset.woff2" in request.url and requested.append(request.url),
        )
        page.goto(base + "/feedback", wait_until="load")
        assert page.evaluate("typeof DatemateFullFonts") == "undefined"
        settle(page)
        assert not requested, requested
        widths = page.evaluate(
            """async rare => {
            const probe = document.createElement('div');
            probe.style.cssText = 'position:absolute;left:0;top:0;font:400 40px Pretendard, monospace;white-space:nowrap';
            const mono = probe.cloneNode();
            mono.style.fontFamily = 'monospace';
            document.body.append(probe, mono);
            probe.textContent = mono.textContent = rare.join('');
            await document.fonts.load("400 40px 'Pretendard'", rare.join(''));
            await document.fonts.ready;
            return [probe.getBoundingClientRect().width, mono.getBoundingClientRect().width,
                document.fonts.check("400 40px 'Pretendard'", rare.join(''))];
        }""",
            rare,
        )
        assert widths[2] is True
        assert widths[0] != widths[1], (
            widths
        )  # 대체 글꼴(monospace)이 아니라 Pretendard 전체 파일로 그려졌다
        assert len(requested) == 1 and "Pretendard-Regular.subset.woff2" in requested[0], requested
    finally:
        page.close()
