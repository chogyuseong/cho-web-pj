/* 공개 클라이언트 ID가 설정된 경우에만 로드한다. 비밀 API 키는 사용하지 않는다. */
let naverLoader;
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
  card.append(node('h2','우리 코스 지도'),tabs,node('p',courseTitle(selected),'map-course-title'),node('p',`이동 ${travelMinutes(selected)}분 · ${travelMode(selected).label}`,'hint map-travel-mode'),mapLegend(selected),node('p','지도 위에서 마우스 휠로 확대·축소할 수 있어요.','hint map-zoom-hint'),drawPlanMap(selected));
  const places=node('div',undefined,'map-place-list');
  selected.places.forEach((place,index)=>places.append(placeMapLink((index+1)+'. '+place.name,place)));
  card.append(places);(mobile?slot:rail).append(card);planMapCard=card;
}

/* 구간 선 모양은 구간 수단(leg.mode)을 따른다. 자동차이면서 실제 길찾기 경로가 있으면 도로 실선,
   도보는 짧은 점선, 대중교통·자전거(그리고 길찾기를 하지 않은 자동차)는 긴 점선. 점선은 직선 연결이다. */
function legLineStyle(plan,leg){
  const mode=legMode(plan,leg);
  if(plan.conditions.mode==='real'&&mode==='car'&&leg?.status==='api'&&leg.path?.length>1)return 'road';
  return mode==='walk'?'short':'long';
}
const LINE_DASH={leaflet:{short:'4 6',long:'14 8'},svg:{short:'4 6',long:'14 8'},naver:{road:'solid',short:'shortdash',long:'longdash'}};
function mapLegend(plan){
  const styles=new Map();
  for(const leg of plan.legs||[]){const style=legLineStyle(plan,leg);if(!styles.has(style))styles.set(style,new Set());styles.get(style).add(TRANSPORT_NAMES[legMode(plan,leg)]||'이동');}
  const parts=[];
  if(styles.has('road'))parts.push('실선은 자동차 실제 도로 경로');
  if(styles.has('short'))parts.push('짧은 점선은 '+[...styles.get('short')].join('·'));
  if(styles.has('long'))parts.push('긴 점선은 '+[...styles.get('long')].join('·'));
  const dashed=styles.has('short')||styles.has('long');
  const legend=node('p','선 모양: '+parts.join(' · ')+(dashed?'. 점선은 직선 연결이며 실제 경로가 아니에요.':'.'),'hint map-legend');
  // 팝업 표시 설명은 지도에 팝업 표시가 있을 때만 보인다(popupMapNote 가 켜고 끈다).
  if(typeof PopupCourse!=='undefined'){const popups=node('span',' 네모 ‘팝업’은 팝업 글에서 읽은 주변 장소예요(코스·이동선에 넣지 않음). 점선 네모 ‘팝업 일대’는 동네 기준점이라 위치가 대략이에요.','map-legend-popups');popups.hidden=!popupMapItems().length;legend.append(popups);}
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

/* 팝업 글에서 읽은 거점은 축제와 별도의 표시 층이다. 데이터는 코스 결과 팝업 구역의 거점 묶음(PopupCourse.mapItems)과 같은 배열이고,
   위치가 확인된 거점마다 표시 하나와 지도 아래 단추 하나(같은 거점의 여러 글은 지도 아래 정보 칸의 목록). 코스 역(원)·축제(노란 알약)와 다른 네모 모양이며,
   동네 기준점은 점선 네모 + ‘일대’ 글자로 건물과 구분한다. 이동선에 잇지 않고 지도 범위 계산에도 넣지 않는다(중심·확대를 바꾸지 않음). */
function popupMapItems(){return typeof PopupCourse==='undefined'?[]:PopupCourse.mapItems;}
// 네이버 마커 HTML 은 고정 문자열만 쓴다. 거점 이름·글 제목은 title 과 지도 아래 단추·정보 칸의 텍스트 노드로만 전달한다.
const POPUP_MARKER_HTML={building:'<span class="route-marker popup-marker">팝업</span>',area:'<span class="route-marker popup-marker popup-marker-area">팝업 일대</span>'};
function popupMarkerNode(group){const area=group.hub.level==='area_anchor';return node('span',area?'팝업 일대':'팝업','route-marker popup-marker'+(area?' popup-marker-area':''));}
function popupMapTitle(group){return '팝업 글 장소 · '+PopupCourse.label(group.hub)+' · 검색된 글 '+group.posts.length+'건';}
function popupMapInfo(group){
  const hub=group.hub,box=node('div',undefined,'popup-map-info'),list=node('ul',undefined,'popup-map-posts'),shown=group.posts.slice(0,3);
  box.append(node('strong',PopupCourse.label(hub)),node('p',PopupCourse.levelText(hub)),node('p','코스에 포함되지 않은 주변 후보예요. 기간과 장소는 원문에서 확인해 주세요.','hint'),node('p',`검색된 글 ${group.posts.length}건 · 네이버 블로그`));
  for(const post of shown){const item=node('li');item.append(link((post.title||'(제목 없음)')+' ↗',post.url));list.append(item);}
  box.append(list);
  if(group.posts.length>shown.length)box.append(node('p',`외 ${group.posts.length-shown.length}건 · 아래 팝업 글 구역에서 모두 볼 수 있어요`,'hint'));
  return box;
}
/* 지도 아래의 팝업 장소 단추 목록과 정보 칸. 지도 위 팝업 표시는 코스 표시 아래 층이라 출발지와 같은 자리면 대부분 가려지고(확대 단계마다 달라짐),
   지도 폭(약 250~320px) 안의 정보창은 확대·축소 단추를 비키면 본문이 90~160px 로 좁아진다. 그래서 거점마다 44px 이상의 단추를 지도 아래에 두고,
   단추나 지도 표시를 누르면 지도 아래 칸(지도 폭 그대로, 안쪽 스크롤 없음)에 같은 내용(popupMapInfo)을 연다. 한 번에 거점 하나만 연다.
   단추는 aria-expanded·aria-controls 로 열림을 알린다. 지도 표시를 누르면 칸이 화면에 보이게만 스크롤하고 포커스는 옮기지 않는다.
   장소 이름은 텍스트 노드로만 넣는다. */
let popupPanelCount=0;
function popupHubList(){
  const list=node('div',undefined,'map-popup-hubs'),panel=node('div',undefined,'map-popup-panel');
  list.setAttribute('role','group');list.setAttribute('aria-label','지도에 표시한 팝업 장소');list.hidden=true;
  panel.id='map-popup-panel-'+(++popupPanelCount);panel.hidden=true;
  let groups=[],open=-1;
  const chips=()=>[...list.querySelectorAll('.map-popup-hub')];
  const show=(index,reveal=false)=>{
    open=groups[index]?index:-1;
    chips().forEach((chip,i)=>chip.setAttribute('aria-expanded',String(i===open)));
    panel.replaceChildren();panel.hidden=open<0;
    if(open<0)return;
    const at=open;
    panel.append(popupMapInfo(groups[at]),button('정보 닫기',()=>{show(-1);chips()[at]?.focus();},'secondary map-popup-close'));
    if(reveal)panel.scrollIntoView({block:'nearest'});
  };
  // 정보 칸 안(글 링크·닫기)에서 Esc 를 누르면 닫고 그 장소 단추로 돌아간다.
  panel.addEventListener('keydown',event=>{if(event.key==='Escape'&&open>=0){const at=open;show(-1);chips()[at]?.focus();}});
  const set=items=>{
    groups=items;list.replaceChildren();list.hidden=!items.length;
    items.forEach((group,index)=>{
      const area=group.hub.level==='area_anchor',chip=button('',()=>show(open===index?-1:index),'secondary map-popup-hub');
      chip.append(node('span',area?'팝업 일대':'팝업','map-popup-badge'+(area?' is-area':'')),node('span',`${PopupCourse.label(group.hub)} · 글 ${group.posts.length}건`,'map-popup-hub-name'));
      chip.setAttribute('aria-expanded','false');chip.setAttribute('aria-controls',panel.id);list.append(chip);
    });
    show(-1);
  };
  return {list,panel,show,set};
}
function popupMapNote(note,items){
  note.hidden=!items.length;
  note.textContent=items.length?`네모 ‘팝업’ 표시: 팝업 글에서 읽은 장소 ${items.length}곳 (코스에 포함되지 않은 주변 후보예요 · 위치를 확인하지 못한 글은 지도에 없어요). 아래 장소나 지도 표시를 누르면 글 목록이 열려요.`:'';
  const legend=note.closest('.plan-map-card')?.querySelector('.map-legend-popups');if(legend)legend.hidden=!items.length;
}

function drawPlanMap(plan){
  let activeMap=null,resizeObserver=null,disposed=false,festivalMarkers=[],popupMarkers=[];
  const wrap=node('section',undefined,'plan-map');
  // 네이버 인증 실패 알림이 표시를 올린 뒤에 오면 SDK 의 setMap(null) 이 SDK 내부 오류(capitalize)를 낸다(실제 SDK·로컬 주소 401 에서 확인).
  // 정리 하나가 실패해도 나머지 정리, 대체 지도 그리기, 지도 정리(disposeMap)가 이어지게 정리 동작을 하나씩 감싼다.
  const quietly=clear=>{try{clear();}catch{}};
  const clearFestivals=()=>{festivalMarkers.forEach(marker=>quietly(()=>marker.setMap?marker.setMap(null):marker.remove?.()));festivalMarkers=[];};
  // 팝업 표시는 표시마다 정리 함수(마커·이벤트)를 두고, 지도 아래 장소 단추·정보 칸도 함께 비운다. 코스·축제 표시는 건드리지 않는다.
  const popupHubs=popupHubList();
  const clearPopups=()=>{popupMarkers.forEach(clear=>quietly(clear));popupMarkers=[];popupHubs.set([]);};
  // 지도 자체(코스 표시·이동선·식당 표시는 지도와 함께 사라짐)를 지운다. 같은 이유로 remove·destroy 도 감싼다.
  const dropMap=()=>{resizeObserver?.disconnect();const map=activeMap;activeMap=null;quietly(()=>map?.remove?.());quietly(()=>map?.destroy?.());};
  wrap.updateFestivals=()=>{};wrap.updatePopups=()=>{};
  wrap.disposeMap=()=>{disposed=true;clearFestivals();clearPopups();dropMap();};
  const canvas=node('div','네이버 지도를 불러오는 중…','naver-plan-map');
  canvas.setAttribute('aria-label','출발지와 방문 순서가 표시된 네이버 지도');
  const caption=node('p','출발 → 방문 순서 → 귀가','map-caption');
  caption.setAttribute('role','status');
  const festivalNote=node('p','','hint map-festival-note');festivalNote.hidden=true;
  const popupNote=node('p','','hint map-popup-note');popupNote.hidden=true;
  wrap.append(canvas,caption,festivalNote,popupNote,popupHubs.list,popupHubs.panel);
  wrap.showMapFallback=()=>fallback('네이버 지도 인증에 실패했습니다. Dynamic Map 권한과 등록 웹 주소를 확인해 주세요.');
  requestAnimationFrame(()=>render());
  async function render(force=false){
    if(!wrap.isConnected)return;
    clearFestivals();wrap.updateFestivals=()=>{};
    clearPopups();wrap.updatePopups=()=>{};
    dropMap();
    if(!statusData?.map_js_key){fallback('네이버 지도 클라이언트 ID가 설정되지 않았습니다.');return;}
    canvas.textContent='네이버 지도를 불러오는 중…';
    wrap.replaceChildren(canvas,caption,festivalNote,popupNote,popupHubs.list,popupHubs.panel);
    try{
      await loadNaverMaps(statusData.map_js_key,force);
      if(window.naverMapAuthFailed)throw Error('지도 인증 실패');
      if(!wrap.isConnected)return;
      canvas.replaceChildren();
      const points=[plan.conditions.origin,...plan.places,...(plan.conditions.return_home?[plan.conditions.home]:[])];
      const coord=p=>new naver.maps.LatLng(p.lat,p.lon);
      const map=new naver.maps.Map(canvas,{center:coord(points[0]),zoom:14,zoomControl:true,scrollWheel:true});activeMap=map;
      const bounds=new naver.maps.LatLngBounds();
      points.forEach((point,i)=>{
        const label=i===0?'출발':i>plan.places.length?'귀가':String(i);
        // 장소명은 HTML에 삽입하지 않고 텍스트·title로만 전달한다.
        // 쌓임 순서: 팝업 표시(120) < 코스 표시(130) < 축제 표시(150·고른 축제 300). 팝업 동네 기준점이 출발지와 같은 자리여도 출발·번호 표시가 위에 보이고 눌린다.
        const marker=new naver.maps.Marker({map,position:coord(point),title:label+' · '+point.name,zIndex:130,
          icon:{content:'<span class="route-marker '+(i===0?'route-start':'')+'">'+label+'</span>',anchor:new naver.maps.Point(19,19)}});
        bounds.extend(coord(point));
      });
      let actual=0;
      for(let i=0;i<points.length-1;i++){
        const leg=plan.legs[i],style=legLineStyle(plan,leg);
        const isRoad=style==='road';
        const path=isRoad?leg.path.map(([lon,lat])=>new naver.maps.LatLng(lat,lon)):[coord(points[i]),coord(points[i+1])];
        if(isRoad){actual++;path.forEach(p=>bounds.extend(p));}
        new naver.maps.Polyline({map,path,strokeColor:isRoad?'#b5245e':'#55606b',strokeWeight:isRoad?5:3,
          strokeOpacity:.9,strokeStyle:LINE_DASH.naver[style]});
      }
      map.fitBounds(bounds,{top:45,right:45,bottom:45,left:45});
      wrap.updateFestivals=()=>{
        if(disposed||!canvas.isConnected)return;
        clearFestivals();const items=festivalMapItems();
        for(const festival of items){
          const chosen=FestivalPanel.isChosen(festival),position=new naver.maps.LatLng(festival.lat,festival.lon);
          // 축제 이름은 HTML에 넣지 않고 title과 정보창의 텍스트 노드로만 전달한다.
          const marker=new naver.maps.Marker({map,position,title:'축제 · '+festival.title,zIndex:chosen?300:150,
            icon:{content:'<span class="route-marker festival-marker'+(chosen?' festival-marker-chosen':'')+'">축제</span>',anchor:new naver.maps.Point(24,14)}});
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
          const area=group.hub.level==='area_anchor',position=new naver.maps.LatLng(group.hub.lat,group.hub.lon);
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
      if(plan.conditions.mode==='demo')caption.textContent+=' 가상 장소 데모입니다.';
      else if(actual)caption.textContent+=' 실선만 자동차 실제 경로입니다.';
      if(plan.conditions.mode==='real'){
        const originalCaption=caption.textContent;
        // 반경은 각 방문 장소 중심의 직선거리이며 추천 식당은 경로선에 포함하지 않는다.
        plan.places.forEach(place=>new naver.maps.Circle({map,center:coord(place),radius:500,
          strokeColor:'#8758c7',strokeOpacity:.4,strokeWeight:1,fillColor:'#8758c7',fillOpacity:.06}));
        fetchRestaurantMatches(plan).then(data=>{
          if(!wrap.isConnected||!canvas.isConnected)return;
          const locations=new Map();let count=0;
          const mapGroups=[...data.groups,...(data.popular?[{label_prefix:'맛',restaurants:data.popular.restaurants}]:[])];
          for(const group of mapGroups){for(const [j,food] of group.restaurants.entries()){
            const key=food.lat.toFixed(5)+','+food.lon.toFixed(5);
            const label=(group.label_prefix||(group.after_index+1))+'-'+(j+1);
            if(locations.has(key))locations.get(key).labels.push(label);
            else locations.set(key,{food,labels:[label]});
          }}
          for(const {food,labels} of locations.values()){
            const label=labels.join(' / ');
            const marker=new naver.maps.Marker({map,position:coord(food),title:label+' · '+food.name,
              icon:{content:'<span class="route-marker restaurant-marker">'+label+'</span>',anchor:new naver.maps.Point(19,19)}});
            const content=node('div',undefined,'restaurant-map-info');content.append(node('strong',label+' · '+food.name),node('p',food.address||''),placeMapLink('네이버 지도·메뉴 ↗',food));
            const info=new naver.maps.InfoWindow({content});naver.maps.Event.addListener(marker,'click',()=>info.open(map,marker));
            bounds.extend(coord(food));count++;
          }
          if(count)map.fitBounds(bounds,{top:45,right:45,bottom:45,left:45});
          caption.textContent=originalCaption+' 보라색 원: 각 코스 반경 500m · 주황색 번호: 식당 '+count+'곳 (일정 미포함, 맛: 지역 추천).';
        }).catch(()=>{caption.textContent=originalCaption+' 주변 식당 표시를 불러오지 못했어요.';});
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
    dropMap();
    const notice=node('div',undefined,'map-reconnect');
    notice.setAttribute('role','status');
    notice.append(node('strong','네이버 지도 연결이 잠시 끊겼어요'),node('p',message,'hint'),
      button('지도 다시 연결',()=>render(true),'primary'));
    const schematic=node('details',undefined,'map-schematic');
    schematic.append(node('summary','방문 순서 개략도 보기 (실제 지도 아님)'),drawMap(plan));
    wrap.replaceChildren(notice,schematic);
    if(window.L){
      const mapCanvas=node('div',undefined,'naver-plan-map fallback-plan-map');mapCanvas.setAttribute('aria-label','데이트 코스 공개 지도');
      const mapCaption=node('p','공개 지도 · 점선은 방문 순서이며 실제 이동 경로가 아닙니다.','map-caption');
      wrap.prepend(mapCanvas,mapCaption,festivalNote,popupNote,popupHubs.list,popupHubs.panel);
      const points=[plan.conditions.origin,...plan.places,...(plan.conditions.return_home?[plan.conditions.home]:[])].filter(point=>Number.isFinite(point?.lat)&&Number.isFinite(point?.lon));
      if(!points.length)return;
      try{
        const map=L.map(mapCanvas,{scrollWheelZoom:true}).setView([points[0].lat,points[0].lon],14);activeMap=map;
        // 팝업 표시는 코스 원·이동선·축제 원(overlayPane 400)보다 아래 층(popups.css 의 390)에 둔다. 같은 자리여도 출발·번호 원이 위에 보인다.
        map.createPane('popupHubs');
        const layer=L.tileLayer(statusData?.map_tile_url||'https://tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:statusData?.map_tile_attribution||'© OpenStreetMap contributors',maxZoom:19}).addTo(map);
        layer.on('tileerror',()=>mapCaption.textContent='지도 배경을 불러오지 못했어요. 장소 링크와 아래 개략도를 이용해 주세요.');
        const coordinates=points.map(point=>[point.lat,point.lon]);
        points.forEach((point,i)=>{
          const title=node('span',(i===0?'출발':i>plan.places.length?'귀가':String(i))+' · '+point.name);
          L.circleMarker([point.lat,point.lon],{radius:9,color:i===0?'#1f2328':'#b5245e',fillColor:'#fff',fillOpacity:1,weight:3}).addTo(map).bindTooltip(title,{permanent:true,direction:'top'});
        });
        // 구간마다 수단에 맞는 점선으로 잇는다(공개 지도에는 실제 도로 경로를 그리지 않는다).
        for(let i=0;i<coordinates.length-1;i++){const style=legLineStyle(plan,plan.legs[i]);L.polyline([coordinates[i],coordinates[i+1]],{color:'#55606b',weight:3,dashArray:LINE_DASH.leaflet[style==='short'?'short':'long'],className:'route-leg route-leg-'+style}).addTo(map);}
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
        const fit=()=>{if(!disposed&&mapCanvas.isConnected){map.invalidateSize();map.fitBounds(L.latLngBounds(coordinates),{padding:[35,35],maxZoom:16});}};
        requestAnimationFrame(fit);
        if(window.ResizeObserver){resizeObserver=new ResizeObserver(fit);resizeObserver.observe(mapCanvas);}
      }catch{mapCanvas.replaceWith(node('p','공개 지도를 표시하지 못했어요. 아래 개략도와 장소 링크를 이용해 주세요.','hint'));}
    }
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
