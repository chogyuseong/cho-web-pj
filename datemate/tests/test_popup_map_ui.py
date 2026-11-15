"""코스 지도의 팝업 표시 층(1단계 1c): 실제 브라우저, /api/popups 는 page.route 가짜 응답.

네이버 지도는 SDK 를 대신하는 가짜 객체(test_feedback_ui.NAVER_STUB 를 넓힌 것)로, Leaflet 대체 지도는 저장소에 든 실제 Leaflet 으로 본다.
실제 네이버 지도 SDK 와의 연결은 이 테스트가 확인하지 않는다(외부 요청을 막음)."""

import json
import os
import socket
import threading
import time
from urllib.parse import urlsplit

import pytest
import uvicorn
from test_content_security_policy import INIT, offline_routes, poll
from test_feedback_ui import route_festivals
from test_functional_audit import audit_page, generate  # noqa: F401
from test_popup_course_ui import AREA, BUILDING, WORLD, Api, idle
from test_popup_ui import payload, post

from app.main import app as main_app

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

    # 같은 거점의 여러 글은 지도 아래 정보 칸의 목록: 처음 3건 + "외 N건". 내용은 DOM(텍스트 노드)이다. 지도 안 정보창은 열지 않는다.
    info = page.evaluate(
        """()=>{const l=window.__naverListeners.find(l=>!l.removed&&l.target.options?.title?.includes('더현대 서울'));l.fn();
          const c=document.querySelector('.plan-map .map-popup-panel .popup-map-info');return {text:c.textContent,links:[...c.querySelectorAll('a')].map(a=>a.href)}}"""
    )
    assert page.evaluate("window.__opened.length") == 0
    assert "더현대 서울" in info["text"] and "건물 위치 확인" in info["text"]
    assert (
        "코스에 포함되지 않은 주변 후보예요. 기간과 장소는 원문에서 확인해 주세요."
        in info["text"]
    )
    assert "외 2건" in info["text"]
    assert info["links"] == [f"https://blog.naver.com/test/{i}" for i in (1, 2, 3)]
    area = page.evaluate(
        """()=>{const l=window.__naverListeners.find(l=>!l.removed&&l.target.options?.title?.includes('성수 일대'));l.fn();
          const c=document.querySelector('.plan-map .map-popup-panel .popup-map-info');return {text:c.textContent,img:c.querySelectorAll('img').length}}"""
    )
    assert "<img src=x id=xss-pop> 성수 글" in area["text"] and area["img"] == 0
    assert "동네 기준점 성수역 · 대략 위치" in area["text"]
    # 지도 아래 장소 단추: 거점마다 하나, 지도 표시를 누르면 그 단추가 열림 상태가 된다(한 번에 하나).
    chips = page.locator(".plan-map .map-popup-hub")
    assert chips.evaluate_all("cs=>cs.map(c=>c.textContent)") == [
        "팝업더현대 서울 · 글 5건",
        "팝업 일대성수 일대(대략) · 글 2건",
        f"팝업{LONG['name']} · 글 1건",
    ]
    assert chips.evaluate_all("cs=>cs.map(c=>c.getAttribute('aria-expanded'))") == [
        "false",
        "true",
        "false",
    ]

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
    # 지도 아래 장소 단추도 새 지도 기준으로 하나씩만 남고, 열려 있던 정보 칸은 닫힌다.
    assert page.locator(".map-popup-hubs").count() == 1
    assert page.locator(".plan-map .map-popup-hub").count() == 3
    assert page.locator(".plan-map .map-popup-panel").is_hidden()


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

    # 표시를 누르면 지도 아래 정보 칸에 거점 이름·안내·글 목록(처음 3건 + 외 N건). 지도 안 정보창(Leaflet 팝업)은 열지 않는다.
    # 팝업 표시는 지도 범위를 넓히지 않으므로 코스 범위 밖 거점의 표시는 화면 밖일 수 있어 클릭 이벤트를 직접 보낸다.
    marks.nth(0).dispatch_event("click")
    info = page.locator(".plan-map .map-popup-panel .popup-map-info")
    info.wait_for()
    assert (
        "코스에 포함되지 않은 주변 후보예요" in info.inner_text()
        and "외 2건" in info.inner_text()
    )
    assert info.locator("a").count() == 3
    assert page.locator(".plan-map .leaflet-popup").count() == 0
    # 긴 이름: 정보 칸을 연 채로 4개 폭에서 문서 가로 넘침이 없다.
    marks.nth(2).dispatch_event("click")
    page.wait_for_function(
        "document.querySelector('.plan-map .map-popup-panel')?.textContent.includes('SUPERLONG')"
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
    # 지도 아래 장소 단추도 새 지도의 것 한 벌만 있고, 정보 칸은 닫혀 있다.
    assert page.locator(".map-popup-hubs").count() == 1
    assert page.locator(".map-popup-hub").count() == 3
    assert page.locator(".map-popup-panel").count() == 1
    assert page.locator(".plan-map .map-popup-panel").is_hidden()

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
    # 팝업 거점이 없으면 지도 아래 장소 단추·정보 칸도 보이지 않는다.
    assert page.locator(".plan-map .map-popup-hubs").is_hidden()
    assert page.locator(".plan-map .map-popup-hub").count() == 0
    assert page.locator(".plan-map .map-popup-panel").is_hidden()


LEAFLET_CAPTURE = """()=>{statusData.map_js_key=null;window.courseMaps=[];const create=L.map;
  L.map=function(...args){const map=create(...args);window.courseMaps.push(map);return map;};}"""
# 성수처럼 동네 기준점 거점이 출발지와 같은 좌표인 경우(나머지 거점은 그대로).
AREA_AT_ORIGIN = """()=>{const o=selected.conditions.origin;
  PopupCourse.setMapItems(PopupCourse.mapItems.map(g=>g.hub.level==='area_anchor'?{...g,hub:{...g.hub,lat:o.lat,lon:o.lon}}:g));}"""
# 장소 단추마다: 크기, 가운데 점의 맨 위 요소가 그 단추인지(가려지지 않음), 글자 크기. 화면 밖이면 elementFromPoint 가 없으므로 먼저 바로 스크롤한다.
HUB_BUTTONS = """()=>[...document.querySelectorAll('.plan-map .map-popup-hub')].map(c=>{c.scrollIntoView({block:'center',behavior:'instant'});
  const r=c.getBoundingClientRect(),top=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);
  return {w:r.width,h:r.height,top:top?.closest('.map-popup-hub')===c,font:Math.min(...[...c.querySelectorAll('span')].map(s=>parseFloat(getComputedStyle(s).fontSize))),
    controls:c.getAttribute('aria-controls')}})"""
# 열린 정보 칸: 본문 너비, 안쪽 스크롤·가로 넘침, 글자가 든 요소의 가장 작은 글자 크기.
PANEL_BOX = """()=>{const p=document.querySelector('.plan-map .map-popup-panel'),i=p.querySelector('.popup-map-info');
  const texts=[...p.querySelectorAll('*')].filter(e=>[...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim()));
  return {id:p.id,body:i.getBoundingClientRect().width,scrolls:[p,i].some(e=>e.scrollHeight>e.clientHeight+1),
    wide:[p,...p.querySelectorAll('*')].some(e=>e.scrollWidth>e.clientWidth+1),font:Math.min(...texts.map(e=>parseFloat(getComputedStyle(e).fontSize))),
    name:i.querySelector('strong').textContent,page:document.documentElement.scrollWidth<=innerWidth}}"""
EXPANDED = "[...document.querySelectorAll('.plan-map .map-popup-hub')].map(c=>c.getAttribute('aria-expanded'))"


def narrow(page, width):
    """폭을 바꾸고 좁은 화면 자리(#plan-map-slot)에 다시 그려진 지도가 멈출 때까지 기다린다.
    지도가 움직이는 중에 폭을 바꿔도 된다(지우기 전에 확대 애니메이션을 마침, test_leaflet_dispose_during_zoom.py)."""
    page.set_viewport_size({"width": width, "height": 844})
    page.wait_for_function(
        "document.querySelector('#plan-map-slot .plan-map .popup-divicon')", timeout=20000
    )
    page.wait_for_timeout(400)
    page.wait_for_function("!courseMaps.at(-1)._animatingZoom")


def test_hub_buttons_open_every_popup_hub_below_the_map_at_narrow_widths(audit_page):
    """지도 위 '팝업 일대' 표시가 출발·번호 표시에 깔려 누를 자리가 좁고, 지도 안 정보창 본문이 좁던 문제(운영 390px)의 회귀 검사(Leaflet).
    지도 아래 장소 단추로 모든 거점을 44px 이상의 가려지지 않은 자리에서 열고, 정보는 지도 아래 칸에 지도 폭으로 보인다."""
    page, base, errors = audit_page
    route_festivals(page)
    Api(page, default=MAP)
    page.evaluate(LEAFLET_CAPTURE)
    generate(page)
    page.wait_for_function(
        "document.querySelectorAll('.plan-map .popup-divicon').length===3", timeout=20000
    )
    for width in (390, 320):
        narrow(page, width)
        page.evaluate(AREA_AT_ORIGIN)
        page.wait_for_function("document.querySelectorAll('.plan-map .map-popup-hub').length===3")
        chips = page.locator(".plan-map .map-popup-hub")
        # 지도에 올라간 거점 수 = 장소 단추 수. 정보 칸은 닫혀 있다.
        assert page.locator(".plan-map .popup-divicon").count() == 3
        assert page.evaluate(EXPANDED) == ["false"] * 3
        assert page.locator(".plan-map .map-popup-panel").is_hidden()
        panel_id = page.locator(".plan-map .map-popup-panel").get_attribute("id")
        names = page.evaluate("PopupCourse.mapItems.map(g=>PopupCourse.label(g.hub))")
        for i, chip in enumerate(page.evaluate(HUB_BUTTONS)):
            assert chip["w"] >= 44 and chip["h"] >= 44 and chip["top"], (width, i, chip)
            assert chip["font"] >= 14 and chip["controls"] == panel_id, (width, i, chip)
            chips.nth(i).click()
            expanded = ["false"] * 3
            expanded[i] = "true"
            assert page.evaluate(EXPANDED) == expanded, (width, i)
            box = page.evaluate(PANEL_BOX)
            assert box["id"] == panel_id and box["name"] == names[i], (width, i, box)
            # 390px 에서는 본문 220px 이상, 320px 에서도 가로 넘침·안쪽 스크롤 없음. 글자 14px 이상.
            assert box["body"] >= (220 if width == 390 else 200), (width, i, box)
            assert not box["scrolls"] and not box["wide"] and box["page"], (width, i, box)
            assert box["font"] >= 14, (width, i, box)
        # 같은 단추를 다시 누르면 닫힌다. 지도 안 정보창은 열리지 않는다.
        chips.nth(2).click()
        assert page.evaluate(EXPANDED) == ["false"] * 3
        assert page.locator(".plan-map .map-popup-panel").is_hidden()
        assert page.locator(".plan-map .leaflet-popup").count() == 0
        # 출발지와 같은 자리의 지도 표시를 눌러도 같은 정보 칸이 열리고 그 장소 단추가 열림 상태가 된다.
        page.locator(".plan-map .popup-divicon").nth(1).dispatch_event("click")
        assert page.evaluate(EXPANDED) == ["false", "true", "false"], width
        assert page.locator(".plan-map .map-popup-panel").is_visible()
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), width
        chips.nth(1).click()


