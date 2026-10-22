import json
import sys
from datetime import date
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.wait_for_function('Boolean(statusData)')
    page.locator('#quick-start').click()
    page.wait_for_function('selected?.pricing_checked_at&&!document.querySelector("#submit-plan").disabled',timeout=90000)
    options=page.locator('.plan-option-tabs button').count()
    assert options>=2
    for i in [*range(options),0]:
        page.locator('.plan-option-tabs button').nth(i).click()
        page.wait_for_function('i=>document.querySelector(".plan-card.selected").dataset.option===String(i+1)',arg=i)
        assert page.evaluate('document.querySelector(".plan-option-tabs").nextElementSibling.classList.contains("selected")')
        assert page.evaluate('document.querySelector("#plan-detail").previousElementSibling.classList.contains("selected")')
        assert page.locator('.plan-option-tabs button').nth(i).get_attribute('aria-pressed')=='true'
        assert page.locator('.plan-option-tabs button').nth(i).locator('.option-label').inner_text()==f'Option{i+1}'
    page.locator('.plan-card.selected .inspect-plan').click()
    page.context.grant_permissions(['clipboard-read','clipboard-write'])
    page.locator('#plan-detail .detail-header').get_by_role('button',name='링크 복사',exact=True).click()
    assert page.evaluate('navigator.clipboard.readText()').endswith(page.evaluate('selected.id'))
    page.evaluate('window.print=()=>window.__printChecked=true')
    page.locator('#plan-detail .detail-header').get_by_role('button',name='인쇄 / PDF',exact=True).click()
    assert page.evaluate('window.__printChecked')
    page.locator('#plan-detail .stop').first.wait_for()
    lock=page.locator('#plan-detail .stop').first.get_by_role('button',name='○ 장소 고정',exact=True)
    lock.click()
    page.locator('#plan-detail .stop').first.get_by_role('button',name='● 고정됨',exact=True).click()
    page.locator('#plan-detail .stop').first.get_by_role('button',name='장소 정보 · 질문',exact=True).click()
    page.wait_for_function('document.querySelector("#dialog").open&&document.querySelector("#dialog-content h2")?.textContent!=="장소 정보를 불러오고 있어요"')
    page.locator('#close-dialog').click()
    page.locator('#plan-detail .stop').first.get_by_role('button',name='↻ 다른 장소로 변경',exact=True).click()
    page.locator('#dialog-content .plan-card,#dialog-content .warning').first.wait_for(timeout=45000)
    replacement=page.locator('#dialog-content').get_by_role('button',name='이 장소로 교체',exact=True)
    replaced=False
    if replacement.count():
        old=page.evaluate('selected.id')
        replacement.first.click()
        page.wait_for_function('old=>selected.id!==old',arg=old,timeout=45000)
        page.locator('#plan-detail .detail-header').get_by_role('button',name='교체 되돌리기',exact=True).click()
        page.wait_for_function('old=>selected.id===old',arg=old,timeout=30000)
        replaced=True
    else:page.locator('#close-dialog').click()
    card=page.locator('#plan-detail .meal-card-with-photo').first
    card.wait_for()
    card.scroll_into_view_if_needed()
    assert card.locator('.meal-photo .place-photo-panel').count()==1
    a,b=card.locator('.meal-info').bounding_box(),card.locator('.meal-photo').bounding_box()
    assert b['x']>a['x']
    card.get_by_role('button',name='사진·장소 정보',exact=True).click()
    page.wait_for_function('document.querySelector("#dialog").open&&document.querySelector("#dialog-content h2")?.textContent!=="장소 정보를 불러오고 있어요"')
    page.locator('#close-dialog').click()
    card.locator('.place-blogs > summary').click()
    card.locator('.blog-search-post,.place-blog-content > .hint').first.wait_for(timeout=20000)
    page.locator('#plan-detail .meal-more').first.click()
    page.locator('#plan-detail .meal-more-results .meal-card,#plan-detail .meal-more-results > a').first.wait_for(timeout=20000)
    # 사진이 있는 식당 카드의 실제 표시 및 옆 배치를 확인한다.
    page.wait_for_function('document.querySelector("#plan-detail .meal-card-with-photo .meal-photo img")?.naturalWidth>0',timeout=30000)
    assert page.evaluate('(()=>{const box=compactConditionSummary(selected);return box.children.length===4&&Array.from(box.children).every(p=>p.querySelector("strong"))})()')
    page.locator('.plan-option-tabs').screenshot(path=str(root/'docs/screenshots/option-summary-tabs.png'))
    card.screenshot(path=str(root/'docs/screenshots/restaurant-side-photo.png'))
    page.set_viewport_size({'width':390,'height':844})
    card.scroll_into_view_if_needed()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    card.screenshot(path=str(root/'docs/screenshots/restaurant-side-photo-mobile.png'))
    page.locator('#nav-explore').click()
    page.locator('#catalog .place-card').first.wait_for(timeout=20000)
    page.locator('#search').fill('서울숲')
    page.locator('#search-button').click()
    page.wait_for_function('!document.querySelector("#search-button").disabled')
    page.locator('#nav-plan').click()
    page.locator('#origin-location button').click()
    page.locator('.location-search input').fill('서울 중구 세종대로 110')
    page.get_by_role('button',name='주소 검색',exact=True).click()
    page.locator('.location-result').first.wait_for(timeout=20000)
    page.locator('.location-result').first.click()
    page.get_by_role('button',name='이 위치를 출발지로 사용').click()
    assert page.locator('[name=origin_name]').input_value()
    page.locator('[name=max_leg]').evaluate("i=>i.closest('details').open=true")
    page.locator('[name=return_home]').check()
    page.locator('#home-location button').click()
    page.get_by_role('button',name='지도 중심을 선택',exact=True).click()
    page.get_by_role('button',name='이 위치를 귀가지로 사용').click()
    assert page.locator('[name=home_name]').input_value()
    page.locator('[name=request]').fill('카페 2곳 5만원')
    page.locator('#parse').click()
    page.wait_for_function('document.querySelector("[name=budget]").value==="50000"')
    assert page.locator('[name=count]').input_value()=='2'
    # 실제 조건의 대체 후보가 없으면, 교체·되돌리기 버튼은 가상 코스로 별도 검증한다.
    if not replaced:
        data=page.request.post('http://127.0.0.1:8000/api/plans',data={'mode':'demo','visit_date':date.today().isoformat(),'budget':1000000,'max_leg':180}).json()
        fixture=data['plans'][0];cleanup=[p['id'] for p in data['plans']]
        page.evaluate('p=>{plans=[p];selected=p;locks.clear();renderResults();renderDetail();}',fixture)
        page.locator('#plan-detail .stop').first.get_by_role('button',name='↻ 다른 장소로 변경',exact=True).click()
        page.locator('#dialog-content').get_by_role('button',name='이 장소로 교체',exact=True).first.wait_for(timeout=30000)
        page.locator('#dialog-content').get_by_role('button',name='이 장소로 교체',exact=True).first.click()
        page.wait_for_function('id=>selected.id!==id',arg=fixture['id'])
        cleanup.append(page.evaluate('selected.id'))
        page.locator('#plan-detail .detail-header').get_by_role('button',name='교체 되돌리기',exact=True).click()
        page.wait_for_function('id=>selected.id===id',arg=fixture['id'])
        from app import store
        with store.connect() as db:db.executemany('DELETE FROM plans WHERE id=?',[(pid,) for pid in cleanup])
        replaced=True
    assert not errors,errors
    print(json.dumps({'options_checked':options,'selected_option_first':True,'photo_info_dialog':True,'lock_unlock':True,'alternatives_dialog':True,'replace_undo':replaced,'copy_link':True,'print_handler':True,'restaurant_side_photo':True,'blog_button':True,'nearby_restaurants_button':True,'four_line_conditions':True,'mobile_overflow':False,'navigation_search':True,'live_address_search':True,'home_map_selection':True,'request_parse_button':True,'page_errors':errors}))
    browser.close()
