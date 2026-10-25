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
const photoGenerations=new WeakMap();
async function loadSafePhoto(img,photos,onSelected,onFailed){
  const generation=(photoGenerations.get(img)||0)+1;photoGenerations.set(img,generation);
  const active=()=>photoGenerations.get(img)===generation;
  img.hidden=true;img.referrerPolicy='no-referrer';const attempted=new Set(),deadline=Date.now()+20000;
  function select(photo,url,backup){
    if(!active())return;onSelected?.(photo,url);img.alt=photo.title;
    // A hidden lazy image can never enter the viewport to trigger its load.
    // The outer panel already delays loading; once a candidate is verified,
    // load it eagerly so onload can reveal the image.
    img.loading='eager';
    img.onload=()=>{if(active())img.hidden=false;};
    img.onerror=()=>{if(!active())return;if(backup)select(photo,backup);else next();};img.src=url;
    if(img.complete&&img.naturalWidth>0)img.hidden=false;
  }
  async function next(){
    for(const photo of photos){
      if(!active())return;
      const urls=photoCandidates(photo).filter(url=>!attempted.has(url)&&(location.protocol!=='https:'||new URL(url,location.origin).protocol==='https:'));
      if(!urls.length||Date.now()>deadline)continue;urls.forEach(url=>attempted.add(url));
      const probes=urls.map(url=>probePhoto(url).then(ok=>{if(!ok)throw Error('unavailable');return url;}));
      let winner;try{winner=await Promise.any(probes);}catch{continue;}
      if(!active())return;select(photo,winner);
      // Show a working thumbnail immediately, then upgrade without replacing a newer slide.
      if(winner!==urls[0])probes[0].then(url=>{if(active()&&img.src===new URL(winner,location.origin).href)select(photo,url,winner);}).catch(()=>{});
      return;
    }
    if(active()){img.removeAttribute('src');await onFailed?.();}
  }
  await next();
}

