# ruff: noqa: F811  (pytest 고정 장치 audit_page 를 같은 이름의 인자로 받는다)
"""2026-11-27 2차 운영 QA(docs/QA_REPORT-2026-11-27.ko.md)의 낮음 항목 회귀 테스트.

QA-18: 안내 문구가 '서울 성수을(를) …'처럼 조사를 둘 다 적었다 → static/ko-text.js withObjectParticle 이 받침에 맞는 조사 하나를 고른다.
QA-17: 휴대폰에서 바닥글 '의견 보내기'(64×25px)·'예산 무관' label(높이 32px)의 누르는 영역이 44px 보다 작았다 → redesign.css 2-0).
QA-19(첫 화면 JS 나눠 받기)는 구조 정리가 먼저라 이번에 하지 않는다.
"""

import json
import re
import shutil
import subprocess

import pytest

from app.config import ROOT
from test_functional_audit import audit_page, generate  # noqa: F401  (pytest fixture)

STATIC = ROOT / "static"
NODE = shutil.which("node")


@pytest.mark.skipif(not NODE, reason="needs node")
def test_object_particle_follows_the_last_korean_syllable():
    cases = {
        "서울 성수": "서울 성수를",
        "성수동": "성수동을",
        "‘성수’": "‘성수’를",  # 닫는 따옴표는 건너뛴다
        "성수카페(서울 성수동)": "성수카페(서울 성수동)를",  # 괄호 설명 앞 말로 판단
        "낙산공원 ": "낙산공원을",
        "CGV": "CGV을(를)",  # 한글이 아니면 읽는 법을 몰라 예전 표기
        "2호점": "2호점을",
        "": "을(를)",
    }
    script = (STATIC / "ko-text.js").read_text(
        encoding="utf-8"
    ) + f"\nconsole.log(JSON.stringify({json.dumps(list(cases))}.map(withObjectParticle)));"
    out = subprocess.run(
        [NODE, "-e", script], capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout
    assert json.loads(out) == list(cases.values())


def test_no_double_particle_left_and_helper_loads_first():
    leftovers = [
        p.name
        for p in STATIC.glob("*.js")
        if p.name != "ko-text.js" and "을(를)" in p.read_text(encoding="utf-8")
    ]
    assert leftovers == []
    # 'use strict' 가 있으면 첫 화면 묶음 맨 앞이라 묶음 전체가 엄격 모드가 된다(build-edge-pages.mjs 'JS 묶기').
    assert not re.search(
        r"^\s*['\"]use strict['\"]", (STATIC / "ko-text.js").read_text(encoding="utf-8"), re.M
    )
    for page, users in (
        ("index.html", ("simple-form.js", "explore.js")),
        ("shared.html", ("shared.js",)),
    ):
        html = (STATIC / page).read_text(encoding="utf-8")
        for user in users:
            assert html.index("/static/ko-text.js") < html.index(f"/static/{user}"), (page, user)


def test_area_message_uses_one_particle_and_phone_tap_targets_are_44px(audit_page):
    page, _, _ = audit_page
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_function("document.querySelector('#conditions button[data-area]')")
    page.click('#conditions button[data-area="서울 성수"]')
    page.wait_for_function(
        "[...document.querySelectorAll('#conditions *')].some(e=>/데이트할 지역으로 골랐어요/.test(e.textContent))"
    )
    message = page.evaluate(
        "[...document.querySelectorAll('#conditions *')].filter(e=>!e.children.length&&/데이트할 지역으로/.test(e.textContent))[0].textContent"
    )
    assert message == "서울 성수를 데이트할 지역으로 골랐어요.", message
    sizes = page.evaluate("""()=>{
      const h=e=>e&&!e.closest('[hidden]')&&e.getClientRects().length?Math.round(e.getBoundingClientRect().height):null;
      return {feedback:h(document.querySelector('footer .footer-feedback')),
              unlimited:h(document.querySelector('#conditions input[name=budget_unlimited]')?.closest('label'))};}""")
    assert sizes["feedback"] is not None and sizes["feedback"] >= 44, sizes
    # '예산 무관'은 예산 칸 설정에 따라 숨을 수 있다. 보일 때만 높이를 본다.
    assert sizes["unlimited"] is None or sizes["unlimited"] >= 44, sizes
