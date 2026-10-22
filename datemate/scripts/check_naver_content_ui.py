import json
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1280,'height':900})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.wait_for_function('Boolean(statusData)')
    page.evaluate("showPlace('Q482485','real')")
    page.locator('#dialog .place-photo-panel').scroll_into_view_if_needed()
    page.wait_for_function("document.querySelector('#dialog .place-photo img')?.naturalWidth>0",timeout=25000)
    page.locator('#dialog .place-blogs').scroll_into_view_if_needed()
    page.locator('#dialog .place-blogs summary').click()
    page.locator('#dialog .blog-search-post').first.wait_for(timeout=20000)
    counts={'image_loaded':True,'blog_posts':page.locator('#dialog .blog-search-post').count(),'page_errors':errors}
    page.screenshot(path=str(root/'docs'/'screenshots'/'naver-photo-blogs.png'))
    assert not errors,errors
    browser.close()
(root/'docs'/'naver-live-results.json').write_text(json.dumps(counts,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(counts))
