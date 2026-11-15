"""코스 지도의 팝업 표시 층(1단계 1c): 실제 브라우저, /api/popups 는 page.route 가짜 응답.

네이버 지도는 SDK 를 대신하는 가짜 객체(test_feedback_ui.NAVER_STUB 를 넓힌 것)로, Leaflet 대체 지도는 저장소에 든 실제 Leaflet 으로 본다.
실제 네이버 지도 SDK 와의 연결은 이 테스트가 확인하지 않는다(외부 요청을 막음)."""

import json

from test_feedback_ui import route_festivals
from test_functional_audit import audit_page, generate  # noqa: F401
from test_popup_course_ui import AREA, BUILDING, WORLD, Api, idle
from test_popup_ui import payload, post

LONG = BUILDING | dict(
    hub_id="seoul-long",
    name="롯데백화점 본점 에비뉴엘 SUPERLONGHUBNAMEWITHOUTSPACESFORTESTING 지하 1층 행사장",
    district="중구",
    lat=37.565,
    lon=126.981,
)
# 거점 셋(더현대 글 5건, 성수 일대 글 2건, 긴 이름 건물 1건) + 위치 미확인 글 1건.
MAP = payload(
    "ready",
    [post(i, title=f"더현대 글 {i}", place=BUILDING) for i in range(1, 6)]
    + [
        post(6, title="<img src=x id=xss-pop> 성수 글", place=AREA),
        post(7, title="성수 글 둘", place=AREA),
        post(8, title="긴 이름 건물 글", place=LONG),
        post(9, title="위치 모르는 글"),
    ],
)
ONE = payload("ready", [post(20, title="롯데월드몰 글", place=WORLD)])
DEMO = dict(
    mode="demo",
    region="서울",
    visit_date="2026-10-24",
    origin=dict(name="데모 출발점", lat=37.575, lon=126.985),
)

NAVER_STUB = """()=>{
  window.__naverMarkers=[];window.__naverListeners=[];window.__fits=0;window.__opened=[];
  function LatLng(lat,lng){this.lat=()=>lat;this.lng=()=>lng;}
  window.naver={maps:{LatLng,Point:function(x,y){this.x=x;this.y=y;},LatLngBounds:function(){this.extend=()=>{};this.hasLatLng=()=>true;},
    Map:function(){this.fitBounds=()=>{window.__fits++;};this.destroy=()=>{};},
    Marker:function(options){this.options=options;this.setMap=map=>{this.removed=!map;};window.__naverMarkers.push(this);},
    Polyline:function(){},Circle:function(){},
    InfoWindow:function(options){this.content=options.content;this.open=()=>{this.isOpen=true;window.__opened.push(this.content);};this.close=()=>{this.isOpen=false;};},
    Event:{addListener:(target,name,fn)=>{const l={target,name,fn,removed:false};window.__naverListeners.push(l);return l;},removeListener:l=>{l.removed=true;}}}};
  statusData.map_js_key='stub-key';
}"""
NAVER_ACTIVE = "window.__naverMarkers.filter(m=>!m.removed&&m.options.icon.content.includes({kind}))"
POPUPS = NAVER_ACTIVE.format(kind='"popup-marker"')
FESTIVALS = NAVER_ACTIVE.format(kind='"festival-marker"')
COURSE = "window.__naverMarkers.filter(m=>!m.removed&&!/popup-marker|festival-marker/.test(m.options.icon.content))"