function fetchPlacePhotos(place,photoMode,force=false){
  const key=photoMode+':'+place.id;
  if(force)placePhotoRequests.delete(key);
  if(!placePhotoRequests.has(key))placePhotoRequests.set(key,api('/places/'+encodeURIComponent(place.id)+'/media?mode='+photoMode+(force?'&refresh=true':'')).then(async data=>{try{return await discoverPlacePhotos(place,data);}catch{return {...data,message:data.message||'사진 공급자에 연결하지 못했습니다. 다시 시도해 주세요.'};}}).catch(error=>{placePhotoRequests.delete(key);throw error;}));
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
  let refreshNext=false;
  const retry=()=>button('사진 다시 불러오기',()=>{refreshNext=true;placePhotoRequests.delete(photoMode+':'+place.id);photoLoads.clear();panel.replaceChildren(node('p','장소 사진을 불러오고 있어요…','photo-status'));return load();},'secondary photo-retry');
  async function load(){try{
    let data=await fetchPlacePhotos(place,photoMode,refreshNext);refreshNext=false;
    panel.replaceChildren();
    if(!data.photos.length){const empty=node('div',undefined,'photo-empty-card');empty.append(node('strong',place.name),node('p',place.category||'서울 장소'),node('p',place.address||'주소는 장소 정보에서 확인해 주세요.'));panel.append(empty);panel.append(node('p',data.message||'해당 장소의 사진을 찾지 못했습니다.','photo-status'),link('네이버에서 장소 사진 보기 ↗',data.search_url||'https://search.naver.com/search.naver?where=image&query='+encodeURIComponent(place.name+' 서울')),retry());return;}
    const photo=data.photos[0],figure=node('figure',undefined,'place-photo'),img=node('img');
    img.alt=photo.title+' — '+place.name;img.loading=eager?'eager':'lazy';img.decoding='async';img.width=640;img.height=420;
    img.referrerPolicy='no-referrer';
    const imageLink=link('',photo.source);imageLink.setAttribute('aria-label',photo.title+' 사진 원문 열기');imageLink.append(img);
    const credits=node('figcaption');
    if(['search_result','place_public'].includes(photo.kind))credits.append(node('span','네이버 사진 자료 · '),link(photo.kind==='place_public'?'장소 사진 출처':'원본 이미지',photo.source),node('span',' · '),link('검색 결과',photo.search_url));
    else credits.append(node('span','사진: '+photo.author+' · '),link(photo.license,photo.license_url),node('span',' · '),link('사진 원문',photo.source));
    const viewport=node('div',undefined,'photo-viewport');viewport.append(imageLink);figure.append(viewport,credits);
    let current=0,counter=null,busy=false,suppressClickUntil=0;
    const copy=node('div',undefined,'place-photo-copy');copy.append(node('span','PLACE SNAPSHOT','photo-eyebrow'),node('h5',photo.title),node('p',photo.caption||place.description||'원문에서 확인한 장소 사진입니다.'));
    if(place.description&&place.description!==photo.caption)copy.append(node('p',place.description,'hint'));
    copy.append(node('p',`촬영 ${photo.taken_at||'시점 미확인'} · 자료 확인 ${photo.checked_at}`,'hint'),node('p',photo.changes||'원본 변경 없음','hint'));
    if(['search_result','place_public'].includes(photo.kind))copy.append(node('p','검색 참고 이미지 · 원본 이용 조건 확인 필요','hint'));
    panel.append(figure,copy);
    const loading=node('p','사진을 확인하고 있어요…','photo-status');figure.append(loading);
    const updatePhoto=(next,loadedUrl)=>{
      const index=data.photos.indexOf(next);if(index>=0)current=index;
      if(counter)counter.textContent=`${current+1} / ${data.photos.length}`;
      imageLink.href=loadedUrl||next.source;imageLink.setAttribute('aria-label',next.title+' 표시 가능한 사진 크게 보기');
      copy.replaceChildren(node('span',next.image_role?next.image_role+' · 제목 기준':'장소 사진','photo-eyebrow'),node('h5',next.title),node('p',next.caption||place.description||''));
      if(place.description&&place.description!==next.caption)copy.append(node('p',place.description,'hint'));
      copy.append(node('p',`촬영 ${next.taken_at||'시점 미확인'} · 자료 확인 ${next.checked_at||'시점 미확인'}`,'hint'),node('p',next.changes||'원본 변경 없음','hint'));
      if(['search_result','place_public'].includes(next.kind))copy.append(node('p','검색 참고 이미지 · 원본 이용 조건 확인 필요','hint'));
      if(data.photos.length>1&&!full)copy.append(button('장소 사진 '+data.photos.length+'장 보기',()=>showPlace(place.id,photoMode)));
      credits.replaceChildren();if(['search_result','place_public'].includes(next.kind))credits.append(node('span','네이버 사진 자료 · '),link(next.kind==='place_public'?'장소 사진 출처':'원본 이미지',next.source),node('span',' · '),link('검색 결과',next.search_url));else credits.append(node('span','사진: '+next.author+' · '),link(next.license,next.license_url),node('span',' · '),link('사진 원문',next.source));loading.remove();
    };
    const initialLoad=loadSafePhoto(img,data.photos,updatePhoto,async()=>{
      try{if(data.photo_source!=='naver_public_place'){const fallback=await api('/places/'+encodeURIComponent(place.id)+'/media?mode='+photoMode+'&fallback=place');if(fallback.photos?.length){placePhotoRequests.set(photoMode+':'+place.id,Promise.resolve(fallback));await load();return;}}}catch{}
      try{const qid=/^Q[1-9][0-9]*$/.test(place.id)?place.id:null;if(qid){const fallback=await discoverPlacePhotos(place,{...data,photos:[],wikidata_id:qid});if(fallback.photos.length){await loadSafePhoto(img,fallback.photos,updatePhoto,unavailable);return;}}}catch{}
      unavailable();
    });
    function unavailable(){loading.remove();img.replaceWith(node('div','현재 표시할 수 있는 장소 사진이 없어요. 사진 원문에서 확인해 주세요.','photo-status'));panel.append(retry());}
    if(data.photos.length>1){
      viewport.tabIndex=0;viewport.setAttribute('role','group');viewport.setAttribute('aria-label',place.name+' 사진 · 좌우로 넘기기');
      counter=node('span',`1 / ${data.photos.length}`,'photo-counter');counter.setAttribute('aria-live','polite');
      let previousButton,nextButton;
      async function move(delta){
        await initialLoad;
        if(busy)return;busy=true;previousButton.disabled=true;nextButton.disabled=true;viewport.setAttribute('aria-busy','true');
        const previous=current,index=(current+delta+data.photos.length)%data.photos.length;
        try{await loadSafePhoto(img,[data.photos[index]],updatePhoto,async()=>{
          toast('이 사진은 표시할 수 없어 이전 사진을 유지해요.');
          await loadSafePhoto(img,[data.photos[previous]],updatePhoto,unavailable);
        });}finally{busy=false;previousButton.disabled=false;nextButton.disabled=false;viewport.setAttribute('aria-busy','false');}
      }
      previousButton=button('‹',()=>move(-1),'photo-arrow photo-prev');previousButton.setAttribute('aria-label','이전 사진');
      nextButton=button('›',()=>move(1),'photo-arrow photo-next');nextButton.setAttribute('aria-label','다음 사진');
      viewport.append(previousButton,nextButton,counter);
      viewport.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();move(e.key==='ArrowLeft'?-1:1);}});
      let touch=null;
      viewport.addEventListener('touchstart',e=>{touch=e.touches.length===1?{x:e.touches[0].clientX,y:e.touches[0].clientY}:null;},{passive:true});
      viewport.addEventListener('touchend',e=>{if(!touch||!e.changedTouches.length)return;const dx=e.changedTouches[0].clientX-touch.x,dy=e.changedTouches[0].clientY-touch.y;touch=null;if(Math.abs(dx)>45&&Math.abs(dx)>Math.abs(dy)*1.3){suppressClickUntil=Date.now()+500;move(dx<0?1:-1);}},{passive:true});
      viewport.addEventListener('touchcancel',()=>{touch=null;},{passive:true});
      imageLink.addEventListener('click',e=>{if(Date.now()<suppressClickUntil){e.preventDefault();e.stopPropagation();}});
    }
    if(data.photos.length>1&&!full){const more=button('장소 사진 '+data.photos.length+'장 보기',()=>showPlace(place.id,photoMode));copy.append(more);}
    if(full&&data.photos.length>1){const extra=node('div',undefined,'photo-extra');for(const item of data.photos.slice(1,5)){const f=node('figure',undefined,'place-photo'),image=node('img');image.alt=item.title;image.decoding='async';const credit=node('figcaption');if(['search_result','place_public'].includes(item.kind))credit.append(link('NAVER / original',item.source));else credit.append(node('span',item.author+' · '),link(item.license,item.license_url),node('span',' · '),link('사진 원문',item.source));f.append(image,credit);extra.append(f);loadSafePhoto(image,[item],null,()=>image.replaceWith(node('p','추가 사진을 표시할 수 없어요. 원문에서 확인해 주세요.','hint')));}panel.append(extra);}
  }catch(error){panel.replaceChildren(node('p','사진 정보를 불러오지 못했습니다. 다시 시도해 주세요.','photo-status'),retry());}}
  // 목록 전체를 한 번에 조회하지 않고 화면 근처의 장소만 불러온다.
  if(eager)load();else if('IntersectionObserver' in window){const observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting)){observer.disconnect();load();}},{rootMargin:'150px'});observer.observe(panel);}else load();
  return panel;
}
