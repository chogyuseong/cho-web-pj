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
    # 2026-11-24 리디자인 1단계: Pretendard 부분집합 네 굵기(fonts/LICENSE).
    # 2026-11-28 perf/font-loading: 굵기마다 작은 core 파일을 먼저 쓰고 전체 파일은 나중에 받는다(tests/test_core_fonts.py).
    # 미리 받는 것은 본문(400)의 core 하나뿐이다 — 전체 파일이나 다른 굵기를 미리 받으면 첫 화면 CSS·JS 와 회선을 나눠 쓴다(측정: 배포-이어가기.txt).
    for weight in ('Regular', 'SemiBold', 'Bold', 'ExtraBold'):
        data = (STATIC / 'fonts' / 'pretendard' / f'Pretendard-{weight}.subset.woff2').read_bytes()
        assert data[:4] == b'wOF2', (weight, data[:4])
        assert len(data) < 300_000, (weight, len(data))
    assert (STATIC / 'fonts' / 'pretendard' / 'LICENSE.txt').read_text(encoding='utf-8').count('SIL OPEN FONT LICENSE')
    for name in ('index.html', 'shared.html'):
        html = (STATIC / name).read_text(encoding='utf-8')
        assert ('<link rel="preload" href="/static/fonts/pretendard/Pretendard-Regular.core.woff2" as="font" type="font/woff2" crossorigin>'
                in html), name
        assert html.count('rel="preload"') == 1 and html.count('as="font"') == 1, name
    for weight in ('Regular', 'SemiBold', 'Bold', 'ExtraBold'):
        data = (STATIC / 'fonts' / 'pretendard' / f'Pretendard-{weight}.core.woff2').read_bytes()
        assert data[:4] == b'wOF2', (weight, data[:4])


def test_first_screen_has_no_large_hero_image(audit_page):
    """2026-11-26 시안: 처음 화면 오른쪽은 사진이 아니라 글로 된 '추천 동선 미리보기(예시)' 카드다. 큰 그림을 받지 않아 첫 화면이 가볍다.
    (예전 이 자리 테스트: 넓은 화면에서만 WebP 사진을 받고 fetchpriority=high — 사진을 뺐으므로 받는 그림이 없는지를 본다.)"""
    page, base, errors = audit_page
    page.set_viewport_size({'width': 1440, 'height': 900})
    assert page.locator('.hero-photo, .hero img').count() == 0
    assert page.locator('.hero-preview').is_visible()
    loaded = page.evaluate("performance.getEntriesByType('resource').map(r=>r.name).filter(n=>/seoul-evening/.test(n))")
    assert loaded == [], loaded