def test_naver_popup_layer_markers_info_cleanup_and_fallback(audit_page):
    page, base, errors = audit_page
    route_festivals(page)
    api = Api(page, default=MAP)
    # 지도가 먼저 그려지고 팝업 응답이 나중에 오는 순서를 본다.
    api.hold = {"2026-10-24"}
    page.evaluate(NAVER_STUB)
    generate(page)
    page.wait_for_function(f"{FESTIVALS}.length===2", timeout=20000)
    course = page.evaluate(f"{COURSE}.length")
    assert course >= 2 and page.evaluate(f"{POPUPS}.length") == 0
    assert page.locator(".plan-map .map-popup-note").is_hidden()
    assert page.locator(".map-legend-popups").is_hidden()
    api.held.pop("2026-10-24").fulfill(
        status=200, content_type="application/json", body=json.dumps(MAP)
    )
    idle(page)
    page.wait_for_function(f"{POPUPS}.length===3")
    # 거점당 표시 하나: 카드 묶음 수 = 표시 수(위치 미확인 글은 카드 묶음에도 지도에도 없음).
    assert page.locator("#popup-course .popup-hub").count() == 3
    assert page.evaluate("PopupCourse.mapItems.length") == 3
    markers = page.evaluate(
        f"{POPUPS}.map(m=>({{title:m.options.title,content:m.options.icon.content,z:m.options.zIndex}}))"
    )
    assert [m["title"] for m in markers] == [
        "팝업 글 장소 · 더현대 서울 · 검색된 글 5건",
        "팝업 글 장소 · 성수 일대(대략) · 검색된 글 2건",
        f"팝업 글 장소 · {LONG['name']} · 검색된 글 1건",
    ]
    # 마커 HTML 은 고정 문자열뿐(검색 결과 글자를 넣지 않음). 건물과 동네 기준점은 모양·글자로 다르다.
    assert [m["content"] for m in markers] == [
        '<span class="route-marker popup-marker">팝업</span>',
        '<span class="route-marker popup-marker popup-marker-area">팝업 일대</span>',
        '<span class="route-marker popup-marker">팝업</span>',
    ]
    note = page.locator(".plan-map .map-popup-note").inner_text()
    assert (
        "팝업 글에서 읽은 장소 3곳" in note
        and "위치를 확인하지 못한 글은 지도에 없어요" in note
    )
    assert (
        "노란 ‘축제’ 표시: 방문일 축제 2곳"
        in page.locator(".plan-map .map-festival-note").inner_text()
    )
    assert page.locator(".map-legend-popups").is_visible()
    assert (
        "점선 네모 ‘팝업 일대’는 동네 기준점"
        in page.locator(".map-legend").inner_text()
    )

    # 같은 거점의 여러 글은 정보창 목록: 처음 3건 + "외 N건". 내용은 DOM(텍스트 노드)이다.
    info = page.evaluate(
        """()=>{const l=window.__naverListeners.find(l=>!l.removed&&l.target.options?.title?.includes('더현대 서울'));l.fn();
          const c=window.__opened.at(-1);return {text:c.textContent,links:[...c.querySelectorAll('a')].map(a=>a.href)}}"""
    )
    assert "더현대 서울" in info["text"] and "건물 위치 확인" in info["text"]
    assert (
        "코스에 포함되지 않은 주변 후보예요. 기간과 장소는 원문에서 확인해 주세요."
        in info["text"]
    )
    assert "외 2건" in info["text"]
    assert info["links"] == [f"https://blog.naver.com/test/{i}" for i in (1, 2, 3)]
    area = page.evaluate(
        """()=>{const l=window.__naverListeners.find(l=>!l.removed&&l.target.options?.title?.includes('성수 일대'));l.fn();
          const c=window.__opened.at(-1);return {text:c.textContent,img:c.querySelectorAll('img').length}}"""
    )
    assert "<img src=x id=xss-pop> 성수 글" in area["text"] and area["img"] == 0
    assert "동네 기준점 성수역 · 대략 위치" in area["text"]

    # 같은 데이터를 다시 적용해도 중복 없음. 이전 표시·이벤트를 정리하고, 지도 범위(fitBounds)·코스·축제 표시는 그대로.
    fits = page.evaluate("window.__fits")
    page.evaluate(
        "PopupCourse.setMapItems(PopupCourse.mapItems);PopupCourse.setMapItems(PopupCourse.mapItems)"
    )
    assert page.evaluate(f"{POPUPS}.length") == 3
    assert (
        page.evaluate(
            "window.__naverMarkers.filter(m=>m.options.icon.content.includes('popup-marker')&&m.removed).length"
        )
        == 6
    )
    assert (
        page.evaluate(
            "window.__naverListeners.filter(l=>l.target.options?.icon?.content?.includes('popup-marker')&&!l.removed).length"
        )
        == 3
    )
    assert page.evaluate("window.__fits") == fits
    assert page.evaluate(f"{COURSE}.length") == course
    assert page.evaluate(f"{FESTIVALS}.length") == 2

    # 네이버 인증 실패로 Leaflet 으로 바뀌어도 지금 세대의 팝업 표시가 남는다(네이버 쪽 표시는 지움).
    page.evaluate(
        "document.querySelectorAll('.plan-map').forEach(w=>w.showMapFallback())"
    )
    page.wait_for_function(
        "document.querySelectorAll('.plan-map .popup-divicon').length===3"
    )
    assert page.evaluate(f"{POPUPS}.length") == 0
    assert page.locator(".plan-map .festival-circle").count() == 2
    assert page.locator(".plan-map .popup-marker-area").all_inner_texts() == [
        "팝업 일대"
    ]
    assert "3곳" in page.locator(".plan-map .map-popup-note").inner_text()


