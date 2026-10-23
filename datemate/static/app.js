'use strict';
const $=s=>document.querySelector(s), form=$('#conditions');
let statusData, plans=[], selected=null, locks=new Set(), mode='real';
function showPlannerPage(results, navigate=true){
  document.body.classList.toggle('show-date-plan',results);
  document.querySelector('.results-area').hidden=!results;
  document.querySelector('.conditions.panel').hidden=results;
  if(navigate){location.hash=results?'date-plan':'planner-section';}
  requestAnimationFrame(()=>{
    const heading=document.querySelector(results?'.results-area .section-heading h2':'.conditions .section-heading h2');
    heading.tabIndex=-1;heading.focus({preventScroll:true});
    document.getElementById('planner-section').scrollIntoView({block:'start'});
  });
}
window.addEventListener('hashchange',()=>{if(location.hash==='#explore-section'){setTab(true);search().catch(e=>toast(e.message));}else if(location.hash==='#date-plan'){setTab(false);showPlannerPage(true,false);}else if(['#curation','#inspiration'].includes(location.hash)){navigateHomeSection(location.hash,false);}else if(location.hash==='#planner-section'||!location.hash){setTab(false);showPlannerPage(false,false);}});
const won=n=>n==null?'미확인':Number(n).toLocaleString('ko-KR')+'원';
const range=v=>v==null?'미확인':v[0]===v[1]?won(v[0]):won(v[0])+' ~ '+won(v[1]);
const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=typeof text==='string'?text.replaceAll('근거','참조'):text;if(cls)n.className=cls;return n;};
function button(text,action,cls='secondary'){const b=node('button',text,cls);b.type='button';b.addEventListener('click',()=>Promise.resolve(action()).catch(error=>toast(error.message)));return b;}
function searchQueryAddressOnly(value){
  const text=String(value||'').normalize('NFKC').replace(/\s+/g,' ').trim().replace(/((?:대로|로))\s+(\d+(?:번)?길)/g,'$1$2');
  const road=text.match(/[가-힣A-Za-z0-9·.]+(?:대로|로|길)\s*\d+(?:-\d+)?/);
  return road?text.slice(0,road.index+road[0].length).trim():text;
}
function placeSearchQuery(place){return searchQueryAddressOnly(place.name+' '+(place.address||''));}
function normalizeLink(raw){
  if(typeof raw!=='string'||!raw.trim())return null;
  let value=raw.trim().replace(/&amp;/gi,'&');
  if(/^www\./i.test(value))value='https://'+value;
  try{
    const u=new URL(value,location.origin);
    if(u.username||u.password)return null;
    if(u.protocol==='nmap:')return 'https://map.naver.com/p/search/'+encodeURIComponent(u.searchParams.get('dname')||'서울');
    if(!['http:','https:'].includes(u.protocol))return null;
    if(u.origin===location.origin&&/^\/api\/plans\/[a-zA-Z0-9_-]+$/.test(u.pathname))return '/?plan='+encodeURIComponent(u.pathname.split('/').at(-1));
    if(['blog.naver.com','m.blog.naver.com'].includes(u.hostname)&&/PostView\.naver$/i.test(u.pathname)){
      const blog=u.searchParams.get('blogId'),post=u.searchParams.get('logNo');
      if(blog&&/^\d+$/.test(post||''))return 'https://blog.naver.com/'+encodeURIComponent(blog)+'/'+post;
    }
    if(u.hostname==='map.naver.com'&&u.pathname.startsWith('/p/search/')){
      const query=decodeURIComponent(u.pathname.slice('/p/search/'.length));
      u.pathname='/p/search/'+encodeURIComponent(searchQueryAddressOnly(query));
    }
    if(['search.naver.com','m.search.naver.com'].includes(u.hostname)&&u.searchParams.has('query'))u.searchParams.set('query',searchQueryAddressOnly(u.searchParams.get('query')));
    return u.href;
  }catch{return null;}
}
function link(text,url){
  const href=normalizeLink(url);if(!href)return node('span',text||'출처 주소 없음');
  const a=node('a',text);a.href=href;a.target='_blank';a.rel='noopener noreferrer';return a;
}
function sourceLinks(text,url,query){
  const wrap=node('span',undefined,'source-link-options');wrap.append(link(text,url));
  if(query){const fallback=link('원문이 안 열리면 검색 ↗','https://search.naver.com/search.naver?query='+encodeURIComponent(query));fallback.className='source-search-fallback';wrap.append(fallback);}
  return wrap;
}

