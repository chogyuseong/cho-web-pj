"""Browser smoke checks for the calm theme, without paid recommendation calls."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright

out = Path(__file__).resolve().parents[1] / 'docs' / 'screenshots'
out.mkdir(parents=True, exist_ok=True)
with sync_playwright() as pw:
    browser = pw.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width':1440,'height':1000})
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto('http://127.0.0.1:8000', wait_until='networkidle')
    page.locator('[data-region="연남"]').click()
    assert page.locator('[data-region="연남"]').get_attribute('aria-pressed') == 'true'
    page.locator('#quick-budget').fill('130000')
    assert '130,000' in page.locator('#quick-budget-value').inner_text()
    assert page.locator('.hero-photo img').evaluate('(img)=>img.complete && img.naturalWidth>0')
    page.screenshot(path=str(out/'calm-desktop.png'), full_page=True)
    page.locator('#nav-explore').click()
    assert page.locator('#explore-section').is_visible()
    page.locator('#nav-plan').click()
    assert page.locator('#planner-section').is_visible()
    page.locator('[data-preset="종로"]').click()
    assert page.locator('[data-region="종로"]').get_attribute('aria-pressed') == 'true'
    for width in [390, 768, 1024, 1440]:
        page.set_viewport_size({'width':width,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
    page.set_viewport_size({'width':390,'height':844})
    page.evaluate('window.scrollTo(0,0)')
    page.screenshot(path=str(out/'calm-mobile.png'), full_page=True)
    page.locator('#quick-start').focus()
    assert page.locator('#quick-start').evaluate('(e)=>e===document.activeElement')
    page.emulate_media(reduced_motion='reduce')
    assert page.evaluate('getComputedStyle(document.documentElement).scrollBehavior') == 'auto'
    assert not errors, errors
    print(json.dumps({'viewport_widths':[390,768,1024,1440], 'horizontal_overflow':False,
                      'region_budget_presets_navigation':'passed','image':'loaded', 'page_errors':errors}))
    browser.close()
