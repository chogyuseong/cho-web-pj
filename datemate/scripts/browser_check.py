"""별도 설치된 Edge로 로컬 UI를 검증. playwright 패키지가 필요하다."""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'docs'/'screenshots';out.mkdir(exist_ok=True)
results=[]
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(os.getenv('DATEMATE_TEST_URL','http://127.0.0.1:8000'),wait_until='networkidle')
    page.get_by_text('실제 장소 메타데이터',exact=False).wait_for(state='attached')
    page.screenshot(path=str(out/'desktop-home.png'),full_page=True)
    page.locator('[name=visit_date]').fill('2026-10-24')
    page.locator('#submit-plan').click()
    page.locator('.plan-card').first.wait_for()
    assert page.locator('#results .plan-card').count()==3
    results.append('desktop_generate_3_plans')
    page.locator('#plan-detail .stop .actions button').nth(0).click()
    assert page.get_by_text('● 고정됨',exact=True).count()==1
    page.locator('#plan-detail .stop').nth(1).get_by_role('button',name='교체',exact=True).click()
    page.get_by_role('button',name='이 장소로 교체').first.click()
    page.get_by_role('button',name='교체 되돌리기').wait_for()
    results.append('lock_and_replace')
    page.get_by_role('button',name='교체 되돌리기').click()
    page.locator('#plan-detail .stop').first.get_by_role('button',name='장소 정보 · 질문').click()
    page.locator('#dialog .chat-form input').fill('가격은 얼마인가요?')
    page.locator('#dialog .chat-form button').click()
    page.locator('#dialog .chat-box').get_by_text('키 없는 규칙 기반 데모 응답',exact=False).wait_for()
    page.locator('#close-dialog').click()
    results.append('undo_and_place_chat')
    page.locator('.review-form textarea').fill('브라우저 검증용 후기입니다.')
    page.locator('.review-form [name=visited]').fill('2026-01-01')
    page.locator('.review-form button').click()
    page.get_by_role('button',name='내 후기 삭제').wait_for()
    page.get_by_role('button',name='내 후기 삭제').click()
    page.get_by_text('평가 집계 중 · 0건',exact=True).wait_for()
    results.append('review_create_delete')
    page.screenshot(path=str(out/'desktop-plan.png'),full_page=True)
    page.locator('#nav-explore').click()
    page.locator('#catalog .place-card').first.wait_for()
    assert page.locator('#catalog .place-card').count()>=100
    results.append('real_catalog_100_plus')
    mobile=browser.new_page(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
    mobile.on('pageerror',lambda error:errors.append(str(error)))
    mobile.goto(os.getenv('DATEMATE_TEST_URL','http://127.0.0.1:8000'),wait_until='networkidle')
    mobile.locator('[name=visit_date]').fill('2026-10-24')
    mobile.locator('#submit-plan').click()
    mobile.locator('#results .plan-card').first.wait_for()
    assert mobile.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    mobile.locator('#results').scroll_into_view_if_needed()
    mobile.screenshot(path=str(out/'mobile-plan.png'),full_page=True)
    results.append('mobile_generate_no_horizontal_overflow')
    browser.close()
    assert not errors,errors
(ROOT/'docs'/'browser-results.json').write_text(json.dumps({'passed':results,'page_errors':errors},indent=2),encoding='utf-8')
print(json.dumps({'passed':results,'page_errors':errors}))
