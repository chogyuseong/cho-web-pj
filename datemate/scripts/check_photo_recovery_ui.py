import json
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1200,'height':900})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.route('**/test-broken-*',lambda r:r.fulfill(status=404,body='missing'))
    page.evaluate('''()=>{
      const photos=[{title:'first photo',kind:'search_result',image_url:'/test-broken-thumbnail',source:'/static/images/seoul-evening.jpg',search_url:'https://search.naver.com/'},{title:'extra photo',kind:'search_result',image_url:'/test-broken-extra',source:'/test-broken-original',search_url:'https://search.naver.com/'}];
      placePhotoRequests.set('real:test-photo',Promise.resolve({photos}));
      document.querySelector('#results').replaceChildren(placePhotoPanel({id:'test-photo',name:'test'},'real',true,true));
    }''')
    page.wait_for_function("document.querySelector('#results .place-photo img')?.naturalWidth>0&&!document.querySelector('#results .place-photo img').hidden")
    page.locator('.photo-extra .hint').wait_for()
    assert page.locator('#results img').evaluate_all('(imgs)=>imgs.every(i=>i.naturalWidth>0)')
    page.evaluate('''()=>{placePhotoRequests.set('real:test-all-failed',Promise.resolve({photos:[{title:'missing',kind:'search_result',image_url:'/test-broken-all',source:'/test-broken-all-original',search_url:'https://search.naver.com/'}]}));document.querySelector('#results').replaceChildren(placePhotoPanel({id:'test-all-failed',name:'test'},'real',false,true));}''')
    page.locator('#results .photo-retry').wait_for()
    assert page.locator('#results img').count()==0
    assert not errors,errors
    print(json.dumps({'broken_thumbnail_original_recovered':True,'broken_gallery_handled':True,'all_failed_no_broken_icon':True,'page_errors':errors}))
    browser.close()
