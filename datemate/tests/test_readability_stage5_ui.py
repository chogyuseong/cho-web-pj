"""가독성 5단계(2026-11-17): 휴대폰 코스 지도 표시의 누름 영역 44×44px.

네이버 지도는 가짜 SDK(test_popup_map_ui.NAVER_STUB)라 실제 표시 DOM 이 없으므로, maps.js 가 넘긴 표시 HTML 을
네이버처럼(왼쪽 위 = 좌표 - anchor) 지도 칸 안에 놓고 잰다. Leaflet 대체 지도는 저장소에 든 실제 Leaflet 으로 본다."""
from test_functional_audit import audit_page, generate  # noqa: F401
from test_popup_map_ui import LEAFLET_CAPTURE, NAVER_STUB

# 표시 HTML 마다: 왼쪽 위를 (x-anchor.x, y-anchor.y) 에 두고, 보이는 표시의 가운데에서 상하좌우·대각선 21px 떨어진 곳을 누르면 그 표시가 받는지,
# 보이는 크기와 anchor 가 보이는 표시의 가운데인지 잰다. 표시끼리 겹치지 않게 한 줄에 셋씩 110×90px 간격으로 둔다.
NAVER_LAYOUT = """()=>{const host=document.querySelector('.plan-map .naver-plan-map');host.replaceChildren();
  host.scrollIntoView({block:'center',behavior:'instant'});
  const extra=[{icon:{content:'<span class="route-marker restaurant-marker">1-1 / 2-1</span>',anchor:{x:19,y:19}}},
    {icon:{content:'<span class="route-marker parking-marker">P</span>',anchor:{x:16,y:16}}},
    {icon:{content:'<span class="route-marker festival-marker">축제</span>',anchor:{x:24,y:13}}},
    {icon:{content:'<span class="route-marker festival-marker festival-marker-chosen">축제</span>',anchor:{x:24,y:13}}}];
  const list=[...window.__naverMarkers.filter(m=>!m.removed&&!/popup-marker|festival-marker/.test(m.options.icon.content)).map(m=>m.options),...extra];
  const box=host.getBoundingClientRect();
  return list.map((o,i)=>{const x=50+(i%3)*110,y=50+Math.floor(i/3)*90,el=document.createElement('div');el.style.cssText=`position:absolute;left:${x-o.icon.anchor.x}px;top:${y-o.icon.anchor.y}px`;
    el.innerHTML=o.icon.content;host.append(el);const mark=el.firstElementChild,r=mark.getBoundingClientRect(),cx=box.left+x,cy=box.top+y;
    const ex=r.left+r.width/2,ey=r.top+r.height/2;
    const hits=[[21,0],[-21,0],[0,21],[0,-21],[21,21],[-21,-21]].map(([dx,dy])=>document.elementFromPoint(ex+dx,ey+dy)?.closest('.route-marker')===mark);
    return {html:o.icon.content,w:Math.round(r.width),h:Math.round(r.height),dx:Math.round(r.left+r.width/2-cx),dy:Math.round(r.top+r.height/2-cy),hits,
      after:getComputedStyle(mark,'::after').content};});}"""