def test_hub_buttons_and_panel_work_with_the_keyboard(audit_page):
    """Tab 으로 장소 단추에 가서 Enter 로 열고 닫는다. 정보 칸 안에서 Esc·「정보 닫기」는 칸을 닫고 그 단추로 돌아간다.
    지도 위 표시(Leaflet, 키보드 포커스)에서 Enter 를 눌러도 같은 칸이 열린다."""
    page, base, errors = audit_page
    route_festivals(page)
    Api(page, default=MAP)
    page.evaluate(LEAFLET_CAPTURE)
    generate(page)
    page.wait_for_function(
        "document.querySelectorAll('.plan-map .map-popup-hub').length===3", timeout=20000
    )
    narrow(page, 390)
    chips = page.locator(".plan-map .map-popup-hub")
    focused = "document.activeElement.closest('.map-popup-hub,.map-popup-panel,.popup-divicon')?.className||document.activeElement.tagName"
    # 앞 요소에서 Tab 으로 첫 단추에 닿는다.
    page.evaluate(
        "()=>{const n=document.querySelector('.plan-map .map-popup-note');n.tabIndex=-1;n.focus();}"
    )
    page.keyboard.press("Tab")
    assert page.evaluate(
        "document.activeElement===document.querySelector('.plan-map .map-popup-hub')"
    )
    page.keyboard.press("Enter")
    assert page.evaluate(EXPANDED) == ["true", "false", "false"]
    assert page.locator(".plan-map .map-popup-panel").is_visible()
    page.keyboard.press("Enter")
    assert page.evaluate(EXPANDED) == ["false"] * 3
    assert page.locator(".plan-map .map-popup-panel").is_hidden()
    # 둘째 단추를 열고 Tab 으로 칸 안 첫 글 링크까지 간 뒤 Esc: 닫히고 둘째 단추로 돌아온다.
    page.keyboard.press("Tab")
    page.keyboard.press("Enter")
    assert page.evaluate(EXPANDED) == ["false", "true", "false"]
    page.keyboard.press("Tab")
    page.keyboard.press("Tab")
    assert page.evaluate(
        "document.activeElement===document.querySelector('.plan-map .map-popup-panel a')"
    ), page.evaluate(focused)
    page.keyboard.press("Escape")
    assert page.evaluate(EXPANDED) == ["false"] * 3
    assert page.evaluate("document.activeElement===document.querySelectorAll('.plan-map .map-popup-hub')[1]")
    # 「정보 닫기」 단추도 같다.
    page.keyboard.press("Enter")
    page.locator(".plan-map .map-popup-close").focus()
    page.keyboard.press("Enter")
    assert page.evaluate(EXPANDED) == ["false"] * 3
    assert page.evaluate("document.activeElement===document.querySelectorAll('.plan-map .map-popup-hub')[1]")
    # 지도 위 표시에 포커스를 두고 Enter.
    page.locator(".plan-map .popup-divicon").nth(0).focus()
    page.keyboard.press("Enter")
    assert page.evaluate(EXPANDED) == ["true", "false", "false"]
    assert chips.nth(0).get_attribute("aria-controls") == page.locator(
        ".plan-map .map-popup-panel"
    ).get_attribute("id")


