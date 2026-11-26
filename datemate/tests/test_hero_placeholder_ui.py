"""히어로 입력칸 안내 문구가 칸 안에 다 들어간다(2026-11-26 사용자 지적: 휴대폰에서 '…덜 걷고' 근처에서 잘림).

static/header-mode.js syncHeroPlaceholder 가 실제 칸 폭과 문구 폭을 재서, 긴 문구가 안 들어가면 짧은 문구(shortPlaceholder)를 쓴다.
- 데스크톱: 긴 문구 그대로.
- 휴대폰 390·320px: 짧은 문구, 칸 안에 들어감.
- 데이트/여행 스위치를 눌러도 같은 규칙.
문구를 바꾸면 이 테스트가 폭을 다시 확인해 준다."""
import pytest

from test_functional_audit import audit_page  # noqa: F401  (pytest fixture)

LONG = {'date': '예: 비 오는 날 성수에서 덜 걷고 분위기 좋은 저녁 코스', 'travel': '예: 강릉에서 바다 보며 드라이브하고 저녁은 시장에서'}

# 칸 폭과 지금 안내 문구의 실제 그린 폭(같은 글꼴로 canvas 에서 잰다).
MEASURE = """()=>{const i=document.getElementById('hero-command-input');const s=getComputedStyle(i);
const c=document.createElement('canvas').getContext('2d');c.font=`${s.fontWeight} ${s.fontSize} ${s.fontFamily}`;
return {placeholder:i.placeholder,input:i.clientWidth,text:c.measureText(i.placeholder).width};}"""


def switch(page, mode):
    page.locator(f'#mode-switch [data-mode={mode}]').click()
    page.wait_for_function(f"document.querySelector('#mode-switch [data-mode={mode}]').getAttribute('aria-pressed')==='true'")


@pytest.mark.parametrize('width,long_expected', [(1280, True), (390, False), (320, False)])
def test_hero_placeholder_fits_its_field(audit_page, width, long_expected):
    page, base, errors = audit_page
    page.evaluate("try{localStorage.removeItem('datemate-mode')}catch{}")
    page.set_viewport_size({'width': width, 'height': 800})
    page.goto(base + '/', wait_until='networkidle')
    page.evaluate('document.fonts.ready')
    for mode in ('date', 'travel', 'date'):
        if mode == 'travel' or page.locator('body.mode-travel').count():
            switch(page, mode)
        # ResizeObserver·글꼴 로드 뒤 다시 재는 것을 기다린다.
        page.wait_for_function(f"(({MEASURE})()).text<=(({MEASURE})()).input")
        got = page.evaluate(MEASURE)
        assert got['text'] <= got['input'], (width, mode, got)
        assert (got['placeholder'] == LONG[mode]) == long_expected, (width, mode, got)
        assert got['placeholder'].startswith('예: '), got
    page.evaluate("try{localStorage.removeItem('datemate-mode')}catch{}")
    assert not errors, errors
