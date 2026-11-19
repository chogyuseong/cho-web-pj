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
// 자료 확인 시각: 서버가 주는 ISO 시각(2026-11-17T00:22:24.22+00:00)을 이 기기 시간대의 '2026-11-17 09:22'로 보여 준다.
// 날짜만 있는 값(위키미디어)이나 읽을 수 없는 값은 그대로 둔다.
function photoCheckedAt(value){
  const text=String(value||'');if(!/^\d{4}-\d{2}-\d{2}T/.test(text))return text||'시점 미확인';
  const at=new Date(text);if(Number.isNaN(at.getTime()))return text;
  const two=n=>String(n).padStart(2,'0');
  return `${at.getFullYear()}-${two(at.getMonth()+1)}-${two(at.getDate())} ${two(at.getHours())}:${two(at.getMinutes())}`;
}
// 촬영·확인 시점, 변경 여부, 이용 조건은 '사진 정보' 접기 안에 둔다(전에는 사진마다 본문 크기 4줄, 2026-11-17 가독성 정리).
// 네이버 사진의 구분(업체 등록 / 방문자 후기 / 업체 연결 공개 사진 · 등록 주체 미확인, 내용 미검사)도 2026-11-18 부터 여기 첫 줄이다
// (출처 줄에서 옮김, 사용자 지시 — photoCredits 머리 주석). 접기가 없는 크게 보기 창에서는 '원본' 링크의 이름·title 로만 남는다.
// 검색으로 찾은 사진: 네이버 공개 사진(search_result·place_public)과 엄격한 이미지 검색 사진(image_search, 2026-11-19 app/image_search.strict_place_images).
const SEARCH_PHOTO_KINDS=['search_result','place_public','image_search'];
function photoMetaLines(photo){
  const lines=[node('p',`촬영 ${photo.taken_at||'시점 미확인'} · 자료 확인 ${photoCheckedAt(photo.checked_at)}`,'hint'),node('p',photo.changes||'원본 변경 없음','hint')];
  if(SEARCH_PHOTO_KINDS.includes(photo.kind))lines.unshift(node('p','사진 구분: '+photoLabel(photo,photo.kind==='image_search'?'검색 사진':'네이버 공개 사진'),'hint photo-kind'));
  if(SEARCH_PHOTO_KINDS.includes(photo.kind))lines.push(node('p','검색 참고 이미지 · 원본 이용 조건 확인 필요','hint'));
  return lines;
}
// 검색 사진 출처 줄 앞머리: 엄격한 이미지 검색 사진은 '검색 사진', 네이버 공개 사진은 그대로.
// 네이버 이미지 검색 사진은 '네이버 검색결과'임을 앞에 밝힌다(특약 2.1, 2026-11-20).
function searchPhotoPrefix(photo){return photo.kind==='image_search'?'네이버 검색결과 · 검색 사진 · ':'네이버 공개 사진 · ';}
// 사진이 끝내 없을 때 빈칸 대신 보여 줄 네이버 지도 링크. 다른 지도 링크와 같은 주소(app.js placeMapLink: 확인된 업체 번호가 있으면 그 업체 화면)를 쓴다.
function photoMapLink(place){
  const a=placeMapLink('네이버 지도에서 사진 보기 ↗',place);a.classList.add('photo-map-link');return a;
}
// 크게 보기(full)에서는 설명은 그대로 두고 시점·조건 줄만 접는다. 결과 화면의 장소 카드에서는 설명 전체를 접으므로(placePhotoPanel) 줄만 넣는다.
function photoMeta(photo,full){
  if(!full)return photoMetaLines(photo);
  const box=node('details',undefined,'photo-meta');
  box.append(node('summary','사진 정보'),...photoMetaLines(photo));
  return [box];
}
// 장소 일치만 확인하고 사진 내용 검사는 하지 않은 사진임을 라벨에 드러낸다.
function photoLabel(photo,fallback){return (photo.source_label||fallback)+(photo.visual_verification?.status==='unverified'?' · 내용 미검사':'');}
/* 사진 아래 출처 줄. 카드·크게 보기 창·장소 정보 창의 추가 사진이 같은 표기를 쓴다.
   네이버 사진(search_result·place_public): '네이버 공개 사진 · 원본 · 검색' 한 줄.
   엄격한 이미지 검색 사진(image_search, 2026-11-19): '검색 사진 · 원본 · 검색' 한 줄(원본 = 사진 원래 주소, 검색 = 네이버 이미지 검색 결과).
     2026-11-18 전에는 '네이버 사진 자료 · 업체 연결 공개 사진 · 등록 주체 미확인 · 검색 결과'였는데, 휴대폰 식당 카드에서 여러 줄로 쌓여 줄였다(사용자 지시).
     빠진 사진 구분(업체 등록 / 방문자 후기 / 등록 주체 미확인, 내용 미검사)은 '사진 정보' 접기로 옮겼다(사용자 지시):
       · 결과·식당 카드와 장소 정보 창: '사진 정보' 접기 안 첫 줄 '사진 구분: …'(photoMetaLines)
       · 모든 곳: '원본' 링크의 접근 가능한 이름('사진 원본 (업체 등록 사진)')과 title(마우스를 올리면 보임). 크게 보기 창은 접기가 없어 이것뿐.
     사진 구분을 다시 줄에 보이게 하려면 photoSourceLink 의 글자(text)에 photoLabel 을 넣으면 된다.
   위키미디어 등(그 밖의 kind): 촬영자 · 이용 조건 · 사진 원문(이용 조건 표기가 필요해 줄이지 않음). */
