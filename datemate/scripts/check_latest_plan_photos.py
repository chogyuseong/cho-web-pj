import json
from pathlib import Path
from playwright.sync_api import sync_playwright
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import store

plan=json.loads(store.connect().execute('SELECT payload FROM plans ORDER BY rowid DESC LIMIT 1').fetchone()[0])
expected_images=min(3,len(plan['places']))
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000/?plan='+plan['id'],wait_until='networkidle')
    page.wait_for_function('Boolean(selected)',timeout=20000)
    # 상세 영역까지 스크롤하지 않아도 추천 카드의 사진이 로드되어야 한다.
    page.wait_for_function("expected=>Array.from(document.querySelectorAll('#results .plan-photo-preview img')).filter(i=>i.naturalWidth>0).length===expected",arg=expected_images,timeout=45000)
    page.locator('#results .plan-card').first.screenshot(path=str(Path(__file__).resolve().parents[1]/'docs/screenshots/plan-card-photos.png'))
    panels=page.locator('#plan-detail .place-photo-panel')
    results=[]
    for i in range(panels.count()):
        panel=panels.nth(i);panel.scroll_into_view_if_needed()
        try:page.wait_for_function("i=>{const p=document.querySelectorAll('#plan-detail .place-photo-panel')[i];return p?.querySelector('img')?.naturalWidth>0||(!p?.querySelector('img')&&!p?.textContent.includes('불러오고 있어요'))}",arg=i,timeout=40000)
        except Exception:pass
        results.append({'place':plan['places'][i]['name'],'images':panel.locator('img').evaluate_all('(items)=>items.filter(i=>i.naturalWidth>0).length'),'text':panel.inner_text()[:150]})
    assert all(p['images']>0 for p in results),results
    # 실패한 요청의 빈 결과가 계속 캐시되지 않고 재시도되는지 확인한다.
    failures={'count':0}
    def fail_once(route):
        if failures['count']==0:
            failures['count']+=1
            route.fulfill(status=503,content_type='application/json',body=json.dumps({'detail':'test unavailable'}))
        else:route.continue_()
    page.route('**/api/places/'+plan['places'][0]['id']+'/media?*',fail_once)
    page.reload(wait_until='networkidle')
    retry=page.locator('#results .plan-photo-item').first.locator('.photo-retry')
    retry.wait_for(timeout=20000);retry.click()
    page.wait_for_function("document.querySelector('#results .plan-photo-item img')?.naturalWidth>0",timeout=45000)
    assert not errors,errors
    report={'places':results,'card_images':expected_images,'retry_loaded':True,'page_errors':errors}
    (Path(__file__).resolve().parents[1]/'docs/latest-plan-photos.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(report,ensure_ascii=False))
    browser.close()
