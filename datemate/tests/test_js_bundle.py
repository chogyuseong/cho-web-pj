"""JS 묶기(QA-14, 2026-11-27): 첫 화면·공유 화면의 이어진 defer 스크립트 덩어리를 static/bundles/<페이지>.js 로 받는다.

2026-11-28 QA-19: 첫 화면(index.html)은 덩어리가 둘이다 — 바로 받는 첫 묶음(bundles/index.js)과, template#later-scripts 안에 있어
later-scripts.js 가 DOMContentLoaded 뒤에 붙이는 나중 묶음(bundles/index-2.js). 나눈 것 자체의 검사는 tests/test_js_split.py.

묶음은 cloudflare/build-edge-pages.mjs 가 배포 때(테스트는 conftest 가 시작할 때) 만들고, 앱(app/static_pages.bundled_page)과
엣지(build-edge-pages.mjs bundledPage)는 묶음 머리의 원본 해시가 지금 원본과 같을 때만 묶음 태그를 쓴다.
이유·묶음 안의 동작 차이·끄는 법은 build-edge-pages.mjs 의 'JS 묶기' 주석.
"""

import json
import re
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from app import static_pages
from app.config import ROOT
from app.main import app

BUILD = ROOT.parent / "cloudflare" / "build-edge-pages.mjs"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(
    not (BUILD.is_file() and NODE),
    reason="needs node and cloudflare/ (conftest builds the bundles)",
)
SCRIPT = re.compile(r'<script src="/static/([^"?]+\.js)" defer></script>')


def node_module(code, root=None):
    """build-edge-pages.mjs 를 불러 code 를 돌리고 마지막 console.log(JSON) 를 돌려준다."""
    prelude = f"import * as build from {json.dumps(BUILD.as_uri())};\nconst ROOT = {json.dumps(str(root) if root else None)} ?? undefined;\n"
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", prelude + code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return json.loads(result.stdout)


def sources(page):
    return SCRIPT.findall((ROOT / "static" / page).read_text(encoding="utf-8"))


def chunks(page):
    """페이지의 이어진 스크립트 태그 덩어리별 원본 이름(묶음 하나가 되는 단위)."""
    html = (ROOT / "static" / page).read_text(encoding="utf-8")
    return [SCRIPT.findall(run.group(0)) for run in static_pages._SCRIPT_RUN.finditer(html)]


@pytest.mark.parametrize(
    "page,route,bundles",
    [("index.html", "/", ["index.js", "index-2.js"]), ("shared.html", "/shared", ["shared.js"])],
)
def test_page_loads_its_bundles_in_source_order(page, route, bundles):
    groups = chunks(page)
    assert len(groups) == len(bundles)
    # 덩어리 밖에 따로 남은 스크립트 태그가 없다(모든 원본이 어느 묶음엔가 들어간다).
    assert [name for names in groups for name in names] == sources(page)
    tags = []
    for names, bundle in zip(groups, bundles):
        assert len(names) >= 2
        path = ROOT / "static" / "bundles" / bundle
        text = path.read_bytes().decode("utf-8")
        # 머리 = 원본 해시, 몸 = 원본 순서 그대로(BOM 만 빼고), 파일 사이에 줄바꿈과 ';'
        assert text.startswith(static_pages.bundle_header(names))
        body = "".join(
            f"/* ---- {n} ---- */\n"
            + (ROOT / "static" / n).read_bytes().decode("utf-8").removeprefix("﻿")
            + "\n;\n"
            for n in names
        )
        assert text == static_pages.bundle_header(names) + body
        subprocess.run([NODE, "--check", str(path)], check=True)
        version = static_pages.file_version(f"/static/bundles/{bundle}")
        tags.append(f'<script src="/static/bundles/{bundle}?v={version}" defer>')
    with TestClient(app) as client:
        html = client.get(route).text
        assert re.findall(r"<script\b[^>]*>", html) == tags
        for tag in tags:
            served = client.get(tag.split('"')[1])
            assert served.status_code == 200 and served.headers["content-type"].startswith(
                "text/javascript"
            )
    if page == "index.html":
        # 첫 묶음만 브라우저가 바로 받는다. 나중 묶음 태그는 실행되지 않는 template 안에 있다(later-scripts.js 가 붙인다).
        assert f'<template id="later-scripts">\n{tags[1]}</script>\n</template>' in html
        assert html.index(tags[0]) < html.index('<template id="later-scripts">')


