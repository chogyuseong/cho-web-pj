/* 공개 클라이언트 ID가 설정된 경우에만 로드한다. 비밀 API 키는 사용하지 않는다. */
let naverLoader;
// 공개 지도(Leaflet, JS 147KB·CSS 15KB)는 네이버 지도가 실패했을 때만 쓰므로, 그때 처음 불러온다(전에는 모든 첫 화면이 받고 CSS 가 렌더를 막았다).
let leafletLoader=null;
function loadLeaflet(){
  if(window.L)return Promise.resolve();
  if(leafletLoader)return leafletLoader;
  const attach=(tag,props)=>new Promise((resolve,reject)=>{
    const el=Object.assign(document.createElement(tag),props);el.dataset.datemateLeaflet='true';
    el.onload=resolve;el.onerror=()=>{el.remove();reject(Error('공개 지도 로딩 실패'));};
    document.head.append(el);
  });
  leafletLoader=Promise.all([
    document.querySelector('link[data-datemate-leaflet]')?Promise.resolve():attach('link',{rel:'stylesheet',href:'/static/vendor/leaflet/leaflet.css'}),
    attach('script',{src:'/static/vendor/leaflet/leaflet.js'}),
  ]).then(()=>{if(!window.L)throw Error('공개 지도 로딩 실패');}).catch(error=>{leafletLoader=null;throw error;});
  return leafletLoader;
}
function loadNaverMaps(key,force=false){
  if(force){naverLoader=null;window.naverMapAuthFailed=false;}
  if(window.naverMapAuthFailed)return Promise.reject(Error('지도 인증 실패'));
  if(!force&&window.naver?.maps)return Promise.resolve();
  if(naverLoader)return naverLoader;
  naverLoader=new Promise((resolve,reject)=>{
    const script=document.createElement('script');
    script.dataset.datemateNaver='true';
    const timeout=setTimeout(()=>{script.remove();reject(Error('지도 응답 시간 초과'));},20000);
    window.navermap_authFailure=()=>{
      window.naverMapAuthFailed=true;clearTimeout(timeout);reject(Error('지도 인증 실패'));
      // 인증 실패는 SDK onload 이후에도 도착할 수 있다.
      document.querySelectorAll('.plan-map').forEach(w=>w.showMapFallback?.());
    };
    script.src='https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId='+encodeURIComponent(key);
    script.onload=()=>{clearTimeout(timeout);window.naver?.maps?resolve():reject(Error('지도 인증 실패'));};
    script.onerror=()=>{clearTimeout(timeout);reject(Error('지도 로딩 실패'));};
    document.head.append(script);
  });
  const pending=naverLoader;
  pending.catch(()=>{if(naverLoader===pending)naverLoader=null;});
  return pending;
}

// 지도 자리: 모바일은 선택한 코스 카드 바로 뒤(#plan-map-slot), 데스크톱은 오른쪽 패널(#plan-map-rail).
const PLAN_MAP_MOBILE=matchMedia('(max-width:800px)');
let planMapCard=null;
PLAN_MAP_MOBILE.addEventListener('change',()=>{if(typeof selected!=='undefined'&&selected)renderPlanMapCard();});
function renderPlanMapCard(){
  let rail=document.getElementById('plan-map-rail');
  if(!rail){rail=node('aside',undefined,'plan-map-rail');rail.id='plan-map-rail';rail.setAttribute('aria-label','데이트 코스 지도');document.getElementById('planner-section').append(rail);}
  // 이전 지도는 어느 자리에 있었든(이미 문서에서 떨어졌어도) 정리한다.
  for(const holder of [planMapCard,rail])holder?.querySelectorAll('.plan-map').forEach(map=>map.disposeMap?.());
  planMapCard?.remove();planMapCard=null;
  const slot=document.getElementById('plan-map-slot'),mobile=Boolean(slot&&PLAN_MAP_MOBILE.matches);
  rail.replaceChildren();rail.hidden=!selected||mobile;
  if(slot){slot.replaceChildren();slot.hidden=!selected||!mobile;}
  document.getElementById('planner-section').classList.toggle('has-plan-map',Boolean(selected)&&!mobile);
  if(!selected)return;
  const card=node('section',undefined,'plan-map-card'),tabs=node('div',undefined,'map-option-tabs');
  tabs.setAttribute('aria-label','지도에서 볼 코스 선택');
  plans.forEach((plan,index)=>{
    const tab=button('코스 '+(index+1),()=>{
      if(selected?.id===plan.id)return;
      const scrollY=window.scrollY;
      selected=plan;locks=new Set(Object.keys(plan.conditions.locked||{}).map(Number));
      api('/plans/'+plan.id+'/feedback',{kind:'selection'}).catch(()=>{});
      renderResults();renderDetail();
      requestAnimationFrame(()=>{window.scrollTo({top:scrollY,behavior:'instant'});document.querySelector('.plan-map-card [aria-pressed="true"]')?.focus({preventScroll:true});});
    },selected.id===plan.id?'primary':'secondary');
    tab.dataset.mapOption=String(index+1);tab.setAttribute('aria-pressed',String(selected.id===plan.id));tabs.append(tab);
  });
  // 휴대폰에서는 지도가 상세('우리 하루, 자세히 보기', h2) 안에 들어가므로 한 단계 낮은 h3. 그래야 뒤의 '비용은 투명하게'가 지도에 속한 것처럼 읽히지 않는다(구역 표시줄·화면 읽기 목차).
  const mapTitle=node(mobile?'h3':'h2','우리 코스 지도','plan-map-title');
  card.append(mapTitle,tabs,node('p',courseTitle(selected),'map-course-title'),node('p',`이동 ${travelMinutes(selected)}분 · ${travelMode(selected).label}`,'hint map-travel-mode'),mapLegend(selected),node('p','지도 위에서 마우스 휠로 확대·축소할 수 있어요.','hint map-zoom-hint'),mapFocusNote(),drawPlanMap(selected));
  // 지도 아래 장소 목록: 한 줄에 네이버 지도 링크('1. 이름')와 「일정에서 보기」 단추(2026-11-18 가독성 8단계).
  // 단추는 지도 번호 표시와 같은 focusPlanStop(일정의 그 장소 카드로 스크롤 + 제목 포커스). 지도 표시는 키보드 Tab 으로 닿지 않아
  // 키보드·화면 읽기 사용자가 일정으로 가는 길이 이 단추다. 링크는 test_map_links_ui 가 '.map-place-list a' 로 확인한다.
  const places=node('div',undefined,'map-place-list');
  selected.places.forEach((place,index)=>{
    const row=node('div',undefined,'map-place-row'),go=button('일정에서 보기',()=>focusPlanStop(index),'secondary map-place-go');
    go.setAttribute('aria-label',`${index+1}번 ${place.name} 일정에서 보기`);
    row.append(placeMapLink((index+1)+'. '+place.name,place),go);places.append(row);
  });
  // 네이버 지역 검색으로 찾은 장소가 있으면 목록 아래에 '네이버 검색결과' 표시(특약 2.1). 장소마다의 원본 링크는 일정 카드에 있다.
  if(selected.places.some(place=>isNaverResult(place)))places.append(naverAttribution('지역 검색 장소 포함'));
  card.append(places);(mobile?slot:rail).append(card);planMapCard=card;
}

/* 구간 선 모양은 구간 수단(leg.mode)을 따른다. 자동차이면서 실제 길찾기 경로가 있으면 도로 실선,
   도보는 짧은 점선, 대중교통·자전거(그리고 길찾기를 하지 않은 자동차)는 긴 점선. 점선은 직선 연결이다. */