function linkedText(tag,text,cls){
  const root=node(tag,undefined,cls),value=String(text||'').replaceAll('근거','참조');
  const pattern=/https?:\/\/[^\s<>"'`]+/gi;let offset=0;
  for(const match of value.matchAll(pattern)){
    let url=match[0].replace(/[.,;!]+$/,'');
    for(const [open,close] of [['(',')'],['[',']'],['{','}']]){while(url.endsWith(close)&&url.split(close).length>url.split(open).length)url=url.slice(0,-1);}
    root.append(document.createTextNode(value.slice(offset,match.index)),sourceLinks(url,url,url));
    offset=match.index+url.length;
  }
  root.append(document.createTextNode(value.slice(offset)));return root;
}
function toast(text){$('#toast').textContent=text;$('#toast').style.display='block';clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('#toast').style.display='none',6500);}
async function api(path,body,method){const r=await fetch('/api'+path,{method:method||(body?'POST':'GET'),headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});let data;try{data=await r.json();}catch{throw Error('서버 응답을 읽을 수 없습니다.');}if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:Array.isArray(data.detail)?data.detail.map(x=>`${x.loc.at(-1)}: ${x.msg}`).join('\n'):'요청에 실패했습니다.');return data;}
function today(){const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;}
form.elements.visit_date.value=today();
function values(){const f=new FormData(form), number=k=>Number(f.get(k));const data={course_query:f.get('course_query')||'',mode:f.get('mode'),allow_price_estimates:f.has('allow_price_estimates'),allow_estimates:f.has('allow_estimates'),stay_minutes:number('stay_minutes'),region:f.get('region'),origin:selectedLocation('origin'),visit_date:f.get('visit_date'),start:f.get('start'),end:f.get('end'),people:number('people'),budget:number('budget'),transport:f.get('transport'),count:number('count'),themes:f.getAll('themes'),date_category:f.get('date_category')||'',date_subcategory:f.get('date_subcategory')||'',theme_mode:f.get('theme_mode'),setting:f.get('setting'),avoid:f.get('avoid').split(',').map(x=>x.trim()).filter(Boolean),reservation:f.has('reservation'),max_leg:number('max_leg'),max_walk:f.get('max_walk')===''?null:number('max_walk'),return_home:f.has('return_home'),home:null,mbti:f.get('mbti').toUpperCase(),use_mbti:f.has('use_mbti'),request:f.get('request'),locked:{}};
 data.include_meal=f.has('include_meal');data.neighborhood_radius_km=Number(f.get('neighborhood_radius_km')||2.5);
 updateExperienceValues(data,f);
 if(data.return_home)data.home=selectedLocation('home');
 if(selected&&selected.conditions.mode===data.mode)for(const i of locks)data.locked[i]=selected.places[i].id;
 return data;}
