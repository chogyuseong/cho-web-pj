from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    page.goto('http://localhost:8000',wait_until='networkidle')
    page.locator('[data-category="콘셉트별"]').wait_for()
    expected={'콘셉트별':['즐거운 데이트','편안한 데이트','지적인 데이트','동심 데이트'],
              '타입별':['활동적인','사교적인'], '계절별':['봄','여름','가을','겨울'],
              '날씨별':['맑은 날','비 오는 날','눈 오는 날']}
    for category,items in expected.items():
        page.locator(f'[data-category="{category}"]').click()
        assert page.locator('[name=date_subcategory]').evaluate_all('(els)=>els.map(e=>e.value)')==['']+items
    page.locator('[data-category="콘셉트별"]').click()
    page.locator('[name=date_subcategory][value="지적인 데이트"]').check()
    with page.expect_request('**/api/plans') as request:
        page.locator('#submit-plan').click()
    assert request.value.post_data_json['date_category']=='콘셉트별'
    assert request.value.post_data_json['date_subcategory']=='지적인 데이트'
    page.locator('.plan-card').first.wait_for()
    page.locator('[data-category="타입별"]').click()
    assert page.locator('[name=date_subcategory]:checked').input_value()==''
    page.locator('[name=date_subcategory][value="활동적인"]').check()
    page.screenshot(path=str(root/'docs/screenshots/date-categories-desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
    page.locator('#date-category-tabs').scroll_into_view_if_needed()
    page.screenshot(path=str(root/'docs/screenshots/date-categories-mobile.png'))
    browser.close()
print('4 major categories, all subcategories, selection reset, API payload, recommendation and mobile: PASS')