function legLineStyle(plan,leg){
  const mode=legMode(plan,leg);
  if(plan.conditions.mode==='real'&&mode==='car'&&leg?.status==='api'&&leg.path?.length>1)return 'road';
  return mode==='walk'?'short':'long';
}
// 지도에 그릴 구간 {from,to,leg} 목록. 구간 i 는 출발지·장소 순서의 i 번째에서 i+1 번째로 간다.
// 코스 끝에 둔 저녁 축제(app/festival_time.py)는 마지막 장소에서 행사장(= 출발지 좌표)으로 돌아오는 구간(festival_visit.leg — plan.legs 밖)을 거치고,
// 귀가는 행사장에서 떠난다. 좌표 없는 점(보관 기간이 지난 장소)에 닿는 구간은 그리는 쪽에서 뺀다.
// 코스 중간에 둔 낮 축제(position 'middle', after=i)는 장소 i → 행사장(festival_visit.leg) → 장소 i+1(plan.legs[i+1], 행사장에서 출발)로 잇는다.
function festivalMiddleAfter(plan){
  const visit=plan.festival_visit,after=visit?.after,count=(plan.places||[]).length;
  return visit?.position==='middle'&&Number.isInteger(after)&&after>=0&&after<count-1?after:null;
}
function planSegments(plan){
  const c=plan.conditions||{},places=plan.places||[],legs=plan.legs||[],stops=[c.origin,...places],segments=[],middle=festivalMiddleAfter(plan);
  for(let i=0;i<places.length;i++){
    if(middle!==null&&i===middle+1){segments.push({from:places[middle],to:c.origin,leg:plan.festival_visit.leg},{from:c.origin,to:places[i],leg:legs[i]});continue;}
    segments.push({from:stops[i],to:stops[i+1],leg:legs[i]});
  }
  let last=places.at(-1)||c.origin;
  if(plan.festival_visit?.position==='last'&&places.length){segments.push({from:last,to:c.origin,leg:plan.festival_visit.leg});last=c.origin;}
  if(c.return_home&&c.home)segments.push({from:last,to:c.home,leg:legs[places.length]});
  return segments;
}
const LINE_DASH={leaflet:{short:'4 6',long:'14 8'},svg:{short:'4 6',long:'14 8'},naver:{road:'solid',short:'shortdash',long:'longdash'}};
function mapLegend(plan){
  const styles=new Map();
  for(const {leg} of planSegments(plan)){if(!leg)continue;const style=legLineStyle(plan,leg);if(!styles.has(style))styles.set(style,new Set());styles.get(style).add(TRANSPORT_NAMES[legMode(plan,leg)]||'이동');}
  const parts=[];
  if(styles.has('road'))parts.push('실선은 자동차 실제 도로 경로');
  if(styles.has('short'))parts.push('짧은 점선은 '+[...styles.get('short')].join('·'));
  if(styles.has('long'))parts.push('긴 점선은 '+[...styles.get('long')].join('·'));
  const dashed=styles.has('short')||styles.has('long');
  const legend=node('p','선 모양: '+parts.join(' · ')+(dashed?'. 점선은 직선 연결이며 실제 경로가 아니에요.':'.'),'hint map-legend');
  // 팝업 표시 설명은 지도에 팝업 표시가 있을 때만 보인다(popupMapNote 가 켜고 끈다).
  if(typeof PopupCourse!=='undefined'){const popups=node('span',' 네모 ‘팝업’은 팝업이 자주 열리는 곳이에요(데이트메이트가 정해 둔 목록 · 코스·이동선에 넣지 않음 · 지금 열리는지는 알 수 없어요). 점선 네모 ‘팝업 일대’는 동네 기준 장소라 위치가 대략이에요.','map-legend-popups');popups.hidden=!popupMapItems().length;legend.append(popups);}
  return legend;
}

/* 방문일 축제는 코스 지점과 구분되는 표시로 겹쳐 보여준다. 좌표가 있는 축제만, 코스에는 넣지 않는다. */
function festivalMapItems(){return typeof FestivalPanel==='undefined'?[]:FestivalPanel.mapItems;}
function festivalMapInfo(festival){
  const box=node('div',undefined,'festival-map-info');
  box.append(node('strong',festival.title),node('p',`${festival.start} ~ ${festival.end}`),node('p','코스에 포함되지 않은 축제예요. 일정·요금은 주최 측 안내를 확인해 주세요.','hint'));
  if(festival.source_url)box.append(link('한국관광공사에서 확인 ↗',festival.source_url));
  return box;
}
function festivalMapNote(note,items){
  const chosen=items.some(f=>FestivalPanel.isChosen(f));
  note.hidden=!items.length;
  note.textContent=items.length?`노란 ‘축제’ 표시: 방문일 축제 ${items.length}곳 (코스에는 포함되지 않아요)${chosen?' · 진한 표시가 고른 축제예요':''}`:'';
}

/* 팝업 거점(우리 거점 사전, app/popup_hubs.py)은 축제와 별도의 표시 층이다. 검색된 글과는 무관하다(2026-11-20 부터 글에서 거점을 읽지 않음).
   데이터는 코스 결과 팝업 구역의 거점 목록(PopupCourse.mapItems, {hub, meters})과 같은 배열이고, 거점마다 표시 하나와 지도 아래 단추 하나.
   코스 역(원)·축제(노란 알약)와 다른 네모 모양이며, 동네 거점은 점선 네모 + ‘일대’ 글자로 건물과 구분한다.
   이동선에 잇지 않고 지도 범위 계산에도 넣지 않는다(중심·확대를 바꾸지 않음). */
function popupMapItems(){return typeof PopupCourse==='undefined'?[]:PopupCourse.mapItems;}
// 네이버 마커 HTML 은 고정 문자열만 쓴다. 거점 이름은 title 과 지도 아래 단추·정보 칸의 텍스트 노드로만 전달한다.
const POPUP_MARKER_HTML={building:'<span class="route-marker popup-marker">팝업</span>',area:'<span class="route-marker popup-marker popup-marker-area">팝업 일대</span>'};
function popupMarkerNode(group){const area=group.hub.kind==='area';return node('span',area?'팝업 일대':'팝업','route-marker popup-marker'+(area?' popup-marker-area':''));}
function popupMapTitle(group){return '팝업이 자주 열리는 곳 · '+PopupCourse.label(group.hub);}
function popupMapInfo(group){
  const hub=group.hub,box=node('div',undefined,'popup-map-info');
  box.append(node('strong',PopupCourse.label(hub)),node('p',PopupCourse.levelText(hub)));
  if(group.meters!==null&&group.meters!==undefined)box.append(node('p',PopupCourse.distanceText(group.meters,hub)));
  box.append(node('p','팝업이 자주 열리는 곳으로 데이트메이트가 정해 둔 장소예요. 코스에 포함되지 않았고, 지금 팝업이 열리는지는 알 수 없어요.','hint'));
  // 주변 코스 버튼은 코스 결과 팝업 구역의 거점 목록에 있다. 구역이 지도 아래(모바일)일 수도 왼쪽(데스크톱 2단)일 수도 있어
  // 위치를 말하지 않고, 그 거점으로 바로 가는 단추를 둔다(접혀 있으면 펼침, popups.js 의 PopupCourse.revealHub).
  if(PopupCourse.canReveal(hub.hub_id))box.append(button(`${hub.kind==='area'?'이 일대':'이 장소'} 주변 코스 버튼으로 가기`,()=>PopupCourse.revealHub(hub.hub_id),'secondary popup-map-goto'));
  return box;
}
/* 지도 아래의 팝업 장소 단추 목록과 정보 칸. 지도 위 팝업 표시는 코스 표시 아래 층이라 출발지와 같은 자리면 대부분 가려지고(확대 단계마다 달라짐),
   지도 폭(약 250~320px) 안의 정보창은 확대·축소 단추를 비키면 본문이 90~160px 로 좁아진다. 그래서 거점마다 44px 이상의 단추를 지도 아래에 두고,
   단추나 지도 표시를 누르면 지도 아래 칸(지도 폭 그대로, 안쪽 스크롤 없음)에 같은 내용(popupMapInfo)을 연다. 한 번에 거점 하나만 연다.
   단추는 aria-expanded·aria-controls 로 열림을 알린다. 지도 표시를 누르면 칸이 화면에 보이게만 스크롤하고 포커스는 옮기지 않는다.
   장소 이름은 텍스트 노드로만 넣는다.
   거점이 많으면 처음에는 앞의 POPUP_HUBS_FIRST 곳만 보이고(순서는 그대로) 「장소 n곳 더 보기」(aria-expanded)로 펼치고 「장소 목록 접기」로 다시 접는다.
   숨길 거점이 1곳뿐이면 단추 하나를 펼침 단추 하나로 바꾸는 셈이라 접지 않는다(POPUP_HUBS_FIRST+1 곳까지는 펼침 단추 없이 모두 보임).
   그래서 접힌 목록은 거점 수와 관계없이 최대 4줄이다. 접힌 거점을 지도 표시로 열면 목록을 펼쳐 그 단추가 보이게 하고,
   열린 거점이 숨는 쪽이면 접을 때 칸을 닫는다(열린 칸의 단추가 화면에 없는 상태를 만들지 않음). */
