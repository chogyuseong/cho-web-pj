# [예전 기준 점검 스크립트] 예전 사진 복구 순서(썸네일보다 원본 먼저)를 전제로 합니다.
# 그대로 실행하면 실패할 수 있습니다. 자동 테스트(pytest)가 기준이며, 같은 내용은 tests/test_media.py, tests/test_additional_place_photos.py 에서 확인합니다.
print('[예전 기준 점검 스크립트] 예전 사진 복구 순서(썸네일보다 원본 먼저)를 전제로 합니다. 그대로 실행하면 실패할 수 있습니다. 대신 볼 테스트: tests/test_media.py, tests/test_additional_place_photos.py', flush=True)
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(bypass_csp=True,viewport={'width':1200,'height':900})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    # Both are valid: prefer the large original rather than a search thumbnail.
    page.evaluate('''async()=>{
      const photo={title:'quality',kind:'search_result',image_url:'/static/images/seoul-evening.jpg?thumbnail',source:'/static/images/seoul-evening.jpg?original'};
      const img=document.createElement('img');document.querySelector('#results').append(img);
      await loadSafePhoto(img,[photo],null,()=>{throw Error('valid original failed');});
      if(!img.src.endsWith('?original'))throw Error('thumbnail selected before original');
      const fallback={...photo,source:'/test-broken-quality',image_url:'/static/images/seoul-evening.jpg?fallback'};
      await loadSafePhoto(img,[fallback],null,()=>{throw Error('thumbnail fallback failed');});
      if(!img.src.endsWith('?fallback'))throw Error('original failure did not recover');
    }''')
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
    print(json.dumps({'original_preferred':True,'blocked_original_thumbnail_recovered':True,'broken_thumbnail_original_recovered':True,'broken_gallery_handled':True,'all_failed_no_broken_icon':True,'page_errors':errors}))
    browser.close()