AT_ORIGIN = """()=>{const o=selected.conditions.origin,g=PopupCourse.mapItems.find(g=>g.hub.level==='area_anchor');
  PopupCourse.setMapItems([{...g,hub:{...g.hub,lat:o.lat,lon:o.lon}}]);}"""


def test_naver_popup_marker_stays_under_the_course_markers(audit_page):
    """성수에서 '팝업 일대'가 출발 표시와 같은 자리에 겹쳐 출발 표시를 가리던 문제의 회귀 검사(가짜 SDK, 쌓임 순서).
    팝업 표시 좌표는 그대로 두고, 코스 표시가 팝업 표시보다 위, 축제 표시보다 아래에 오게 한다."""
    page, base, errors = audit_page
    route_festivals(page)
    Api(page, default=MAP)
    page.evaluate(NAVER_STUB)
    generate(page)
    page.wait_for_function(f"{POPUPS}.length===3", timeout=20000)
    page.wait_for_function(f"{FESTIVALS}.length===2")
    page.evaluate(AT_ORIGIN)
    z = page.evaluate(
        f"""()=>{{const o=selected.conditions.origin,p={POPUPS}[0];
          return {{course:{COURSE}.map(m=>m.options.zIndex),popup:p.options.zIndex,festival:{FESTIVALS}.map(m=>m.options.zIndex),
            same:p.options.position.lat()===o.lat&&p.options.position.lng()===o.lon}}}}"""
    )
    # 좌표는 출발지 그대로(일대 표시를 옮기지 않음).
    assert z["same"], z
    assert z["course"] and all(c is not None and c > z["popup"] for c in z["course"]), z
    assert all(f > c for f in z["festival"] for c in z["course"]), z


