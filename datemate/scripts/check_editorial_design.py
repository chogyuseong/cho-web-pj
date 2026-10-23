import sys,json
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import store
with store.connect() as db:row=db.execute('SELECT id FROM plans ORDER BY rowid DESC LIMIT 1').fetchone()
output=Path('docs/design-preview');output.mkdir(exist_ok=True)
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle');page.locator('.inspiration-card').first.wait_for()
    page.screenshot(path=str(output/'desktop.png'))
    for width in [320,390,768,1440]:
        page.set_viewport_size({'width':width,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),('home',width)
        if width==390:page.screenshot(path=str(output/'mobile.png'))
    if row:
        page.goto('http://127.0.0.1:8000/?plan='+row[0],wait_until='networkidle');page.wait_for_function('Boolean(selected)')
        for width in [320,390,768,1440]:
            page.set_viewport_size({'width':width,'height':900})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),('result',width)
        page.screenshot(path=str(output/'results.png'))
    assert not errors,errors
    print('PASS: home/results widths 320,390,768,1440; no overflow; no JS errors; screenshots saved')
    browser.close()
