"""실제 추천·식당 변경 미리보기·필수 조건·피드백·공유 의견 UI 검증."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
base='http://127.0.0.1:8000'
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    context=browser.new_context(viewport={'width':1440,'height':1000})
    page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base,wait_until='networkidle');page.wait_for_function('Boolean(statusData)')
    page.locator('[name=meeting_type]').select_option('first')
    page.locator('[name=priority]').select_option('food')
    page.locator('[data-region="연남"]').click();page.locator('#quick-start').click()
    page.wait_for_function('selected?.pricing_checked_at&&!document.querySelector("#submit-plan").disabled',timeout=90000)
    original=page.evaluate('selected.id')
    assert page.evaluate('selected.conditions.meeting_type')=='first'
    # 고정 장소는 앞에 식당을 추가했다가 되돌려도 원래 장소를 가리켜야 한다.
    page.locator('#plan-detail .stop').first.get_by_role('button',name='○ 장소 고정',exact=True).click()
    assert page.locator('#plan-detail .execution-grid>div').count()==4
    cards=page.locator('#plan-detail .meal-card-with-photo')
    cards.first.wait_for(timeout=30000)
    add=page.locator('#plan-detail').get_by_role('button',name='이 식당을 일정에 넣기',exact=True).first
    add.wait_for(timeout=25000);add.click()
    page.wait_for_function('document.querySelector("[name=meal_menu]")?.options[0]?.textContent!=="메뉴 가격 조회 중…"',timeout=25000)
    page.locator('[name=meal_menu]').select_option('0')
    # 식사를 기존 일정 맨 뒤에 추가하는 변경을 명시적으로 선택한다.
    count=page.evaluate('selected.places.length')
    page.locator('[name=meal_position]').select_option('add:-1')
    page.get_by_role('button',name='이동·시간·비용 미리 계산',exact=True).click()
    page.get_by_role('button',name='이 변경안으로 확정',exact=True).wait_for(timeout=60000)
    assert page.evaluate('selected.id')==original
    page.locator('#dialog-content').screenshot(path=str(root/'docs/screenshots/meal-change-preview.png'))
    page.get_by_role('button',name='이 변경안으로 확정',exact=True).click()
    page.wait_for_function('id=>selected.id!==id',arg=original,timeout=30000)
    assert page.evaluate('selected.places.length')==count+1
    assert page.evaluate('locks.has(1)')
    page.locator('#plan-detail .detail-header').get_by_role('button',name='교체 되돌리기',exact=True).click()
    page.wait_for_function('id=>selected.id===id',arg=original)
    assert page.evaluate('locks.has(0)&&!locks.has(1)')
    page.locator('.visit-feedback > summary').click()
    page.locator('[name=visit_used]').select_option('yes');page.locator('[name=visit_reuse]').select_option('yes')
    with page.expect_response('**/feedback'):page.get_by_role('button',name='방문 피드백 저장',exact=True).click()
    assert page.request.get(base+'/api/my/feedback-summary').json()['self_reported_visits']>=1
    page.locator('.partner-agreement > summary').click()
    page.get_by_role('button',name='내 의견 저장',exact=True).wait_for()
    page.locator('.partner-agreement select').first.select_option('yes')
    with page.expect_response('**/agreement'):page.get_by_role('button',name='내 의견 저장',exact=True).click()
    other=browser.new_context();guest=other.new_page();guest.on('pageerror',lambda e:errors.append(str(e)))
    guest.goto(base+'/?plan='+original,wait_until='networkidle');guest.locator('.partner-agreement > summary').click()
    guest.get_by_role('button',name='내 의견 저장',exact=True).wait_for();guest.locator('.partner-agreement select').first.select_option('yes')
    with guest.expect_response('**/agreement'):guest.get_by_role('button',name='내 의견 저장',exact=True).click()
    page.get_by_role('button',name='상대방 의견 새로고침',exact=True).click()
    page.wait_for_function('!Array.from(document.querySelectorAll(".partner-agreement button")).find(b=>b.textContent==="합의한 취향으로 다시 계산")?.disabled')
    page.get_by_role('button',name='합의한 취향으로 다시 계산',exact=True).click()
    page.get_by_role('button',name='이 변경안으로 확정',exact=True).wait_for(timeout=60000)
    page.locator('#close-dialog').click()
    page.set_viewport_size({'width':390,'height':844})
    page.locator('.execution-summary').scroll_into_view_if_needed()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.locator('.execution-summary').screenshot(path=str(root/'docs/screenshots/execution-summary-mobile.png'))
    assert not errors,errors
    print(json.dumps({'live_meal_preview_apply_undo':True,'required_controls':True,'execution_four_checks':True,'visit_feedback':True,'two_browser_agreement_preview':True,'mobile_overflow':False,'page_errors':errors}))
    other.close();context.close();browser.close()
