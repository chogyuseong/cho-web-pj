import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
base=os.getenv('DATEMATE_TEST_URL','http://127.0.0.1:8001')
results=[]
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1200,'height':900})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base,wait_until='networkidle')
    assert page.locator('[name=origin_lat],[name=origin_lon],[name=home_lat],[name=home_lon]').count()==0
    page.locator('#origin-location button').click()
    page.locator('#location-map .leaflet-tile-loaded').first.wait_for()
    page.locator('#location-map').click(position={'x':200,'y':130})
    page.get_by_role('button',name='이 위치를 출발지로 사용').click()
    assert page.locator('[name=origin_name]').input_value()=='지도에서 선택한 출발지'
    results.append('live_osm_map_click_select_origin')
    page.locator('#origin-location button').click()
    page.locator('.location-search input').fill('서울 중구 세종대로 110')
    page.get_by_role('button',name='주소 검색',exact=True).click()
    page.get_by_text('주소 검색에는 네이버 Maps 키 설정이 필요합니다.',exact=False).wait_for()
    results.append('missing_key_message')
    page.locator('#close-dialog').click()
    # 실제 네이버 호출을 한 것으로 기록하지 않는 주소 결과 모의 검증.
    page.route('**/api/locations/search',lambda route:route.fulfill(json={'status':'ok','message':'','results':[
        {'name':'서울 종로구 테스트로 1','road_address':'서울 종로구 테스트로 1','jibun_address':'서울 종로구 테스트동 1','lat':37.575,'lon':126.985}]}))
    page.locator('#origin-location button').click()
    page.locator('.location-search input').fill('테스트 주소')
    page.locator('.location-search input').press('Enter')
    page.locator('.location-result').click()
    page.get_by_role('button',name='이 위치를 출발지로 사용').click()
    assert page.locator('[name=origin_name]').input_value()=='서울 종로구 테스트로 1'
    page.locator('[name=visit_date]').fill('2026-10-24')
    with page.expect_request('**/api/plans') as request:
        page.locator('#submit-plan').click()
    assert request.value.post_data_json['origin']=={'name':'서울 종로구 테스트로 1','lat':37.575,'lon':126.985}
    page.locator('#results .plan-card').first.wait_for()
    results.append('mock_address_selection_submits_matching_coordinates')
    page.locator('#conditions details summary').click()
    page.locator('[name=return_home]').check()
    page.locator('#home-location button').click()
    page.get_by_role('button',name='지도 중심을 선택',exact=True).click()
    page.get_by_role('button',name='이 위치를 귀가지로 사용').click()
    with page.expect_request('**/api/plans') as request:
        page.locator('#submit-plan').click()
    assert request.value.post_data_json['home']['name']=='지도에서 선택한 귀가지'
    results.append('home_picker_and_payload')
    page.locator('[name=mode]').select_option('real')
    assert page.locator('[name=origin_name]').input_value()==''
    page.locator('#submit-plan').click()
    page.get_by_text('출발지를 주소 검색 또는 지도에서 선택해 주세요.',exact=False).first.wait_for()
    results.append('real_mode_requires_explicit_location')
    page.set_viewport_size({'width':390,'height':844})
    page.locator('#origin-location button').click()
    page.locator('#location-map .leaflet-tile-loaded').first.wait_for()
    confirm=page.get_by_role('button',name='이 위치를 출발지로 사용')
    assert confirm.is_visible()
    bounds=confirm.bounding_box()
    assert bounds['y']>=0 and bounds['y']+bounds['height']<=844
    page.locator('#location-map').click(position={'x':160,'y':100})
    confirm.click()
    assert not page.locator('#dialog').is_visible()
    page.locator('#origin-location button').click()
    page.locator('#location-map .leaflet-tile-loaded').first.wait_for()
    assert page.evaluate('document.querySelector("#dialog").scrollWidth <= document.querySelector("#dialog").clientWidth')
    page.screenshot(path=str(root/'docs'/'screenshots'/'mobile-location-picker.png'))
    results.append('mobile_picker_no_overflow')
    results.append('mobile_confirm_visible_without_scrolling_and_clickable')
    assert not errors,errors
    browser.close()
(root/'docs'/'location-tests.json').write_text(json.dumps({'passed':results,'page_errors':errors,'naver_live_api':'not_run_missing_key'},indent=2),encoding='utf-8')
print(json.dumps({'passed':results,'page_errors':errors}))
