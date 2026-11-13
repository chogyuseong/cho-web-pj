# [예전 기준 점검 스크립트] 지역을 고르지 않고 바로 추천을 누르던 예전 조건 화면과 8011번 포트 서버를 전제로 합니다.
# 그대로 실행하면 실패할 수 있습니다. 자동 테스트(pytest)가 기준이며, 같은 내용은 tests/test_course_map_wheel.py, tests/test_route_geometry.py 에서 확인합니다.
"""8011번 로컬 서버에서 실제 지도 표시를 확인한다. 키와 요청 URL은 출력하지 않는다."""
print('[예전 기준 점검 스크립트] 지역을 고르지 않고 바로 추천을 누르던 예전 조건 화면과 8011번 포트 서버를 전제로 합니다. 그대로 실행하면 실패할 수 있습니다. 대신 볼 테스트: tests/test_course_map_wheel.py, tests/test_route_geometry.py', flush=True)
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    page.goto(os.getenv('DATEMATE_TEST_URL','http://127.0.0.1:8011'),wait_until='networkidle')
    page.locator('#submit-plan').click()
    page.locator('#plan-detail .plan-map').wait_for()
    page.wait_for_timeout(13000)
    markers=page.locator('#plan-detail .route-marker').count()
    caption=page.locator('#plan-detail .plan-map').inner_text()
    print(json.dumps({'markers':markers,'naver_map_rendered':markers>=4,'fallback':markers==0},ensure_ascii=True))
    page.locator('#plan-detail .plan-map').screenshot(path=str(root/'docs/screenshots/naver-plan-map.png'))
    if markers>=4:
        assert '실제 이동 경로가 아닙니다' in caption
        page.set_viewport_size({'width':390,'height':844})
        page.wait_for_timeout(500)
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
    browser.close()
