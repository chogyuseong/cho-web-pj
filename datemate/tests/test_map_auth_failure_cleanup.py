"""네이버 지도 인증 실패 알림이 축제·팝업 표시를 올린 뒤에 올 때의 지도 정리(기존 문제).

실제 SDK 에서는 인증 실패 뒤 마커 setMap(null) 이 SDK 내부 오류(capitalize)를 내서, 대체 지도(Leaflet) 전환과
지도 정리(disposeMap, 코스 탭 전환)가 그 자리에서 멈췄다. 여기서는 가짜 SDK 가 인증 실패 뒤 setMap·destroy 에서 같은 오류를 내게 한다.
실제 SDK 와의 연결은 이 테스트가 확인하지 않는다(외부 요청을 막음)."""

from test_feedback_ui import route_festivals
from test_functional_audit import audit_page, generate  # noqa: F401
from test_popup_course_ui import Api
from test_popup_map_ui import FESTIVALS, MAP, NAVER_STUB, POPUPS

# 인증 실패(window.__broken) 뒤에는 마커 setMap 과 지도 destroy 가 실제 SDK 처럼 던진다.
BREAK_AFTER_AUTH = """()=>{window.__broken=false;const fail=()=>{throw new TypeError("Cannot read properties of null (reading 'capitalize')");};
  const Marker=naver.maps.Marker;naver.maps.Marker=function(options){Marker.call(this,options);const set=this.setMap;this.setMap=map=>{if(window.__broken)fail();set(map);};};
  const Map=naver.maps.Map;naver.maps.Map=function(...args){Map.apply(this,args);this.destroy=()=>{if(window.__broken)fail();};};}"""


def test_fallback_and_dispose_survive_sdk_errors_after_auth_failure(audit_page):
    page, base, errors = audit_page
    route_festivals(page)
    Api(page, default=MAP)
    page.evaluate(NAVER_STUB)
    page.evaluate(BREAK_AFTER_AUTH)
    generate(page)
    page.wait_for_function(f"{FESTIVALS}.length===2", timeout=20000)
    page.wait_for_function(f"{POPUPS}.length===3")

    # 1) 표시를 올린 뒤 인증 실패 알림: 정리 오류가 있어도 대체 지도에 코스·축제·팝업 표시가 그려진다.
    page.evaluate("window.__broken=true;window.naverMapAuthFailed=true")
    page.evaluate("document.querySelectorAll('.plan-map').forEach(w=>w.showMapFallback())")
    page.wait_for_function(
        "document.querySelector('.plan-map .fallback-plan-map.leaflet-container')"
    )
    page.wait_for_function("document.querySelectorAll('.plan-map .festival-circle').length===2")
    assert page.locator(".plan-map .popup-divicon").count() == 3
    # 지도 아래 장소 단추는 대체 지도 기준 한 벌만 남는다.
    assert page.locator(".map-popup-hubs").count() == 1
    assert page.locator(".plan-map .map-popup-hub").count() == 3
    assert page.locator(".plan-map .map-reconnect").count() == 1
    assert page.locator(".plan-map .leaflet-overlay-pane path.route-leg").count() >= 1

    # 2) 네이버 지도에 표시가 있는 채로 인증 실패 뒤 코스 탭을 바꿔도(지도 정리 disposeMap) 새 지도가 그려진다.
    # (1 단계에서 정리하다 던진 가짜 마커는 removed 표시가 남지 않으므로 새로 만든 마커 수로 센다.)
    made = "window.__naverMarkers.length"
    before = page.evaluate(made)
    page.evaluate("window.__broken=false;window.naverMapAuthFailed=false")
    page.locator(".map-option-tabs button").nth(1).click()
    page.wait_for_function(
        "document.querySelector('.map-option-tabs [aria-pressed=\"true\"]')?.dataset.mapOption==='2'"
    )
    page.wait_for_function("!document.querySelector('.plan-map .fallback-plan-map')")
    page.wait_for_function(f"n=>{made}>=n+2+3", arg=before)
    page.evaluate("window.__broken=true")
    before = page.evaluate(made)
    page.locator(".map-option-tabs button").nth(0).click()
    # 정리가 멈추면 탭 단추를 다시 만들지 못해 '코스 1'이 눌린 상태가 되지 않는다.
    page.wait_for_function(
        "document.querySelector('.map-option-tabs [aria-pressed=\"true\"]')?.dataset.mapOption==='1'"
    )
    page.wait_for_function("document.querySelectorAll('.plan-map').length===1")
    page.wait_for_function(f"n=>{made}>=n+2+3", arg=before)
    assert page.locator(".plan-map .fallback-plan-map").count() == 0
    # 정리가 멈추지 않았으므로 장소 단추도 새 지도의 것 한 벌뿐이다.
    assert page.locator(".map-popup-hubs").count() == 1
    assert page.locator(".plan-map .map-popup-hub").count() == 3
    # 페이지 오류가 없어야 한다(audit_page 가 끝에서 확인).