const POPUP_HUBS_FIRST=3;
let popupPanelCount=0;
function popupHubList(){
  const list=node('div',undefined,'map-popup-hubs'),panel=node('div',undefined,'map-popup-panel');
  list.setAttribute('role','group');list.setAttribute('aria-label','지도에 표시한 팝업 장소');list.hidden=true;
  const id=++popupPanelCount;list.id='map-popup-hubs-'+id;panel.id='map-popup-panel-'+id;panel.hidden=true;
  let groups=[],open=-1,folded=false;
  const chips=()=>[...list.querySelectorAll('.map-popup-hub')];
  const more=button('',()=>fold(!folded,true),'secondary map-popup-more');
  more.setAttribute('aria-controls',list.id);
  const fold=(value,focus=false)=>{
    const foldable=groups.length>POPUP_HUBS_FIRST+1;
    folded=value&&foldable;
    chips().forEach((chip,i)=>{chip.hidden=folded&&i>=POPUP_HUBS_FIRST;});
    more.setAttribute('aria-expanded',String(!folded));
    more.textContent=folded?`장소 ${groups.length-POPUP_HUBS_FIRST}곳 더 보기`:'장소 목록 접기';
    if(folded&&open>=POPUP_HUBS_FIRST)show(-1);
    // 펼치면 키보드 사용자가 새로 보인 첫 장소에서 이어 가게 한다(펼침 단추는 목록 끝이라 Tab 으로는 앞쪽에 못 감).
    else if(!folded&&focus)chips()[POPUP_HUBS_FIRST]?.focus();
  };
  const show=(index,reveal=false)=>{
    open=groups[index]?index:-1;
    if(folded&&open>=POPUP_HUBS_FIRST)fold(false);
    chips().forEach((chip,i)=>chip.setAttribute('aria-expanded',String(i===open)));
    panel.replaceChildren();panel.hidden=open<0;
    if(open<0)return;
    const at=open;
    panel.append(popupMapInfo(groups[at]),button('정보 닫기',()=>{show(-1);chips()[at]?.focus();},'secondary map-popup-close'));
    if(reveal)revealPanel();
  };
  // 데스크톱 오른쪽 패널(자체 스크롤, 지도가 위쪽에 붙음)에서는 패널만 움직여 칸 머리를 붙은 지도 바로 아래(scroll-padding-top)에 둔다.
  // 칸이 보이는 자리보다 길면 'nearest' 가 칸 아래쪽을 맞춰 머리가 지도 밑에 숨고, 'start' 는 패널 밖 문서까지 움직이기 때문이다. 모바일은 그대로 'nearest'.
  const revealPanel=()=>{
    const card=panel.closest('.plan-map-rail .plan-map-card');
    if(!card){panel.scrollIntoView({block:'nearest'});return;}
    const pad=parseFloat(getComputedStyle(card).scrollPaddingTop)||0,top=panel.getBoundingClientRect().top-card.getBoundingClientRect().top;
    if(top<pad||panel.getBoundingClientRect().bottom>card.getBoundingClientRect().bottom)card.scrollTop+=top-pad;
  };
  // 정보 칸 안(단추·닫기)에서 Esc 를 누르면 닫고 그 장소 단추로 돌아간다.
  panel.addEventListener('keydown',event=>{if(event.key==='Escape'&&open>=0){const at=open;show(-1);chips()[at]?.focus();}});
  const set=items=>{
    groups=items;list.replaceChildren();list.hidden=!items.length;
    items.forEach((group,index)=>{
      const area=group.hub.kind==='area',chip=button('',()=>show(open===index?-1:index),'secondary map-popup-hub');
      chip.append(node('span',area?'팝업 일대':'팝업','map-popup-badge'+(area?' is-area':'')),node('span',PopupCourse.label(group.hub),'map-popup-hub-name'));
      chip.setAttribute('aria-expanded','false');chip.setAttribute('aria-controls',panel.id);list.append(chip);
    });
    if(items.length>POPUP_HUBS_FIRST+1)list.append(more);
    show(-1);fold(true);
  };
  return {list,panel,show,set};
}
function popupMapNote(note,items){
  note.hidden=!items.length;
  note.textContent=items.length?`네모 ‘팝업’ 표시: 팝업이 자주 열리는 곳 ${items.length}곳 (데이트메이트가 정해 둔 목록이에요 · 코스에 포함되지 않아요 · 지금 팝업이 열리는지는 알 수 없어요). 아래 장소나 지도 표시를 누르면 설명이 열려요.`:'';
  const legend=note.closest('.plan-map-card')?.querySelector('.map-legend-popups');if(legend)legend.hidden=!items.length;
}

/* 지도의 장소 번호 표시(1..N, 출발·귀가 제외)를 누르면 코스 상세(#plan-detail)의 같은 순번 장소 카드로 스크롤하고
   카드 제목(h4)에 키보드 포커스를 옮긴다(데스크톱 오른쪽 패널·휴대폰 일정 뒤 지도 모두). 스크롤은 behavior 를 주지 않아
   html 의 scroll-behavior(동작 줄이기면 auto)를 따르고, 머리 가림은 html 의 scroll-padding-top 이 맡는다.
   제목은 원래 포커스를 받지 않으므로 tabindex=-1 을 잠시 붙이고(이미 있으면 그대로), 포커스가 떠나면 우리가 붙인 것만 뗀다.
   포커스 표시는 plan-map.css(.timeline-card>h4.map-stop-target:focus) — 마우스로 누른 뒤의 스크립트 포커스는 :focus-visible 이 아니라서 따로 둔다. */
function focusPlanStop(index){
  const stop=document.querySelectorAll('#plan-detail .stop')[index],title=stop?.querySelector('.timeline-card>h4');
  if(!title)return false;
  if(!title.classList.contains('map-stop-target')){
    const added=!title.hasAttribute('tabindex');
    if(added)title.tabIndex=-1;
    title.classList.add('map-stop-target');
    title.addEventListener('blur',()=>{title.classList.remove('map-stop-target');if(added)title.removeAttribute('tabindex');},{once:true});
  }
  stop.scrollIntoView({block:'start'});
  title.focus({preventScroll:true});
  return true;
}
/* ── 일정 카드 → 지도(리디자인 3단계, datemate_2026.md §2.5) ───────────────────────────────────────
   위 focusPlanStop(지도 표시 → 일정 카드)의 반대 방향. 일정 장소 카드의 「코스 지도에서 보기」(plan-detail.js)가 부른다.
   지도(drawPlanMap 의 wrap.focusStop)가 그 장소 표시를 강조하고 지도를 그 위치로 옮긴다(네이버 지도·공개 지도 Leaflet 모두).
   지도를 아직 불러오는 중이면 그린 직후에 옮긴다. 개략도만 남은 경우(공개 지도도 실패)는 옮길 지도가 없다고 알린다.
   - 데스크톱: 지도는 오른쪽 고정 패널에 늘 보이므로 페이지는 그대로 두고, 패널 카드가 아래로 넘겨져 지도가 가려졌으면 패널 안만 넘긴다.
     키보드 포커스는 누른 단추에 그대로 둔다(일정을 계속 읽는다).
   - 휴대폰(지도가 일정 뒤 #plan-map-slot): 지도 바로 위 안내 줄로 스크롤하고, 그 줄의 「N번 일정으로 돌아가기」 단추로 포커스를 옮긴다.
   안내 줄(.map-focus-status, role=status)은 처음부터 문서에 있어야 화면 읽기가 바뀐 글을 읽는다(비어 있으면 높이 0). */