def test_naver_markers_get_a_44px_touch_area_on_phones_only(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 844})
    page.evaluate(NAVER_STUB)
    generate(page)
    page.wait_for_function("document.querySelector('#plan-map-slot .naver-plan-map')&&window.__naverMarkers.length>=3", timeout=20000)
    rows = page.evaluate(NAVER_LAYOUT)
    course = [r for r in rows if 'restaurant-marker' not in r['html'] and 'parking' not in r['html'] and 'festival' not in r['html']]
    assert len(course) >= 3, rows
    for row in rows:
        # 보이는 표시 둘레 44×44px(가운데에서 21px)는 모두 그 표시가 받는다. 보이는 표시는 좌표 점 가운데에 그대로 있다.
        assert all(row['hits']), row  # 전(투명 여백 없음)에는 38px 원이라 21px 떨어진 곳은 지도 바탕
        assert abs(row['dx']) <= 1 and abs(row['dy']) <= 1, row
    # 보이는 번호 원은 38px 그대로(투명 여백으로만 넓힘).
    assert all(r['w'] == 38 and r['h'] == 38 for r in course), course
    # 축제 표시는 글꼴과 관계없이 48×26px(maps.js 의 anchor 24,13 이 가운데). 고른 축제도 같은 크기.
    festival = [r for r in rows if 'festival-marker' in r['html']]
    assert len(festival) == 2 and all(r['w'] == 48 and r['h'] == 26 for r in festival), festival
    # 데스크톱은 투명 여백 없이 전과 같다.
    page.set_viewport_size({'width': 1440, 'height': 1000})
    page.wait_for_function("document.querySelector('#plan-map-rail .naver-plan-map')", timeout=20000)
    desktop = page.evaluate(NAVER_LAYOUT)
    assert all(r['after'] == 'none' for r in desktop), desktop
    assert all(r['w'] == 38 and r['h'] == 38 for r in desktop if r['html'] in {c['html'] for c in course}), desktop
    assert not errors, errors


# Leaflet 코스 점마다: 좌표 점 가운데의 맨 위가 보이는 원(투명 원이 아님)인지, 상하좌우 20px 이 지도 바탕이 아니라 그 점의 원(보이는 원 또는 투명 원)인지.
LEAFLET_HITS = """()=>{const m=courseMaps.at(-1),box=m.getContainer().getBoundingClientRect();
  const pts=[selected.conditions.origin,...selected.places];
  const hit=[...document.querySelectorAll('.plan-map path.route-hit-area')].map(p=>{const r=p.getBoundingClientRect();return {w:Math.round(r.width),h:Math.round(r.height)};});
  const points=pts.map(p=>{const c=m.latLngToContainerPoint([p.lat,p.lon]),x=box.left+c.x,y=box.top+c.y;
    const at=(dx,dy)=>document.elementFromPoint(x+dx,y+dy);
    const name=e=>e?(e.getAttribute('class')||e.tagName):'none';
    return {x:Math.round(x),y:Math.round(y),center:name(at(0,0)),ring:[[20,0],[-20,0],[0,20],[0,-20]].map(([dx,dy])=>name(at(dx,dy)))};});
  return {hit,points,pane:getComputedStyle(m.getPane('routeHits')||document.body).zIndex};}"""


def test_leaflet_course_points_get_a_44px_touch_area_under_the_visible_circles(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 844})
    page.evaluate(LEAFLET_CAPTURE)
    generate(page)
    page.wait_for_function("document.querySelector('#plan-map-slot .fallback-plan-map')&&courseMaps.length", timeout=20000)
    page.wait_for_function("!courseMaps.at(-1)._animatingZoom")
    page.locator('#plan-map-slot .fallback-plan-map').scroll_into_view_if_needed()
    page.wait_for_timeout(400)
    state = page.evaluate(LEAFLET_HITS)
    points = state['points']
    assert state['pane'] == '385', state
    assert len(state['hit']) == len(points) and all(h['w'] >= 44 and h['h'] >= 44 for h in state['hit']), state
    # 지도 안에 보이는 점만 본다(맞춤 확대라 모두 보여야 함).
    assert points, state
    for p in points:
        # 가운데는 보이는 원(투명 원이 덮지 않음), 둘레 20px 은 지도 바탕이 아니라 원이 받는다.
        assert 'leaflet-interactive' in p['center'] and 'route-hit-area' not in p['center'], p
        assert all('leaflet-interactive' in r for r in p['ring']), p
    # 데스크톱(넓은 화면, 마우스)은 투명 원을 그리지 않는다.
    page.set_viewport_size({'width': 1440, 'height': 1000})
    page.wait_for_function("document.querySelector('#plan-map-rail .fallback-plan-map')", timeout=20000)
    page.wait_for_function("courseMaps.at(-1).getContainer().closest('#plan-map-rail')")
    assert page.locator('#plan-map-rail path.route-hit-area').count() == 0
    assert not errors, errors