function photoSourceLink(photo,text){
  const a=link(text,photo.source),kind=photoLabel(photo,'사진 출처');
  // link 는 안전한 https 주소가 아니면 <span> 을 돌려준다. 그때는 이름을 붙이지 않는다(눌러지는 것이 아님).
  if(a.tagName==='A'){a.setAttribute('aria-label','사진 원본 ('+kind+')');a.title=kind;}
  return a;
}
function photoCredits(photo){
  const credits=node('figcaption');
  if(SEARCH_PHOTO_KINDS.includes(photo.kind)){
    credits.append(node('span',searchPhotoPrefix(photo)),photoSourceLink(photo,'원본'));
    // 검색 주소가 없으면 '검색' 자체를 뺀다(전에는 '검색 결과'가 링크 아닌 글자로 남았다).
    if(photo.search_url){const search=link('검색',photo.search_url);if(search.tagName==='A')search.setAttribute('aria-label','네이버 검색 결과');credits.append(node('span',' · '),search);}
  }
  else credits.append(node('span','사진: '+photo.author+' · '),link(photo.license,photo.license_url),node('span',' · '),link('사진 원문',photo.source));
  return credits;
}
// 장소 사진 크게 보기: 같은 페이지 안의 대화상자에서 자르지 않고 보여 준다. 여러 장이면 이전·다음, Esc·닫기·바깥 누르기로 닫는다.
// 장소 정보 대화상자(#dialog) 위에서도 열 수 있게 별도의 dialog 를 쓴다.
const PhotoViewer={
  dialog:null,photos:[],index:0,title:'',opener:null,
  build(){
    const dialog=node('dialog',undefined,'photo-viewer');dialog.id='photo-viewer';dialog.setAttribute('aria-labelledby','photo-viewer-title');
    const top=node('div',undefined,'dialog-top photo-viewer-top'),heading=node('h2','','photo-viewer-title');heading.id='photo-viewer-title';
    const close=button('✕',()=>dialog.close(),'photo-viewer-close');close.setAttribute('aria-label','닫기');
    top.append(heading,close);
    const figure=node('figure',undefined,'place-photo photo-viewer-figure'),frame=node('div',undefined,'photo-viewer-frame'),img=node('img');
    img.decoding='async';img.referrerPolicy='no-referrer';
    const status=node('p','','photo-status photo-viewer-status');status.setAttribute('role','status');
    const prev=button('‹',()=>this.move(-1),'photo-arrow photo-prev'),next=button('›',()=>this.move(1),'photo-arrow photo-next');
    prev.setAttribute('aria-label','이전 사진');next.setAttribute('aria-label','다음 사진');
    const counter=node('span','','photo-counter');counter.setAttribute('aria-live','polite');
    frame.append(img,status,prev,next,counter);figure.append(frame);
    dialog.append(top,figure);
    dialog.addEventListener('click',event=>{if(event.target===dialog)dialog.close();});
    dialog.addEventListener('keydown',event=>{if(this.photos.length>1&&(event.key==='ArrowLeft'||event.key==='ArrowRight')){event.preventDefault();this.move(event.key==='ArrowLeft'?-1:1);}});
    dialog.addEventListener('close',()=>{photoGenerations.set(img,(photoGenerations.get(img)||0)+1);img.removeAttribute('src');if(this.opener?.isConnected)this.opener.focus();});
    document.body.append(dialog);
    Object.assign(this,{dialog,heading,figure,img,status,prev,next,counter,close});
  },
  open(photos,index,title,opener){
    if(!photos?.length)return;
    if(!this.dialog)this.build();
    this.photos=photos;this.title=title;this.opener=opener||null;
    const many=photos.length>1;this.prev.hidden=this.next.hidden=this.counter.hidden=!many;
    if(!this.dialog.open)this.dialog.showModal();
    this.show(Math.min(Math.max(0,index||0),photos.length-1));
    this.close.focus();
  },
  move(delta){this.show((this.index+delta+this.photos.length)%this.photos.length);},
  show(index){
    this.index=index;const photo=this.photos[index];
    this.heading.textContent=this.title+' 사진';
    this.counter.textContent=`${index+1} / ${this.photos.length}`;
    this.figure.querySelector('figcaption')?.remove();this.figure.append(photoCredits(photo));
    this.status.textContent='사진을 불러오고 있어요…';
    loadSafePhoto(this.img,[photo],()=>{this.status.textContent='';},()=>{this.status.textContent='이 사진은 표시할 수 없어요. 아래 출처 링크에서 원문을 확인해 주세요.';});
  }
};
const photoGenerations=new WeakMap();
/* thumb:true(카드)면 사진마다 서버가 줄인 사진(photo.thumb_url, /photo-thumb, 폭 960 WebP)을 먼저 하나만 시험하고, 되면 그것으로 끝낸다.
   안 되면(404: 허용 목록 만료·받기 실패·줄여도 안 작아짐 등) 아래 원래 방식(원본 후보를 한꺼번에 시험)으로 넘어간다.
   줄인 사진을 원본 후보와 '같이' 시험하면 원본도 다 받아 버려 줄인 효과가 없으므로 반드시 먼저·따로 시험한다(2026-11-18, app/photo_thumb.py).
   크게 보기(PhotoViewer)는 thumb 없이 부른다(원본). 레저 사진 격자(leisure.js)도 2026-11-18 부터 thumb:true(그 '크게 보기' 링크는 원본). */
