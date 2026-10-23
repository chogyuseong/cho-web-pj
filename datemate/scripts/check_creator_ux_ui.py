import json,struct,tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000},accept_downloads=True)
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.wait_for_function('Boolean(statusData)')
    page.locator('.inspiration-card').first.wait_for()
    assert page.locator('.inspiration-card li').count()>0
    page.locator('.inspiration-card button').first.click()
    assert page.locator('[name=request]').input_value()
    assert page.evaluate('locationState.origin.name')
    page.locator('#submit-plan').click()
    page.wait_for_function('selected?.id&&!document.querySelector("#submit-plan").disabled',timeout=240000)
    assert page.locator('.fit-reasons').count()==1
    plan=page.evaluate('selected')
    assert plan['decision_summary']['fit_reasons']
    assert page.locator('.plan-option-tabs button strong').first.inner_text()==plan['decision_summary']['title']
    page.get_by_role('button',name='코스 카드 저장',exact=True).click()
    page.locator('.share-canvas').wait_for()
    with page.expect_download() as download:
        page.get_by_role('button',name='PNG 이미지 저장',exact=True).click()
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)/'card.png';download.value.save_as(path);content=path.read_bytes()
        assert content[:8]==b'\x89PNG\r\n\x1a\n'
        assert struct.unpack('>II',content[16:24])==(1080,1350)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.locator('#close-dialog').click()
    blog=page.locator('#plan-detail .place-blogs').first
    blog.locator('summary').click()
    page.wait_for_function('Boolean(document.querySelector("#plan-detail .place-blog-content")?.textContent.trim())&&!document.querySelector("#plan-detail .place-blog-content").textContent.includes("찾고 있어요")',timeout=30000)
    excerpts=page.locator('#plan-detail .blog-excerpt').count()
    # An empty provider result must remain a usable, honest empty state.
    assert page.locator('#plan-detail .place-blog-content').first.inner_text()
    photo=page.locator('#plan-detail .place-photo-panel').first
    photo.scroll_into_view_if_needed()
    photo.locator('.photo-next').wait_for(timeout=45000)
    photo.locator('.photo-next').click()
    page.wait_for_function('document.querySelector("#plan-detail .photo-counter")?.textContent==="2 / 5"',timeout=30000)
    page.route('**/api/places/ux-photo-empty/media?mode=real',lambda r:r.fulfill(json={'photos':[],'status':'not_found','message':'일치 사진 없음'}))
    page.evaluate("document.body.append(placePhotoPanel({id:'ux-photo-empty',name:'사진 없는 장소',category:'문화·예술',address:'서울'},'real',false,true))")
    page.locator('.photo-empty-card').wait_for()
    assert page.get_by_text('사진 없는 장소',exact=True).count()>0
    assert not errors,errors
    print(json.dumps({'inspiration':True,'input_applied':True,'fit_reasons':True,'descriptive_options':True,'png_size':[1080,1350],'blog_excerpts':excerpts,'mobile_no_overflow':True,'js_errors':errors}))
    browser.close()