def test_leaflet_popup_layer_lifecycle_view_and_failures(audit_page):
    page, base, errors = audit_page
    route_festivals(page)
    api = Api(page, default=MAP)
    api.by_day["2026-12-01"] = (200, ONE)
    api.by_day["2026-12-02"] = (500, {"detail": "점검용 연결 실패"})
    page.evaluate(
        """()=>{statusData.map_js_key=null;window.courseMaps=[];window.itemsAtMap=[];const create=L.map;
          L.map=function(...args){const map=create(...args);window.courseMaps.push(map);window.itemsAtMap.push(PopupCourse.mapItems.length);return map;};}"""
    )
    generate(page)
    page.wait_for_function(
        "document.querySelectorAll('.plan-map .popup-divicon').length===3",
        timeout=20000,
    )
    # 팝업 응답이 지도를 만들기 전에 와 있었고(지도 초기화 전 응답), 지도가 그 데이터를 그렸다.
    assert page.evaluate("itemsAtMap.at(-1)") == 3
    assert page.locator(".plan-map .festival-circle").count() == 2
    marks = page.locator(".plan-map .popup-divicon")
    assert marks.locator(".popup-marker").all_inner_texts() == [
        "팝업",
        "팝업 일대",
        "팝업",
    ]
    assert marks.nth(1).locator(".popup-marker-area").count() == 1
    assert (
        marks.nth(0).get_attribute("title")
        == "팝업 글 장소 · 더현대 서울 · 검색된 글 5건"
    )
    # 팝업 표시는 이동선에 잇지 않는다: 이동선은 코스 지점 사이 구간 수 그대로.
    legs = page.evaluate("selected.places.length+(selected.conditions.return_home?1:0)")
    assert page.locator(".plan-map path.route-leg").count() == legs
    page.wait_for_function("!courseMaps.at(-1)._animatingZoom")
    page.wait_for_timeout(400)
    view = "(()=>{const m=courseMaps.at(-1),c=m.getCenter();return [c.lat.toFixed(6),c.lng.toFixed(6),m.getZoom()]})()"
    before = page.evaluate(view)
    page.evaluate(
        "PopupCourse.setMapItems(PopupCourse.mapItems);PopupCourse.setMapItems(PopupCourse.mapItems)"
    )
    assert marks.count() == 3 and page.evaluate(view) == before

    # 표시를 누르면 거점 이름·안내·글 목록(처음 3건 + 외 N건). 팝업 표시는 지도 범위를 넓히지 않으므로
    # 코스 범위 밖 거점의 표시는 화면 밖일 수 있어 클릭 이벤트를 직접 보낸다.
    marks.nth(0).dispatch_event("click")
    info = page.locator(".plan-map .leaflet-popup-content .popup-map-info")
    info.wait_for()
    assert (
        "코스에 포함되지 않은 주변 후보예요" in info.inner_text()
        and "외 2건" in info.inner_text()
    )
    assert info.locator("a").count() == 3
    # 긴 이름: 정보창을 연 채로 4개 폭에서 문서 가로 넘침이 없다.
    marks.nth(2).dispatch_event("click")
    page.wait_for_function(
        "document.querySelector('.leaflet-popup-content')?.textContent.includes('SUPERLONG')"
    )
    for width in (320, 390, 768, 1440):
        page.set_viewport_size({"width": width, "height": 900})
        page.wait_for_timeout(150)
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), width
    page.set_viewport_size({"width": 1440, "height": 1000})

    # 코스 탭을 바꿔 지도를 다시 그려도 팝업 표시가 남고, 이전 지도의 표시는 남지 않는다.
    count = page.evaluate("courseMaps.length")
    page.locator(".map-option-tabs button").nth(1).click()
    page.wait_for_function("count=>courseMaps.length>count", arg=count)
    page.wait_for_function(
        "document.querySelectorAll('.plan-map .popup-divicon').length===3"
    )
    assert page.locator(".popup-divicon").count() == 3

    # 늦은 응답: 새 조건을 고르면 이전 표시를 바로 지우고, 더 늦게 온 이전 응답은 표시를 바꾸지 않는다.
    page.evaluate("AbortController.prototype.abort=function(){}")
    api.hold = {"2026-11-30"}
    page.evaluate("c=>PopupCourse.load(c)", DEMO | dict(visit_date="2026-11-30"))
    page.wait_for_function(
        "document.querySelectorAll('.plan-map .popup-divicon').length===0"
    )
    page.evaluate("c=>PopupCourse.load(c)", DEMO | dict(visit_date="2026-12-01"))
    idle(page)
    page.wait_for_function(
        "document.querySelectorAll('.plan-map .popup-divicon').length===1"
    )
    api.held.pop("2026-11-30").fulfill(
        status=200, content_type="application/json", body=json.dumps(MAP)
    )
    page.wait_for_timeout(300)
    assert marks.count() == 1
    assert (
        marks.nth(0).get_attribute("title")
        == "팝업 글 장소 · 롯데월드몰 · 검색된 글 1건"
    )

    # 팝업 조회 실패: 팝업 표시만 없어지고 코스·축제 표시(원·이동선)와 지도 보기는 그대로.
    paths = page.locator(".plan-map .leaflet-overlay-pane path").count()
    page.wait_for_function("!courseMaps.at(-1)._animatingZoom")
    before = page.evaluate(view)
    page.evaluate("c=>PopupCourse.load(c)", DEMO | dict(visit_date="2026-12-02"))
    idle(page)
    page.wait_for_selector("#popup-course .popup-state-error")
    assert marks.count() == 0
    assert page.locator(".plan-map .festival-circle").count() == 2
    assert page.locator(".plan-map .leaflet-overlay-pane path").count() == paths
    assert page.evaluate(view) == before
    assert page.locator(".plan-map .map-popup-note").is_hidden()
    assert page.locator(".map-legend-popups").is_hidden()