def test_leaflet_popup_marker_stays_under_the_course_markers(audit_page):
    """Leaflet: 팝업 표시가 코스 원(출발·번호)과 같은 자리여도 코스 원이 위에 보이고 눌리며, 팝업 표시는 드러난 부분으로 눌린다."""
    page, base, errors = audit_page
    route_festivals(page)
    Api(page, default=MAP)
    page.evaluate(LEAFLET_CAPTURE)
    generate(page)
    page.wait_for_function(
        "document.querySelectorAll('.plan-map .popup-divicon').length===3", timeout=20000
    )
    page.wait_for_function("!courseMaps.at(-1)._animatingZoom")
    page.wait_for_timeout(300)
    page.evaluate(AT_ORIGIN)
    hit = page.evaluate(
        """()=>{const m=courseMaps.at(-1),o=selected.conditions.origin,p=m.latLngToContainerPoint([o.lat,o.lon]),
            box=m.getContainer().getBoundingClientRect(),x=box.left+p.x,y=box.top+p.y;
          const mark=document.querySelector('.plan-map .popup-divicon .popup-marker').getBoundingClientRect();
          const top=document.elementFromPoint(x,y),edge=document.elementFromPoint(mark.left+4,y);
          return {center:top.tagName.toLowerCase()+'.'+(top.getAttribute('class')||''),edge:edge.closest('.popup-divicon')?'popup':edge.tagName,
            markX:Math.round(mark.left+mark.width/2-x),markY:Math.round(mark.top+mark.height/2-y)}}"""
    )
    # 팝업 표시의 가운데는 여전히 출발지 좌표(위치를 어긋내지 않음).
    assert abs(hit["markX"]) <= 1 and abs(hit["markY"]) <= 1, hit
    # 출발지 자리에서 맨 위는 코스 원(SVG 경로)이다.
    assert hit["center"].startswith("path.") and "leaflet-interactive" in hit["center"], hit
    # 원 밖으로 드러난 팝업 표시 왼쪽 끝은 팝업 표시가 받는다.
    assert hit["edge"] == "popup", hit
    assert page.locator(".plan-map .leaflet-tooltip").filter(has_text="출발 · ").first.is_visible()


def test_naver_hub_buttons_and_markers_open_the_panel_below_the_map(audit_page):
    """네이버 지도(가짜 SDK): 동네 기준점이 출발지와 같은 좌표여도 지도 아래 장소 단추(44px 이상, 가려지지 않음)로 모든 거점을 열고,
    지도 표시를 눌러도 지도 안 정보창(InfoWindow) 대신 같은 정보 칸이 열린다. 거점이 없어지거나 지도를 정리하면 단추·칸도 사라진다.
    실제 SDK 화면은 이 테스트가 확인하지 않는다(외부 요청을 막음)."""
    page, base, errors = audit_page
    route_festivals(page)
    Api(page, default=MAP)
    page.evaluate(NAVER_STUB)
    page.evaluate(
        """()=>{const Info=naver.maps.InfoWindow;window.__infoContents=[];
          naver.maps.InfoWindow=function(options){Info.call(this,options);window.__infoContents.push(options.content);};}"""
    )
    generate(page)
    # 좁은 화면에서는 지도가 코스 카드 뒤로 옮겨 다시 그려진다.
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_function("document.querySelector('#plan-map-slot .plan-map')")
    page.wait_for_function(f"{POPUPS}.length===3", timeout=20000)
    page.evaluate(AREA_AT_ORIGIN)
    page.wait_for_function(f"{POPUPS}.length===3")
    names = page.evaluate("PopupCourse.mapItems.map(g=>PopupCourse.label(g.hub))")
    chips = page.locator(".plan-map .map-popup-hub")
    for width in (390, 320):
        page.set_viewport_size({"width": width, "height": 844})
        page.wait_for_timeout(200)
        for i, chip in enumerate(page.evaluate(HUB_BUTTONS)):
            assert chip["w"] >= 44 and chip["h"] >= 44 and chip["top"] and chip["font"] >= 14, (width, i, chip)
            chips.nth(i).click()
            box = page.evaluate(PANEL_BOX)
            assert box["name"] == names[i] and box["id"] == chip["controls"], (width, i, box)
            assert box["body"] >= (220 if width == 390 else 200), (width, i, box)
            assert not box["scrolls"] and not box["wide"] and box["page"] and box["font"] >= 14, (width, i, box)
        chips.nth(2).click()
        assert page.evaluate(EXPANDED) == ["false"] * 3
    # 출발지와 같은 좌표의 '팝업 일대' 표시를 누르면 같은 칸이 열린다. 팝업용 InfoWindow 는 만들지 않는다.
    page.evaluate(
        "()=>window.__naverListeners.find(l=>!l.removed&&l.target.options?.title?.includes('성수 일대')).fn()"
    )
    assert page.evaluate(EXPANDED) == ["false", "true", "false"]
    assert page.evaluate(
        "window.__infoContents.filter(c=>c?.classList?.contains('popup-map-info')).length"
    ) == 0
    # 거점이 없어지면 단추·칸이 보이지 않는다.
    page.evaluate("window.__items=PopupCourse.mapItems;PopupCourse.setMapItems([])")
    assert page.locator(".plan-map .map-popup-hubs").is_hidden()
    assert page.locator(".plan-map .map-popup-panel").is_hidden()
    assert chips.count() == 0
    # 다시 올리고 칸을 연 채로 지도를 정리(disposeMap, 코스 탭 전환 때와 같은 정리)하면 표시·단추·칸이 모두 사라진다.
    page.evaluate("PopupCourse.setMapItems(window.__items)")
    chips.nth(0).click()
    assert page.locator(".plan-map .map-popup-panel").is_visible()
    page.evaluate("document.querySelector('.plan-map').disposeMap()")
    assert page.evaluate(f"{POPUPS}.length") == 0
    assert chips.count() == 0
    assert page.locator(".plan-map .map-popup-hubs").is_hidden()
    assert page.locator(".plan-map .map-popup-panel").is_hidden()
    # 정리한 지도에는 다시 적용해도 그리지 않는다.
    page.evaluate("PopupCourse.setMapItems(window.__items)")
    assert chips.count() == 0


