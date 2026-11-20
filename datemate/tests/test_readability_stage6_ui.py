"""가독성 6단계(2026-11-17): 지도 장소 번호를 누르면 일정의 그 장소로, 결과 화면 사진은 화면 근처에서 받기.

1) 코스 지도(네이버 지도·Leaflet 대체 지도)의 장소 번호 표시(1..N)를 누르면 #plan-detail 의 같은 순번 장소 카드로 스크롤하고
   카드 제목(h4)에 포커스가 간다. 출발·귀가 표시는 동작이 없고, 식당·축제 표시의 정보창은 그대로다.
   네이버 지도는 가짜 SDK(test_popup_map_ui.NAVER_STUB)라 maps.js 가 등록한 click 처리를 직접 부른다.
2) 결과 화면 장소 사진(placePhotoPanel eager)은 사진 목록만 바로 받고, 사진 바이트는 카드가 화면 근처에 올 때 받는다.
   인쇄 직전(beforeprint)에는 남은 사진을 시작하고, 아직 못 받은 사진 칸은 인쇄에서 뺀다."""
import pytest

from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401
from test_popup_map_ui import LEAFLET_CAPTURE, NAVER_STUB
from test_results_extras_ui import wide_png


@pytest.fixture(autouse=True)
def release_finished_plan_jobs():
    """이 파일의 화면 테스트는 코스를 7번 만든다. 서버는 끝난 작업을 10분 동안 기억하고 기억 중인 작업이 100개면 새 추천을 429 로 막는다
    (app/plan_jobs.py). 전체 실행에서 이 파일 뒤의 테스트(test_results_flow_ui·test_review_improvements·test_security_limits)가
    그 한도에 걸려 실패했으므로(로컬 Docker 2회), 이 파일이 만든 끝난 작업은 테스트마다 지워 다른 테스트의 몫을 쓰지 않게 한다."""
    yield
    from app import plan_jobs
    with plan_jobs._lock:
        for key in [k for k, job in plan_jobs._jobs.items() if job.get('status') != 'running']:
            del plan_jobs._jobs[key]


# 포커스가 간 곳: 몇 번째 장소 카드의 제목인지(-1 = 장소 제목 아님), 제목이 화면 안에 보이고 가려지지 않았는지, 포커스 표시.
FOCUSED = """()=>{const a=document.activeElement,stops=[...document.querySelectorAll('#plan-detail .stop')];
  const index=stops.findIndex(s=>s.querySelector('.timeline-card>h4')===a);
  if(index<0)return {index,tag:a?.tagName};
  const r=a.getBoundingClientRect(),top=document.elementFromPoint(r.left+Math.min(20,r.width/2),r.top+r.height/2);
  const style=getComputedStyle(a);
  return {index,tabindex:a.getAttribute('tabindex'),inView:r.top>=0&&r.bottom<=innerHeight,uncovered:a.contains(top),
    outline:style.outlineStyle,outlineWidth:parseFloat(style.outlineWidth),name:a.textContent};}"""
# 네이버 표시마다: 표시 HTML, 등록된 click 처리 수.
NAVER_MARKERS = """()=>window.__naverMarkers.filter(m=>!m.removed).map(m=>({html:m.options.icon.content,title:m.options.title,
  clicks:window.__naverListeners.filter(l=>l.target===m&&l.name==='click'&&!l.removed).length}))"""


def click_naver_marker(page, number):
    """number 번 장소 표시의 click 처리를 부른다(가짜 SDK 라 표시 DOM 이 없다).
    실제 SDK 는 click 을 알린 직후 지도 칸에 포커스를 되돌린다(2026-11-17 운영에서 확인: 제목 포커스를 뺏고 지도로 다시 스크롤). 그것도 흉내 낸다."""
    page.evaluate("""n=>{const m=window.__naverMarkers.filter(m=>!m.removed&&m.options.icon.content.includes('>'+n+'</span>')
        &&m.options.icon.content.includes('route-stop-marker')).at(-1);
      window.__naverListeners.filter(l=>l.target===m&&l.name==='click'&&!l.removed).forEach(l=>l.fn());
      const canvas=document.querySelector('.plan-map .naver-plan-map');canvas.tabIndex=0;canvas.focus({preventScroll:true});}""", number)