LEAFLET_CAPTURE = """()=>{statusData.map_js_key=null;window.courseMaps=[];const create=L.map;
  L.map=function(...args){const map=create(...args);window.courseMaps.push(map);return map;};}"""
# 정보창(바깥 틀·본문 글자)과 지도 왼쪽 위 확대·축소 단추의 화면 위치.
LEAFLET_INFO_BOX = """()=>{const map=document.querySelector('.plan-map .leaflet-container'),r=e=>e.getBoundingClientRect();
  const a=r(map),z=r(map.querySelector('.leaflet-control-zoom')),p=r(map.querySelector('.leaflet-popup-content-wrapper')),t=r(map.querySelector('.leaflet-popup-content .popup-map-info'));
  return {mapLeft:a.left,mapRight:a.right,zoomRight:z.right,zoomBottom:z.bottom,popLeft:p.left,popRight:p.right,popTop:p.top,textLeft:t.left,textRight:t.right}}"""


def test_leaflet_info_window_clears_the_zoom_buttons_at_narrow_widths(audit_page):
    """정보창 왼쪽 글자가 확대·축소 단추에 가리던 문제(운영 390px)의 회귀 검사. 거점을 지도 왼쪽 끝에 두고 정보창을 연다."""
    page, base, errors = audit_page
    route_festivals(page)
    Api(page, default=MAP)
    page.evaluate(LEAFLET_CAPTURE)
    generate(page)
    page.wait_for_function(
        "document.querySelectorAll('.plan-map .popup-divicon').length===3", timeout=20000
    )
    for width in (390, 320):
        # 지도 움직임(첫 맞춤·자동 이동)이 끝난 뒤 폭을 바꾼다. 움직이는 중에 지도를 지우면 Leaflet 이 _leaflet_pos 오류를 낸다(테스트 순서 문제).
        page.wait_for_function("!courseMaps.at(-1)._animatingZoom")
        page.wait_for_timeout(700)
        page.set_viewport_size({"width": width, "height": 844})
        # 좁은 화면에서는 지도가 코스 카드 뒤(#plan-map-slot)로 옮겨 다시 그려진다.
        page.wait_for_function(
            "document.querySelector('#plan-map-slot .plan-map .popup-divicon')", timeout=20000
        )
        page.wait_for_timeout(400)
        page.wait_for_function("!courseMaps.at(-1)._animatingZoom")
        page.evaluate("courseMaps.at(-1).closePopup()")
        page.evaluate(
            """()=>{const m=courseMaps.at(-1),s=m.getSize(),p=m.containerPointToLatLng([4,Math.round(s.y*0.75)]);
              const g=PopupCourse.mapItems.find(g=>g.hub.level==='area_anchor');
              PopupCourse.setMapItems([{...g,hub:{...g.hub,lat:p.lat,lon:p.lng}}]);}"""
        )
        # 앞서 연 정보창은 Leaflet 이 200ms 동안 흐려지며 닫힌 뒤 지운다.
        page.wait_for_timeout(300)
        page.locator(".plan-map .popup-divicon").first.dispatch_event("click")
        page.locator(".plan-map .leaflet-popup-content .popup-map-info").wait_for()
        # 자동 이동(패닝)이 끝날 때까지 기다린다.
        page.wait_for_timeout(700)
        box = page.evaluate(LEAFLET_INFO_BOX)
        # 정보창 전체가 단추 오른쪽에서 시작하고 지도 오른쪽 끝을 넘지 않는다(글자가 단추 밑에 깔리지 않음).
        assert box["popLeft"] >= box["zoomRight"], (width, box)
        assert box["popRight"] <= box["mapRight"], (width, box)
        assert box["textLeft"] >= box["zoomRight"] and box["textRight"] <= box["mapRight"], (width, box)
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), width