async function loadSafePhoto(img,photos,onSelected,onFailed,{thumb=false}={}){
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
      if(thumb&&photo.thumb_url&&!attempted.has(photo.thumb_url)){
        attempted.add(photo.thumb_url);
        if(await probePhoto(photo.thumb_url)){
          // 표시 중에 줄인 사진이 깨지면(드묾) 원본 첫 후보로 바꾼다(select 의 backup).
          if(active())select(photo,photo.thumb_url,photoCandidates(photo)[0]);
          return;
        }
      }
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

/* 사진 바이트는 화면 근처에 올 때 받기 시작한다(2026-11-17 운영 측정: 결과 사진 한 장이 3~7MB, 8192×5464 7.5MB 도 있었음).
   결과 화면 장소 카드(eager)는 사진 목록(/media, 지도 링크 확인 rememberVerifiedMapTarget 도 함께 함)은 바로 받되,
   후보 검사(new Image())와 <img> 는 카드가 화면에서 PHOTO_NEAR_MARGIN 안으로 들어올 때 시작한다. 검사용 Image() 가 이미 원본을 다 받으므로
   <img loading="lazy"> 만으로는 줄지 않는다. 인쇄 직전(beforeprint)에는 남은 사진을 모두 시작한다.
   IntersectionObserver 가 없는 브라우저는 전처럼 바로 받는다. */
const PHOTO_NEAR_MARGIN='600px 0px';
const deferredPhotoStarts=new Map();
function startPhotoNearViewport(target,start){
  if(!('IntersectionObserver' in window)){start();return;}
  for(const [run,element] of deferredPhotoStarts)if(!element.isConnected)run.cancel();
  let done=false;
  const observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting))run();},{rootMargin:PHOTO_NEAR_MARGIN});
  const stop=()=>{done=true;observer.disconnect();deferredPhotoStarts.delete(run);};
  function run(){if(done)return;stop();start();}
  run.cancel=stop;
  deferredPhotoStarts.set(run,target);observer.observe(target);
}
// 인쇄에서는 화면 밖 사진도 나와야 하므로 남은 사진을 모두 시작한다(닫힌 접기 안 사진은 종이에도 안 나오므로 그대로 둔다).
// 인쇄 전에 다 받지 못한 사진 칸은 인쇄에서 숨긴다(place-photos.css).
addEventListener('beforeprint',()=>{for(const [run,element] of [...deferredPhotoStarts]){if(!element.isConnected)run.cancel();else if(!element.closest('details:not([open])'))run();}});