def many_hubs(count):
    """거점 count 곳(건물·동네 기준점을 번갈아), 거점마다 글 2건. 받은 순서(데모 코스는 출발지 기준이 없음)가 거점 순서다."""
    posts = []
    for i in range(count):
        base = AREA if i % 2 else BUILDING
        place = base | dict(
            hub_id=f"seoul-many-{i}",
            name=f"거점{i} " + ("일대" if i % 2 else "백화점"),
            lat=37.53 + i * 0.004,
            lon=126.95 + i * 0.006,
        )
        posts += [post(i * 10 + j, title=f"거점{i} 글 {j}", place=place) for j in (1, 2)]
    return payload("ready", posts)


VISIBLE = "[...document.querySelectorAll('.plan-map .map-popup-hub')].map(c=>!c.hidden&&c.getBoundingClientRect().height>0)"
MORE = """()=>{const b=document.querySelector('.plan-map .map-popup-more');return b&&{text:b.textContent,expanded:b.getAttribute('aria-expanded'),
  controls:b.getAttribute('aria-controls'),list:document.querySelector('.plan-map .map-popup-hubs').id,h:b.getBoundingClientRect().height,
  font:parseFloat(getComputedStyle(b).fontSize),last:b===b.parentElement.lastElementChild}}"""


def test_many_hub_buttons_fold_behind_a_more_button(audit_page):
    """거점이 많으면 앞의 3곳만 보이고 「장소 n곳 더 보기」(aria-expanded)로 펼치고 다시 접는다(Leaflet, 390px·320px).
    접힌 거점을 지도 표시로 열면 목록이 펼쳐져 그 단추가 보이고, 열린 거점이 숨는 쪽이면 접을 때 칸을 닫는다."""
    page, base, errors = audit_page
    route_festivals(page)
    Api(page, default=many_hubs(8))
    page.evaluate(LEAFLET_CAPTURE)
    generate(page)
    page.wait_for_function(
        "document.querySelectorAll('.plan-map .popup-divicon').length===8", timeout=20000
    )
    for width in (390, 320):
        narrow(page, width)
        # 폭마다 같은 데이터를 다시 적용해 처음(접힌) 상태에서 본다.
        page.evaluate("PopupCourse.setMapItems(PopupCourse.mapItems)")
        chips = page.locator(".plan-map .map-popup-hub")
        more = page.locator(".plan-map .map-popup-more")
        # 지도에는 8곳 모두, 단추는 8개 중 앞의 3개만 보인다(순서는 거점 순서 그대로).
        assert page.locator(".plan-map .popup-divicon").count() == 8
        assert chips.evaluate_all("cs=>cs.map(c=>c.textContent)") == [
            f"{'팝업 일대' if i % 2 else '팝업'}거점{i} {'일대(대략)' if i % 2 else '백화점'} · 글 2건"
            for i in range(8)
        ]
        assert page.evaluate(VISIBLE) == [True] * 3 + [False] * 5, width
        state = page.evaluate(MORE)
        assert state["text"] == "장소 5곳 더 보기" and state["expanded"] == "false", state
        assert state["controls"] == state["list"] and state["last"], state
        assert state["h"] >= 44 and state["font"] >= 14, state
        # 펼치면 모두 보이고 포커스는 새로 보인 첫 장소(넷째) 단추로 간다. 모든 단추가 44px 이상, 가려지지 않음.
        more.click()
        assert page.evaluate(VISIBLE) == [True] * 8, width
        assert page.evaluate(MORE)["text"] == "장소 목록 접기"
        assert more.get_attribute("aria-expanded") == "true"
        assert page.evaluate("document.activeElement===document.querySelectorAll('.plan-map .map-popup-hub')[3]")
        for i, chip in enumerate(page.evaluate(HUB_BUTTONS)):
            assert chip["w"] >= 44 and chip["h"] >= 44 and chip["top"] and chip["font"] >= 14, (width, i, chip)
        # 다시 접기(키보드 Enter). 포커스는 펼침 단추에 남는다.
        more.focus()
        page.keyboard.press("Enter")
        assert page.evaluate(VISIBLE) == [True] * 3 + [False] * 5
        assert more.get_attribute("aria-expanded") == "false"
        assert page.evaluate("document.activeElement.classList.contains('map-popup-more')")
        # 접힌 거점(일곱째)을 지도 표시로 열면 목록이 펼쳐지고 그 단추가 열림 상태로 보인다.
        page.locator(".plan-map .popup-divicon").nth(6).dispatch_event("click")
        assert page.evaluate(VISIBLE) == [True] * 8, width
        assert page.evaluate(EXPANDED) == ["false"] * 6 + ["true", "false"]
        assert more.get_attribute("aria-expanded") == "true"
        assert page.locator(".plan-map .map-popup-panel").is_visible()
        box = page.evaluate(PANEL_BOX)
        assert box["name"] == "거점6 백화점" and box["body"] >= (220 if width == 390 else 200), box
        assert not box["scrolls"] and not box["wide"] and box["page"] and box["font"] >= 14, box
        # 열린 거점이 숨는 쪽인데 접으면 칸도 닫는다(열린 칸의 단추가 화면에 없는 상태를 만들지 않음).
        more.click()
        assert page.evaluate(EXPANDED) == ["false"] * 8
        assert page.locator(".plan-map .map-popup-panel").is_hidden()
        # 보이는 거점(둘째)이 열린 채로 접고 펴는 것은 칸에 영향이 없다.
        chips.nth(1).click()
        more.click()
        more.click()
        assert page.evaluate(EXPANDED) == ["false", "true"] + ["false"] * 6
        assert page.locator(".plan-map .map-popup-panel").is_visible()
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), width
    # 지도 정리(disposeMap)와 함께 펼침 단추도 사라진다.
    page.evaluate("document.querySelector('.plan-map').disposeMap()")
    assert page.locator(".plan-map .map-popup-more").count() == 0
    assert page.locator(".plan-map .map-popup-hub").count() == 0