@pytest.mark.parametrize('width', [390, 1440])
def test_naver_stop_marker_scrolls_to_the_place_card_and_focuses_its_title(audit_page, width):
    page, base, errors = audit_page
    page.set_viewport_size({'width': width, 'height': 844})
    page.evaluate(NAVER_STUB)
    generate(page)
    holder = '#plan-map-slot' if width == 390 else '#plan-map-rail'
    page.wait_for_function(f"document.querySelector('{holder} .naver-plan-map')&&window.__naverMarkers.length>=3", timeout=20000)
    places = page.evaluate('selected.places.length')
    markers = page.evaluate(NAVER_MARKERS)
    stops = [m for m in markers if 'route-stop-marker' in m['html']]
    # 장소 번호 표시 1..N 만 단추(고정 이름, 장소 이름은 HTML 에 넣지 않음), 출발·귀가는 그대로.
    assert len(stops) == places, markers
    for number, marker in enumerate(stops, 1):
        assert f'role="button" aria-label="{number}번 장소 · 눌러서 일정에서 보기">{number}</span>' in marker['html'], marker
        assert marker['clicks'] == 1, marker
    start = [m for m in markers if '>출발<' in m['html']]
    assert start and all(m['clicks'] == 0 and 'role=' not in m['html'] for m in start), start
    # 지도 쪽(휴대폰은 일정 뒤 지도, 데스크톱은 오른쪽 패널)을 보고 있다가 마지막 장소 번호를 누른다.
    page.evaluate(f"document.querySelector('{holder} .naver-plan-map').scrollIntoView({{block:'center',behavior:'instant'}})")
    before = page.evaluate('scrollY')
    for number in (places, 1):
        click_naver_marker(page, number)
        page.wait_for_function("document.activeElement?.matches('#plan-detail .timeline-card>h4')")
        page.wait_for_timeout(700)  # 부드러운 스크롤(html scroll-behavior)이 끝날 때까지
        state = page.evaluate(FOCUSED)
        assert state['index'] == number - 1, state
        assert state['tabindex'] == '-1' and state['inView'] and state['uncovered'], state
        # 마우스·손가락으로 누른 뒤의 스크립트 포커스도 표시가 보인다.
        assert state['outline'] == 'solid' and state['outlineWidth'] >= 2, state
        assert state['name'] == page.evaluate(f'selected.places[{number - 1}].name')
    if width == 390:
        assert page.evaluate('scrollY') < before  # 지도(일정 뒤)에서 위의 장소 카드로 올라감
    # 포커스가 떠나면 잠시 붙인 tabindex 를 뗀다(제목이 Tab 순서·클릭 포커스에 남지 않게).
    page.evaluate("document.querySelector('#plan-detail .detail h2').tabIndex=-1;document.querySelector('#plan-detail .detail h2').focus()")
    assert page.evaluate("[...document.querySelectorAll('#plan-detail .timeline-card>h4')].every(h=>!h.hasAttribute('tabindex')&&!h.classList.contains('map-stop-target'))")
    assert not errors, errors


def test_naver_restaurant_and_festival_markers_still_open_their_info_windows(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 844})
    page.evaluate(NAVER_STUB)
    generate(page)
    page.wait_for_function("document.querySelector('#plan-map-slot .naver-plan-map')&&window.__naverMarkers.length>=3", timeout=20000)
    # 축제 표시를 하나 얹고(FestivalPanel.mapItems) 다시 그리게 한 뒤, 그 표시를 누르면 정보창이 열리고 포커스는 옮기지 않는다.
    page.evaluate("""()=>{const o=selected.conditions.origin;
      FestivalPanel.mapItems=[{title:'시험 축제',start:'2026-10-24',end:'2026-10-25',lat:o.lat,lon:o.lon}];
      document.querySelector('#plan-map-slot .plan-map').updateFestivals();}""")
    page.evaluate("""()=>{document.activeElement?.blur();const m=window.__naverMarkers.filter(m=>!m.removed&&m.options.icon.content.includes('festival-marker')).at(-1);
      window.__naverListeners.filter(l=>l.target===m&&l.name==='click').forEach(l=>l.fn());}""")
    assert page.evaluate('window.__opened.length') == 1
    assert page.evaluate(FOCUSED)['index'] == -1
    assert not errors, errors


# Leaflet 코스 점: 장소 순번별 화면 좌표와 원 요소의 이름·커서.
LEAFLET_POINTS = """()=>{const m=courseMaps.at(-1),box=m.getContainer().getBoundingClientRect();
  const at=p=>{const c=m.latLngToContainerPoint([p.lat,p.lon]);return {x:box.left+c.x,y:box.top+c.y};};
  return {origin:at(selected.conditions.origin),places:selected.places.map(at),
    circles:[...document.querySelectorAll('.plan-map path.route-stop-circle')].map(p=>({role:p.getAttribute('role'),label:p.getAttribute('aria-label'),cursor:getComputedStyle(p).cursor})),
    hitNamed:[...document.querySelectorAll('.plan-map path.route-hit-area')].filter(p=>p.hasAttribute('role')).length};}"""


