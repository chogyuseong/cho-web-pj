import json
import sys
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
    page.locator('[name=course_query]').fill('연남동 데이트 코스')
    page.locator('[data-region="연남"]').click()
    page.locator('#quick-start').click()
    page.wait_for_function('selected?.course_search&&!document.querySelector("#submit-plan").disabled',timeout=90000)
    evidence=page.evaluate('selected.course_search')
    assert evidence['query']=='연남동 데이트 코스'
    assert evidence['status']=='available',evidence
    assert 1<=len(evidence['posts'])<=3
    assert evidence['rating_status']=='unavailable'
    if evidence['matches']:
        assert page.evaluate('selected.places.some(p=>selected.course_search.matches[p.id])')
    assert page.locator('.course-source a').count()==len(evidence['posts'])
    plan=page.evaluate('selected')
    from app.quality import in_area,meal_penalty
    from app.models import Conditions
    conditions=Conditions.model_validate(plan['conditions'])
    assert all(in_area(p,conditions) for p in plan['places'])
    assert meal_penalty(plan,conditions)==0
    for place in plan['places']:
        if place['id'].startswith('discovered:'):
            assert page.request.get('http://127.0.0.1:8000/api/places/'+place['id']+'?mode=real').ok
    page.locator('.course-evidence > summary').click()
    page.locator('.course-search-panel').screenshot(path=str(root/'docs/screenshots/course-search.png'))
    assert not errors,errors
    print(json.dumps({'status':evidence['status'],'posts':len(evidence['posts']),'discovery':evidence.get('discovery'),'matched_places':len(evidence['matches']),'selected_matches':page.evaluate('selected.places.filter(p=>selected.course_search.matches[p.id]).length'),'selected_places':[(p['name'],p.get('meal',False)) for p in plan['places']],'meal_included':True,'area_verified':True,'page_errors':errors},ensure_ascii=True))
    browser.close()