def test_hub_buttons_fold_only_above_four_hubs_on_both_maps(audit_page):
    """4곳 이하면 펼침 단추가 없고 모두 보인다. 5곳이면 3곳 + 「장소 2곳 더 보기」. 네이버 지도(가짜 SDK)에서도 접힌 거점의 표시를 누르면 펼쳐진다.
    대체 지도로 바뀌어도(인증 실패) 펼침 단추는 한 벌만, 접힌 상태로 다시 시작한다."""
    page, base, errors = audit_page
    route_festivals(page)
    Api(page, default=many_hubs(4))
    page.evaluate(NAVER_STUB)
    generate(page)
    page.wait_for_function(f"{POPUPS}.length===4", timeout=20000)
    assert page.evaluate(VISIBLE) == [True] * 4
    assert page.locator(".plan-map .map-popup-more").count() == 0
    page.evaluate(
        "items=>{const groups=PopupCourse.groups(items.posts,null);PopupCourse.setMapItems(groups)}",
        many_hubs(5),
    )
    page.wait_for_function(f"{POPUPS}.length===5")
    assert page.evaluate(VISIBLE) == [True] * 3 + [False] * 2
    assert page.evaluate(MORE)["text"] == "장소 2곳 더 보기"
    # 다섯째 거점의 네이버 표시를 누르면 펼쳐지고 그 단추가 열림 상태.
    page.evaluate(
        "()=>window.__naverListeners.find(l=>!l.removed&&l.target.options?.title?.includes('거점4 백화점')).fn()"
    )
    assert page.evaluate(VISIBLE) == [True] * 5
    assert page.evaluate(EXPANDED) == ["false"] * 4 + ["true"]
    assert page.evaluate(MORE)["expanded"] == "true"
    # 인증 실패로 Leaflet 으로 바뀌면 칸은 닫히고 목록은 다시 접힌 상태(한 벌).
    page.evaluate("document.querySelectorAll('.plan-map').forEach(w=>w.showMapFallback())")
    page.wait_for_function("document.querySelectorAll('.plan-map .popup-divicon').length===5")
    assert page.locator(".map-popup-more").count() == 1
    assert page.evaluate(VISIBLE) == [True] * 3 + [False] * 2
    assert page.locator(".plan-map .map-popup-panel").is_hidden()
    page.evaluate(
        "items=>PopupCourse.setMapItems(PopupCourse.groups(items.posts,null))", many_hubs(4)
    )
    assert page.locator(".plan-map .map-popup-more").count() == 0
    assert page.evaluate(VISIBLE) == [True] * 4


REVEALED = """id=>{const b=[...document.querySelectorAll('#popup-course .popup-hub')].find(b=>b.dataset.hubId===id),r=b.getBoundingClientRect(),
  header=parseFloat(getComputedStyle(document.documentElement).scrollPaddingTop)||0;
  return {posts:b.querySelectorAll('.popup-post').length,more:b.querySelectorAll('.popup-hub-more').length,
    focus:document.activeElement===b.querySelector('.popup-hub-name'),name:b.querySelector('.popup-hub-name').textContent,
    top:Math.round(r.top),header:Math.round(header),inView:r.top>=header-2&&r.top<innerHeight/2,
    hubsMore:document.querySelectorAll('#popup-course .popup-hubs-more').length}}"""


def test_panel_rest_line_names_the_section_and_jumps_to_the_hub_group(audit_page):
    """정보 칸의 "외 n건"은 위치("아래")를 말하지 않고 ‘팝업스토어 글’ 구역 이름으로 부르며, 「이 장소 글 n건 모두 보기」는
    그 구역의 같은 거점 묶음을 펼쳐(다른 장소·이 장소의 글 더 보기) 그곳으로 스크롤하고 거점 이름에 포커스를 둔다. 데스크톱 2단·390px 모두."""
    page, base, errors = audit_page
    route_festivals(page)
    data = many_hubs(5)
    # 다섯째 거점(구역에서는 「다른 장소 2곳 더 보기」 뒤, 지도 아래에서는 접힌 쪽)에 글을 3건 더 둔다(모두 5건).
    fifth = data["posts"][-1]["place"]
    data["posts"] += [post(100 + j, title=f"거점4 더 {j}", place=fifth) for j in range(3)]
    Api(page, default=data)
    page.evaluate(LEAFLET_CAPTURE)
    generate(page)
    page.wait_for_function(
        "document.querySelectorAll('.plan-map .popup-divicon').length===5", timeout=20000
    )
    assert page.evaluate("document.getElementById('popup-course-title').textContent").endswith(
        "팝업스토어 글"
    )
    for width in (1440, 390):
        if width == 390:
            narrow(page, width)
        # 구역을 처음 상태로 다시 그린다(앞 폭에서 펼친 묶음을 되돌림).
        page.evaluate("d=>PopupCourse.render(d,selected.conditions)", data)
        page.wait_for_function("document.querySelectorAll('.plan-map .map-popup-hub').length===5")
        assert page.evaluate("document.querySelectorAll('#popup-course .popup-hub').length") == 3
        # 글이 2건뿐인 거점은 "외 n건"·단추가 없다.
        page.locator(".plan-map .map-popup-hub").nth(0).click()
        assert page.locator(".plan-map .map-popup-panel .popup-map-goto").count() == 0
        # 접힌 다섯째 거점을 지도 표시로 연다.
        page.locator(".plan-map .popup-divicon").nth(4).dispatch_event("click")
        panel = page.locator(".plan-map .map-popup-panel")
        text = panel.inner_text()
        assert "외 2건은 ‘팝업스토어 글’ 구역에서 볼 수 있어요." in text, text
        assert "아래" not in text, text
        goto = panel.locator(".popup-map-goto")
        assert goto.inner_text() == "이 장소 글 5건 모두 보기"
        h = goto.evaluate("b=>[b.getBoundingClientRect().height,parseFloat(getComputedStyle(b).fontSize)]")
        assert h[0] >= 44 and h[1] >= 14, h
        # 키보드로 누른다.
        goto.focus()
        page.keyboard.press("Enter")
        state = page.evaluate(REVEALED, "seoul-many-4")
        assert state["posts"] == 5 and state["more"] == 0, (width, state)
        assert state["hubsMore"] == 0 and state["focus"] and state["name"] == "거점4 백화점", (width, state)
        # 문서 스크롤은 부드럽게 움직인다(selle.css scroll-behavior:smooth). 고정 머리글 아래 화면 위쪽 절반에 멈춘다.
        page.wait_for_function(f"id=>({REVEALED})(id).inView", arg="seoul-many-4")
        assert page.evaluate("document.querySelectorAll('#popup-course .popup-hub').length") == 5
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), width
        # 이미 펼친 묶음으로 다시 가도(더 보기 단추가 없어도) 같은 곳으로 간다.
        page.evaluate("window.scrollTo({top:0,behavior:'instant'})")
        page.locator(".plan-map .popup-divicon").nth(4).dispatch_event("click")
        panel.locator(".popup-map-goto").click()
        page.wait_for_function(f"id=>({REVEALED})(id).inView", arg="seoul-many-4")
        state = page.evaluate(REVEALED, "seoul-many-4")
        assert state["posts"] == 5 and state["focus"], (width, state)
    # 구역이 숨으면(스위치 꺼짐 404 등) 단추를 두지 않고 문구만 남는다.
    page.evaluate("document.getElementById('popup-course').hidden=true")
    page.locator(".plan-map .popup-divicon").nth(4).dispatch_event("click")
    page.locator(".plan-map .map-popup-hub").nth(0).click()
    page.locator(".plan-map .map-popup-hub").nth(4).click()
    assert page.locator(".plan-map .map-popup-panel .popup-map-goto").count() == 0
    assert "외 2건은 ‘팝업스토어 글’ 구역에서" in page.locator(".plan-map .map-popup-panel").inner_text()