def test_app_and_edge_build_the_same_pages():
    pages = node_module("console.log(JSON.stringify(build.buildEdgePages()));")
    for route, name in (("/", "index.html"), ("/shared", "shared.html"), ("404", "not-found.html")):
        assert static_pages.versioned_page(name) == pages[route], route


def test_same_regex_and_header_on_both_sides():
    source = BUILD.read_text(encoding="utf-8")
    js = {
        name: re.search(rf"const {name} = /(.+)/g;", source).group(1).replace("\\/", "/")
        for name in ("SCRIPT_RUN", "SCRIPT_SRC")
    }
    assert js["SCRIPT_RUN"] == static_pages._SCRIPT_RUN.pattern
    assert js["SCRIPT_SRC"] == static_pages._SCRIPT_SRC.pattern
    assert (
        f"BUNDLE_HEADER_FIRST_LINE = {json.dumps(static_pages.BUNDLE_HEADER_FIRST_LINE)};" in source
    )


def test_stale_or_missing_bundle_falls_back_to_source_tags(tmp_path, monkeypatch):
    """개발 중 원본을 고치면(묶음이 오래되면) 두 쪽 모두 원본 태그를 그대로 쓴다 — 예전 코드를 보내지 않는다."""
    static = tmp_path / "static"
    static.mkdir()
    (static / "a.js").write_text("function a(){return 1}\n", encoding="utf-8")
    # 앞 파일이 ';' 없이 끝나고 뒤 파일이 '(' 로 시작해도 한 문장으로 붙지 않아야 한다(세미콜론 자동 삽입 함정).
    (static / "b.js").write_text("﻿(() => { window.b = a() })()", encoding="utf-8")
    tags = (
        '<script src="/static/a.js" defer></script>\n  <script src="/static/b.js" defer></script>'
    )
    (static / "index.html").write_text(f"<!doctype html><title>t</title>{tags}\n", encoding="utf-8")
    monkeypatch.setattr(static_pages, "ROOT", tmp_path)

    def both():
        edge = node_module(
            'console.log(JSON.stringify(build.versionedPage("index.html", ROOT)));', tmp_path
        )
        app_page = static_pages.versioned_page("index.html")
        assert app_page == edge
        return app_page

    assert "/static/a.js?v=" in both()  # 묶음 없음
    node_module("console.log(JSON.stringify(build.writeBundles(ROOT)));", tmp_path)
    bundle = (static / "bundles" / "index.js").read_text(encoding="utf-8")
    assert "﻿" not in bundle and "return 1}\n\n;\n/* ---- b.js ---- */\n(() =>" in bundle
    page = both()
    assert "/static/bundles/index.js?v=" in page and "/static/a.js" not in page
    subprocess.run([NODE, "--check", str(static / "bundles" / "index.js")], check=True)
    (static / "a.js").write_text(
        "function a(){return 2}\n", encoding="utf-8"
    )  # 원본이 바뀜 → 묶음이 오래됨
    page = both()
    assert "/static/a.js?v=" in page and "/static/b.js?v=" in page and "bundles/" not in page


def test_bundles_are_not_committed():
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", str(ROOT / "static" / "bundles" / "index.js")],
        cwd=ROOT.parent,
    )
    if ignored.returncode == 128:
        pytest.skip("not a git checkout")
    assert ignored.returncode == 0