def test_naver_info_window_keeps_room_for_the_zoom_buttons(audit_page):
    """네이버 지도(가짜 SDK): 정보창 자동 이동 여백이 왼쪽 위 확대·축소 단추 너비보다 넓고, 정보창 너비가 그 여백을 뺀 지도 너비 안에 든다.
    실제 SDK 의 자동 이동 동작은 이 테스트가 확인하지 않는다(외부 요청을 막음)."""
    page, base, errors = audit_page
    route_festivals(page)
    Api(page, default=MAP)
    page.evaluate(NAVER_STUB)
    page.evaluate(
        """()=>{const Info=naver.maps.InfoWindow;window.__infoOptions=[];
          naver.maps.InfoWindow=function(options){Info.call(this,options);window.__infoOptions.push(options);};}"""
    )
    generate(page)
    # 좁은 화면에서는 지도가 코스 카드 뒤로 옮겨 다시 그려진다.
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_function("document.querySelector('#plan-map-slot .plan-map')")
    page.wait_for_function(f"{POPUPS}.length===3", timeout=20000)
    result = page.evaluate(
        """()=>{const l=window.__naverListeners.find(l=>!l.removed&&l.target.options?.title?.includes('성수 일대'));l.fn();
          const c=window.__opened.at(-1),o=window.__infoOptions.find(o=>o.content===c),canvas=document.querySelector('.plan-map .naver-plan-map');
          return {padX:o.autoPanPadding?.x,padY:o.autoPanPadding?.y,disabled:!!o.disableAutoPan,map:canvas.clientWidth,max:parseFloat(c.style.maxWidth)}}"""
    )
    # 네이버 큰 확대·축소 단추(왼쪽 위, 기본 위치)의 오른쪽 끝보다 넓은 여백.
    assert result["padX"] >= 56 and result["padY"] >= 20 and not result["disabled"], result
    # 정보창(본문 칸 + 안쪽 여백 24px + 테두리 2px)과 양쪽 여백이 지도 너비 안에 든다.
    assert result["max"] + 24 + 2 + 2 * result["padX"] <= result["map"], result
