import base64
from playwright.sync_api import sync_playwright
png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jL1kAAAAASUVORK5CYII=')
with sync_playwright() as p:
 b=p.chromium.launch(channel='msedge',headless=True);page=b.new_page(viewport={'width':390,'height':844})
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.route('https://photos.example.test/**',lambda r:r.fulfill(content_type='image/png',body=png))
 page.goto('http://127.0.0.1:8000',wait_until='networkidle')
 result=page.evaluate('''async()=>{
   const original=probePhoto;let release;probePhoto=url=>url.includes('slow')?new Promise(resolve=>release=resolve):Promise.resolve(true);
   const img=document.createElement('img');document.body.append(img);const seen=[];const started=performance.now();
   await loadSafePhoto(img,[{kind:'search_result',title:'first',source:'https://photos.example.test/slow.png',image_url:'https://photos.example.test/fast.png'}],(_,url)=>seen.push(url),()=>{});
   const elapsed=performance.now()-started,first=img.src;
   await loadSafePhoto(img,[{kind:'search_result',title:'second',source:'https://photos.example.test/second.png',image_url:'https://photos.example.test/second.png'}],(_,url)=>seen.push(url),()=>{});
   release(true);await new Promise(resolve=>setTimeout(resolve,50));probePhoto=original;
   return {elapsed,first,current:img.src,seen};
 }''')
 assert result['elapsed']<1000 and result['first'].endswith('/fast.png')
 assert result['current'].endswith('/second.png') and not any(x.endswith('/slow.png') for x in result['seen'])
 page.route('https://broken.example.test/**',lambda r:r.fulfill(status=404))
 page.route('**/api/places/source-fallback/media?mode=real&fallback=place',lambda r:r.fulfill(json={'photo_source':'naver_public_place','photos':[{'kind':'place_public','title':'공개 업체사진','image_url':'https://photos.example.test/public.png','source':'https://map.naver.com/p/entry/place/123','search_url':'https://example.com'}]}))
 page.evaluate('''()=>{placePhotoRequests.set('real:source-fallback',Promise.resolve({photos:[{kind:'search_result',title:'broken',source:'https://broken.example.test/1.jpg',image_url:'https://broken.example.test/2.jpg'}]}));const panel=placePhotoPanel({id:'source-fallback',name:'검사장소'},'real',false,true);panel.id='source-fallback';document.body.append(panel);}''')
 page.wait_for_function('document.querySelector("#source-fallback .photo-viewport img")?.naturalWidth>0',timeout=15000)
 assert page.locator('#source-fallback .photo-viewport a').get_attribute('href').endswith('/public.png')
 assert not errors,errors
 print('PASS: fast thumbnail despite hanging original; stale original cannot replace next slide; dead-image public-source recovery')
 b.close()