function mapFocusNote(){
  const box=node('div',undefined,'map-focus-note'),status=node('p','','map-focus-status');
  status.setAttribute('role','status');
  const back=button('',()=>focusPlanStop(Number(back.dataset.index)),'secondary map-focus-back');back.hidden=true;
  box.append(status,back);return box;
}
function focusPlanMapStop(index){
  const card=planMapCard,place=selected?.places?.[index];
  if(!card?.isConnected||!place)return false;
  const wrap=card.querySelector('.plan-map'),status=card.querySelector('.map-focus-status'),back=card.querySelector('.map-focus-back');
  const mobile=Boolean(card.closest('#plan-map-slot')),name=`${index+1}번 장소(${place.name})`;
  const state=Number.isFinite(place.lat)&&Number.isFinite(place.lon)?wrap?.focusStop?.(index)||'none':'nowhere';
  if(status)status.textContent={applied:`${name}를 지도 가운데에 표시했어요.`,pending:`지도를 불러오면 ${name}를 가운데에 표시할게요.`,
    none:`지도를 불러오지 못해 ${name} 위치를 표시하지 못했어요. 장소 목록의 네이버 지도 링크를 이용해 주세요.`,nowhere:`${name}는 위치 정보가 없어 지도에 표시하지 못해요.`}[state];
  if(back){back.hidden=!mobile;back.dataset.index=String(index);back.textContent=`${index+1}번 일정으로 돌아가기`;}
  if(mobile){
    (status||wrap||card).scrollIntoView({block:'start'});
    back?.focus({preventScroll:true});
  }else if(wrap){
    // 패널 카드(넘김 가능) 안에서 지도 칸(.naver-plan-map, 공개 지도도 같은 class)이 보이게 필요한 만큼만 넘긴다(안내 줄은 패널에서 화면 읽기 전용, redesign.css).
    // 카드 밖 문서는 움직이지 않는다(popupHubList revealPanel 과 같은 방식). 이미 다 보이면 그대로 둔다(위의 요약·탭이 밀려나지 않게).
    const box=card.getBoundingClientRect(),map=(wrap.querySelector('.naver-plan-map')||wrap).getBoundingClientRect();
    if(map.top<box.top)card.scrollTop+=map.top-box.top-8;
    else if(map.bottom>box.bottom)card.scrollTop+=Math.min(map.bottom-box.bottom+8,map.top-box.top-8);
  }
  return true;
}
// 장소 번호 표시의 접근 가능한 이름은 고정 문구(번호만)다. 장소 이름은 HTML 에 넣지 않고 title(네이버 표시 옵션)로만 준다.
function stopMarkerLabel(number){return number+'번 장소 · 눌러서 일정에서 보기';}
/* ── 겹친 장소 번호 합치기(가독성 7단계, 2026-11-18) ──────────────────────────────────────────────
   왜: 운영 성수 코스(390px, 확대 14)에서 2·3번 표시가 7px 거리로 겹쳐, 2번 원 가운데를 누르면 98%가 3번으로 갔다.
   무엇: 네이버 지도의 장소 번호(1..N) 표시를 화면 거리로 묶어, 가까운 것은 '2·3' 알약 표시 하나로 그린다(drawPlanMap 의 drawStops).
   함께 맞춰야 하는 값(하나를 바꾸면 나머지도):
     · 표시 지름 38px  = plan-map.css .route-marker width/height = STOP_MERGE_PX = 아래 stopMarkerWidth 의 1개 너비 = 기준점 y(19 = 38/2)
     · 알약 모서리 19px = plan-map.css .route-stop-merged border-radius(높이의 절반)
     · 너비 공식       = stopMarkerWidth, tests/test_readability_stage7_ui.py 가 56px(2개)·74px(3개)·기준점 x 를 확인한다
   대체 지도(Leaflet, 이 파일 fallback()의 drawLeafletStops)도 같은 planStopGroups 로 묶는다(2026-11-18 가독성 8단계). */

// 화면 거리(px)가 이보다 가까운 장소 번호는 한 표시로 합친다. 번호 표시 지름과 같게 둬서 '조금이라도 겹치면 합침'이다.
// 더 일찍 합치고 싶으면(예: 휴대폰 누름 영역 44px 기준) 이 값만 키우면 된다.
const STOP_MERGE_PX=38;
// 묶음 하나의 표시 너비(px). 1개는 원(38), 2개부터 번호가 하나 늘 때마다 18px 넓힌다('2·3' 56, '1·2·3' 74).
// 두 자리 번호('10·11')도 56px 안에 들어가는 것을 test_merged_marker_text_fits_inside_the_pill 이 실제 CSS 로 잰다.
// 너비는 CSS 가 아니라 style 로 준다: 네이버 표시의 기준점(anchor)을 너비의 가운데로 줘야 장소 좌표에 표시 가운데가 오기 때문이다.
function stopMarkerWidth(count){return 38+18*(count-1);}
// places 의 순번을 화면에서 겹치는 것끼리 묶는다. 결과는 [[0],[1,2],…](바깥·안쪽 모두 순번 오름차순, 모든 순번이 정확히 한 번).
// 묶는 법(욕심 방식): 장소를 순서대로 보며, 앞에서 만든 묶음 중 '첫 장소'와의 거리가 STOP_MERGE_PX 미만인 첫 묶음에 넣는다.
//   그래서 사슬처럼 이어진 경우(A–B 30px, B–C 30px, A–C 60px)는 {A,B},{C} 가 된다. B 와 C 의 표시가 조금 겹칠 수 있지만
//   한 표시가 끝없이 길어지지 않는다. 사슬 전체를 묶고 싶으면 '묶음의 아무 장소와 가까우면' 으로 바꾸면 된다(find 안의 비교).
// offsetOf(place)→{x,y}: 지금 확대 수준의 화면 좌표(px). 던지거나 숫자가 아니면(투영 없음·SDK 변경) 묶지 않고 번호마다 하나를 돌려준다
//   → 지도는 합치기 전과 똑같이 보인다(가짜 SDK 를 쓰는 기존 화면 테스트도 이 경로).
function planStopGroups(places,offsetOf){
  const single=places.map((_,i)=>[i]);
  let offsets;
  try{offsets=places.map(place=>{const at=offsetOf(place);return {x:+at.x,y:+at.y};});}catch{return single;}
  if(offsets.some(at=>!Number.isFinite(at.x)||!Number.isFinite(at.y)))return single;
  const groups=[];
  offsets.forEach((at,i)=>{
    const near=groups.find(group=>Math.hypot(offsets[group[0]].x-at.x,offsets[group[0]].y-at.y)<STOP_MERGE_PX);
    if(near)near.push(i);else groups.push([i]);
  });
  return groups;
}