@pytest.mark.parametrize('width', [390, 1440])
def test_leaflet_stop_circle_scrolls_to_the_place_card(audit_page, width):
    page, base, errors = audit_page
    page.set_viewport_size({'width': width, 'height': 844})
    page.evaluate(LEAFLET_CAPTURE)
    generate(page)
    holder = '#plan-map-slot' if width == 390 else '#plan-map-rail'
    page.wait_for_function(f"document.querySelector('{holder} .fallback-plan-map')&&courseMaps.length", timeout=20000)
    page.wait_for_function("!courseMaps.at(-1)._animatingZoom")
    page.locator(f'{holder} .fallback-plan-map').scroll_into_view_if_needed()
    page.wait_for_timeout(400)
    state = page.evaluate(LEAFLET_POINTS)
    places = len(state['places'])
    assert [c['label'] for c in state['circles']] == [f'{n}번 장소 · 눌러서 일정에서 보기' for n in range(1, places + 1)], state
    assert all(c['role'] == 'button' and c['cursor'] == 'pointer' for c in state['circles']), state
    assert state['hitNamed'] == 0  # 투명한 누름 원은 이름 없이 같은 동작만
    # 출발 원을 누르면 아무 데도 가지 않는다.
    page.mouse.click(state['origin']['x'], state['origin']['y'])
    page.wait_for_timeout(300)
    assert page.evaluate(FOCUSED)['index'] == -1
    # 마지막 장소 원(가운데)을 누르면 그 장소 카드로. 휴대폰은 보이는 원 바깥 투명 영역(가운데에서 19px)도 같다.
    targets = [(places, 0)] + ([(1, 19)] if width == 390 else [(1, 0)])
    for number, offset in targets:
        page.locator(f'{holder} .fallback-plan-map').scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        point = page.evaluate(LEAFLET_POINTS)['places'][number - 1]
        target = page.evaluate("([x,y])=>{const e=document.elementFromPoint(x,y);return e?.getAttribute('class')||e?.tagName}", [point['x'] + offset, point['y']])
        if 'leaflet-tooltip' in (target or ''):
            pytest.skip(f'장소 이름 말풍선이 겹쳐 {number}번 점을 누를 수 없는 배치: {target}')
        # 원 가운데를 지나는 이동선(route-leg)은 누름을 받지 않는다(전에는 선이 원 위에서 가운데 누름을 가져갔다).
        assert 'route-stop-circle' in target or 'route-hit-area' in target, (number, offset, target)
        page.mouse.click(point['x'] + offset, point['y'])
        page.wait_for_function("document.activeElement?.matches('#plan-detail .timeline-card>h4')")
        page.wait_for_timeout(700)
        focused = page.evaluate(FOCUSED)
        assert focused['index'] == number - 1 and focused['inView'] and focused['uncovered'], (number, offset, focused)
    assert not errors, errors


# 사진: 장소마다 다른 주소(어느 장소 사진을 받았는지 구분)를 돌려주는 /media 와 그림.
def mount_lazy_photos(page, base):
    png = wide_png()
    requested = []

    def media(route):
        place = route.request.url.split('/api/places/')[1].split('/media')[0]
        url = f'{base}/lazy-photo-{place}.png'
        route.fulfill(json={'status': 'available', 'photos': [{'kind': 'place_public', 'source_label': '업체 등록 사진', 'title': '사진',
                      'source': url, 'image_url': url, 'search_url': base, 'checked_at': '2026-11-17'}]})

    def image(route):
        requested.append(route.request.url)
        route.fulfill(body=png, content_type='image/png')
    page.route('**/api/places/*/media?*', media)
    page.route('**/lazy-photo-*.png', image)
    page.route('**/api/places/*/blogs?*', lambda route: route.fulfill(json={'posts': [], 'message': '없음'}))
    return requested


def real_detail(page):
    page.evaluate("selected.conditions.mode='real';plans.forEach(p=>{p.conditions.mode='real';p.places.forEach(x=>x.demo=false)});renderResults();renderDetail()")
    wait_for_selected_detail(page)
    page.wait_for_function("document.querySelectorAll('#plan-detail .timeline-card .place-photo').length===selected.places.length", timeout=20000)


PHOTO_STATE = """()=>[...document.querySelectorAll('#plan-detail .timeline-card .place-photo-panel')].map(p=>{const i=p.querySelector('.photo-open img'),r=p.getBoundingClientRect();
  return {top:Math.round(r.top),height:Math.round(r.height),shown:!!i&&!i.hidden&&i.naturalWidth>0,hidden:!!i&&i.hidden,src:i?.getAttribute('src')||'',loading:i?.loading,decoding:i?.decoding,
    print:getComputedStyle(p).display};})"""


