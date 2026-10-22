import json
import sys
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import store

root=Path(__file__).resolve().parents[1]
plan=json.loads(store.connect().execute('SELECT payload FROM plans ORDER BY rowid DESC LIMIT 1').fetchone()[0])
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000/?plan='+plan['id'],wait_until='networkidle')
    page.wait_for_function('Boolean(selected)')
    panels=page.locator('#results .plan-photo-item .place-blogs')
    assert panels.count()==3
    results=[]
    for i in range(3):
        panel=panels.nth(i)
        panel.locator('summary').click()
        page.wait_for_function("i=>document.querySelectorAll('#results .place-blogs')[i]?.querySelector('.place-blog-content')?.textContent.includes('관련도순')",arg=i,timeout=30000)
        links=panel.locator('.blog-search-post>a')
        rows=links.evaluate_all('(items)=>items.map(a=>({title:a.textContent,url:a.href,target:a.target}))')
        assert 1<=len(rows)<=3
        assert all(urlsplit(r['url']).hostname in ['blog.naver.com','m.blog.naver.com'] and r['target']=='_blank' for r in rows)
        results.append({'place':plan['places'][i]['name'],'links':rows})
    page.locator('#results .plan-card').first.screenshot(path=str(root/'docs/screenshots/plan-blog-links.png'))
    assert not errors,errors
    (root/'docs/plan-blog-links.json').write_text(json.dumps({'places':results,'page_errors':errors},ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps({'places':[{'name':p['place'],'posts':len(p['links'])} for p in results],'page_errors':errors},ensure_ascii=False))
    browser.close()