function drawPlanMap(plan){
  let activeMap=null,resizeObserver=null,disposed=false,festivalMarkers=[],popupMarkers=[],parkingMarkers=[];
  const wrap=node('section',undefined,'plan-map');
  // 네이버 인증 실패 알림이 표시를 올린 뒤에 오면 SDK 의 setMap(null) 이 SDK 내부 오류(capitalize)를 낸다(실제 SDK·로컬 주소 401 에서 확인).
  // 정리 하나가 실패해도 나머지 정리, 대체 지도 그리기, 지도 정리(disposeMap)가 이어지게 정리 동작을 하나씩 감싼다.
  const quietly=clear=>{try{clear();}catch{}};
  const clearFestivals=()=>{festivalMarkers.forEach(marker=>quietly(()=>marker.setMap?marker.setMap(null):marker.remove?.()));festivalMarkers=[];};
  // 팝업 표시는 표시마다 정리 함수(마커·이벤트)를 두고, 지도 아래 장소 단추·정보 칸도 함께 비운다. 코스·축제 표시는 건드리지 않는다.
  const popupHubs=popupHubList();
  const clearPopups=()=>{popupMarkers.forEach(clear=>quietly(clear));popupMarkers=[];popupHubs.set([]);};
  // 주차장 표시(P)는 일정의 주차장 패널이 받은 응답을 기다려 그린다. 지도는 요청을 시작하지 않는다.
  const parkingNote=node('p','','hint map-parking-note');parkingNote.hidden=true;
  const clearParking=()=>{parkingMarkers.forEach(clear=>quietly(clear));parkingMarkers=[];parkingMapNote(parkingNote,[]);};
  // draw(lots)는 그린 표시마다 지우는 함수를 돌려준다. 다시 찾기로 응답이 또 오면 앞 표시를 지우고 다시 그린다.
  const watchParking=draw=>{if(plan.conditions.mode!=='real'||!parkingStops(plan).length)return;
    let drawn=[];const clearDrawn=()=>{drawn.forEach(clear=>quietly(clear));drawn=[];};
    const stop=onParkingLoaded(plan,data=>{if(disposed||!data||!wrap.isConnected)return;
      clearDrawn();const lots=parkingMapLots(data);drawn=draw(lots);parkingMapNote(parkingNote,lots);});
    parkingMarkers.push(()=>{stop();clearDrawn();});};
  // 지도 자체(코스 표시·이동선·식당 표시는 지도와 함께 사라짐)를 지운다. 같은 이유로 remove·destroy 도 감싼다.
  // Leaflet(1.9.4)은 애니메이션 확대의 끝맺음을 transitionend 와 함께 setTimeout(_onZoomTransitionEnd,250) 으로도 예약하는데, remove() 는 이 예약을 지우지 않고
  // _mapPane 만 지운다. 확대 중(빠른 폭 변경·코스 탭 전환으로 다시 그릴 때)에 지우면 250ms 뒤 그 끝맺음이 지워진 _mapPane 의 _leaflet_pos 를 읽다 페이지 오류가 난다.
  // 지우기 전에 진행 중인 확대를 Leaflet 자신의 끝맺음으로 마쳐 두면(_animatingZoom=false) 예약된 끝맺음은 아무것도 하지 않는다.
  const dropMap=()=>{resizeObserver?.disconnect();const map=activeMap;activeMap=null;
    if(window.L&&map instanceof L.Map&&map._animatingZoom)map._onZoomTransitionEnd();
    quietly(()=>map?.remove?.());quietly(()=>map?.destroy?.());};
  wrap.updateFestivals=()=>{};wrap.updatePopups=()=>{};
  wrap.disposeMap=()=>{disposed=true;applyFocus=null;clearFestivals();clearPopups();clearParking();dropMap();};
  // 일정 카드 → 지도(focusPlanMapStop). focused: 강조할 장소 순번(0부터). applyFocus(pan): 지금 그려진 지도(네이버·Leaflet)가 강조를 다시 그리고
  // pan 이면 그 장소로 옮긴다. 지도를 그리기 전·다시 그리는 중이면 null 이라 순번만 기억해 두고, 지도를 그린 직후에 옮긴다.
  // 돌려주는 값: 'applied'(옮김) · 'pending'(지도 불러오는 중) · 'none'(개략도만 남아 옮길 지도가 없음).
  let focused=null,applyFocus=null;
  wrap.dataset.mapState='loading';
  wrap.focusStop=index=>{focused=index;if(applyFocus){applyFocus(true);return 'applied';}return wrap.dataset.mapState==='none'?'none':'pending';};
  const reduceMotion=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
  const canvas=node('div','네이버 지도를 불러오는 중…','naver-plan-map');
  canvas.setAttribute('role','region');canvas.setAttribute('aria-label','출발지와 방문 순서가 표시된 네이버 지도');
  const caption=node('p','출발 → 방문 순서 → 귀가','map-caption');
  caption.setAttribute('role','status');
  const festivalNote=node('p','','hint map-festival-note');festivalNote.hidden=true;
  const popupNote=node('p','','hint map-popup-note');popupNote.hidden=true;
  wrap.append(canvas,caption,parkingNote,festivalNote,popupNote,popupHubs.list,popupHubs.panel);
  wrap.showMapFallback=()=>fallback('네이버 지도 인증에 실패했습니다. Dynamic Map 권한과 등록 웹 주소를 확인해 주세요.');
  requestAnimationFrame(()=>render());
  async function render(force=false){
    if(!wrap.isConnected)return;
    clearFestivals();wrap.updateFestivals=()=>{};
    clearPopups();wrap.updatePopups=()=>{};
    clearParking();
    dropMap();applyFocus=null;wrap.dataset.mapState='loading';
    if(!statusData?.map_js_key){fallback('네이버 지도 클라이언트 ID가 설정되지 않았습니다.');return;}
    canvas.textContent='네이버 지도를 불러오는 중…';
    wrap.replaceChildren(canvas,caption,parkingNote,festivalNote,popupNote,popupHubs.list,popupHubs.panel);
    try{
      await loadNaverMaps(statusData.map_js_key,force);
      if(window.naverMapAuthFailed)throw Error('지도 인증 실패');
      if(!wrap.isConnected)return;
      canvas.replaceChildren();
      const points=[plan.conditions.origin,...plan.places,...(plan.conditions.return_home?[plan.conditions.home]:[])];
      const coord=p=>new naver.maps.LatLng(p.lat,p.lon);
      // 보관 기간(21일)이 지나 좌표를 지운 네이버 검색 장소(lat·lon 이 null)는 표시·이동선에서 뺀다(공개 지도 fallback 과 같은 기준).
      const located=p=>Number.isFinite(p?.lat)&&Number.isFinite(p?.lon);
      const start=points.find(located);
      if(!start){fallback('지도에 표시할 위치가 없어요.');return;}
      const map=new naver.maps.Map(canvas,{center:coord(start),zoom:14,zoomControl:true,scrollWheel:true});activeMap=map;
      const bounds=new naver.maps.LatLngBounds();
      points.forEach((point,i)=>{
        if(!located(point))return;
        bounds.extend(coord(point));
        // 장소 번호(1..N)는 아래 drawStops 가 화면 거리에 따라 묶어 그린다. 여기서는 출발·귀가만(누름 동작 없음).
        if(i>0&&i<=plan.places.length)return;
        const label=i===0?'출발':'귀가';
        // 장소명은 HTML에 삽입하지 않고 텍스트·title로만 전달한다.
        // 쌓임 순서: 팝업 표시(120) < 코스 표시(130) < 축제 표시(150·고른 축제 300). 팝업 동네 기준점이 출발지와 같은 자리여도 출발·번호 표시가 위에 보이고 눌린다.
        new naver.maps.Marker({map,position:coord(point),title:label+' · '+point.name,zIndex:130,
          icon:{content:'<span class="route-marker '+(i===0?'route-start':'')+'">'+label+'</span>',anchor:new naver.maps.Point(19,19)}});
      });
      // 장소 번호(1..N) 표시: 눌러서 일정의 그 장소로 간다(role=button·고정 이름·손가락 커서). 묶는 기준·함께 맞출 값은 위 planStopGroups 머리 주석.
      // drawStops 는 지금 확대 수준에서 번호를 묶어 '전부 지우고 다시' 그린다. 부르는 곳은 둘:
      //   ① 처음 fitBounds 직후(실제 SDK 는 지도를 만든 직후·fitBounds 직후에도 투영 좌표를 준다, 2026-11-18 운영 SDK 에서 확인)
      //   ② 지도의 zoom_changed(확대 단추·두 손가락·식당 표시 뒤 fitBounds 모두). 실제 SDK 는 zoom_changed 때 이미 새 확대 수준의 좌표를 준다
      //      ('zooming' 은 바뀌기 전 좌표라 쓰지 않는다). 끌어서 옮기기는 화면 거리가 그대로라 다시 묶을 필요가 없다.
      // 표시 수가 장소 수(최대 몇 개)뿐이라 매번 새로 만드는 비용은 작다. 표시마다 붙인 click 처리는 표시와 함께 SDK 가 버린다.
      let stopMarkers=[],stopGroups=[];
      const drawStops=()=>{
        // 지도를 다시 그렸거나(코스 탭 전환·다시 연결) 정리했으면 예전 지도의 늦은 zoom_changed 는 무시한다.
        if(disposed||activeMap!==map)return;
        stopMarkers.forEach(marker=>quietly(()=>marker.setMap(null)));stopMarkers=[];stopGroups=[];
        // 좌표 있는 장소만 묶는다. planStopGroups 는 넘긴 배열의 순번을 돌려주므로 일정 순번(stops[m])으로 바꿔 쓴다.
        const stops=plan.places.map((place,index)=>({place,index})).filter(({place})=>located(place));
        planStopGroups(stops.map(s=>s.place),place=>map.getProjection().fromCoordToOffset(coord(place))).forEach(grouped=>{
          // members: 이 표시에 묶인 장소 순번(0부터). 화면 번호는 +1. '·'(가운뎃점)으로 잇는다.
          const members=grouped.map(m=>stops[m].index);stopGroups.push(members);
          // 일정 카드에서 고른 장소(focused)가 든 표시는 강조(is-focused·aria-current, plan-map.css)하고 다른 번호 위에 둔다.
          const lit=focused!==null&&members.includes(focused);
          const numbers=members.map(i=>i+1),label=numbers.join('·'),width=stopMarkerWidth(members.length);
          // 합친 표시의 자리는 묶인 장소 좌표의 평균(한 장소면 그 장소 그대로).
          const lat=members.reduce((sum,i)=>sum+plan.places[i].lat,0)/members.length,lon=members.reduce((sum,i)=>sum+plan.places[i].lon,0)/members.length;
          // 화면 읽기 이름: 한 장소는 예전과 같은 문구(test_readability_stage6_ui 가 그대로 확인), 합친 표시는 어디로 가는지(앞 번호)를 말한다.
          const merged=members.length>1,name=merged?label+'번 장소 · 눌러서 일정에서 '+numbers[0]+'번부터 보기':stopMarkerLabel(numbers[0]);
          // 보안: content(HTML)에는 숫자·고정 문구만 넣는다. 장소 이름(외부 검색 결과)은 title 옵션으로만 준다(SDK 가 글자로 다룸).
          // 이 줄을 고칠 때 장소 이름이나 검색 결과 글자를 content 에 이어 붙이지 말 것.
          const marker=new naver.maps.Marker({map,position:new naver.maps.LatLng(lat,lon),zIndex:lit?140:130,
            title:members.map(i=>(i+1)+' · '+plan.places[i].name).join(' / '),
            icon:{content:'<span class="route-marker route-stop-marker'+(lit?' is-focused':'')+(merged?' route-stop-merged" style="width:'+width+'px':'')+'" role="button" aria-label="'+name+'"'+(lit?' aria-current="true"':'')+'>'+label+'</span>',
              anchor:new naver.maps.Point(width/2,19)}});
          // 합친 표시는 앞 번호 장소로 간다(일정에서 뒤 번호는 바로 아래 카드). 묶인 장소를 고르게 하려면 여기서 작은 선택 칸을 열면 된다.
          // 네이버 지도는 표시 click 을 알린 뒤 지도 칸(tabindex)에 포커스를 되돌려 그 칸으로 다시 스크롤한다(운영 SDK 에서 확인).
          // 그래서 이번 누름 처리가 다 끝난 뒤(setTimeout)에 장소 제목으로 옮긴다.
          naver.maps.Event.addListener(marker,'click',()=>setTimeout(()=>focusPlanStop(members[0])));
          stopMarkers.push(marker);
        });
      };
      let actual=0;
      for(const {from,to,leg} of planSegments(plan)){
        const style=legLineStyle(plan,leg);
        // 한쪽 끝의 좌표가 없는 구간(보관 기간이 지난 장소)은 선을 그리지 않는다.
        if(!located(from)||!located(to))continue;
        const isRoad=style==='road';
        const path=isRoad?leg.path.map(([lon,lat])=>new naver.maps.LatLng(lat,lon)):[coord(from),coord(to)];
        if(isRoad){actual++;path.forEach(p=>bounds.extend(p));}
        new naver.maps.Polyline({map,path,strokeColor:isRoad?'#b5245e':'#55606b',strokeWeight:isRoad?5:3,
          strokeOpacity:.9,strokeStyle:LINE_DASH.naver[style]});
      }
      map.fitBounds(bounds,{top:45,right:45,bottom:45,left:45});
      // 장소 번호는 화면 거리로 묶으므로 fitBounds 로 확대 수준이 정해진 뒤에 그리고, 확대 수준이 바뀔 때마다 다시 묶는다(drawStops 주석).
      drawStops();
      naver.maps.Event.addListener(map,'zoom_changed',drawStops);
      // 일정 카드 → 지도: 강조를 다시 그리고 그 장소로 옮긴다. 다른 번호와 한 표시로 합쳐져 있으면 두 단계 확대해 떼어 보이게 한다
      // (확대하면 zoom_changed → drawStops 가 다시 묶는다). 동작 줄이기면 움직임 없이 바로 옮긴다. SDK 에 없는 함수는 부르지 않는다.
      applyFocus=pan=>{
        drawStops();
        const place=plan.places[focused];
        if(!pan||!located(place))return;
        const at=coord(place),merged=stopGroups.some(group=>group.length>1&&group.includes(focused));
        const zoom=merged&&map.getZoom?Math.min(map.getZoom()+2,21):null;
        if(zoom!==null&&!reduceMotion()&&map.morph)map.morph(at,zoom);
        else{if(zoom!==null)map.setZoom?.(zoom,false);if(!reduceMotion()&&map.panTo)map.panTo(at);else map.setCenter?.(at);}
      };
      wrap.dataset.mapState='naver';
      if(focused!==null)applyFocus(true);
      wrap.updateFestivals=()=>{
        if(disposed||!canvas.isConnected)return;
        clearFestivals();const items=festivalMapItems();
        for(const festival of items){
          const chosen=FestivalPanel.isChosen(festival),position=new naver.maps.LatLng(festival.lat,festival.lon);
          // 축제 이름은 HTML에 넣지 않고 title과 정보창의 텍스트 노드로만 전달한다.
          const marker=new naver.maps.Marker({map,position,title:'축제 · '+festival.title,zIndex:chosen?300:150,
            icon:{content:'<span class="route-marker festival-marker'+(chosen?' festival-marker-chosen':'')+'">축제</span>',anchor:new naver.maps.Point(24,13)}});
          const info=new naver.maps.InfoWindow({content:festivalMapInfo(festival)});naver.maps.Event.addListener(marker,'click',()=>info.open(map,marker));
          festivalMarkers.push(marker);
          if(chosen&&!bounds.hasLatLng?.(position)){bounds.extend(position);map.fitBounds(bounds,{top:45,right:45,bottom:45,left:45});}
        }
        festivalMapNote(festivalNote,items);
      };
      wrap.updateFestivals();
      wrap.updatePopups=()=>{
        if(disposed||!canvas.isConnected)return;
        clearPopups();const items=popupMapItems();
        items.forEach((group,index)=>{
          const area=group.hub.kind==='area',position=new naver.maps.LatLng(group.hub.lat,group.hub.lon);
          const marker=new naver.maps.Marker({map,position,title:popupMapTitle(group),zIndex:120,
            icon:{content:POPUP_MARKER_HTML[area?'area':'building'],anchor:new naver.maps.Point(area?36:22,14)}});
          // 지도 안 정보창 대신 지도 아래 정보 칸을 연다(지도 폭이 좁아 정보창 본문이 160px 남짓이었음).
          const listener=naver.maps.Event.addListener(marker,'click',()=>popupHubs.show(index,true));
          popupMarkers.push(()=>{if(listener)naver.maps.Event.removeListener?.(listener);marker.setMap(null);});
        });
        popupHubs.set(items);popupMapNote(popupNote,items);
      };
      wrap.updatePopups();
      caption.textContent=actual===points.length-1
        ?'네이버 지도 · 자동차 실제 도로 경로 (조회 시점 기준)'
        :'네이버 지도 · 점선은 방문 순서의 직선 연결이며 실제 이동 경로가 아닙니다.';
      if(plan.conditions.mode==='demo')caption.textContent+=' 서울 체험 코스(가상 장소)예요.';
      else if(actual)caption.textContent+=' 실선만 자동차 실제 경로입니다.';
      if(plan.conditions.mode==='real'){
        const originalCaption=caption.textContent;
        // 반경은 각 방문 장소 중심의 직선거리이며 추천 식당은 경로선에 포함하지 않는다.
        plan.places.filter(located).forEach(place=>new naver.maps.Circle({map,center:coord(place),radius:500,
          strokeColor:'#8758c7',strokeOpacity:.4,strokeWeight:1,fillColor:'#8758c7',fillOpacity:.06}));
        fetchRestaurantMatches(plan).then(data=>{
          if(!wrap.isConnected||!canvas.isConnected)return;
          const locations=new Map();let count=0;
          for(const group of data.groups){for(const [j,food] of group.restaurants.entries()){
            const key=food.lat.toFixed(5)+','+food.lon.toFixed(5);
            const label=(group.after_index+1)+'-'+(j+1);
            if(locations.has(key))locations.get(key).labels.push(label);
            else locations.set(key,{food,labels:[label]});
          }}
          for(const {food,labels} of locations.values()){
            const label=labels.join(' / ');
            const marker=new naver.maps.Marker({map,position:coord(food),title:label+' · '+food.name,
              icon:{content:'<span class="route-marker restaurant-marker">'+label+'</span>',anchor:new naver.maps.Point(19,19)}});
            const content=node('div',undefined,'restaurant-map-info');content.append(node('strong',label+' · '+food.name),node('p',food.address||''),placeMapLink('네이버 지도에서 메뉴보기 ↗',food));
            const info=new naver.maps.InfoWindow({content});naver.maps.Event.addListener(marker,'click',()=>info.open(map,marker));
            bounds.extend(coord(food));count++;
          }
          if(count)map.fitBounds(bounds,{top:45,right:45,bottom:45,left:45});
          caption.textContent=originalCaption+' 보라색 원: 각 코스 반경 500m · 주황색 번호: 식당 '+count+'곳 (일정 미포함).';
        }).catch(()=>{caption.textContent=originalCaption+' 주변 식당 표시를 불러오지 못했어요.';});
        // 쌓임 순서: 식당 < 주차장 P(110) < 팝업(120) < 코스(130) < 축제(150). 표시 글자는 고정 문자열, 이름은 title·정보창 텍스트로만.
        watchParking(lots=>lots.map(lot=>{
          const marker=new naver.maps.Marker({map,position:coord(lot),title:'주차장 · '+lot.name,zIndex:110,
            icon:{content:'<span class="route-marker parking-marker">P</span>',anchor:new naver.maps.Point(16,16)}});
          const info=new naver.maps.InfoWindow({content:parkingMapInfo(lot)});
          const listener=naver.maps.Event.addListener(marker,'click',()=>info.open(map,marker));
          return ()=>{quietly(()=>info.close());if(listener)naver.maps.Event.removeListener?.(listener);marker.setMap(null);};
        }));
      }
    }catch(error){if(wrap.isConnected){
      const reasons={'지도 인증 실패':'네이버 지도 인증에 실패했습니다. 등록 웹 주소와 Dynamic Map 권한을 확인해 주세요.',
        '지도 응답 시간 초과':'지도 서버의 응답이 늦어 연결이 중단됐습니다.',
        '지도 로딩 실패':'네이버 지도 스크립트를 받지 못했습니다. 네트워크나 콘텐츠 차단 설정을 확인해 주세요.'};
      fallback(reasons[error.message]||'네이버 지도 화면을 표시하지 못했습니다. 다시 연결해 주세요.');
    }}
  }
  function fallback(message){
    if(disposed||!wrap.isConnected)return;
    clearFestivals();wrap.updateFestivals=()=>{};festivalNote.hidden=true;
    clearPopups();wrap.updatePopups=()=>{};popupMapNote(popupNote,[]);
    clearParking();
    dropMap();applyFocus=null;wrap.dataset.mapState='loading';
    const notice=node('div',undefined,'map-reconnect');
    notice.setAttribute('role','status');
    notice.append(node('strong','네이버 지도 연결이 잠시 끊겼어요'),node('p',message,'hint'),
      button('지도 다시 연결',()=>render(true),'primary'));
    const schematic=node('details',undefined,'map-schematic');
    schematic.append(node('summary','방문 순서 개략도 보기 (실제 지도 아님)'),drawMap(plan));
    wrap.replaceChildren(notice,schematic);
    loadLeaflet().then(()=>{if(disposed||!wrap.isConnected)return;
      const mapCanvas=node('div',undefined,'naver-plan-map fallback-plan-map');mapCanvas.setAttribute('role','region');mapCanvas.setAttribute('aria-label','데이트 코스 공개 지도');
      const mapCaption=node('p','공개 지도 · 점선은 방문 순서이며 실제 이동 경로가 아닙니다.','map-caption');
      wrap.prepend(mapCanvas,mapCaption,parkingNote,festivalNote,popupNote,popupHubs.list,popupHubs.panel);
      const points=[plan.conditions.origin,...plan.places,...(plan.conditions.return_home?[plan.conditions.home]:[])].filter(point=>Number.isFinite(point?.lat)&&Number.isFinite(point?.lon));
      if(!points.length){wrap.dataset.mapState='none';return;}
      try{
        const map=L.map(mapCanvas,{scrollWheelZoom:true}).setView([points[0].lat,points[0].lon],14);activeMap=map;
        // 팝업 표시는 코스 원·이동선·축제 원(overlayPane 400)보다 아래 층(popups.css 의 390)에 둔다. 같은 자리여도 출발·번호 원이 위에 보인다.
        map.createPane('popupHubs');
        const layer=L.tileLayer(statusData?.map_tile_url||'https://tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:statusData?.map_tile_attribution||'© OpenStreetMap contributors',maxZoom:19}).addTo(map);
        layer.on('tileerror',()=>mapCaption.textContent='지도 배경을 불러오지 못했어요. 장소 링크와 아래 개략도를 이용해 주세요.');
        const coordinates=points.map(point=>[point.lat,point.lon]);
        // 휴대폰(plan-map.css 와 같은 조건): 보이는 원(지름 약 21px)은 그대로 두고 그 아래 투명한 지름 44px 원을 깔아 누름 영역을 넓힌다.
        // 투명한 원은 따로 둔 낮은 층(385: 팝업 표시 390·코스 원 400 아래)에 그려, 다른 장소의 보이는 원이나 팝업·주차 표시를 덮지 않고
        // 지도 바탕을 누를 자리만 넓힌다.
        // 장소 번호(1..N) 점은 눌러서 일정의 그 장소로 간다. points 는 좌표 없는 점을 걸렀으므로 순번은 plan.places 에서 찾는다.
        const stopIndex=point=>plan.places.indexOf(point);
        // 보이는 원에만 role=button·이름을 주고, 아래의 투명한 누름 원은 같은 동작만 한다(화면 읽기에 단추가 둘로 읽히지 않게).
        const goToStop=(circle,index,named)=>{if(index<0)return;circle.on('click',()=>focusPlanStop(index));
          const path=named&&circle.getElement?.();if(path){path.setAttribute('role','button');path.setAttribute('aria-label',stopMarkerLabel(index+1));}};
        const touch=matchMedia('(max-width:720px),(pointer:coarse)').matches;
        if(touch)map.createPane('routeHits').style.zIndex='385';
        // 출발·귀가 원(누름 동작 없음, 묶지 않음).
        points.filter(point=>stopIndex(point)<0).forEach(point=>{
          const origin=point===plan.conditions.origin;
          if(touch)L.circleMarker([point.lat,point.lon],{pane:'routeHits',radius:22,stroke:false,fillColor:'#fff',fillOpacity:0,className:'route-hit-area'}).addTo(map);
          L.circleMarker([point.lat,point.lon],{radius:9,color:origin?'#1f2328':'#b5245e',fillColor:'#fff',fillOpacity:1,weight:3}).addTo(map)
            .bindTooltip(node('span',(origin?'출발':'귀가')+' · '+point.name),{permanent:true,direction:'top'});
        });
        // 장소 번호 원: 네이버 지도(drawStops)와 같은 planStopGroups 로 화면에서 겹치는 번호를 '2·3' 원 하나로 묶는다(2026-11-18 가독성 8단계).
        // 화면 좌표는 map.latLngToContainerPoint, 확대·축소(zoomend)마다 다시 묶는다. 지도 칸 크기가 0 이면(숨겨진 칸) 모든 점이 한자리로
        // 계산돼 전부 합쳐지므로 그때는 묶지 않는다(offsetOf 가 던지면 planStopGroups 가 번호마다 하나를 돌려준다).
        // 원 반지름 9px(지름 18px)이라 묶는 거리는 네이버 표시와 같은 STOP_MERGE_PX(38px)로 둔다 — 여기에 툴팁 글자도 함께 겹치기 때문.
        const stopLayer=L.layerGroup().addTo(map);
        const stops=plan.places.map((place,index)=>({place,index})).filter(({place})=>Number.isFinite(place?.lat)&&Number.isFinite(place?.lon));
        let leafletGroups=[];
        const drawLeafletStops=()=>{
          if(disposed||activeMap!==map)return;
          stopLayer.clearLayers();
          const size=map.getSize();
          const groups=planStopGroups(stops.map(s=>s.place),place=>{if(!size.x||!size.y)throw Error('지도 크기 없음');return map.latLngToContainerPoint([place.lat,place.lon]);});
          leafletGroups=groups.map(members=>members.map(m=>stops[m].index));
          groups.forEach(members=>{
            const indexes=members.map(m=>stops[m].index),numbers=indexes.map(i=>i+1),label=numbers.join('·'),merged=indexes.length>1;
            // 일정 카드에서 고른 장소(focused)가 든 원은 크게, 진한 테두리·홍색 칠로 강조하고 맨 위로 올린다(aria-current).
            const lit=focused!==null&&indexes.includes(focused);
            const at=[indexes.reduce((s,i)=>s+plan.places[i].lat,0)/indexes.length,indexes.reduce((s,i)=>s+plan.places[i].lon,0)/indexes.length];
            if(touch)goToStop(L.circleMarker(at,{pane:'routeHits',radius:22,stroke:false,fillColor:'#fff',fillOpacity:0,className:'route-hit-area'}).addTo(stopLayer),indexes[0],false);
            const circle=L.circleMarker(at,{radius:lit?12:9,color:lit?'#111827':'#b5245e',fillColor:lit?'#E0004D':'#fff',fillOpacity:1,weight:lit?4:3,className:'route-stop-circle'+(merged?' route-stop-merged-circle':'')+(lit?' is-focused':'')}).addTo(stopLayer);
            // 툴팁은 글자 노드로만(장소 이름은 외부 검색 결과). 합친 원은 '2·3 · 이름A / 이름B'.
            circle.bindTooltip(node('span',label+' · '+indexes.map(i=>plan.places[i].name).join(' / ')),{permanent:true,direction:'top',className:lit?'route-stop-tooltip-focused':''});
            goToStop(circle,indexes[0],true);
            // 합친 원의 화면 읽기 이름: 네이버 지도와 같은 문구(앞 번호로 간다는 것).
            if(merged)circle.getElement?.()?.setAttribute('aria-label',label+'번 장소 · 눌러서 일정에서 '+numbers[0]+'번부터 보기');
            if(lit){circle.bringToFront();circle.getElement?.()?.setAttribute('aria-current','true');}
          });
        };
        drawLeafletStops();
        map.on('zoomend',drawLeafletStops);
        // 일정 카드 → 지도(네이버 지도 쪽 applyFocus 와 같은 규칙): 강조를 다시 그리고 그 장소로 옮긴다. 합쳐진 원이면 두 단계 확대.
        applyFocus=pan=>{
          drawLeafletStops();
          const place=plan.places[focused];
          if(!pan||!Number.isFinite(place?.lat)||!Number.isFinite(place?.lon))return;
          const merged=leafletGroups.some(group=>group.length>1&&group.includes(focused));
          map.setView([place.lat,place.lon],merged?Math.min(map.getZoom()+2,map.getMaxZoom?.()||19):map.getZoom(),{animate:!reduceMotion()});
        };
        wrap.dataset.mapState='leaflet';
        // 구간마다 수단에 맞는 점선으로 잇는다(공개 지도에는 실제 도로 경로를 그리지 않는다).
        // 이동선은 장소 원 뒤에 그려져 원 가운데를 지나므로, 누름을 받지 않게 해(interactive:false) 원 가운데를 눌러도 장소로 가게 한다.
        // 구간은 planSegments(저녁 축제면 행사장을 거침). 좌표 없는 점(보관 기간이 지난 장소)에 닿는 구간은 그리지 않는다.
        const hasPoint=point=>Number.isFinite(point?.lat)&&Number.isFinite(point?.lon);
        for(const {from,to,leg} of planSegments(plan)){if(!hasPoint(from)||!hasPoint(to))continue;const style=legLineStyle(plan,leg);L.polyline([[from.lat,from.lon],[to.lat,to.lon]],{color:'#55606b',weight:3,dashArray:LINE_DASH.leaflet[style==='short'?'short':'long'],className:'route-leg route-leg-'+style,interactive:false}).addTo(map);}
        wrap.updateFestivals=()=>{
          if(disposed||!mapCanvas.isConnected)return;
          clearFestivals();const items=festivalMapItems();
          for(const festival of items){
            const chosen=FestivalPanel.isChosen(festival);
            const marker=L.circleMarker([festival.lat,festival.lon],{radius:chosen?11:8,color:'#8a5a00',weight:chosen?4:2,dashArray:chosen?null:'3 3',fillColor:'#f2b632',fillOpacity:chosen?1:.85,className:'festival-circle'+(chosen?' festival-circle-chosen':'')}).addTo(map);
            marker.bindTooltip(node('span','축제 · '+festival.title),{permanent:chosen,direction:'bottom'});
            marker.bindPopup(festivalMapInfo(festival));
            festivalMarkers.push(marker);
          }
          festivalMapNote(festivalNote,items);
        };
        wrap.updateFestivals();
        wrap.updatePopups=()=>{
          if(disposed||!mapCanvas.isConnected)return;
          clearPopups();const items=popupMapItems();
          items.forEach((group,index)=>{
            const icon=L.divIcon({className:'popup-divicon',html:popupMarkerNode(group),iconSize:null});
            const marker=L.marker([group.hub.lat,group.hub.lon],{icon,title:popupMapTitle(group),keyboard:true,zIndexOffset:-100,pane:'popupHubs'}).addTo(map);
            // 클릭·키보드(Enter) 모두 지도 아래 정보 칸을 연다(지도 안 정보창을 쓰지 않음). Leaflet 은 Enter 를 bindPopup 에서만 처리하므로 직접 받는다.
            marker.on('click',()=>popupHubs.show(index,true));
            marker.on('keypress',event=>{if(event.originalEvent?.key==='Enter')popupHubs.show(index,true);});
            popupMarkers.push(()=>{marker.off();marker.remove();});
          });
          popupHubs.set(items);popupMapNote(popupNote,items);
        };
        wrap.updatePopups();
        watchParking(lots=>lots.map(lot=>{
          const icon=L.divIcon({className:'parking-divicon',html:node('span','P','route-marker parking-marker'),iconSize:null});
          const marker=L.marker([lot.lat,lot.lon],{icon,title:'주차장 · '+lot.name,keyboard:true}).addTo(map);
          marker.bindPopup(parkingMapInfo(lot));
          return ()=>{marker.off();marker.remove();};
        }));
        // 전체 맞춤 뒤에 일정 카드에서 고른 장소가 있으면 그 장소로 다시 옮긴다(지도를 불러오기 전에 눌렀거나, 폭이 바뀌어 다시 맞춘 경우).
        const fit=()=>{if(!disposed&&mapCanvas.isConnected){map.invalidateSize();map.fitBounds(L.latLngBounds(coordinates),{padding:[35,35],maxZoom:16});if(focused!==null)applyFocus?.(true);}};
        requestAnimationFrame(fit);
        if(window.ResizeObserver){resizeObserver=new ResizeObserver(fit);resizeObserver.observe(mapCanvas);}
      }catch{applyFocus=null;wrap.dataset.mapState='none';mapCanvas.replaceWith(node('p','공개 지도를 표시하지 못했어요. 아래 개략도와 장소 링크를 이용해 주세요.','hint'));}
    }).catch(()=>{if(!disposed)wrap.dataset.mapState='none';});
  }
  return wrap;
}
async function officialPlaceMap(container,place,key){
  try{
    await loadNaverMaps(key);
    if(!container.isConnected)return;
    const coordinates=new naver.maps.LatLng(place.lat,place.lon);
    container.replaceChildren();
    const map=new naver.maps.Map(container,{center:coordinates,zoom:15});
    new naver.maps.Marker({position:coordinates,map,title:place.name});
  }catch{
    container.textContent='네이버 지도 로딩 실패. 아래 지도 링크에서 위치를 확인해 주세요.';
  }
}
