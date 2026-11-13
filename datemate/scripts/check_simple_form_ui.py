"""조건 화면 수동 점검. 로컬 서버(http://127.0.0.1:8000)를 띄운 뒤 실행한다.

꼭 정할 것은 지역(동네 칩·현재 위치·다른 곳 찾기)뿐이고, 날짜·시간·예산·인원·장소 수·교통은
요약 한 줄과 '바꾸기' 안의 칩으로 고친다. 데모 모드로 실제 추천까지 한 번 돌려 본다."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    # Playwright wait_for_function evaluates text with eval, which CSP blocks.
    page=browser.new_page(viewport={'width':1440,'height':1000},bypass_csp=True)
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.wait_for_function('Boolean(statusData)&&document.querySelector(".simple-plan-form")')
    for name in ('mode','region','course_query','mbti','trust_mode','stay_minutes','allow_estimates'):
        assert not page.locator('[name='+name+']').is_visible(),name
    # 처음에는 지역과 자유 입력만 펼쳐 두고 나머지는 요약 한 줄로 접는다.
    assert page.locator('[name=origin_name]').is_visible() and page.locator('[name=request]').is_visible()
    for name in ('visit_date','start','end','budget','people','count','transport'):
        assert not page.locator('[name='+name+']').is_visible(),name
    assert page.locator('.field-requirement').count()==1
    assert page.locator('.quick-summary-text').is_visible()
    assert page.get_by_role('group',name='인기 동네').get_by_role('button').count()==7
    page.locator('.simple-activity-ideas button').first.click()
    assert page.locator('[name=request]').input_value()=='카페 투어'
    page.locator('.condition-toggle').click()
    details=page.locator('#condition-details')
    details.get_by_role('group',name='시간대').get_by_role('button',name='직접',exact=True).click()
    details.get_by_role('group',name='전체 예산').get_by_role('button',name='15만',exact=True).click()
    page.locator('[name=people]').fill('3')
    page.locator('[name=count]').select_option('2')
    page.locator('[name=transport]').select_option('transit')
    page.locator('.simple-extra-options > summary').click()
    page.locator('[name=setting]').select_option('indoor')
    # Exercise real form serialization and server validation without external API charges.
    page.evaluate("form.elements.mode.value='demo';clearLocationsForMode()")
    details.get_by_role('group',name='방문 날짜').get_by_role('button',name='직접',exact=True).click()
    page.locator('[name=visit_date]').fill('2026-10-24')
    page.locator('[name=start]').fill('12:00')
    page.locator('[name=end]').fill('19:00')
    page.locator('[name=request]').fill('')
    submitted=[]
    page.on('request',lambda r:submitted.append(r.post_data_json) if r.url.endswith('/api/plan-jobs') and r.method=='POST' else None)
    page.locator('#submit-plan').click()
    page.wait_for_function('selected?.id&&!document.querySelector("#submit-plan").disabled',timeout=90000)
    data=submitted[-1]
    assert (data['people'],data['count'],data['transport'],data['setting'])==(3,2,'transit','indoor')
    assert data['budget']==150000 and data['start']=='12:00' and data['allow_estimates']
    assert data['trust_mode']=='balanced' and data['mbti']==''
    assert page.locator('#results .plan-card.selected').is_visible()
    page.locator('#edit-conditions').click()
    assert page.locator('[name=budget]').input_value()=='150000'
    assert page.locator('[name=people]').input_value()=='3'
    assert '15만 원' in page.locator('.quick-summary-text').inner_text()
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(Path(__file__).resolve().parents[1]/'docs/screenshots/simple-form-mobile.png'),full_page=True)
    page.locator('#submit-plan').click()
    page.wait_for_function('selected?.id&&!document.querySelector("#submit-plan").disabled',timeout=90000)
    assert page.locator('#results .plan-card.selected').is_visible()
    assert not errors,errors
    # 지역 칩 한 번으로 시·도와 출발지가 함께 채워진다(분위기·분류는 그대로).
    page.locator('#nav-plan').click()
    page.get_by_role('group',name='인기 동네').get_by_role('button',name='부산 해운대',exact=True).click()
    assert page.locator('[name=region]').input_value()=='부산'
    assert page.evaluate('locationState.origin.name').startswith('부산')
    page.wait_for_function("""document.querySelector('[data-area="부산 해운대"]').getAttribute('aria-pressed')==='true'""")
    # 홈 테마 카드도 같은 방식으로 지역을 채운다.
    page.locator('.curation-card[data-preset="제주 애월"]').click()
    assert page.locator('[name=region]').input_value()=='제주'
    page.wait_for_function("""document.querySelector('[data-area="제주 애월"]').getAttribute('aria-pressed')==='true'""")
    assert not errors,errors
    print(json.dumps({'required_sections':1,'summary_line':True,'area_chips':7,'defaults_valid':True,'recommend_and_edit_and_resubmit':True,'mobile_overflow':False,'errors':errors}))
    browser.close()