async function init(){try{statusData=await api('/status');$('#status').textContent=`서울 전용 · 가상 장소 ${statusData.counts.demo.places}건 · 실제 장소 메타데이터 ${statusData.counts.real.places}건 / 색인 ${statusData.counts.real.indexed}건 · ${statusData.llm} · ${statusData.embedding==='demo'?'문자 해시 임베딩 데모 (의미 검색 아님)':'의미 임베딩 설정'} · 실제 운영정보 확인 필요`;
for(const theme of statusData.themes){const l=node('label'),i=node('input');i.type='checkbox';i.name='themes';i.value=theme;l.append(i,node('span',theme));$('#themes').append(l);}form.elements.region.value=statusData.region;mountDateCategories(statusData.date_categories);
const id=new URLSearchParams(location.search).get('plan');if(id){selected=await api('/plans/'+encodeURIComponent(id));mode=selected.conditions.mode;locks=new Set(Object.keys(selected.conditions.locked||{}).map(Number));form.elements.count.value=selected.conditions.count;plans=[selected];renderResults();renderDetail();showPlannerPage(true);}
if(location.hash==='#explore-section'){setTab(true);await search();}else if(['#curation','#inspiration'].includes(location.hash)){navigateHomeSection(location.hash,false);}else await resumePlanSearch();
}catch(e){$('#status').textContent=e.message;}}
let parsedRequest='';
async function applyRequest(){const text=form.elements.request.value.trim();if(!text||text===parsedRequest)return;const result=await api('/conditions/parse',{text});for(const [key,value] of Object.entries(result.patch)){if(key==='themes'){setDateClassification('콘셉트별','');document.querySelectorAll('[name=themes]').forEach(c=>c.checked=value.includes(c.value));}else if(form.elements[key]){if(form.elements[key].type==='checkbox')form.elements[key].checked=Boolean(value);else form.elements[key].value=value;}}$('#parse-notice').textContent=result.warnings.join(' ');parsedRequest=text;}
$('#parse').onclick=()=>applyRequest().then(()=>toast('해석된 조건을 폼에서 확인하고 수정해 주세요.')).catch(e=>toast(e.message));
function beginPlanSearch(){
  plans=[];selected=null;locks.clear();
  const detail=$('#plan-detail');detail.replaceChildren();
  $('#results').replaceChildren(detail);renderPlanMapCard();
  $('#results').setAttribute('aria-busy','true');
  $('#result-count').textContent='새 코스를 찾고 있어요';
  const progress=$('#progress');progress.classList.add('is-searching');
  const icon=node('span',undefined,'search-spinner');icon.setAttribute('aria-hidden','true');
  const copy=node('div',undefined,'search-progress-copy');
  copy.append(node('strong','우리에게 맞는 코스를 찾고 있어요'),node('p','조건 확인 → 코스 탐색 → 실시간 단가 검색·비용 계산 중…'),node('small','검색을 진행 중이에요. 결과가 준비되면 여기에 보여드릴게요.'));
  progress.replaceChildren(icon,copy);
}
form.addEventListener('submit',async e=>{
  e.preventDefault();const submit=$('#submit-plan');if(submit.disabled)return;
  try{
    submit.disabled=true;beginPlanSearch();setTab(false);showPlannerPage(true);
    await applyRequest();const data=values();mode=data.mode;
    const result=await createPlanWithProgress(data);plans=result.plans;selected=plans[0]||null;
    renderResults(result);renderDetail();
    $('#progress').textContent=plans.length?`추천 완료 · ${plans.length}개의 일정`:(result.reasons?.[0]||'추천 조건을 확인해 주세요.');
    if(window.innerWidth<720)$('#results').scrollIntoView({behavior:'smooth'});
  }catch(error){toast(error.message);showSearchFailure(error);}
  finally{submit.disabled=false;$('#progress').classList.remove('is-searching');$('#results').setAttribute('aria-busy','false');}
});
form.elements.mode.addEventListener('change',()=>{selected=null;locks.clear();plans=[];mode=form.elements.mode.value;clearLocationsForMode();$('#mode-badge').textContent=mode==='demo'?'DEMO SPACE':'REAL DATA';renderResults();renderDetail();});