function fetchPlacePhotos(place,photoMode,force=false){
  const key=photoMode+':'+place.id;
  if(force)placePhotoRequests.delete(key);
  if(!placePhotoRequests.has(key))placePhotoRequests.set(key,api('/places/'+encodeURIComponent(place.id)+'/media?mode='+photoMode+(force?'&refresh=true':''),null,'GET',{timeout:60000}).then(async data=>{rememberVerifiedMapTarget(place,data);try{return await discoverPlacePhotos(place,data);}catch{return {...data,message:data.message||'사진 공급자에 연결하지 못했습니다. 다시 시도해 주세요.'};}}).catch(error=>{placePhotoRequests.delete(key);throw error;}));
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
    // 사진이 없으면 빈 사진 칸 대신 이름·주소 카드와 네이버 지도 링크를 둔다(2026-11-19, 전에는 네이버 이미지 검색 결과 링크).
    if(!data.photos.length){const empty=node('div',undefined,'photo-empty-card');empty.append(node('strong',place.name),node('p',place.category||'장소'),node('p',place.address||'주소는 장소 정보에서 확인해 주세요.'));panel.append(empty);panel.append(node('p',data.message||'해당 장소의 사진을 찾지 못했습니다.','photo-status'),photoMapLink(place),retry());return;}
    const photo=data.photos[0],figure=node('figure',undefined,'place-photo'),img=node('img');
    img.alt=photo.title+' — '+place.name;img.loading=eager?'eager':'lazy';img.decoding='async';img.width=640;img.height=420;
    // 사진을 받기 전(화면 근처를 기다리는 동안)에는 src 없는 img 의 대체 글자가 보이지 않게 숨겨 둔다. 자리는 .photo-viewport 가 잡는다.
    img.referrerPolicy='no-referrer';img.hidden=true;
    // 사진을 누르면 같은 페이지 안의 큰 보기 창이 열린다(원문은 아래 출처 줄의 링크로 연다).
    const imageLink=node('button',undefined,'photo-open');imageLink.type='button';imageLink.setAttribute('aria-label',photo.title+' 사진 크게 보기');imageLink.append(img);
    imageLink.addEventListener('click',()=>{if(Date.now()>=suppressClickUntil)PhotoViewer.open(data.photos,current,place.name,imageLink);});
    const credits=photoCredits(photo);
    const viewport=node('div',undefined,'photo-viewport');viewport.append(imageLink);figure.append(viewport,credits);
    let current=0,counter=null,busy=false,suppressClickUntil=0;
    const copy=node('div',undefined,'place-photo-copy');copy.append(node('span','장소 사진','photo-eyebrow'),node('h5',photo.title),node('p',photo.caption||place.description||'원문에서 확인한 장소 사진입니다.'));
    if(place.description&&place.description!==photo.caption)copy.append(node('p',place.description,'hint'));
    copy.append(...photoMeta(photo,full));
    // 결과 화면의 장소 카드: 사진과 출처 줄만 보이고 사진 제목·설명·확인 시점은 '사진 정보' 하나로 접는다(2026-11-17 가독성 정리).
    let copyHost=copy;
    if(!full){copyHost=node('details',undefined,'photo-meta photo-copy-fold');copyHost.append(node('summary','사진 정보'),copy);}
    panel.append(figure,copyHost);
    if(data.photos.length>1&&!full)panel.append(button('장소 사진 '+data.photos.length+'장 보기',()=>showPlace(place.id,photoMode),'secondary photo-more'));
    const loading=node('p','사진을 확인하고 있어요…','photo-status');figure.append(loading);
    const updatePhoto=(next,loadedUrl)=>{
      const index=data.photos.indexOf(next);if(index>=0)current=index;
      if(counter)counter.textContent=`${current+1} / ${data.photos.length}`;
      imageLink.setAttribute('aria-label',next.title+' 사진 크게 보기');
      // 머리 글자는 사진의 역할만(예: '외관 · 제목 기준'). 사진 구분(업체 등록 등)은 아래 photoMeta 의 '사진 구분' 줄에 한 번만 둔다.
      copy.replaceChildren(node('span',next.image_role?next.image_role+' · 제목 기준':'장소 사진','photo-eyebrow'),node('h5',next.title),node('p',next.caption||place.description||''));
      if(place.description&&place.description!==next.caption)copy.append(node('p',place.description,'hint'));
      copy.append(...photoMeta(next,full));
      credits.replaceChildren(...photoCredits(next).childNodes);loading.remove();
    };
    // 결과 화면 장소 카드(eager)는 사진 바이트를 화면 근처에 올 때 받는다(startPhotoNearViewport). 다른 곳은 패널 자체가 이미 화면 근처에서 load() 했다.
    const initialLoad=new Promise(resolve=>{
      const begin=()=>resolve(loadSafePhoto(img,data.photos,updatePhoto,async()=>{
        try{if(data.photo_source!=='matched_review_photos'){const fallback=await api('/places/'+encodeURIComponent(place.id)+'/media?mode='+photoMode+'&fallback=reviews',null,'GET',{timeout:60000});if(fallback.photos?.length){placePhotoRequests.set(photoMode+':'+place.id,Promise.resolve(fallback));await load();return;}}}catch{}
        try{const qid=/^Q[1-9][0-9]*$/.test(place.id)?place.id:null;if(qid){const fallback=await discoverPlacePhotos(place,{...data,photos:[],wikidata_id:qid});if(fallback.photos.length){await loadSafePhoto(img,fallback.photos,updatePhoto,unavailable);return;}}}catch{}
        unavailable();
      },{thumb:true}));
      if(eager&&!full)startPhotoNearViewport(figure,begin);else begin();
    });
    // 후보 사진을 하나도 띄우지 못하면(깨진 칸 대신) 안내 글과 네이버 지도 링크를 둔다.
    function unavailable(){loading.remove();const box=node('div',undefined,'photo-status');box.append(node('p','현재 표시할 수 있는 장소 사진이 없어요.'),photoMapLink(place));imageLink.replaceWith(box);panel.append(retry());}
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
          await loadSafePhoto(img,[data.photos[previous]],updatePhoto,unavailable,{thumb:true});
        },{thumb:true});}finally{busy=false;previousButton.disabled=false;nextButton.disabled=false;viewport.setAttribute('aria-busy','false');}
      }
      previousButton=button('‹',()=>move(-1),'photo-arrow photo-prev');previousButton.setAttribute('aria-label','이전 사진');
      nextButton=button('›',()=>move(1),'photo-arrow photo-next');nextButton.setAttribute('aria-label','다음 사진');
      viewport.append(previousButton,nextButton,counter);
      viewport.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();move(e.key==='ArrowLeft'?-1:1);}});
      let touch=null;
      viewport.addEventListener('touchstart',e=>{touch=e.touches.length===1?{x:e.touches[0].clientX,y:e.touches[0].clientY}:null;},{passive:true});
      viewport.addEventListener('touchend',e=>{if(!touch||!e.changedTouches.length)return;const dx=e.changedTouches[0].clientX-touch.x,dy=e.changedTouches[0].clientY-touch.y;touch=null;if(Math.abs(dx)>45&&Math.abs(dx)>Math.abs(dy)*1.3){suppressClickUntil=Date.now()+500;move(dx<0?1:-1);}},{passive:true});
      viewport.addEventListener('touchcancel',()=>{touch=null;},{passive:true});
    }
    if(data.photos.length>1&&!full){const more=button('장소 사진 '+data.photos.length+'장 보기',()=>showPlace(place.id,photoMode));copy.append(more);}
    if(full&&data.photos.length>1){const extra=node('div',undefined,'photo-extra');for(const [offset,item] of data.photos.slice(1,5).entries()){const f=node('figure',undefined,'place-photo'),image=node('img');image.alt=item.title;image.decoding='async';const credit=node('figcaption');if(SEARCH_PHOTO_KINDS.includes(item.kind))credit.append(node('span',searchPhotoPrefix(item)),photoSourceLink(item,'원본'));else credit.append(node('span',item.author+' · '),link(item.license,item.license_url),node('span',' · '),link('사진 원문',item.source));const open=node('button',undefined,'photo-open');open.type='button';open.setAttribute('aria-label',item.title+' 사진 크게 보기');open.append(image);open.addEventListener('click',()=>PhotoViewer.open(data.photos,offset+1,place.name,open));f.append(open,credit);extra.append(f);loadSafePhoto(image,[item],null,()=>image.replaceWith(node('p','추가 사진을 표시할 수 없어요. 원문에서 확인해 주세요.','hint')),{thumb:true});}panel.append(extra);}
  }catch(error){panel.replaceChildren(node('p','사진 정보를 불러오지 못했습니다. 다시 시도해 주세요.','photo-status'),retry());}}
  // 목록 전체를 한 번에 조회하지 않고 화면 근처의 장소만 불러온다.
  if(eager)load();else if('IntersectionObserver' in window){const observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting)){observer.disconnect();load();}},{rootMargin:'150px'});observer.observe(panel);}else load();
  return panel;
}