def test_result_photos_start_downloading_only_near_the_viewport(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 844})
    requested = mount_lazy_photos(page, base)
    generate(page)
    page.evaluate("window.scrollTo({top:0,behavior:'instant'})")
    real_detail(page)
    page.evaluate("window.scrollTo({top:0,behavior:'instant'})")
    page.wait_for_timeout(1500)
    ids = page.evaluate('selected.places.map(p=>p.id)')
    state = page.evaluate(PHOTO_STATE)
    far = [i for i, s in enumerate(state) if s['top'] > 844 + 600 + 50]
    assert far, state  # 휴대폰 결과 화면에서 장소 사진은 처음 화면에서 멀다
    for i in far:
        # 화면 근처가 아닌 사진은 아직 받지 않았고(검사용 Image() 도 없음) 대체 글자 없이 숨어 있다.
        assert not any(ids[i] in url for url in requested), (i, requested)
        assert state[i]['hidden'] and state[i]['src'] == '', state[i]
    # 사진 목록(/media)은 이미 받아 출처 줄·사진 칸 자리는 그려져 있다.
    assert page.locator('#plan-detail .timeline-card .place-photo figcaption').count() == len(ids)
    # 내려가면 그 사진을 받아 보인다(실패 복구·세대 토큰은 loadSafePhoto 그대로).
    last = far[-1]
    page.locator('#plan-detail .timeline-card .place-photo-panel').nth(last).scroll_into_view_if_needed()
    page.wait_for_function(f"(()=>{{const i=document.querySelectorAll('#plan-detail .timeline-card .place-photo-panel')[{last}].querySelector('.photo-open img');return !i.hidden&&i.naturalWidth>0;}})()", timeout=15000)
    assert any(ids[last] in url for url in requested)
    img = page.evaluate(PHOTO_STATE)[last]
    assert img['decoding'] == 'async' and img['loading'] == 'eager', img  # 확인한 후보는 바로 그린다(숨긴 lazy 이미지 문제, plan-assets-diagnosis)
    # 기다리는 동안의 사진 칸과 사진이 온 뒤의 높이가 같다('확인하고 있어요' 줄은 사진 칸 위에 얹힘). 화면 근처에서 받아도 아래 일정이 당겨지지 않는다.
    assert img['height'] == state[last]['height'], (state[last], img)
    # 코스 카드의 '장소 사진 n곳'(닫힌 접기) 사진은 펼칠 때 받는다.
    preview = page.locator('#results .plan-card .plan-photo-details')
    if preview.count() and not preview.first.evaluate('d=>d.open'):
        assert page.evaluate("[...document.querySelectorAll('.plan-photo-preview .place-photo img')].every(i=>i.hidden&&!i.getAttribute('src'))")
        preview.first.locator(':scope > summary').click()
        page.wait_for_function("[...document.querySelectorAll('.plan-photo-preview .place-photo img')].some(i=>!i.hidden&&i.naturalWidth>0)", timeout=15000)
    assert not errors, errors


def test_print_starts_remaining_photos_and_hides_unloaded_ones(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 844})
    requested = mount_lazy_photos(page, base)
    generate(page)
    real_detail(page)
    page.evaluate("window.scrollTo({top:0,behavior:'instant'})")
    page.wait_for_timeout(1000)
    state = page.evaluate(PHOTO_STATE)
    pending = [i for i, s in enumerate(state) if s['hidden']]
    assert pending, state
    # 인쇄 매체에서 아직 못 받은 사진 칸은 빠지고(빈 칸·출처 줄만 남지 않게), 받은 사진 칸은 그대로 나온다.
    page.emulate_media(media='print')
    printed = page.evaluate(PHOTO_STATE)
    page.emulate_media(media='screen')
    for i, s in enumerate(printed):
        assert s['print'] == ('none' if s['hidden'] else 'grid'), (i, s)
    # 인쇄 직전(beforeprint)에는 남은 사진을 모두 받기 시작하고, 받은 뒤에는 인쇄에 나온다.
    page.evaluate("dispatchEvent(new Event('beforeprint'))")
    page.wait_for_function("[...document.querySelectorAll('#plan-detail .timeline-card .place-photo-panel .photo-open img')].every(i=>!i.hidden&&i.naturalWidth>0)", timeout=15000)
    ids = page.evaluate('selected.places.map(p=>p.id)')
    assert all(any(pid in url for url in requested) for pid in ids), requested
    page.emulate_media(media='print')
    assert all(s['print'] == 'grid' for s in page.evaluate(PHOTO_STATE))
    page.emulate_media(media='screen')
    assert not errors, errors
