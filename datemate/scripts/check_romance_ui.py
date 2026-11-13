# [예전 기준 점검 스크립트] 서울 시절 홈 화면(테마 카드 분위기마다 카드 하나)을 전제로 합니다. 지금 홈 테마 카드는 전국 6개 동네입니다.
# 그대로 실행하면 실패할 수 있습니다. 자동 테스트(pytest)가 기준이며, 같은 내용은 tests/test_imported_design_ui.py, tests/test_nationwide_home.py 에서 확인합니다.
"""디자인 변경 후 주요 화면과 기존 일정 동작 확인. localhost:8000 서버 필요."""
print('[예전 기준 점검 스크립트] 서울 시절 홈 화면(테마 카드 분위기마다 카드 하나)을 전제로 합니다. 지금 홈 테마 카드는 전국 6개 동네입니다. 그대로 실행하면 실패할 수 있습니다. 대신 볼 테스트: tests/test_imported_design_ui.py, tests/test_nationwide_home.py', flush=True)
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
out=root/'docs/screenshots'
out.mkdir(exist_ok=True)
results=[]
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(bypass_csp=True)
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    for width in (1440,768,390,320):
        page.set_viewport_size({'width':width,'height':1000 if width>720 else 844})
        page.goto('http://localhost:8000',wait_until='networkidle')
        page.wait_for_function('document.querySelectorAll("[name=themes]").length===7')
        page.evaluate('document.fonts.ready')
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),width
        assert page.locator('.hero-photo img').evaluate('i=>i.complete&&i.naturalWidth>0')
        page.screenshot(path=str(out/f'romance-home-{width}.png'),full_page=True)
        page.locator('[data-mood="지적인 데이트"]').click()
        assert page.locator('[name=date_subcategory]:checked').input_value()=='지적인 데이트'
        page.locator('[name=date_subcategory][value=""]').check()
        page.locator('#submit-plan').click()
        page.locator('#results .plan-card').first.wait_for()
        assert page.locator('#results .plan-card').count()==3
        page.wait_for_timeout(1500)
        assert page.locator('#plan-detail .plan-map').count()==1
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),(width,'plans')
        page.locator('#plan-detail .stop .actions button').first.click()
        assert page.get_by_text('● 고정됨',exact=True).count()==1
        page.locator('#plan-detail .stop').nth(1).get_by_role('button',name='교체',exact=True).click()
        page.get_by_role('button',name='이 장소로 교체').first.click()
        page.get_by_role('button',name='교체 되돌리기').wait_for()
        page.get_by_role('button',name='교체 되돌리기').click()
        page.screenshot(path=str(out/f'romance-plan-{width}.png'),full_page=True)
        page.locator('#nav-explore').click()
        page.locator('#catalog .place-card').first.wait_for()
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),(width,'explore')
        page.screenshot(path=str(out/f'romance-explore-{width}.png'),full_page=True)
        results.append(f'{width}px: image, theme preset, 3 plans, map, lock, replace, undo, explore OK')
    assert not errors,errors
    browser.close()
(root/'docs/romance-ui-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print('\n'.join(results))
