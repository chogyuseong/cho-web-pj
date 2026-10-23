import json
from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.wait_for_function('Boolean(statusData)&&document.querySelector(".simple-plan-form")')
    for name in ('mode','region','course_query','mbti','trust_mode','stay_minutes','allow_estimates'):
        assert not page.locator('[name='+name+']').is_visible(),name
    for name in ('visit_date','start','end','budget','request'):
        assert page.locator('[name='+name+']').is_visible(),name
    assert not page.locator('[name=people]').is_visible()
    page.locator('.simple-activity-ideas button').first.click()
    assert page.locator('[name=request]').input_value()=='카페 투어'
    page.locator('.simple-extra-options > summary').click()
    page.locator('[name=people]').fill('3')
    page.locator('[name=count]').select_option('2')
    page.locator('[name=transport]').select_option('transit')
    page.locator('[name=setting]').select_option('indoor')
    # Exercise real form serialization and server validation without external API charges.
    page.evaluate("form.elements.mode.value='demo';clearLocationsForMode()")
    page.locator('[name=visit_date]').fill('2026-10-24')
    page.locator('[name=start]').fill('12:00')
    page.locator('[name=end]').fill('19:00')
    page.locator('[name=budget]').fill('150000')
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
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(Path(__file__).resolve().parents[1]/'docs/screenshots/simple-form-mobile.png'),full_page=True)
    page.locator('#submit-plan').click()
    page.wait_for_function('selected?.id&&!document.querySelector("#submit-plan").disabled',timeout=90000)
    assert page.locator('#results .plan-card.selected').is_visible()
    assert not errors,errors
    page.locator('#nav-plan').click()
    page.locator('.curation-card[data-preset="연남"]').click()
    assert page.locator('[name=request]').input_value()
    assert page.evaluate('locationState.origin.name').startswith('연남')
    assert page.locator('[name=budget]').is_visible()
    assert not errors,errors
    print(json.dumps({'essential_sections':4,'optional_settings':True,'defaults_valid':True,'recommend_and_edit_and_resubmit':True,'mobile_overflow':False,'errors':errors}))
    browser.close()