function drawMap(p){const wrap=node('div',undefined,'map');const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 600 230');svg.setAttribute('role','img');svg.setAttribute('aria-label','장소 좌표 개략도. 실제 도로 경로 아님');const points=[p.conditions.origin,...p.places,...(p.conditions.return_home?[p.conditions.home]:[])];const lats=points.map(x=>x.lat),lons=points.map(x=>x.lon),minLat=Math.min(...lats),minLon=Math.min(...lons),dy=Math.max(.002,Math.max(...lats)-minLat),dx=Math.max(.002,Math.max(...lons)-minLon);const coords=points.map(x=>[60+(x.lon-minLon)/dx*480,180-(x.lat-minLat)/dy*130]);const path=document.createElementNS(ns,'polyline');path.setAttribute('points',coords.map(x=>x.join(',')).join(' '));path.setAttribute('fill','none');path.setAttribute('stroke','#91a27b');path.setAttribute('stroke-width','3');path.setAttribute('stroke-dasharray','7 6');svg.append(path);coords.forEach(([x,y],i)=>{const circle=document.createElementNS(ns,'circle');circle.setAttribute('cx',x);circle.setAttribute('cy',y);circle.setAttribute('r',17);circle.setAttribute('fill',i===0?'#e4774b':'#294d3d');const t=document.createElementNS(ns,'text');t.setAttribute('x',x);t.setAttribute('y',y+5);t.setAttribute('text-anchor','middle');t.setAttribute('fill','white');t.setAttribute('font-size','12');t.textContent=i===0?'출발':i>p.places.length?'귀가':String(i);svg.append(circle,t);});wrap.append(svg,node('div','좌표 개략도 · 직선 연결 · 실제 지도/경로 아님','map-caption'));return wrap;}
function openDialog(title){const root=$('#dialog-content');root.replaceChildren(node('h2',title));if(!$('#dialog').open)$('#dialog').showModal();return root;}
$('#close-dialog').onclick=()=>$('#dialog').close();$('#dialog').addEventListener('click',e=>{if(e.target===$('#dialog'))$('#dialog').close();});
async function showAlternatives(index){if(locks.has(index)){toast('고정한 장소는 먼저 고정을 해제하세요.');return;}const root=openDialog('조금 다른 장소로 바꿔볼까요?');const oldPlaceId=selected.places[index].id;const reason=experienceSelect('어떤 점을 바꾸고 싶나요?','replacement_reason',[['','변경 이유 선택'],['budget','비싸요'],['distance','멀어요'],['taste','취향이 아니에요'],['visited','이미 가봤어요']]);reason.querySelector('select').required=true;root.append(reason);root.append(node('p','앞뒤 이동과 전체 시간·비용을 다시 확인하고 있어요.','hint'));const result=await api('/plans/'+selected.id+'/alternatives',{index,locked:[...locks]});if(!result.alternatives.length)root.append(node('p','현재 조건을 충족하는 대체 장소가 없습니다. 시간·예산·테마 조건을 직접 수정해 주세요.','warning'));for(const option of result.alternatives){const card=node('article',undefined,'plan-card');card.append(node('h3',option.places[index].name),node('p',`전체 ${range(option.total)} · 시간 변화 ${option.delta.minutes}분 · 비용 변화 ${option.delta.cost.map(won).join(' ~ ')}`,'hint'),button('이 장소로 교체',async()=>{if(!reason.querySelector('select').reportValidity())return;const old=selected.id;selected=await api('/plans/'+old+'/replace',{index,locked:[...locks],replacement_id:option.places[index].id});replaceInList(old,selected);api('/plans/'+old+'/feedback',{kind:'replace_reason',place_id:oldPlaceId,reason:reason.querySelector('select').value}).catch(()=>toast('일정은 변경됐지만 변경 이유 저장에 실패했어요.'));$('#dialog').close();renderResults();renderDetail();}));root.append(card);}}
async function showPlace(id,placeMode){const root=openDialog('장소 정보를 불러오고 있어요');const p=await api('/places/'+encodeURIComponent(id)+'?mode='+placeMode);root.replaceChildren(node('span',p.demo?'가상 장소 · 시연용':'실제 장소 메타데이터 · 운영정보 확인 필요','tag'),node('h2',p.name),node('p',p.description||'확인된 설명이 없습니다.'));const facts=node('dl',undefined,'facts');for(const [key,value] of [['분류',p.category],['주소',p.address||'미확인'],['가격',range(p.price)],['운영시간',p.hours?p.hours.map(n=>`${Math.floor(n/60)}:${String(n%60).padStart(2,'0')}`).join(' ~ '):'미확인'],['휴무',p.closed_days===null?'미확인':p.closed_days.length?p.closed_days.map(n=>['월','화','수','목','금','토','일'][n]).join(', ')+'요일':'없음 (데모 가정)'],['체류 시간',p.stay?`${p.stay}분 / ${p.stay_basis}`:'미확인'],['예약',p.reservation===null?'미확인':p.reservation?'필요':'불필요'],['확인 시점',p.checked_at],['자료 유형',p.source_type],['외부 평점',p.rating?JSON.stringify(p.rating):'확보한 자료 없음'],['권리',p.license]])facts.append(node('dt',key),node('dd',value));root.append(operatingFactsNotice(p),facts,link('메타데이터 원문',p.source),node('h3','사진 · 영상'));
if(!p.demo&&statusData?.map_js_key){const map=node('div', 'NAVER Maps', 'map');root.append(map);officialPlaceMap(map,p,statusData.map_js_key);}const photos=(p.photos||[]).filter(x=>x.license&&x.source&&x.url).slice(0,5),videos=(p.videos||[]).filter(x=>x.source).slice(0,3);const gallery=node('div',undefined,'media-grid');photos.forEach(photo=>{const figure=node('figure'),img=node('img');loadSafePhoto(img,[{...photo,image_url:photo.url,title:photo.title||p.name}],null,()=>img.replaceWith(node('p','사진을 표시할 수 없어요. 사진 원문을 확인해 주세요.','hint')));img.alt=p.name;img.loading='lazy';figure.append(img,link('사진 출처 · '+photo.license,photo.source));gallery.append(figure);});root.append(gallery,placePhotoPanel(p,placeMode,true),placeBlogPanel(p,placeMode));if(!videos.length)root.append(node('p','확보한 영상이 없습니다. 영상 내용은 분석하지 않았습니다.','hint'));videos.forEach(v=>root.append(link(v.title||'영상 원문',v.source)));const links=node('div',undefined,'actions'),q=encodeURIComponent(p.name+' '+p.region);links.append(link('구글 사진 더보기','https://www.google.com/search?tbm=isch&q='+q),link('구글 영상 더보기','https://www.google.com/search?tbm=vid&q='+q),link('네이버 지도','https://map.naver.com/p/search/'+q));root.append(links,node('h3','근거를 보며 질문하기'),chatWidget('place',id,placeMode));}

async function loadReviews(root,p){const data=await api('/plans/'+p.id+'/reviews');root.replaceChildren(node('h3','우리 서비스의 일정 이용 후기'),node('strong',data.average==null?data.label:`★ ${data.average} / 5 · ${data.count}건`),node('p',data.verification,'hint'));const f=node('form',undefined,'review-form'),grid=node('div',undefined,'field-grid');function field(label,type,name,value){const l=node('label',label),i=node(type==='textarea'?'textarea':'input');i.name=name;if(type!=='textarea')i.type=type;i.required=true;i.value=value||'';l.append(i);return [l,i];}const [nick,n]=field('공개 별명','text','nickname','산책하는 우리');n.maxLength=40;const [rating,r]=field('별점 (1~5)','number','rating','5');r.min=1;r.max=5;const [visit,v]=field('방문일 (자기 신고)','date','visited',today());v.max=today();const [body,b]=field('후기 내용','textarea','body');b.rows=4;grid.append(nick,rating,visit);const save=node('button','후기 저장 / 내 후기 수정','primary');f.append(grid,body,save,node('p','최대 2 MiB 요청. 같은 브라우저의 동일 방문 순서 후기는 한 건으로 갱신됩니다.','hint'));const mine=data.rows.find(x=>x.mine);if(mine){n.value=mine.nickname;r.value=mine.rating;v.value=mine.visited;b.value=mine.body;}f.onsubmit=async e=>{e.preventDefault();save.disabled=true;try{await api('/plans/'+p.id+'/review',{nickname:n.value,rating:Number(r.value),visited:v.value,body:b.value},'PUT');await loadReviews(root,p);toast('후기를 저장했습니다.');}catch(error){toast(error.message);}finally{save.disabled=false;}};root.append(f);for(const review of data.rows){const row=node('article',undefined,'review');row.append(node('strong',`${review.nickname} · ★ ${review.rating}`),node('p',`방문 ${review.visited} · 작성 ${new Date(review.created*1000).toLocaleDateString('ko-KR')} · 자기 신고`,'review-meta'),node('p',review.body,'review-body'));const actions=node('div',undefined,'actions');if(review.mine)actions.append(button('내 후기 삭제',async()=>{await api('/reviews/'+review.id,null,'DELETE');await loadReviews(root,p);}));actions.append(button('신고',async()=>{const reason=prompt('신고 사유를 입력해 주세요.');if(reason?.trim()){const answer=await api('/reviews/'+review.id+'/report',{reason});toast(answer.notice);}}));row.append(actions);root.append(row);}}
function setTab(explore){document.body.classList.toggle('show-explore',explore);document.body.classList.remove('show-date-plan');if(!explore)showPlannerPage(false,false);$('#planner-section').hidden=explore;$('#explore-section').hidden=!explore;$('#nav-plan').classList.toggle('active',!explore);$('#nav-explore').classList.toggle('active',explore);
if(explore){
  if(location.hash!=='#explore-section')history.pushState(null,'','#explore-section');
  requestAnimationFrame(()=>{const section=$('#explore-section'),heading=section.querySelector('h2');heading.tabIndex=-1;heading.focus({preventScroll:true});section.scrollIntoView({block:'start',behavior:'auto'});});
}}
$('#nav-explore').onclick=()=>{setTab(true);search().catch(e=>toast(e.message));};
async function search(){return ExploreView.search();}
$('#search-button').onclick=()=>search().catch(e=>toast(e.message));$('#search').addEventListener('keydown',e=>{if(e.key==='Enter')search().catch(e=>toast(e.message));});mountLocationFields();mountPriceControls();init();

$('#edit-conditions').onclick=()=>{setTab(false);showPlannerPage(false);};


// Reveal the destination screen before scrolling, including repeated anchor clicks.
function navigateHomeSection(hash,updateHistory=true){
  if(!['#planner-section','#curation','#inspiration'].includes(hash))return;
  setTab(false);
  if(updateHistory&&location.hash!==hash)history.pushState(null,'',hash);
  requestAnimationFrame(()=>{
    const section=document.querySelector(hash);if(!section)return;
    const heading=section.querySelector('h2')||section;
    heading.tabIndex=-1;heading.focus({preventScroll:true});
    section.scrollIntoView({block:'start',behavior:'instant'});
  });
}
document.addEventListener('click',event=>{
  const anchor=event.target.closest('a[href]');
  if(!anchor||event.defaultPrevented||event.button!==0||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;
  const hash=anchor.getAttribute('href');
  if(['#planner-section','#curation','#inspiration'].includes(hash)){event.preventDefault();navigateHomeSection(hash);}
});
$('#nav-plan').onclick=()=>navigateHomeSection('#planner-section');
