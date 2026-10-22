"""추천 버튼의 성공·실제자료 부족·먼 출발지·명시적 데모 복구를 검증한다."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
passed=[]
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1280,'height':900})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.locator('#themes input').first.wait_for(state='attached')
    page.locator('#submit-plan').click()
    page.locator('#results .plan-card').first.wait_for()
    assert page.locator('#results .plan-card').count()==3
    passed.append('default_demo_returns_three')
    page.locator('[name=mode]').select_option('real')
    page.evaluate("locationState.origin={name:'검증용 출발지',lat:37.575,lon:126.985}; form.elements.origin_name.value=locationState.origin.name;")
    page.locator('#submit-plan').click()
    page.get_by_role('heading',name='실제 장소의 운영정보가 아직 부족해요').wait_for()
    assert '완료' not in page.locator('#progress').inner_text()
    passed.append('real_missing_data_is_not_reported_as_success')
    page.get_by_role('button',name='데모 기본 조건으로 시연하기').click()
    page.locator('#results .plan-card').first.wait_for()
    assert page.locator('[name=mode]').input_value()=='demo'
    assert page.locator('#results .plan-card').count()==3
    passed.append('explicit_demo_reset_recovers')
    page.evaluate("locationState.origin={name:'먼 출발지 테스트',lat:37.5,lon:127.05}; form.elements.origin_name.value=locationState.origin.name;")
    page.locator('#submit-plan').click()
    page.get_by_role('heading',name='출발지가 데모 시연 구역에서 멀어요').wait_for()
    assert page.locator('[name=origin_name]').input_value()=='먼 출발지 테스트'
    passed.append('far_origin_explained_without_silent_change')
    page.screenshot(path=str(root/'docs'/'screenshots'/'recommendation-diagnostics.png'),full_page=True)
    page.get_by_role('button',name='데모 기본 조건으로 시연하기').click()
    page.locator('#results .plan-card').first.wait_for()
    page.locator('[name=people]').fill('0')
    page.locator('#submit-plan').click()
    assert '항목을 확인' in page.locator('#progress').inner_text()
    passed.append('invalid_form_explained')
    assert not errors,errors
    browser.close()
result={'passed':passed,'page_errors':errors,'llm_calls':0}
(root/'docs'/'recommendation-tests.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result))
