const placePhotoRequests=new Map();
const photoLoads=new Map();
function photoCandidates(photo){
  // 검색 썸네일은 카드 크기로 확대하면 흐려지므로 원본을 먼저 시도한다.
  // Commons의 source는 이미지가 아닌 설명 페이지이므로 후보로 쓰지 않는다.
  const urls=photo.kind==='search_result'?[photo.source,photo.image_url,photo.url]:[photo.image_url,photo.url];
  return [...new Set(urls.filter(Boolean))].filter(url=>{try{return ['https:','http:'].includes(new URL(url,location.origin).protocol);}catch{return false;}});
}
function probePhoto(url){
  const cached=photoLoads.get(url);if(cached&&cached.until>Date.now())return cached.promise;
  const promise=new Promise(resolve=>{const probe=new Image();probe.referrerPolicy='no-referrer';let timer;const done=ok=>{clearTimeout(timer);probe.onload=null;probe.onerror=null;resolve(ok&&probe.naturalWidth>0);};probe.onload=()=>done(true);probe.onerror=()=>done(false);timer=setTimeout(()=>{done(false);probe.src='';},6000);probe.src=url;});
  photoLoads.set(url,{promise,until:Date.now()+60000});return promise;
}
async function loadSafePhoto(img,photos,onSelected,onFailed){
  img.hidden=true;img.referrerPolicy='no-referrer';const attempted=new Set(),deadline=Date.now()+20000;
  async function next(){
    for(const photo of photos){for(const url of photoCandidates(photo)){
      if(attempted.has(url)||Date.now()>deadline)continue;attempted.add(url);
      if(!await probePhoto(url))continue;
      onSelected?.(photo);img.alt=photo.title;img.onload=()=>{img.hidden=false;};img.onerror=()=>{img.hidden=true;next();};img.src=url;
      if(img.complete&&img.naturalWidth>0)img.hidden=false;return;
    }}
    img.removeAttribute('src');onFailed();
  }
  await next();
}
function fetchPlacePhotos(place,photoMode){
  const key=photoMode+':'+place.id;
  if(!placePhotoRequests.has(key))placePhotoRequests.set(key,api('/places/'+encodeURIComponent(place.id)+'/media?mode='+photoMode).then(async data=>{try{return await discoverPlacePhotos(place,data);}catch{return {...data,message:data.message||'사진 공급자에 연결하지 못했습니다. 다시 시도해 주세요.'};}}).catch(error=>{placePhotoRequests.delete(key);throw error;}));
  return placePhotoRequests.get(key);
}
function planPhotoPreview(plan){
  const row=node('div',undefined,'plan-photo-preview');
  if(plan.conditions.mode==='demo')return row;
  for(const place of plan.places.slice(0,3)){
    const item=node('div',undefined,'plan-photo-item');
    item.append(node('strong',place.name,'plan-photo-name'),placePhotoPanel(place,plan.conditions.mode,false,true),placeBlogPanel(place,plan.conditions.mode));
    row.append(item);
  }
  return row;
}
function placePhotoPanel(place,photoMode,full=false,eager=false){
  const panel=node('section',undefined,'place-photo-panel');panel.setAttribute('aria-label',place.name+' 사진과 설명');
  if(place.demo||photoMode==='demo'){
    panel.append(node('p','가상 장소 · 실제 사진을 붙이지 않습니다.','hint'));return panel;
  }
  const pending=node('p','장소 사진을 불러오고 있어요…','photo-status');pending.setAttribute('role','status');panel.append(pending);
  const retry=()=>button('사진 다시 불러오기',()=>{placePhotoRequests.delete(photoMode+':'+place.id);photoLoads.clear();panel.replaceChildren(node('p','장소 사진을 불러오고 있어요…','photo-status'));return load();},'secondary photo-retry');
  async function load(){try{
    const data=await fetchPlacePhotos(place,photoMode);
    panel.replaceChildren();
    if(!data.photos.length){panel.append(node('p',data.message||'해당 장소의 사진을 찾지 못했습니다.','photo-status'),retry());return;}
    const photo=data.photos[0],figure=node('figure',undefined,'place-photo'),img=node('img');
    img.alt=photo.title+' — '+place.name;img.loading=eager?'eager':'lazy';img.decoding='async';img.width=640;img.height=420;
    img.referrerPolicy='no-referrer';
    const imageLink=link('',photo.source);imageLink.setAttribute('aria-label',photo.title+' 사진 원문 열기');imageLink.append(img);
    const credits=node('figcaption');
    if(photo.kind==='search_result')credits.append(node('span','네이버 이미지 검색 · '),link('원본 이미지',photo.source),node('span',' · '),link('검색 결과',photo.search_url));
    else credits.append(node('span','사진: '+photo.author+' · '),link(photo.license,photo.license_url),node('span',' · '),link('사진 원문',photo.source));
    figure.append(imageLink,credits);
    const copy=node('div',undefined,'place-photo-copy');copy.append(node('span','PLACE SNAPSHOT','photo-eyebrow'),node('h5',photo.title),node('p',photo.caption||place.description||'원문에서 확인한 장소 사진입니다.'));
    if(place.description&&place.description!==photo.caption)copy.append(node('p',place.description,'hint'));
    copy.append(node('p',`촬영 ${photo.taken_at||'시점 미확인'} · 자료 확인 ${photo.checked_at}`,'hint'),node('p',photo.changes||'원본 변경 없음','hint'));
    if(photo.kind==='search_result')copy.append(node('p','검색 참고 이미지 · 원본 이용 조건 확인 필요','hint'));
    panel.append(figure,copy);
    const loading=node('p','사진을 확인하고 있어요…','photo-status');figure.append(loading);
    const updatePhoto=next=>{
      imageLink.href=next.source;imageLink.setAttribute('aria-label',next.title+' 사진 원문 열기');
      copy.replaceChildren(node('span','PLACE SNAPSHOT','photo-eyebrow'),node('h5',next.title),node('p',next.caption||place.description||''));
      if(place.description&&place.description!==next.caption)copy.append(node('p',place.description,'hint'));
      copy.append(node('p',`촬영 ${next.taken_at||'시점 미확인'} · 자료 확인 ${next.checked_at||'시점 미확인'}`,'hint'),node('p',next.changes||'원본 변경 없음','hint'));
      if(next.kind==='search_result')copy.append(node('p','검색 참고 이미지 · 원본 이용 조건 확인 필요','hint'));
      if(data.photos.length>1&&!full)copy.append(button('장소 사진 '+data.photos.length+'장 보기',()=>showPlace(place.id,photoMode)));
      credits.replaceChildren();if(next.kind==='search_result')credits.append(node('span','네이버 이미지 검색 · '),link('원본 이미지',next.source),node('span',' · '),link('검색 결과',next.search_url));else credits.append(node('span','사진: '+next.author+' · '),link(next.license,next.license_url),node('span',' · '),link('사진 원문',next.source));loading.remove();
    };
    loadSafePhoto(img,data.photos,updatePhoto,async()=>{
      try{const qid=/^Q[1-9][0-9]*$/.test(place.id)?place.id:null;if(qid){const fallback=await discoverPlacePhotos(place,{...data,photos:[],wikidata_id:qid});if(fallback.photos.length){await loadSafePhoto(img,fallback.photos,updatePhoto,unavailable);return;}}}catch{}
      unavailable();
    });
    function unavailable(){loading.remove();img.replaceWith(node('div','현재 표시할 수 있는 장소 사진이 없어요. 사진 원문에서 확인해 주세요.','photo-status'));panel.append(retry());}
    if(data.photos.length>1&&!full){const more=button('장소 사진 '+data.photos.length+'장 보기',()=>showPlace(place.id,photoMode));copy.append(more);}
    if(full&&data.photos.length>1){const extra=node('div',undefined,'photo-extra');for(const item of data.photos.slice(1,5)){const f=node('figure',undefined,'place-photo'),image=node('img');image.alt=item.title;image.decoding='async';const credit=node('figcaption');if(item.kind==='search_result')credit.append(link('NAVER / original',item.source));else credit.append(node('span',item.author+' · '),link(item.license,item.license_url),node('span',' · '),link('사진 원문',item.source));f.append(image,credit);extra.append(f);loadSafePhoto(image,[item],null,()=>image.replaceWith(node('p','추가 사진을 표시할 수 없어요. 원문에서 확인해 주세요.','hint')));}panel.append(extra);}
  }catch(error){panel.replaceChildren(node('p','사진 정보를 불러오지 못했습니다. 다시 시도해 주세요.','photo-status'),retry());}}
  // 목록 전체를 한 번에 조회하지 않고 화면 근처의 장소만 불러온다.
  if(eager)load();else if('IntersectionObserver' in window){const observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting)){observer.disconnect();load();}},{rootMargin:'150px'});observer.observe(panel);}else load();
  return panel;
}
