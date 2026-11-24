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
    # 한 번의 실행 안에서 열고·띄우고·재고·닫는다(전체 테스트가 느릴 때 단계 사이에 다른 비동기 작업이 끼지 않게).
    state = page.evaluate("""async()=>{
      openDialog('장소 정보');
      const dialog=document.querySelector('#dialog');
      toast('대화상자 위 안내');
      const el=document.querySelector('#toast');const r=el.getBoundingClientRect();
      const hit=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);
      const open={label:dialog.getAttribute('aria-labelledby'),title:document.getElementById('dialog-title')?.textContent,
        parent:el.parentElement.id,shown:getComputedStyle(el).display!=='none'&&r.width>0&&r.height>0,
        onTop:!!hit&&el.contains(hit)};
      // close 이벤트는 비동기로 온다. 토스트를 되돌리는 처리(먼저 붙음)가 끝난 뒤에 잰다.
      const closed=new Promise(resolve=>dialog.addEventListener('close',()=>resolve(),{once:true}));
      dialog.close();await closed;
      return {...open,afterClose:el.parentElement===document.body};}""")
    assert state == {'label': 'dialog-title', 'title': '장소 정보', 'parent': 'dialog', 'shown': True,
                     'onTop': True, 'afterClose': True}, state


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
    # 2026-11-24 리디자인 1단계: Pretendard 부분집합 네 굵기(fonts/LICENSE). 본문(400)·제목(800)만 미리 받는다.
    for weight in ('Regular', 'SemiBold', 'Bold', 'ExtraBold'):
        data = (STATIC / 'fonts' / 'pretendard' / f'Pretendard-{weight}.subset.woff2').read_bytes()
        assert data[:4] == b'wOF2', (weight, data[:4])
        assert len(data) < 300_000, (weight, len(data))
    assert (STATIC / 'fonts' / 'pretendard' / 'LICENSE.txt').read_text(encoding='utf-8').count('SIL OPEN FONT LICENSE')
    for name in ('index.html', 'shared.html'):
        html = (STATIC / name).read_text(encoding='utf-8')
        for weight in ('Regular', 'ExtraBold'):
            assert (f'<link rel="preload" href="/static/fonts/pretendard/Pretendard-{weight}.subset.woff2" as="font" type="font/woff2" crossorigin>'
                    in html), (name, weight)


def test_hero_photo_is_skipped_on_narrow_screens_and_prioritised_on_wide(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 1440, 'height': 900})
    page.wait_for_function("(()=>{const i=document.querySelector('.hero-photo img');return i.complete&&i.naturalWidth===1400;})()")
    assert page.evaluate("document.querySelector('.hero-photo img').currentSrc").endswith('/static/images/seoul-evening.webp')
    assert page.evaluate("document.querySelector('.hero-photo img').getAttribute('fetchpriority')") == 'high'
    page.set_viewport_size({'width': 390, 'height': 844})
    page.wait_for_function("document.querySelector('.hero-photo img').currentSrc.startsWith('data:')")
    assert (STATIC / 'images' / 'seoul-evening.webp').stat().st_size < (STATIC / 'images' / 'seoul-evening.jpg').stat().st_size