# 오른쪽 지도 패널(.plan-map-card, 자체 스크롤) 안에서 지도와 열린 정보 칸이 각각 몇 px 보이는지. 고정된 지도에 가려진 칸 부분은 보이지 않은 것으로 센다.
RAIL_VIEW = """()=>{const card=document.querySelector('.plan-map-rail .plan-map-card'),map=card.querySelector('.naver-plan-map'),
  panel=card.querySelector('.map-popup-panel'),c=card.getBoundingClientRect(),m=map.getBoundingClientRect(),p=panel.getBoundingClientRect();
  const sticky=getComputedStyle(map).position==='sticky',top=Math.max(c.top,sticky?m.bottom:c.top);
  return {sticky,card:Math.round(c.height),map:Math.round(m.height),scrollTop:Math.round(card.scrollTop),
    mapVisible:Math.round(Math.max(0,Math.min(m.bottom,c.bottom)-Math.max(m.top,c.top))),
    panelVisible:Math.round(Math.max(0,Math.min(p.bottom,c.bottom)-Math.max(p.top,top)))}}"""
# 패널 안 요소가 고정 지도 밑에 숨지 않았는지(패널 안에서 보이는 자리, 지도 아래).
UNDER_MAP = """sel=>{const card=document.querySelector('.plan-map-rail .plan-map-card'),m=card.querySelector('.naver-plan-map').getBoundingClientRect(),
  c=card.getBoundingClientRect(),r=document.querySelector(sel).getBoundingClientRect();return r.top>=m.bottom-1&&r.bottom<=c.bottom+1}"""


