/* 코스 만들기 폼(2026-11-25 사용자 시안 Downloads/screencapture-gemini-*-09_04_12.png, 가이드 datemate_2026.md §2.4).
   한 장의 카드 안에 위에서부터: 어디로 갈까요?(인기 동네 칩 + 전국 17 시·도) → 방문 날짜·시작·종료 → 예산(1인 기준 칩)·이동 수단 →
   원하는 활동 칩 → 상세 조건(접힘) → [3개 코스 비교하기]. 꼭 정할 것은 지역뿐이고 나머지는 기본값으로 채워 둔다.
   예전의 '기본 조건 · 바꾸기' 요약 패널(날짜·시간대·전체 예산 칩)은 시안에 맞춰 없앴다 — 날짜·시간은 칸을 바로 보이고, 전체 예산(원)·인원·장소 수는
   상세 조건 안에 있다. 한 줄 요청(자연어)은 카드 맨 위 접힘(.simple-dream)으로, 히어로 한 줄 입력(theme-cards.js)이 쓰면 펼친다.
   기존 API 와 다른 화면(테마 카드·축제·지난번처럼)이 쓰는 입력 이름(form.elements.*)은 그대로다. */
document.addEventListener('DOMContentLoaded',()=>{
  const form=document.getElementById('conditions');
  const retained=document.createElement('div');retained.hidden=true;retained.id='automatic-plan-settings';
  while(form.firstChild)retained.append(form.firstChild);
  form.append(retained);form.classList.add('simple-plan-form');
  const again=node('div',undefined,'last-conditions');again.hidden=true;
  form.append(again);
  function group(title,required=false,note=''){const section=node('fieldset',undefined,'simple-form-group'),legend=node('legend',title);if(note)legend.append(node('small',note,'legend-note'));if(required)legend.append(node('span','필수','field-requirement'));section.append(legend);form.append(section);return section;}
  function take(name){return form.elements[name]?.closest('label');}
  function chip(text,action){const item=button(text,action,'quick-chip');item.setAttribute('aria-pressed','false');return item;}
  function chipRow(label){const row=node('div',undefined,'quick-chips');row.setAttribute('role','group');row.setAttribute('aria-label',label);return row;}
  const pad=n=>String(n).padStart(2,'0');
  function dayAfter(days){const d=new Date();d.setDate(d.getDate()+days);return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;}
  const minutes=value=>{const [h,m]=String(value).split(':').map(Number);return h*60+m;};
  // 방문일이 오늘이면 이미 시작 시각이 지난 시간대는 고를 수 없다.
  function startPassed(start){const now=new Date();return form.elements.visit_date.value===today()&&minutes(start)<=now.getHours()*60+now.getMinutes();}
  function setValue(name,value){const input=form.elements[name];if(input.value===String(value))return;input.value=String(value);for(const type of ['input','change'])input.dispatchEvent(new Event(type,{bubbles:true}));}
  // 예산 무관은 숨긴 체크박스(budget_unlimited)에 둔다. 켜져 있으면 추천 요청에 budget_unlimited:true 를 싣는다.
  const unlimited=form.elements.budget_unlimited;
  function setUnlimited(on){if(!unlimited||unlimited.checked===on)return;unlimited.checked=on;unlimited.dispatchEvent(new Event('change',{bubbles:true}));}

  // 1. 어디로 갈까요?: 인기 동네 칩(시안 순서) + 오른쪽 '전국 17 시·도' 고르기 + 현재 위치·지역 칸 검색·지도에서 고르기.
  // 칩 가운데 preset 이 있는 것은 홈 '주말 떠나기 좋은 동네' 카드(index.html data-preset)를 그대로 쓴다(값을 한 곳에서 관리).
  // 연남·서촌은 카드에 없어 기준 역 좌표를 여기 둔다(연남 = 2호선 홍대입구역, 서촌 = 3호선 경복궁역 — 서촌은 theme-cards.js
  // HERO_QUICK_STARTS 와 같은 값). 출발지 이름은 시·도로 시작해야 서버의 지역 일치 검증을 통과한다.
  const HOTSPOTS=[
    {label:'서울 성수',preset:'서울 성수'},
    {label:'서울 연남·홍대',state:'서울',origin:'서울 연남 홍대입구역 지역 중심',lat:37.5572,lon:126.9245},
    {label:'서울 서촌·안국',state:'서울',origin:'서울 서촌 경복궁역 지역 중심',lat:37.5757,lon:126.9735},
    {label:'부산 해운대',preset:'부산 해운대'},
    {label:'강릉 안목',preset:'강릉 안목해변'},
    {label:'경주 황리단길',preset:'경주 황리단길'},
    {label:'제주 애월',preset:'제주 애월'}
  ];
  // '시·도 직접 선택'은 좌표를 지어내지 않는다: 고른 시·도의 중심가 이름으로 위치 검색(/locations/search)을 돌려 결과에서 고르게 한다.
  // 검색어를 바꾸려면 여기만 고친다(첫 결과가 엉뚱하면 사용자가 칸에 다시 검색할 수 있다).
  const REGION_HUBS={서울:'시청역',부산:'서면역',대구:'동성로',인천:'송도 센트럴파크',광주:'충장로',대전:'은행동',울산:'삼산동',세종:'나성동',경기:'수원역',
    강원:'춘천역',충북:'청주 성안길',충남:'천안역',전북:'전주 한옥마을',전남:'여수 이순신광장',경북:'경주 황리단길',경남:'창원 상남동',제주:'제주시청'};
  const region=group('지역 선택',true);region.classList.add('area-group');
  const regionPick=node('label',undefined,'region-pick'),regionSelect=node('select');
  regionPick.append(node('span','전국 17 시·도','region-pick-label'),regionSelect);regionSelect.setAttribute('aria-label','시·도 직접 선택');
  regionSelect.append(Object.assign(node('option','시·도 직접 선택'),{value:''}),...Object.keys(REGION_HUBS).map(name=>Object.assign(node('option',name),{value:name})));
  region.querySelector('legend').after(regionPick);
  const areaRow=chipRow('인기 동네'),areaStatus=node('p','','hint area-status');areaStatus.setAttribute('role','status');
  const areaCards=[...document.querySelectorAll('.curation-card[data-preset]')];
  function ready(){if(statusData)return true;toast('장소 정보를 준비 중이에요. 잠시 후 다시 눌러 주세요.');return false;}
  // 화면이 뜬 직후 서버 상태를 받기 전에 누른 동네는 버리지 않고, 서버가 준비되는 대로(server-wake.js) 마지막으로 누른 것을 적용한다.
  let pendingArea=null,pendingWait=null;
  function whenReady(action){
    if(statusData){action();return;}
    pendingArea=action;areaStatus.textContent='장소 정보를 준비하고 있어요. 곧 적용할게요…';
    if(pendingWait)return;
    pendingWait=ServerWake.ready().then(()=>{
      pendingWait=null;
      const run=pendingArea;pendingArea=null;
      if(statusData)run();else areaStatus.textContent='장소 정보를 불러오지 못했어요. 새로고침한 뒤 다시 눌러 주세요.';
    });
  }
  // 칩마다 출발지(state·origin·lat·lon). preset 칩은 동네 카드의 data-* 를 읽는다.
  const spots=HOTSPOTS.map(spot=>{
    if(!spot.preset)return spot;
    const card=areaCards.find(c=>c.dataset.preset===spot.preset);
    return card?{...spot,card,state:card.dataset.state,origin:card.dataset.origin,lat:Number(card.dataset.lat),lon:Number(card.dataset.lon)}:null;
  }).filter(Boolean);
  const areaChips=spots.map(spot=>{
    const item=chip(spot.label,()=>whenReady(()=>{
      if(spot.card)applyPresetArea(spot.card);else applyArea(spot.state,{name:spot.origin,lat:spot.lat,lon:spot.lon});
      areaStatus.textContent=spot.label+'을(를) 데이트할 지역으로 골랐어요.';refresh();
    }));
    item.dataset.area=spot.label;item.spot=spot;return item;
  });
  const here=button('현재 위치',useCurrentLocation,'quick-chip current-location');
  areaRow.append(...areaChips,here);
  const locationChoice=node('div',undefined,'location-choice');locationChoice.hidden=true;
  region.append(areaRow,areaStatus,locationChoice,document.getElementById('origin-location'),node('p','목록에 없는 곳은 위 칸에 동네·역·주소를 입력해 검색하거나 ‘지도에서 고르기’로 골라 주세요. 고른 위치가 코스의 시작 기준이 돼요.','hint'));
  regionSelect.addEventListener('change',()=>{
    const name=regionSelect.value;if(!name)return;
    whenReady(()=>{
      originInput.value=`${name} ${REGION_HUBS[name]}`;
      areaStatus.textContent=`${name}에서 시작할 곳을 찾고 있어요. 아래 결과에서 하나를 고르거나, 칸에 동네·역을 다시 검색해 주세요.`;
      searchOrigin();
    });
  });

  // 1-1. ‘데이트할 지역’ 칸에서 바로 검색한다. 입력 중 자동 호출은 하지 않는다(서버가 사용자별로 1초에 한 번만 받는다).
  const originInput=form.elements.origin_name,originHost=document.getElementById('origin-location');
  const originLabel=originInput.closest('label'),mapButton=originHost.querySelector('button');
  originInput.readOnly=false;originInput.maxLength=200;originInput.autocomplete='off';originInput.spellcheck=false;
  originInput.placeholder='동네·역·주소로 검색';originInput.enterKeyHint='search';
  const searchRow=node('div',undefined,'origin-search');
  const searchButton=button('검색',()=>searchOrigin(),'secondary origin-search-button');
  originLabel.before(searchRow);searchRow.append(originLabel,searchButton);
  const searchStatus=node('p','','hint origin-search-status');searchStatus.id='origin-search-status';searchStatus.setAttribute('role','status');
  const resultList=node('ul',undefined,'origin-search-results');resultList.id='origin-search-results';resultList.setAttribute('role','listbox');resultList.setAttribute('aria-label','지역 검색 결과');resultList.hidden=true;
  originInput.setAttribute('role','combobox');originInput.setAttribute('aria-autocomplete','list');originInput.setAttribute('aria-expanded','false');
  originInput.setAttribute('aria-controls',resultList.id);originInput.setAttribute('aria-describedby',searchStatus.id);
  // 장소 이름으로 찾은 결과(네이버 지역 검색)는 '네이버 검색결과' 블록 안에 목록을 둔다(naver-attribution.js naverResultBlock).
  // 주소 검색(지오코딩) 결과와 접힌 상태에서는 목록을 블록 없이 이 자리에 둔다.
  const resultHolder=node('div',undefined,'origin-search-holder');resultHolder.append(resultList);
  mapButton.before(searchStatus,resultHolder);
  // 목록을 누르는 동안 입력칸의 포커스를 잃지 않게 한다(잃으면 입력 중인 글이 원래 지역으로 되돌아간다).
  resultList.addEventListener('mousedown',event=>event.preventDefault());
  let searchResults=[],activeIndex=-1,searching=false,appliedOrigin=locationState.origin;
  const selectedName=()=>locationState.origin?.name||'';
  function regionOf(point){return regionFromAddress(point.road_address)||regionFromAddress(point.jibun_address)||regionFromAddress(point.name);}
  // 출발지 이름은 시·도로 시작해야 서버의 시·도·주소 일치 검증을 통과한다.
  function originNameOf(point,area){const address=String(point.road_address||point.jibun_address||point.name||'').trim();return regionFromAddress(address)===area?address:area+' '+address;}
  function closeResults(){searchStatus.classList.remove('visually-hidden');resultHolder.replaceChildren(resultList);resultList.hidden=true;resultList.replaceChildren();searchResults=[];activeIndex=-1;originInput.setAttribute('aria-expanded','false');originInput.removeAttribute('aria-activedescendant');}
  function setActive(index){
    activeIndex=index;
    [...resultList.children].forEach((item,i)=>item.setAttribute('aria-selected',String(i===index)));
    const item=resultList.children[index];
    if(item){originInput.setAttribute('aria-activedescendant',item.id);item.scrollIntoView({block:'nearest'});}else originInput.removeAttribute('aria-activedescendant');
  }
  function showResults(results,message){
    closeResults();
    if(!results.length){searchStatus.textContent=(message||'찾는 곳이 없어요.')+' 다른 이름으로 검색하거나 ‘지도에서 고르기’를 이용해 주세요.';return;}
    searchResults=results;
    results.forEach((point,i)=>{
      const known=Boolean(regionOf(point)),item=node('li',undefined,'origin-search-option');
      item.id='origin-search-option-'+i;item.setAttribute('role','option');item.setAttribute('aria-selected','false');
      // 역·가게·명소 이름으로 찾은 결과(place_name)는 이름과 주소를 함께 보인다. 모두 텍스트로만 넣는다.
      if(point.place_name){
        // 네이버 블록 안이라 API 가 준 값만 — 주소가 없으면 우리 글('주소 정보 없음')을 넣지 않는다(네이버 답 2-1 중간 삽입, 2026-11-26).
        item.append(node('strong',point.place_name));
        const address=point.road_address||point.jibun_address;if(address)item.append(node('span',address,'hint origin-search-address'));
      }else{
        item.append(node('strong',point.road_address||point.name));
        if(point.jibun_address&&point.jibun_address!==point.road_address)item.append(node('span','지번: '+point.jibun_address,'hint'));
      }
      // 시·도를 알 수 없는 결과: 고를 수 없게만 하고(흐리게, home.css .origin-search-option[aria-disabled=true]), 까닭은 블록 밖 상태 줄에 쓴다.
      // 예전처럼 항목 안에 '시·도를 알 수 없어 고를 수 없어요'를 넣으면 네이버 결과 중간에 우리 글을 넣는 것(네이버 답 2-1).
      if(!known)item.setAttribute('aria-disabled','true');
      item.addEventListener('click',()=>chooseResult(i));
      resultList.append(item);
    });
    if(results.some(point=>point.place_name)){
      const block=naverResultBlock('지역 검색','https://map.naver.com/p/search/'+encodeURIComponent(originInput.value.trim()),{tag:'div',className:'origin-naver-block'});
      block.body.append(resultList);resultHolder.replaceChildren(block);
      // 블록 머리글의 링크를 누르는 동안에도 입력칸의 포커스를 지킨다(목록과 같은 이유). 링크의 새 창 열기는 click 이라 그대로 된다.
      block.addEventListener('mousedown',event=>event.preventDefault());
    }
    resultList.hidden=false;originInput.setAttribute('aria-expanded','true');
    const usable=results.filter(regionOf).length,naver=results.some(point=>point.place_name);
    searchStatus.textContent=usable?`검색 결과 ${results.length}곳이에요.${usable<results.length?` 시·도를 알 수 없는 ${results.length-usable}곳(흐린 항목)은 고를 수 없어요.`:''} 하나를 누르거나 위아래 화살표로 고른 뒤 Enter 를 눌러 주세요.`:'시·도를 알 수 없는 결과뿐이에요. 시·도 이름을 붙여(예: 부산 광안리) 다시 검색하거나 ‘지도에서 고르기’를 이용해 주세요.';
    // 네이버 블록 바로 위에 우리 안내를 보이지 않게 한다(네이버 답 2-2 앞 삽입). 화면 읽기 프로그램은 입력칸 설명(aria-describedby)으로 그대로 듣는다.
    // 고를 수 있는 결과가 하나도 없으면(사용자가 다음에 할 일을 알아야 함) 보이게 둔다.
    searchStatus.classList.toggle('visually-hidden',naver&&usable>0);
  }
  async function searchOrigin(){
    if(searching)return;
    const query=originInput.value.trim();
    if(query.length<2){closeResults();searchStatus.textContent='동네·역·주소를 두 글자 이상 입력하고 검색해 주세요.';originInput.focus();return;}
    // disabled 로 바꾸면 버튼에 있던 포커스가 사라져 입력한 검색어가 되돌려지므로 aria-disabled 만 쓴다.
    searching=true;searchButton.setAttribute('aria-disabled','true');closeResults();searchStatus.textContent=`‘${query}’을(를) 찾고 있어요…`;
    // 새 질의: 앞서 지역 검색으로 고른 출발지를 이 브라우저(지난번처럼 추천)에서 지운다(특약 1.4, form-state.js).
    LastConditions.newQuery('local');
    try{const data=await api('/locations/search',{query}),at=Date.now();showResults((data.results||[]).map(point=>({...point,received_at:at})),data.message);}
    catch(error){searchStatus.textContent=(error.message||'검색하지 못했어요.')+' 잠시 후 다시 검색하거나 ‘지도에서 고르기’를 이용해 주세요.';}
    finally{searching=false;searchButton.removeAttribute('aria-disabled');}
  }
  function chooseResult(index){
    const point=searchResults[index];if(!point)return;
    const area=regionOf(point);
    if(!area){setActive(index);searchStatus.textContent='이 결과는 시·도를 알 수 없어 고를 수 없어요. 다른 결과를 고르거나 시·도 이름을 붙여 다시 검색해 주세요.';return;}
    // 역·가게·명소 이름으로 찾은 결과(place_name)는 네이버 지역 검색 결과다. 받은 시각을 붙여 기기 보관을 24시간으로 묶는다.
    const origin={name:originNameOf(point,area),lat:point.lat,lon:point.lon};
    applyArea(area,point.place_name?NaverDeviceRetention.mark(origin,'local',point.received_at):origin);
    appliedOrigin=locationState.origin;closeResults();searchStatus.textContent='';closeLocationChoice();
    areaStatus.textContent=(point.place_name?point.place_name+'('+originInput.value+')':originInput.value)+'을(를) 데이트할 지역으로 골랐어요.';
    refresh();
  }
  originInput.addEventListener('keydown',event=>{
    const count=searchResults.length;
    if(event.key==='Enter'){event.preventDefault();if(!resultList.hidden&&activeIndex>=0)chooseResult(activeIndex);else searchOrigin();}
    else if((event.key==='ArrowDown'||event.key==='ArrowUp')&&count){
      event.preventDefault();
      if(resultList.hidden){resultList.hidden=false;originInput.setAttribute('aria-expanded','true');}
      setActive(event.key==='ArrowDown'?(activeIndex+1)%count:(activeIndex<=0?count-1:activeIndex-1));
    }else if(event.key==='Escape'){
      if(!resultList.hidden){event.preventDefault();closeResults();searchStatus.textContent='검색 결과를 닫았어요.';}
      else if(originInput.value!==selectedName()){event.preventDefault();originInput.value=selectedName();searchStatus.textContent='입력을 지우고 지금 고른 지역으로 되돌렸어요.';}
    }
  });
  originInput.addEventListener('input',()=>{
    if(!resultList.hidden)closeResults();
    const hint=originInput.value.trim()&&originInput.value!==selectedName()?'Enter 또는 ‘검색’을 누르면 찾아요.':'';
    if(searchStatus.textContent!==hint)searchStatus.textContent=hint;
  });
  // 칸을 벗어나면(검색 결과를 보고 있지 않을 때) 고르지 않은 검색어는 지금 고른 지역 이름으로 되돌린다.
  originHost.addEventListener('focusout',()=>setTimeout(()=>{
    if(searching||originHost.contains(document.activeElement)||!resultList.hidden||originInput.value===selectedName())return;
    const typed=originInput.value.trim();originInput.value=selectedName();
    if(typed)searchStatus.textContent='검색한 곳을 고르지 않아 지금 고른 지역을 그대로 둬요.';
  }));
  // 칩·현재 위치·지도 창·축제·지난번처럼 추천이 출발지를 바꾸면 칸 표시와 검색 결과를 맞춘다.
  function syncOrigin(){
    if(locationState.origin!==appliedOrigin){
      appliedOrigin=locationState.origin;closeResults();searchStatus.textContent='';closeLocationChoice();
      originInput.value=selectedName();return;
    }
    if(!searching&&!originHost.contains(document.activeElement)&&resultList.hidden&&originInput.value!==selectedName())originInput.value=selectedName();
  }

  // 1-2. 현재 위치. 오차(coords.accuracy)를 보고, 정확하지 않으면 조용히 적용하지 않고 고르게 한다.
  // 코스 장소는 출발지 반경 2.5km(기본) 안에서 찾으므로 오차 1km 이내면 같은 동네로 보고 바로 쓴다.
  // 20km 를 넘으면 IP·통신사 기준 위치라 다른 시·군·시·도일 수 있어 적용 버튼 없이 검색으로 안내한다.
  const PRECISE_METERS=1000,ROUGH_LIMIT_METERS=20000;
  const LOCATION_HELP={
    1:'위치 권한이 허용되지 않았어요. 브라우저 주소창 왼쪽의 사이트 정보(자물쇠) 아이콘에서 위치를 ‘허용’으로 바꾼 뒤 다시 눌러 주세요.',
    2:'기기가 현재 위치를 알아내지 못했어요. 기기의 위치 서비스를 켜고(Windows: 설정 › 개인 정보 및 보안 › 위치) 와이파이를 켠 뒤 다시 눌러 주세요.',
    3:'현재 위치를 확인하는 데 시간이 너무 오래 걸렸어요. 잠시 뒤 다시 눌러 주세요.'
  };
  function readPosition(options){return new Promise((resolve,reject)=>navigator.geolocation.getCurrentPosition(resolve,reject,options));}
  function distanceText(meters){if(meters<1000)return '약 '+Math.max(100,Math.round(meters/100)*100)+'m';const km=meters/1000;return '약 '+(km<10?Math.round(km*10)/10:Math.round(km))+'km';}
  function closeLocationChoice(){locationChoice.hidden=true;locationChoice.replaceChildren();}
  function toSearch(text){areaStatus.textContent=text+' 아래 ‘데이트할 지역’ 칸에 동네·역·주소를 입력해 검색할 수도 있어요.';originInput.focus();}
  function applyHere(area,origin,meters){
    closeLocationChoice();applyArea(area,origin);appliedOrigin=locationState.origin;
    const place=origin.name.replace(/ · 현재 위치$/,'');
    areaStatus.textContent=`현재 위치(${place})를 데이트할 지역으로 골랐어요.`+(meters==null?'':` 대략적인 위치(오차 ${distanceText(meters)})라 실제와 다를 수 있어요. 다르면 아래 칸에서 동네를 검색해 주세요.`);
    refresh();
  }
  function offerRough(area,origin,meters,place){
    closeLocationChoice();
    const known=Number.isFinite(meters),tooFar=known&&meters>ROUGH_LIMIT_METERS;
    const text=!known?`위치의 정확도를 알 수 없어요. ${place} 근처로 나왔어요.`:tooFar?`대략적인 위치예요(오차 ${distanceText(meters)}). ${place} 근처로 나왔지만 오차가 너무 커서 이 위치로는 정하지 않을게요. 동네를 직접 검색해 주세요.`:`대략적인 위치예요(오차 ${distanceText(meters)}). ${place} 근처로 나왔어요. 맞으면 이 위치로 정하고, 아니면 동네를 직접 검색해 주세요.`;
    areaStatus.textContent=text;
    const actions=node('div',undefined,'location-choice-actions');
    if(!tooFar)actions.append(button('이 위치로 정하기',()=>applyHere(area,origin,known?meters:null),'secondary'));
    actions.append(button('동네 직접 검색하기',()=>{closeLocationChoice();areaStatus.textContent='동네·역·주소를 입력하고 검색해 주세요.';originInput.focus();originInput.select();},'secondary'));
    locationChoice.append(actions);locationChoice.hidden=false;
  }
  async function useCurrentLocation(){
    if(!ready()||here.disabled)return;
    closeLocationChoice();
    if(!navigator.geolocation){toSearch('이 브라우저에서는 현재 위치를 쓸 수 없어요.');return;}
    here.disabled=true;areaStatus.textContent='현재 위치를 확인하고 있어요…';
    try{
      let position;
      // 정확한 위치(GPS·와이파이)를 먼저 새로 요청하고, 시간 초과일 때만 낮은 정확도로 한 번 더 시도한다.
      try{position=await readPosition({enableHighAccuracy:true,timeout:15000,maximumAge:0});}
      catch(error){
        if(error?.code!==3){toSearch(LOCATION_HELP[error?.code]||'현재 위치를 확인하지 못했어요.');return;}
        areaStatus.textContent='정확한 위치를 받지 못해 대략적인 위치로 한 번 더 확인하고 있어요…';
        try{position=await readPosition({enableHighAccuracy:false,timeout:20000,maximumAge:60000});}
        catch(again){toSearch(LOCATION_HELP[again?.code]||LOCATION_HELP[3]);return;}
      }
      const lat=position.coords.latitude,lon=position.coords.longitude,meters=Number(position.coords.accuracy);
      let data=null;
      try{data=await api('/locations/region',{lat,lon});}catch{}
      if(data?.status!=='ok'||!data.region){toSearch(data?.status==='outside'?'현재 위치가 국내가 아니에요.':'현재 위치의 시·도를 확인하지 못했어요.');return;}
      // 출발지 이름은 시·도로 시작한다(서버의 시·도·주소 일치 검증).
      const label=String(data.label||'').trim(),place=regionFromAddress(label)===data.region?label:data.region;
      const origin={name:place+' · 현재 위치',lat,lon};
      if(Number.isFinite(meters)&&meters<=PRECISE_METERS)applyHere(data.region,origin,null);
      else offerRough(data.region,origin,meters,place);
    }finally{here.disabled=false;refresh();}
  }

  // 2. 언제: 방문 날짜·시작·종료 칸을 바로 보인다(시안). 오늘인데 시작 시각이 지났으면 다음 시간대(없으면 내일)로 맞추고 아래 줄에 알린다.
  const when=node('div',undefined,'field-grid when-grid');
  when.append(take('visit_date'),take('start'),take('end'));
  const whenNote=node('p','','hint choice-note date-note');whenNote.setAttribute('role','status');
  form.append(when,whenNote);
  // 지난 시작 시각을 맞출 때 고르는 다음 시간대(예전 시간대 칩과 같은 값).
  const timeWindows=[['11:00','19:00'],['11:00','17:00'],['13:00','19:00'],['17:00','22:00']];
  function fitTimeToToday(){
    const from=form.elements.start.value;
    if(!startPassed(from))return null;
    const next=timeWindows.find(([start])=>!startPassed(start));
    if(next){setValue('start',next[0]);setValue('end',next[1]);return {from,time:next.join('–')};}
    setValue('visit_date',dayAfter(1));return {date:true};
  }
  function announceFit(adjustment){
    if(!adjustment)return;
    whenNote.textContent=adjustment.date?`오늘은 고를 수 있는 시간대가 모두 지나 ${dateText(form.elements.visit_date.value)}로 맞췄어요.`
      :`오늘은 ${adjustment.from} 시작이 이미 지나 시간대를 ${adjustment.time}에 맞췄어요.`;
    whenNote.classList.add('is-adjusted');
  }
  // 처음 열 때: 기본값(오늘 11:00–19:00)이 이미 지났으면 조용히 맞춘다(알림 없이 — 사용자가 고른 값이 아니다).
  if(form.elements.visit_date.value===today()&&form.elements.start.value==='11:00'&&form.elements.end.value==='19:00'){
    const next=timeWindows.find(([start])=>!startPassed(start));
    if(startPassed('11:00')){if(next){form.elements.start.value=next[0];form.elements.end.value=next[1];}else form.elements.visit_date.value=dayAfter(1);}
  }
  form.elements.visit_date.addEventListener('change',()=>{whenNote.textContent='';whenNote.classList.remove('is-adjusted');announceFit(fitTimeToToday());});
  function dateText(value){
    if(!value)return '날짜를 정해 주세요';
    const d=new Date(value+'T00:00');if(Number.isNaN(d.getTime()))return value;
    const relative=value===today()?'오늘 ':value===dayAfter(1)?'내일 ':'';
    return `${relative}${d.getMonth()+1}월 ${d.getDate()}일 (${'일월화수목금토'[d.getDay()]})`;
  }

  // 3. 예산(1인 기준)과 이동 수단(시안: 한 줄에 나란히, 휴대폰은 위아래).
  // 예산 칸(budget)은 일행 합계(원)라 칩은 '1인 상한 × 인원'을 넣는다(1인 3만·6만·10만·15만 원까지 — HTML 시안의 네 칸).
  // 시안의 '15만원+'는 상한이 없는 것처럼 읽혀 '15만원'으로 적었다 — 상한 없이 찾으려면 오른쪽 '예산 무관'을 켠다.
  // 인원을 바꾸면 고른 칩의 1인 상한으로 합계를 다시 맞춘다. 정확한 합계는 상세 조건의 '전체 예산 (원)'에 직접 넣는다
  // — 그때는 어느 칩도 눌리지 않고 아래 줄에 합계·1인 금액을 보인다. 칩·상한을 바꾸면 theme-cards.js(기념일 budget_per_person)도 본다.
  const BUDGET_TIERS=[['3만원',30000],['6만원',60000],['10만원',100000],['15만원',150000]];
  const people=()=>Math.max(1,Number(form.elements.people.value)||2);
  const won=n=>n>=10000&&n%10000===0?n/10000+'만 원':Number(n).toLocaleString('ko-KR')+'원';
  const budgetTransport=node('div',undefined,'budget-transport');
  const budgetGroup=node('fieldset',undefined,'simple-form-group budget-group'),budgetLegend=node('legend','1인 예상 예산');
  budgetGroup.append(budgetLegend);
  // '예산 무관'은 숨긴 체크박스(budget_unlimited)를 그대로 보이는 체크로 꺼낸다(제목 줄 오른쪽).
  const freeLabel=take('budget_unlimited');if(freeLabel){freeLabel.hidden=false;freeLabel.classList.add('budget-free');budgetGroup.append(freeLabel);}
  const budgetRow=chipRow('1인 예상 예산');budgetRow.classList.add('segmented');
  let tier=null;  // 마지막으로 누른 1인 상한(인원이 바뀌면 이 값으로 합계를 다시 맞춘다). 직접 입력하면 null.
  const budgetChips=BUDGET_TIERS.map(([label,per])=>{const item=chip(label,()=>{tier=per;setUnlimited(false);setValue('budget',per*people());refresh();});item.per=per;return item;});
  budgetRow.append(...budgetChips);
  unlimited?.addEventListener('change',()=>{if(unlimited.checked)tier=null;setTimeout(refresh);});
  const budgetNote=node('p','','hint choice-note budget-note');budgetNote.setAttribute('role','status');
  budgetGroup.append(budgetRow,budgetNote);
  form.elements.people.addEventListener('change',()=>{if(tier&&!unlimited?.checked)setValue('budget',tier*people());});
  form.elements.budget.addEventListener('input',()=>{tier=null;setUnlimited(false);});
  // 이동 수단: 숨긴 select(transport)를 네 칸 선택 막대로.
  const transportGroup=node('fieldset',undefined,'simple-form-group transport-group');transportGroup.append(node('legend','이동 수단'));
  const transportRow=chipRow('이동 수단');transportRow.classList.add('segmented');
  const transportChips=[...form.elements.transport.options].map(option=>{const item=chip(option.textContent,()=>{setValue('transport',option.value);refresh();});item.dataset.transport=option.value;return item;});
  transportRow.append(...transportChips);transportGroup.append(transportRow);
  budgetTransport.append(budgetGroup,transportGroup);form.append(budgetTransport);

  // 4. 원하는 활동(여러 개, 가이드 2.4 '원하는 활동 대분류 복수 선택 칩').
  // 숨긴 분류 체크박스(name=themes, app.js 가 서버 /status 의 themes 로 만든다)를 누르기 쉬운 칩으로 꺼낸다. 값은 서버 분류 이름 그대로
  // (app/models.py THEMES), 칩 글자만 쉬운 말로. 고르면 그 분류의 장소로만 코스를 짜고(app/planner.py — 식사 시간대 식당은 예외),
  // 안 고르면 예전처럼 골고루. 상황 테마·자연어 해석이 체크박스를 바꿔도 refresh 가 칩 눌림을 맞춘다. 분류가 늘면 ACTIVITY_CHIPS 에 더한다.
  const ACTIVITY_CHIPS=[['카페·미식','카페·맛집'],['산책·풍경','산책·풍경'],['문화·예술','전시·문화'],['체험·제작','공방·체험'],['오락·놀이','놀거리'],['레저·활동','레저·스포츠'],['휴식·힐링','휴식·힐링']];
  const activity=group('선호 활동',false,'(복수 선택 가능)');activity.classList.add('activity-group');
  const activityRow=chipRow('원하는 활동');
  const activityChips=ACTIVITY_CHIPS.map(([value,label])=>{
    const item=chip(label,()=>{
      const input=form.querySelector(`[name=themes][value="${value}"]`);
      if(!input){toast('장소 정보를 준비 중이에요. 잠시 후 다시 눌러 주세요.');return;}
      input.checked=!input.checked;input.dispatchEvent(new Event('change',{bubbles:true}));
      item.setAttribute('aria-pressed',String(input.checked));
    });
    item.dataset.theme=value;return item;
  });
  activityRow.append(...activityChips);
  activity.append(activityRow,node('p','고른 종류의 장소로만 코스를 짜요(식사 시간대 식당은 따로 넣어요). 고르지 않으면 골고루 섞어요.','hint'));

  // 5. 한 줄 요청(자연어, 선택): 카드 맨 위 접힘. 히어로 한 줄 입력(theme-cards.js)이 이 칸에 넣고 해석할 때 펼친다.
  const preference=node('details',undefined,'simple-dream');
  preference.append(node('summary','한 줄로 적어서 조건 채우기 (선택)','simple-dream-summary'));
  form.insertBefore(preference,region);
  const request=take('request');request.firstChild.textContent='어떤 데이트를 꿈꾸나요?';
  form.elements.request.placeholder='예: 비 오는 날 실내 위주로 / 전시 보고 산책 / 매운 음식은 제외';
  const scenarios=node('div',undefined,'simple-dream-examples quick-chips');scenarios.setAttribute('role','group');scenarios.setAttribute('aria-label','이런 데이트는 어때요');
  for(const text of ['비 오는 날 성수 실내 데이트','덜 걷고 분위기 좋은 저녁 코스','바다 보며 걷는 주말 오후']){
    scenarios.append(button(text,()=>{const input=form.elements.request;input.value=text;input.dispatchEvent(new Event('input',{bubbles:true}));input.focus();},'quick-chip'));
  }
  // 자주 쓰는 조건 칩은 입력칸 바로 위, ‘이렇게 이해했어요’는 해석 버튼 아래에 둔다(request-understanding.js).
  preference.append(scenarios,request);
  const understanding=typeof RequestUnderstanding==='undefined'?[]:RequestUnderstanding.mount(preference,request);
  const parse=document.getElementById('parse');parse.textContent='이 마음으로 조건 채우기';
  preference.append(parse,...understanding);
  // 해석 결과 안내(#parse-notice)는 접힘 밖에 둔다 — 테마 카드·지난번처럼도 이 줄에 쓰므로 접혀 있어도 보여야 한다.
  form.insertBefore(document.getElementById('parse-notice'),region);

  // 6. 상세 조건(기본 접힘). 인원·장소 수·전체 예산(원)과 예전부터 있던 조건(실내외·테마 구성·체류·피할 활동·예약·귀가·MBTI·여유·이동 제한)을 모은다.
  // 하나라도 기본값과 다르면 머리글에 '상세 조건 설정됨 · …' 요약을 붙인다(detailSummary). 요약 문구를 바꾸면 tests/test_ux_p0_form_ui.py 도 고친다.
  const optional=node('details',undefined,'simple-extra-options');
  const optionalSummary=node('summary',undefined,'simple-extra-summary'),optionalBadge=node('span','','detail-badge');
  optionalSummary.append(node('span','상세 조건 더보기','simple-extra-title'),node('span','도보 제한 · 실내외 · 귀가 동선 · MBTI','simple-extra-hint'),optionalBadge);optional.append(optionalSummary);
  // 줄 1: 인원 · 방문 장소 수 · 실내·실외(숨긴 select setting 을 세 칸 막대로).
  const row1=node('div',undefined,'field-grid detail-row detail-row-3');
  for(const name of ['people','count']){const label=take(name);if(label)row1.append(label);}
  const settingBox=node('div',undefined,'detail-setting'),settingTitle=node('span','실내 · 실외 비중','detail-label');settingTitle.id='detail-setting-label';
  const settingRow=chipRow('실내 · 실외 비중');settingRow.classList.add('segmented','detail-segmented');
  const settingChips=[...form.elements.setting.options].map(option=>{const item=chip({any:'모두',indoor:'실내만',outdoor:'실외만'}[option.value]||option.textContent,()=>{setValue('setting',option.value);refresh();});item.dataset.setting=option.value;return item;});
  settingRow.append(...settingChips);settingBox.append(settingTitle,settingRow);row1.append(settingBox);
  // 줄 2: 전체 도보 제한 슬라이더(10~60분, 60 = 제한 없음 → max_walk 빈칸) · 구간당 최대 이동(분).
  const row2=node('div',undefined,'field-grid detail-row');
  const walkCard=node('div',undefined,'detail-card walk-card'),walkHead=node('div',undefined,'detail-card-head');
  const walkValue=node('span','','walk-value');walkValue.setAttribute('aria-hidden','true');
  const walkRange=node('input');walkRange.type='range';walkRange.min='10';walkRange.max='60';walkRange.step='5';walkRange.id='walk-range';walkRange.setAttribute('aria-label','전체 도보 제한(분), 60은 제한 없음');
  walkHead.append(Object.assign(node('label','전체 도보 제한'),{htmlFor:'walk-range'}),walkValue);
  const walkScale=node('div',undefined,'walk-scale');walkScale.setAttribute('aria-hidden','true');for(const t of ['10분','20분','35분','60분 (무관)'])walkScale.append(node('span',t));
  walkCard.append(walkHead,walkRange,walkScale);
  walkRange.addEventListener('input',()=>{const v=Number(walkRange.value);setValue('max_walk',v>=60?'':v);});
  const legCard=node('div',undefined,'detail-card');const legLabel=take('max_leg');if(legLabel){legLabel.firstChild.textContent='구간당 최대 이동 시간 (분)';legCard.append(legLabel);}
  row2.append(walkCard,legCard);
  const walkInput=take('max_walk');  // 숫자 칸은 '더 많은 조건'으로(슬라이더가 못 고르는 값 — 예: 12분 — 을 직접 넣을 때).
  // 줄 3: 귀가 · 예약 토글 카드. 귀가를 켜면 귀가지(지도·주소)를 고르는 칸이 함께 필요하다(app.js 가 return_home 이면 home 위치를 싣는다).
  const row3=node('div',undefined,'field-grid detail-row detail-toggles');
  for(const [name,title,sub] of [['return_home','귀가 시간 · 교통비 포함','종료 시각 기준 귀가 동선까지 계산해요'],['reservation','예약 필요 장소 허용','인기 다이닝·원데이 클래스를 포함해요']]){
    const label=take(name);if(!label)continue;
    const input=label.querySelector('input');label.replaceChildren(node('span',undefined,'toggle-text'),input);
    label.firstChild.append(node('strong',title),node('small',sub));label.classList.add('toggle-card');row3.append(label);
  }
  const homeHost=document.getElementById('home-location');
  // 줄 4: 피할 활동 · MBTI.
  const row4=node('div',undefined,'field-grid detail-row');
  const avoid=take('avoid');if(avoid)row4.append(avoid);
  const mbtiBox=node('div',undefined,'detail-mbti');for(const name of ['mbti','use_mbti']){const label=take(name);if(label)mbtiBox.append(label);}
  row4.append(mbtiBox);
  optional.append(row1,row2,row3);if(homeHost)optional.append(homeHost);optional.append(row4);
  // 더 많은 조건: 정확한 전체 예산(원)·테마 구성·체류·식사·여유·지난 반응·새 장소·필수 조건·가격 추정.
  const more=node('details',undefined,'detail-more');more.append(node('summary','더 많은 조건'));
  const moreGrid=node('div',undefined,'field-grid');
  const budgetLabel=take('budget');if(budgetLabel){budgetLabel.firstChild.textContent='전체 예산 (원, 일행 합계)';moreGrid.append(budgetLabel);}
  for(const name of ['theme_mode','stay_minutes']){const label=take(name);if(label)moreGrid.append(label);}
  if(walkInput){walkInput.firstChild.textContent='전체 도보 제한 (분, 직접 입력)';moreGrid.append(walkInput);}
  more.append(moreGrid);
  const preview=document.querySelector('.price-input-preview');if(preview)more.append(preview);
  more.append(take('include_meal'));
  const feedback=take('use_feedback');if(feedback)more.append(feedback);
  const fresh=take('fresh_one');if(fresh)more.append(fresh);
  const buffer=node('label','이동 구간별 여유시간'),bufferSelect=node('select');bufferSelect.name='transition_buffer_minutes';
  for(const [value,title] of [[0,'기본 · 추가 여유 없음'],[5,'구간마다 5분 여유'],[10,'느긋하게 · 구간마다 10분 여유']]){const option=node('option',title);option.value=value;bufferSelect.append(option);}buffer.append(bufferSelect);more.append(buffer);
  const hard=retained.querySelector('.experience-controls details');
  if(hard)more.append(hard);
  const estimates=take('allow_price_estimates');if(estimates)more.append(estimates);
  optional.append(more);
  PlanningStudy.mount(more);
  const submit=document.getElementById('submit-plan');submit.textContent='3가지 맞춤 코스 비교하기 →';
  form.append(optional,submit,node('p','조건에 맞는 후보가 부족하면 범위를 넓혀 찾고, 바뀐 조건을 알려드려요. 비용·이동 시간은 추정이 포함될 수 있어요.','hint'),
    button('내가 결정한 코스 다시 보기',()=>PlanningStudy.showDecisions(),'secondary saved-decisions'));
  // 자동으로 정하는 값. MBTI 는 상세 조건에서 사용자가 고르므로 비우지 않는다(2026-11-24 UX P0).
  form.elements.trust_mode.value='balanced';
  retained.querySelectorAll('[required]').forEach(input=>input.required=false);
  // 상세 조건 안의 칸이 잘못되면(예: 인원 0) 접힘을 펼쳐 바로 고칠 수 있게 한다.
  form.addEventListener('invalid',event=>{if(optional.contains(event.target))optional.open=true;},true);
  // 상세 조건 요약 배지. 기본값과 다른 것만 이 순서로 센다(앞 두 개를 보여 주고 나머지는 '외 N건').
  const DETAIL_DEFAULTS={setting:'any',theme_mode:'mix',stay_minutes:'60',max_leg:'30',transition_buffer_minutes:'0',people:'2',count:'3'};
  function detailSummary(){
    const f=form.elements,parts=[];
    if(f.max_walk?.value)parts.push(`도보 ${f.max_walk.value}분 제한`);
    if(f.setting&&f.setting.value!==DETAIL_DEFAULTS.setting)parts.push({indoor:'실내만',outdoor:'실외만'}[f.setting.value]||f.setting.selectedOptions[0]?.textContent);
    if(f.people&&f.people.value!==DETAIL_DEFAULTS.people)parts.push(`${f.people.value}명`);
    if(f.count&&f.count.value!==DETAIL_DEFAULTS.count)parts.push(`${f.count.value}곳`);
    if(f.avoid?.value.trim())parts.push(`피할 활동 ${f.avoid.value.trim()}`);
    if(f.max_leg&&f.max_leg.value!==DETAIL_DEFAULTS.max_leg)parts.push(`구간 이동 ${f.max_leg.value}분까지`);
    if(f.theme_mode&&f.theme_mode.value!==DETAIL_DEFAULTS.theme_mode)parts.push(f.theme_mode.selectedOptions[0]?.textContent||'테마 집중');
    if(f.stay_minutes&&f.stay_minutes.value!==DETAIL_DEFAULTS.stay_minutes)parts.push(`장소당 ${f.stay_minutes.value}분`);
    if(f.transition_buffer_minutes&&f.transition_buffer_minutes.value!==DETAIL_DEFAULTS.transition_buffer_minutes)parts.push(`구간마다 ${f.transition_buffer_minutes.value}분 여유`);
    if(f.reservation?.checked)parts.push('예약 필요한 곳 포함');
    if(f.return_home?.checked)parts.push('귀가 포함');
    if(f.use_mbti?.checked&&f.mbti?.value)parts.push(`MBTI ${f.mbti.value.toUpperCase()}`);
    if(f.include_meal&&!f.include_meal.checked)parts.push('식사 빼기');
    // 상황 테마가 채운 분류(숨긴 체크박스 themes, theme-cards.js)도 배지에 보인다 — 활동 칩과 같은 값이다.
    const themes=[...form.querySelectorAll('[name=themes]:checked')].map(input=>input.value);
    if(themes.length)parts.push('분류 '+themes.join('·'));
    const shown=parts.slice(0,2).join(', ')+(parts.length>2?` 외 ${parts.length-2}건`:'');
    optionalBadge.textContent=parts.length?'상세 조건 설정됨 · '+shown:'';
    optionalBadge.hidden=!parts.length;
  }
  for(const type of ['input','change'])optional.addEventListener(type,detailSummary);
  form.addEventListener('change',()=>setTimeout(detailSummary));
  detailSummary();

  function budgetText(value,free=false){if(free)return '예산 무관';const n=Number(value);if(value===''||!Number.isFinite(n))return '예산 미정';return won(n);}
  const transportText=value=>[...form.elements.transport.options].find(option=>option.value===value)?.textContent||value;
  function refresh(){
    const f=form.elements,origin=locationState.origin;
    syncOrigin();
    for(const item of areaChips){const spot=item.spot;
      item.setAttribute('aria-pressed',String(Boolean(origin&&origin.name===spot.origin&&Math.abs(origin.lat-spot.lat)<1e-6&&Math.abs(origin.lon-spot.lon)<1e-6)));}
    if(origin&&regionSelect.value&&regionSelect.value!==f.region.value)regionSelect.value=f.region.value;
    for(const item of activityChips)item.setAttribute('aria-pressed',String(Boolean(form.querySelector(`[name=themes][value="${item.dataset.theme}"]`)?.checked)));
    for(const item of transportChips)item.setAttribute('aria-pressed',String(item.dataset.transport===f.transport.value));
    for(const item of settingChips)item.setAttribute('aria-pressed',String(item.dataset.setting===f.setting.value));
    // 도보 슬라이더 ↔ max_walk(빈칸 = 제한 없음). 슬라이더가 못 고르는 값(예: 12)은 가장 가까운 칸에 두고 글자는 실제 값.
    const walk=f.max_walk.value===''?60:Math.min(60,Math.max(10,Math.round(Number(f.max_walk.value)/5)*5));
    if(document.activeElement!==walkRange)walkRange.value=String(walk);
    walkValue.textContent=f.max_walk.value===''?'제한 없음':`${f.max_walk.value}분 이하`;
    // 예산 칩: 합계가 '1인 상한 × 인원'과 같은 칩. 마지막으로 누른 칩이 있으면 그 칩(합계가 같은 칩이 둘일 수 있다).
    const free=Boolean(unlimited?.checked),total=Number(f.budget.value),count=people();
    const match=free?null:(budgetChips.find(item=>item.per===tier&&item.per*count===total)||budgetChips.find(item=>item.per*count===total));
    for(const item of budgetChips){item.setAttribute('aria-pressed',String(item===match));item.disabled=free;}
    const note=free?'예산 상한 없이 코스를 찾아요.':match?`1인 ${won(match.per)}까지 · ${count}명 합계 ${won(total)}으로 찾아요.`
      :Number.isFinite(total)&&f.budget.value!==''?`전체 예산 ${won(total)}(직접 입력) · 1인 약 ${won(Math.round(total/count/1000)*1000)}`:'예산을 골라 주세요.';
    if(budgetNote.textContent!==note)budgetNote.textContent=note;
  }

  // 다시 온 사용자는 맨 위 ‘지난번처럼 추천’ 한 번으로 같은 조건(날짜는 오늘)으로 추천받는다.
  function savedText(saved){
    const area=saved.origin.name.split(' · ')[0].replace(/ 지역 중심$/,'');
    return [area,`${saved.start}–${saved.end}`,`${saved.people}명`,budgetText(saved.budget,saved.budget_unlimited),`${saved.count}곳`,transportText(saved.transport)].join(' · ');
  }
  function renderAgain(){
    const saved=LastConditions.load(),known=saved&&[...form.elements.region.options].some(option=>option.value===saved.region);
    again.replaceChildren();again.hidden=!known;if(!known)return;
    const action=button('',()=>useSaved(saved),'primary full again-button');
    action.append(node('strong','지난번처럼 추천'),node('span',savedText(saved),'again-summary'));
    again.append(action,node('p','날짜는 오늘로 맞춰서 바로 추천해요. 조건을 바꾸려면 아래에서 고르세요.','hint'));
  }
  let savedWait=null;
  function useSaved(saved){
    // 서버가 켜지는 중에 누른 ‘지난번처럼 추천’은 준비되면 그대로 진행한다.
    if(!statusData&&ServerWake.waiting){
      if(!savedWait){toast('서버를 준비하고 있어요. 준비되면 바로 추천할게요.');savedWait=ServerWake.ready().then(()=>{savedWait=null;if(statusData)useSaved(saved);});}
      return;
    }
    if(!ready())return;
    if(document.getElementById('submit-plan').disabled){toast('코스를 찾는 중이에요. 끝난 뒤 다시 눌러 주세요.');return;}
    applyArea(saved.region,saved.origin);
    setValue('visit_date',today());
    for(const name of ['start','end','budget','people','count','transport'])setValue(name,saved[name]);
    setUnlimited(saved.budget_unlimited===true);tier=null;
    let note='';
    if(startPassed(saved.start)){setValue('visit_date',dayAfter(1));note=' 오늘은 시작 시각이 지나 내일로 맞췄어요.';}
    whenNote.textContent='';
    refresh();
    document.getElementById('parse-notice').textContent='지난번 조건으로 추천해요.'+note;
    form.requestSubmit();
  }
  LastConditions.changed=renderAgain;renderAgain();

  // 다른 화면(테마 카드·지도 창·축제)이 값을 바꾼 뒤에도 칩 상태를 맞춘다.
  for(const type of ['input','change','submit'])form.addEventListener(type,()=>setTimeout(refresh));
  document.addEventListener('click',()=>setTimeout(refresh));
  document.getElementById('dialog').addEventListener('close',()=>setTimeout(refresh));
  refresh();
});
