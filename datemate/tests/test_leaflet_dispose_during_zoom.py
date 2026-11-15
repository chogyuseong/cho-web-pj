"""Leaflet 대체 지도가 확대·축소 애니메이션 중에 지워질 때의 페이지 오류(_leaflet_pos) 회귀 검사.

원인(Leaflet 1.9.4, static/vendor/leaflet/leaflet.js): 애니메이션 확대(_animateZoom)는 끝맺음을 transitionend 와 함께
setTimeout(_onZoomTransitionEnd, 250) 으로도 예약한다. map.remove() 는 이 예약을 지우지 않고(_stop 은 이동·flyTo 만 멈춤) _mapPane 만 지우므로,
250ms 뒤 _onZoomTransitionEnd → _move → _getMapPanePos 가 지워진 _mapPane 의 _leaflet_pos 를 읽다 TypeError 를 낸다.
지도를 다시 그리는 곳(renderPlanMapCard 의 disposeMap, 폭 변경·코스 탭 전환)에서 애니메이션 중인 지도를 지우면 늘 난다.
외부 요청은 막는다(지도 타일은 받지 않음)."""

from test_feedback_ui import route_festivals
from test_functional_audit import audit_page, generate  # noqa: F401
from test_popup_course_ui import Api
from test_popup_map_ui import LEAFLET_CAPTURE, MAP

# 지금 지도가 멈춘 뒤 한 단계 확대를 시작하고, 애니메이션이 실제로 시작될 때(_animatingZoom)까지 기다린다.
START_ZOOM = """async()=>{const map=courseMaps.at(-1);map.setZoom(map.getZoom()+1);
  for(let i=0;i<10&&!map._animatingZoom;i++)await new Promise(r=>requestAnimationFrame(r));return map._animatingZoom===true}"""
# 다음 지도 정리(disposeMap) 때 지우는 지도가 애니메이션 중이었는지 남긴다(재현 조건이 실제로 생겼는지 확인).
# 데스크톱에서는 renderPlanMapCard 가 같은 지도를 카드·패널 두 곳에서 찾아 두 번 정리하므로 첫 정리 때의 값을 본다.
WATCH_DISPOSE = """()=>{window.animatingAtDispose=[];document.querySelectorAll('.plan-map').forEach(w=>{const d=w.disposeMap,map=courseMaps.at(-1);
  w.disposeMap=()=>{animatingAtDispose.push(map._animatingZoom===true);d();};});}"""


def settle(page):
    page.wait_for_function("courseMaps.length&&!courseMaps.at(-1)._animatingZoom", timeout=20000)
    page.wait_for_timeout(400)


def test_removing_a_zooming_leaflet_map_raises_no_page_error(audit_page):
    page, base, errors = audit_page
    route_festivals(page)
    Api(page, default=MAP)
    page.evaluate(LEAFLET_CAPTURE)
    generate(page)
    page.wait_for_function(
        "document.querySelectorAll('.plan-map .popup-divicon').length===3", timeout=20000
    )
    settle(page)

    # 1) 확대 애니메이션 중에 같은 작업(task) 안에서 지도를 다시 그린다(정리 → 새 지도). 가장 확실한 재현.
    for _ in range(3):
        count = page.evaluate("courseMaps.length")
        assert page.evaluate(START_ZOOM)
        page.evaluate(WATCH_DISPOSE)
        page.evaluate("renderPlanMapCard()")
        assert page.evaluate("animatingAtDispose[0]") is True
        page.wait_for_function("n=>courseMaps.length>n", arg=count)
        # 예약된 끝맺음(250ms)이 지난 뒤까지 본다.
        page.wait_for_timeout(500)
        assert errors == [], errors
        settle(page)

    # 1-2) 확대를 요청한 직후(애니메이션이 시작되는 다음 프레임 전)에 지운다. Leaflet 은 그 프레임에서 _mapPane 이 없으면 시작하지 않는다.
    count = page.evaluate("courseMaps.length")
    page.evaluate(WATCH_DISPOSE)
    page.evaluate(
        "()=>{const map=courseMaps.at(-1);map.setZoom(map.getZoom()+1);window.zoomQueued=!map._animatingZoom;renderPlanMapCard();}"
    )
    assert page.evaluate("zoomQueued") and page.evaluate("animatingAtDispose[0]") is False
    page.wait_for_function("n=>courseMaps.length>n", arg=count)
    page.wait_for_timeout(500)
    assert errors == [], errors
    settle(page)

    # 2) 사용자 흐름: 확대 중에 화면 폭을 바꿔(데스크톱 ↔ 모바일) 지도가 다른 자리로 다시 그려진다.
    for width in (390, 1440, 390):
        count = page.evaluate("courseMaps.length")
        assert page.evaluate(START_ZOOM)
        page.evaluate(WATCH_DISPOSE)
        page.set_viewport_size({"width": width, "height": 844 if width == 390 else 1000})
        page.wait_for_function("n=>courseMaps.length>n", arg=count)
        assert page.evaluate("animatingAtDispose[0]") is True, width
        page.wait_for_timeout(500)
        assert errors == [], (width, errors)
        settle(page)

    # 3) 확대 중에 코스 탭을 바꾼다(지도 다시 그리기).
    for tab in (1, 0):
        count = page.evaluate("courseMaps.length")
        assert page.evaluate(START_ZOOM)
        page.evaluate(WATCH_DISPOSE)
        page.locator(".map-option-tabs button").nth(tab).click()
        page.wait_for_function("n=>courseMaps.length>n", arg=count)
        assert page.evaluate("animatingAtDispose[0]") is True, tab
        page.wait_for_timeout(500)
        assert errors == [], (tab, errors)
        settle(page)

    # 다시 그린 지도는 정상: 코스 표시·팝업 표시가 한 벌.
    assert page.locator(".plan-map").count() == 1
    assert page.locator(".plan-map .popup-divicon").count() == 3
    assert page.locator(".plan-map .map-popup-hubs").count() == 1
