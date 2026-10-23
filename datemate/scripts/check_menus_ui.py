import sys,json
from pathlib import Path
from urllib.parse import quote
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import RUNTIME
places=[json.loads((RUNTIME/'menu-debug'/f'{i}.json').read_text(encoding='utf-8')) for i in [4,5]]
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    for i,food in enumerate(places):
        page.evaluate('''food=>{const box=restaurantMenuPanel(food);box.id='menu-case';document.body.append(box);}''',food)
        panel=page.locator('#menu-case');panel.scroll_into_view_if_needed()
        if i==0:
            panel.locator('.menu-price-row').first.wait_for(timeout=30000)
            assert panel.locator('.menu-price-row').count()==4
            assert '13,000원' in panel.inner_text() and '12,000원' in panel.inner_text()
        else:
            page.wait_for_function('document.querySelector("#menu-case .menu-price-row")||document.querySelector("#menu-case .menu-image-preview img")',timeout=30000)
            if panel.locator('.menu-image-preview img').count():
                page.wait_for_function('document.querySelector("#menu-case .menu-image-preview img")?.naturalWidth>0',timeout=45000)
                panel.get_by_role('button',name='메뉴판 크게 보기',exact=False).click()
                assert page.locator('.menu-image-gallery img').count()>0
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.locator('#close-dialog').click()
            else:
                assert panel.locator('.menu-price-row').count()==4
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        panel.evaluate('(e)=>e.remove()')
    assert not errors,errors
    print('PASS: live menu prices; matched live menu format; mobile; no JS errors')
    browser.close()
