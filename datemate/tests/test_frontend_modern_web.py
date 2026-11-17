"""2026-11-17 modern-web-guidance 점검에서 고친 것들의 회귀 검사.

한글 조합 중 Enter, 모달 위 토스트, 대화상자 이름, Leaflet 지연 로딩, 진짜 WOFF2 글꼴과 preload, 모바일에서 받지 않는 히어로 사진.
"""
from app.config import ROOT
from test_functional_audit import audit_page  # noqa: F401

STATIC = ROOT / 'static'


def test_enter_while_composing_hangul_does_not_search(audit_page):
    page, base, errors = audit_page
    calls = page.evaluate("""()=>{
      let n=0;window.search=async()=>{n++;};
      const box=document.querySelector('#search');
      const press=init=>box.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,...init}));
      press({isComposing:true});press({keyCode:229});
      const composing=n;press({});
      return [composing,n];}""")
    assert calls == [0, 1], calls


def test_toast_shows_inside_an_open_modal_and_returns_to_the_page(audit_page):
    page, base, errors = audit_page
    page.evaluate("openDialog('장소 정보')")
    assert page.evaluate("document.querySelector('#dialog').getAttribute('aria-labelledby')") == 'dialog-title'
    assert page.evaluate("document.getElementById('dialog-title').textContent") == '장소 정보'
    page.evaluate("toast('대화상자 위 안내')")
    assert page.evaluate("document.querySelector('#toast').parentElement.id") == 'dialog'
    assert page.locator('#toast').is_visible()
    # 모달 바깥은 비활성(inert)이라 눌러 볼 수 없는 위치가 아니라, 토스트가 실제 맨 위에 그려지는지 본다.
    on_top = page.evaluate("""()=>{const r=document.querySelector('#toast').getBoundingClientRect();
      return document.elementFromPoint(r.left+r.width/2,r.top+r.height/2)?.closest('#toast')!==null;}""")
    assert on_top
    page.evaluate("document.querySelector('#dialog').close()")
    assert page.evaluate("document.querySelector('#toast').parentElement===document.body")


def test_leaflet_is_not_loaded_until_the_fallback_map_needs_it(audit_page):
    page, base, errors = audit_page
    assert page.evaluate("typeof window.L") == 'undefined'
    assert page.evaluate("document.querySelectorAll('script[src*=\"leaflet\"],link[href*=\"leaflet\"]').length") == 0
    page.evaluate("loadLeaflet()")
    page.wait_for_function("typeof window.L==='object'&&typeof L.map==='function'")
    assert page.evaluate("document.querySelectorAll('link[data-datemate-leaflet]').length") == 1
    # 두 번 불러도 한 번만 붙는다.
    page.evaluate("loadLeaflet()")
    assert page.evaluate("document.querySelectorAll('script[data-datemate-leaflet]').length") == 1


def test_heading_font_is_real_woff2_and_preloaded():
    data = (STATIC / 'fonts' / 'line-heading-800.woff2').read_bytes()
    assert data[:4] == b'wOF2', data[:4]
    assert len(data) < 150_000, len(data)
    for name in ('index.html', 'shared.html'):
        html = (STATIC / name).read_text(encoding='utf-8')
        assert ('<link rel="preload" href="/static/fonts/line-heading-800.woff2" as="font" type="font/woff2" crossorigin>'
                in html), name


def test_hero_photo_is_skipped_on_narrow_screens_and_prioritised_on_wide(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 1440, 'height': 900})
    page.wait_for_function("(()=>{const i=document.querySelector('.hero-photo img');return i.complete&&i.naturalWidth===1400;})()")
    assert page.evaluate("document.querySelector('.hero-photo img').currentSrc").endswith('/static/images/seoul-evening.webp')
    assert page.evaluate("document.querySelector('.hero-photo img').getAttribute('fetchpriority')") == 'high'
    page.set_viewport_size({'width': 390, 'height': 844})
    page.wait_for_function("document.querySelector('.hero-photo img').currentSrc.startsWith('data:')")
    assert (STATIC / 'images' / 'seoul-evening.webp').stat().st_size < (STATIC / 'images' / 'seoul-evening.jpg').stat().st_size
