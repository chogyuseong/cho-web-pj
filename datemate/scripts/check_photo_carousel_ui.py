import base64
from playwright.sync_api import sync_playwright
png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jL1kAAAAASUVORK5CYII=')
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':390,'height':844},has_touch=True)
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.route('https://photos.example.test/**',lambda r:r.fulfill(content_type='image/png',body=png))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.evaluate('''()=>{
      const photos=[1,2,3].map(i=>({title:'사진'+i,kind:'search_result',image_url:'https://photos.example.test/'+i+'.png',source:'https://photos.example.test/'+i+'.png',search_url:'https://example.com',checked_at:'2026-10-23'}));
      placePhotoRequests.set('real:carousel-test',Promise.resolve({photos}));
      const panel=placePhotoPanel({id:'carousel-test',name:'검사 장소',category:'문화·예술'},'real',false,true);panel.id='carousel-test';document.body.append(panel);
    }''')
    root=page.locator('#carousel-test');root.locator('.photo-next').wait_for()
    page.wait_for_function('document.querySelector("#carousel-test img")?.naturalWidth>0')
    root.locator('.photo-next').click()
    page.wait_for_function('document.querySelector("#carousel-test .photo-counter").textContent==="2 / 3"')
    root.locator('.photo-prev').click()
    page.wait_for_function('document.querySelector("#carousel-test .photo-counter").textContent==="1 / 3"')
    root.locator('.photo-prev').click()
    page.wait_for_function('document.querySelector("#carousel-test .photo-counter").textContent==="3 / 3"')
    root.locator('.photo-viewport').focus();page.keyboard.press('ArrowRight')
    page.wait_for_function('document.querySelector("#carousel-test .photo-counter").textContent==="1 / 3"')
    root.locator('.photo-viewport').evaluate("""el=>{const start=new Event('touchstart');Object.defineProperty(start,'touches',{value:[{clientX:240,clientY:100}]});el.dispatchEvent(start);const end=new Event('touchend');Object.defineProperty(end,'changedTouches',{value:[{clientX:100,clientY:110}]});el.dispatchEvent(end);}""")
    page.wait_for_function('document.querySelector("#carousel-test .photo-counter").textContent==="2 / 3"')
    assert root.locator('.photo-choices').count()==0
    color=page.locator('.data-banner .eyebrow').evaluate('(e)=>getComputedStyle(e).color')
    assert color=='rgb(255, 255, 255)',color
    page.route('https://photos.example.test/broken.png',lambda r:r.fulfill(status=404))
    page.evaluate('''()=>{
      const good={title:'정상',kind:'search_result',image_url:'https://photos.example.test/good.png',source:'https://photos.example.test/good.png'};
      const bad={title:'실패',kind:'search_result',image_url:'https://photos.example.test/broken.png',source:'https://photos.example.test/broken.png'};
      placePhotoRequests.set('real:broken-carousel',Promise.resolve({photos:[good,bad]}));const panel=placePhotoPanel({id:'broken-carousel',name:'실패 검사'},'real',false,true);panel.id='broken-carousel';document.body.append(panel);
    }''')
    page.locator('#broken-carousel .photo-next').click()
    page.wait_for_function('document.querySelector("#broken-carousel .photo-viewport")?.getAttribute("aria-busy")==="false"')
    assert page.locator('#broken-carousel .photo-counter').inner_text()=='1 / 2'
    assert page.locator('#broken-carousel img').evaluate('(e)=>e.naturalWidth>0')
    assert not errors,errors
    print('PASS: white banner label; next/previous/wrap/keyboard/swipe; no numbered buttons; no JS errors')
    browser.close()