def test_desktop_rail_keeps_the_map_in_view_while_reading_the_panel(audit_page):
    """데스크톱 2단(오른쪽 지도 패널)에서 장소 단추·정보 칸을 내려 봐도 지도가 패널 위쪽에 남는다(Leaflet). 1440×900·1280×720 에서 지도 전체와
    칸 일부가 함께 보이고, 높이가 낮은 화면(1280×560)에서는 지도를 붙이지 않아 지도가 패널을 가리지 않는다. 키보드 포커스가 지도 밑에 숨지 않는다.
    모바일 1단(390px)의 지도는 붙지 않고 카드도 따로 스크롤하지 않는다."""
    page, base, errors = audit_page
    route_festivals(page)
    Api(page, default=MAP)
    page.evaluate(LEAFLET_CAPTURE)
    generate(page)
    page.wait_for_function(
        "document.querySelectorAll('.plan-map-rail .plan-map .popup-divicon').length===3", timeout=20000
    )
    chips = page.locator(".plan-map .map-popup-hub")
    for width, height, least in ((1440, 900, 380), (1280, 720, 260)):
        page.set_viewport_size({"width": width, "height": height})
        page.wait_for_timeout(300)
        # 네이버 지도 SDK 가 지도 요소에 직접 넣는 style="position:relative" 를 흉내 낸다(운영에서 이 때문에 지도가 붙지 않았다).
        page.evaluate("document.querySelector('.plan-map-rail .naver-plan-map').style.position='relative'")
        page.evaluate("document.querySelector('#plan-map-rail').scrollIntoView({block:'start',behavior:'instant'})")
        if chips.nth(0).get_attribute("aria-expanded") != "true":
            chips.nth(0).click()
        # 칸 머리가 지도 바로 아래에 오게 패널을 내린다(scrollIntoView 가 패널의 scroll-padding 을 따름).
        page.evaluate("document.querySelector('.plan-map .map-popup-panel').scrollIntoView({block:'start',behavior:'instant'})")
        view = page.evaluate(RAIL_VIEW)
        assert view["sticky"] and view["scrollTop"] > 0, (width, view)
        assert view["mapVisible"] == view["map"] and view["map"] >= 240, (width, view)
        assert view["panelVisible"] >= least, (width, view)
        # 지도가 패널의 절반 넘게 가리지 않는다.
        assert view["map"] <= view["card"] / 2, (width, view)
        # 패널을 끝까지 내린 뒤 Shift+Tab 으로 위쪽 단추에 가도 지도 밑에 숨지 않는다.
        page.evaluate("()=>{const c=document.querySelector('.plan-map-rail .plan-map-card');c.scrollTop=c.scrollHeight;}")
        page.locator(".plan-map .map-popup-panel a").first.focus()
        page.keyboard.press("Shift+Tab")
        assert page.evaluate("document.activeElement===document.querySelectorAll('.plan-map .map-popup-hub')[2]")
        assert page.evaluate(UNDER_MAP, ".plan-map .map-popup-hub:nth-child(3)"), width
        # 지도 표시를 눌러 연 칸도 지도 밑이 아닌 곳으로 들어온다.
        page.evaluate("()=>{const c=document.querySelector('.plan-map-rail .plan-map-card');c.scrollTop=c.scrollHeight;}")
        page.locator(".plan-map .popup-divicon").nth(1).dispatch_event("click")
        page.wait_for_timeout(100)
        assert page.evaluate(UNDER_MAP, ".plan-map .map-popup-panel strong"), width
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), width
        chips.nth(0).click()
    # 낮은 화면: 붙이지 않는다(예전 동작).
    page.set_viewport_size({"width": 1280, "height": 560})
    page.wait_for_timeout(300)
    page.evaluate("document.querySelector('.plan-map .map-popup-panel').scrollIntoView({block:'start',behavior:'instant'})")
    view = page.evaluate(RAIL_VIEW)
    assert not view["sticky"] and view["panelVisible"] > 0, view
    # 모바일 1단: 지도는 붙지 않고 카드는 따로 스크롤하지 않는다.
    narrow(page, 390)
    assert page.evaluate(
        """()=>{const card=document.querySelector('#plan-map-slot .plan-map-card'),map=card.querySelector('.naver-plan-map');
          return getComputedStyle(map).position!=='sticky'&&getComputedStyle(card).overflowY==='visible'&&card.scrollHeight<=card.clientHeight+1}"""
    )


def test_hub_buttons_cause_no_csp_violation_or_console_error():
    """CSP 를 끄지 않은 브라우저(테스트 기본: 네이버 키 없음 → Leaflet)에서 장소 단추·지도 표시·정보 칸·닫기를 써도
    CSP 위반·콘솔 오류·페이지 오류가 없다(인라인 스크립트·인라인 이벤트 처리기를 쓰지 않음). 외부 요청은 막거나 가짜로 답한다."""
    playwright = pytest.importorskip("playwright.sync_api")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    base = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(main_app, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        with playwright.sync_playwright() as pw:
            browser = pw.chromium.launch(
                channel=os.getenv("DATEMATE_BROWSER_CHANNEL", "msedge"), headless=True
            )
            context = browser.new_context(viewport={"width": 390, "height": 844})
            context.add_init_script(INIT)
            offline_routes(context, base, [])
            # 나중에 등록한 route 가 먼저 받는다.
            context.route(
                lambda url: urlsplit(url).path == "/api/popups",
                lambda route: route.fulfill(json=MAP),
            )
            page = context.new_page()
            errors, console = [], []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on(
                "console",
                lambda m: console.append(m.text)
                if m.type == "error" or "Content Security Policy" in m.text
                else None,
            )
            response = page.goto(base, wait_until="networkidle")
            assert "script-src-attr 'none'" in response.headers["content-security-policy"]
            poll(page, "typeof statusData !== 'undefined' && statusData && document.querySelector('.simple-plan-form')")
            page.evaluate(
                "() => {form.elements.mode.value='demo';form.elements.mode.dispatchEvent(new Event('change',{bubbles:true}));"
                "form.elements.visit_date.value='2026-10-24';form.elements.max_leg.value=180;form.elements.budget.value=1000000;}"
            )
            page.locator("#submit-plan").click()
            poll(page, "selected && selected.id", 60)
            poll(page, "document.querySelectorAll('.plan-map .map-popup-hub').length === 3", 20)
            chips = page.locator(".plan-map .map-popup-hub")
            for i in range(3):
                chips.nth(i).click()
                poll(page, f"document.querySelectorAll('.plan-map .map-popup-hub')[{i}].getAttribute('aria-expanded') === 'true'")
            page.locator(".plan-map .map-popup-close").click()
            page.locator(".plan-map .popup-divicon").nth(0).dispatch_event("click")
            poll(page, "!document.querySelector('.plan-map .map-popup-panel').hidden")
            # 「이 장소 글 n건 모두 보기」(팝업 글 구역으로 이동)와 거점이 많을 때의 펼침 단추.
            page.locator(".plan-map .popup-map-goto").click()
            poll(page, "document.activeElement?.classList.contains('popup-hub-name')")
            page.evaluate(
                "()=>{const m=PopupCourse.mapItems;PopupCourse.setMapItems([...m,...m.map(g=>({...g,hub:{...g.hub,hub_id:g.hub.hub_id+'-2'}}))]);}"
            )
            page.locator(".plan-map .map-popup-more").click()
            poll(page, "document.querySelectorAll('.plan-map .map-popup-hub:not([hidden])').length === 6")
            page.locator(".plan-map .map-popup-more").click()
            page.wait_for_timeout(500)
            violations = page.evaluate("() => window.__csp || []")
            browser.close()
        assert violations == [] and console == [] and errors == [], (violations, console, errors)
    finally:
        server.should_exit = True
        thread.join(5)
