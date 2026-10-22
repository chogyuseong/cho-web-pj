import json
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1200,'height':900})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.wait_for_function('Boolean(statusData)')
    records=[]
    for field,text in [('course_query','종로 카페투어'),('request','카페 투어 하고 싶어')]:
        page.evaluate('''()=>{locationState.origin={name:'종로',lat:37.5765,lon:126.9855};form.elements.origin_name.value='종로';
          form.elements.visit_date.value='2026-10-24';form.elements.budget.value='150000';
          form.elements.course_query.value='';form.elements.request.value='';
          form.elements.include_meal.checked=true;setDateClassification('콘셉트별','지적인 데이트');}''')
        page.locator('[name='+field+']').fill(text)
        old=page.evaluate('selected?.id||null')
        page.evaluate('form.requestSubmit()')
        page.wait_for_function('old=>selected?.id&&selected.id!==old&&!document.querySelector("#submit-plan").disabled',arg=old,timeout=120000)
        plan=page.evaluate('selected')
        assert not plan['conditions']['include_meal']
        assert len(plan['places'])==3
        assert all(not p.get('meal') and ('cafe' in p.get('tags',[]) or any(w in (p['name']+' '+(p.get('description') or '')) for w in ['카페','커피','디저트','티하우스','베이커리','찻집'])) for p in plan['places']),[(p['name'],p.get('tags')) for p in plan['places']]
        assert not any(r['condition']=='request_activity' and r['state']=='unmet' for r in plan['condition_checks'])
        records.append({'field':field,'cafes':len(plan['places'])})
    assert not page.locator('[name=include_meal]').is_checked()
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert not errors,errors
    print(json.dumps({'real_cafe_tour_inputs':records,'automatic_request_parse':True,'meal_checkbox_updated':True,'mobile_overflow':False,'page_errors':errors}))
    browser.close()
