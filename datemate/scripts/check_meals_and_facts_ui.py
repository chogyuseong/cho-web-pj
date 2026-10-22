import json
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.wait_for_function('Boolean(statusData)')
    page.evaluate("locationState.origin={name:'서울시청',lat:37.5665,lon:126.978};form.elements.origin_name.value='서울시청'")
    page.locator('#submit-plan').click()
    page.wait_for_function('Boolean(selected)',timeout=45000)
    groups=page.locator('#plan-detail .meal-suggestions')
    assert groups.count()==2
    assert groups.first.locator('.meal-card').count()==3
    groups.first.screenshot(path=str(root/'docs/screenshots/meal-suggestions.png'))
    first=groups.first.locator('.meal-card').first
    first.locator('.place-blogs summary').click()
    first.locator('.blog-search-post').first.wait_for(timeout=25000)
    assert first.locator('.blog-search-post').count()<=3
    groups.first.locator('.meal-more').click()
    page.wait_for_function("!document.querySelector('#plan-detail .meal-more').disabled",timeout=20000)
    extra=groups.first.locator('.meal-more-results').inner_text()
    assert '지역 API' in extra or groups.first.locator('.meal-more-results .meal-card').count()>0
    checks=page.evaluate('selected.condition_checks')
    assert not any(r['state']=='unknown' and r['condition'] in ['people','transport','stay_minutes'] for r in checks)
    page.locator('#results .condition-differences').first.screenshot(path=str(root/'docs/screenshots/fewer-unknowns.png'))
    fact_count=page.evaluate('selected.confirmed_facts.length')
    assert fact_count>0
    assert not errors,errors
    report={'meal_groups':groups.count(),'first_group_restaurants':groups.first.locator('.meal-card').count(),'confirmed_places':fact_count,
        'unknown_conditions':sorted({r['condition'] for r in checks if r['state']=='unknown'}),'page_errors':errors}
    (root/'docs/meals-and-facts-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(report));browser.close()
