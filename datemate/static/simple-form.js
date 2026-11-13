/* One short needs form; keep defaults in the form for existing API integrations.
   사용자가 꼭 정할 것은 지역뿐이다. 날짜·시간·예산·인원·장소 수·교통은 기본값을 요약 한 줄로 보여 주고 ‘바꾸기’ 안에서 칩으로 고친다. */
document.addEventListener('DOMContentLoaded',()=>{
  const form=document.getElementById('conditions');
  const retained=document.createElement('div');retained.hidden=true;retained.id='automatic-plan-settings';
  while(form.firstChild)retained.append(form.firstChild);
  form.append(retained);form.classList.add('simple-plan-form');
  const again=node('div',undefined,'last-conditions');again.hidden=true;
  const intro=node('p','데이트할 지역만 고르면 바로 추천받을 수 있어요. 날짜·시간·예산은 기본값으로 채워 두었고, 필요하면 바꿀 수 있어요.','simple-form-intro');
  form.append(again,intro,button('내가 결정한 코스 다시 보기',()=>PlanningStudy.showDecisions(),'secondary saved-decisions'));
  function group(title,required=false){const section=node('fieldset',undefined,'simple-form-group'),legend=node('legend',title);if(required)legend.append(node('span','필수','field-requirement'));section.append(legend);form.append(section);return section;}
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

  // 1. 지역: 홈 테마 카드의 동네를 그대로 칩으로 쓰고, 현재 위치·지역 칸 검색·지도에서 고르기를 함께 둔다.
  const region=group('1. 어디에서 만날까요?',true);
  const areaRow=chipRow('인기 동네'),areaStatus=node('p','','hint area-status');areaStatus.setAttribute('role','status');
  const areaCards=[...document.querySelectorAll('.curation-card[data-preset]')];
  function ready(){if(statusData)return true;toast('장소 정보를 준비 중이에요. 잠시 후 다시 눌러 주세요.');return false;}
  // 화면이 뜬 직후 서버 상태를 받기 전에 누른 동네는 버리지 않고, 준비되는 대로(최대 30초) 마지막으로 누른 것을 적용한다.
  let pendingArea=null,pendingTimer=null;
  function whenReady(action){
    if(statusData){action();return;}
    pendingArea=action;areaStatus.textContent='장소 정보를 준비하고 있어요. 곧 적용할게요…';
    if(pendingTimer)return;
    let waited=0;
    pendingTimer=setInterval(()=>{
      waited+=100;
      if(!statusData&&waited<30000)return;
      clearInterval(pendingTimer);pendingTimer=null;
      const run=pendingArea;pendingArea=null;
      if(statusData)run();else areaStatus.textContent='장소 정보를 불러오지 못했어요. 새로고침한 뒤 다시 눌러 주세요.';
    },100);
  }
  const areaChips=areaCards.map(card=>{const item=chip(card.dataset.preset,()=>whenReady(()=>{applyPresetArea(card);areaStatus.textContent=card.dataset.preset+'을(를) 데이트할 지역으로 골랐어요.';refresh();}));item.dataset.area=card.dataset.preset;return item;});
  const here=button('현재 위치',useCurrentLocation,'quick-chip current-location');
  areaRow.append(...areaChips,here);
  const locationChoice=node('div',undefined,'location-choice');locationChoice.hidden=true;
  region.append(areaRow,areaStatus,locationChoice,document.getElementById('origin-location'),node('p','목록에 없는 곳은 위 칸에 동네·역·주소를 입력해 검색하거나 ‘지도에서 고르기’로 골라 주세요. 고른 위치가 코스의 시작 기준이 돼요.','hint'));

  // 1-1. ‘데이트할 지역’ 칸에서 바로 검색한다. 입력 중 자동 호출은 하지 않는다(서버가 사용자별로 1초에 한 번만 받는다).
  const originInput=form.elements.origin_name,originHost=document.getElementById('origin-location');
  const originLabel=originInput.closest('label'),mapButton=originHost.querySelector('button');
  originInput.readOnly=false;originInput.maxLength=200;originInput.autocomplete='off';originInput.spellcheck=false;
  originInput.placeholder='동네·역·주소로 검색';
  const searchRow=node('div',undefined,'origin-search');
  const searchButton=button('검색',()=>searchOrigin(),'secondary origin-search-button');
  originLabel.before(searchRow);searchRow.append(originLabel,searchButton);
  const searchStatus=node('p','','hint origin-search-status');searchStatus.id='origin-search-status';searchStatus.setAttribute('role','status');
  const resultList=node('ul',undefined,'origin-search-results');resultList.id='origin-search-results';resultList.setAttribute('role','listbox');resultList.setAttribute('aria-label','지역 검색 결과');resultList.hidden=true;
  originInput.setAttribute('role','combobox');originInput.setAttribute('aria-autocomplete','list');originInput.setAttribute('aria-expanded','false');
  originInput.setAttribute('aria-controls',resultList.id);originInput.setAttribute('aria-describedby',searchStatus.id);
  mapButton.before(searchStatus,resultList);
  // 목록을 누르는 동안 입력칸의 포커스를 잃지 않게 한다(잃으면 입력 중인 글이 원래 지역으로 되돌아간다).
  resultList.addEventListener('mousedown',event=>event.preventDefault());
  let searchResults=[],activeIndex=-1,searching=false,appliedOrigin=locationState.origin;
  const selectedName=()=>locationState.origin?.name||'';
  function regionOf(point){return regionFromAddress(point.road_address)||regionFromAddress(point.jibun_address)||regionFromAddress(point.name);}
  // 출발지 이름은 시·도로 시작해야 서버의 시·도·주소 일치 검증을 통과한다.
  function originNameOf(point,area){const address=String(point.road_address||point.jibun_address||point.name||'').trim();return regionFromAddress(address)===area?address:area+' '+address;}
  function closeResults(){resultList.hidden=true;resultList.replaceChildren();searchResults=[];activeIndex=-1;originInput.setAttribute('aria-expanded','false');originInput.removeAttribute('aria-activedescendant');}
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
        item.append(node('strong',point.place_name),node('span',point.road_address||point.jibun_address||'주소 정보 없음','hint origin-search-address'));
      }else{
        item.append(node('strong',point.road_address||point.name));
        if(point.jibun_address&&point.jibun_address!==point.road_address)item.append(node('span','지번: '+point.jibun_address,'hint'));
      }
      if(!known){item.setAttribute('aria-disabled','true');item.append(node('span','시·도를 알 수 없어 고를 수 없어요','hint origin-search-unknown'));}
      item.addEventListener('click',()=>chooseResult(i));
      resultList.append(item);
    });
    resultList.hidden=false;originInput.setAttribute('aria-expanded','true');
    const usable=results.filter(regionOf).length;
    searchStatus.textContent=usable?`검색 결과 ${results.length}곳이에요. 하나를 누르거나 위아래 화살표로 고른 뒤 Enter 를 눌러 주세요.`:'시·도를 알 수 없는 결과뿐이에요. 시·도 이름을 붙여(예: 부산 광안리) 다시 검색하거나 ‘지도에서 고르기’를 이용해 주세요.';
  }
  async function searchOrigin(){
    if(searching)return;
    const query=originInput.value.trim();
    if(query.length<2){closeResults();searchStatus.textContent='동네·역·주소를 두 글자 이상 입력하고 검색해 주세요.';originInput.focus();return;}
    // disabled 로 바꾸면 버튼에 있던 포커스가 사라져 입력한 검색어가 되돌려지므로 aria-disabled 만 쓴다.
    searching=true;searchButton.setAttribute('aria-disabled','true');closeResults();searchStatus.textContent=`‘${query}’을(를) 찾고 있어요…`;
    try{const data=await api('/locations/search',{query});showResults(data.results||[],data.message);}
    catch(error){searchStatus.textContent=(error.message||'검색하지 못했어요.')+' 잠시 후 다시 검색하거나 ‘지도에서 고르기’를 이용해 주세요.';}
    finally{searching=false;searchButton.removeAttribute('aria-disabled');}
  }
  function chooseResult(index){
    const point=searchResults[index];if(!point)return;
    const area=regionOf(point);
    if(!area){setActive(index);searchStatus.textContent='이 결과는 시·도를 알 수 없어 고를 수 없어요. 다른 결과를 고르거나 시·도 이름을 붙여 다시 검색해 주세요.';return;}
    applyArea(area,{name:originNameOf(point,area),lat:point.lat,lon:point.lon});
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

  // 2. 나머지 조건은 요약 한 줄로 접는다. 날짜는 지나치기 쉬워 맨 앞에 요일과 함께 둔다.
  const summary=node('div',undefined,'quick-summary'),summaryText=node('p',undefined,'quick-summary-text');
  summaryText.id='quick-summary-text';
  const toggle=button('바꾸기',()=>setOpen(panel.hidden),'secondary condition-toggle');
  toggle.setAttribute('aria-expanded','false');toggle.setAttribute('aria-controls','condition-details');toggle.setAttribute('aria-describedby','quick-summary-text');
  summary.append(summaryText,toggle);form.append(summary);
  const panel=node('div',undefined,'condition-details');panel.id='condition-details';panel.hidden=true;form.append(panel);
  function setOpen(open){panel.hidden=!open;toggle.setAttribute('aria-expanded',String(open));toggle.textContent=open?'접기':'바꾸기';}
  function field(title){const section=node('fieldset',undefined,'quick-field');section.append(node('legend',title));panel.append(section);return section;}
  // ‘직접’을 누르거나 값이 칩과 맞지 않을 때만 기존 입력칸을 보여 준다.
  const manual={date:false,time:false,budget:false};
  // 마지막으로 누른 칩. 값이 같은 칩이 둘이면(금요일의 ‘내일’과 ‘이번 토요일’) 누른 쪽을 눌린 상태로 둔다.
  const pressed={date:null,time:null,budget:null};
  // 칩을 누르는 즉시 정해진 값을 바로 아래(role=status)에 알린다. 다른 날·시간대로 맞춘 경우는 눈에 띄게 표시한다.
  function announce(set,text,adjusted=false){set.note.textContent=text;set.note.classList.toggle('is-adjusted',adjusted);}
  function choices(kind,section,label,items,box,input,describe,onDirect){
    const row=chipRow(label),note=node('p','','hint choice-note '+kind+'-note');note.setAttribute('role','status');
    const set={box,note};
    set.chips=items.map(item=>{const own=chip(item.label,()=>{manual[kind]=false;pressed[kind]=own;const adjustment=item.apply();refresh();const [text,adjusted]=describe(adjustment);announce(set,text,adjusted);});own.item=item;return own;});
    set.direct=chip('직접',()=>{manual[kind]=true;pressed[kind]=null;onDirect?.();refresh();announce(set,'아래 칸에 직접 입력해 주세요.');input.focus();});
    row.append(...set.chips,set.direct);section.append(row,note,box);
    return set;
  }
  const dateField=field('날짜');
  const dates=choices('date',dateField,'방문 날짜',[['오늘',0],['내일',1],['이번 토요일',null]].map(([label,offset])=>({label,value:()=>dayAfter(offset??(6-new Date().getDay()+7)%7),apply(){setValue('visit_date',this.value());return fitTimeToToday();}})),take('visit_date'),form.elements.visit_date,adjustment=>{
    const day=dateText(form.elements.visit_date.value);
    if(adjustment?.date)return [`오늘은 고를 수 있는 시간대가 모두 지나 ${day}로 맞췄어요.`,true];
    if(adjustment?.time)return [`${day}로 정했어요. 오늘은 ${adjustment.from} 시작이 이미 지나 시간대를 ${adjustment.time}에 맞췄어요.`,true];
    return [`${day}로 정했어요.`,false];
  });
  form.elements.visit_date.addEventListener('change',()=>{if(manual.date)announce(dates,form.elements.visit_date.value?`${dateText(form.elements.visit_date.value)}로 정했어요.`:'날짜를 정해 주세요.');});
  const timeField=field('시간대'),timeBox=node('div',undefined,'field-grid');timeBox.append(take('start'),take('end'));
  const timeWindows=[['하루 종일 11–19','11:00','19:00'],['점심부터 11–17','11:00','17:00'],['오후 13–19','13:00','19:00'],['저녁 17–22','17:00','22:00']].map(([label,start,end])=>({label,start,end,value:()=>start+'–'+end,apply(){setValue('start',start);setValue('end',end);}}));
  const times=choices('time',timeField,'시간대',timeWindows,timeBox,form.elements.start,()=>[`시간대를 ${form.elements.start.value}–${form.elements.end.value}에 맞췄어요.`,false]);
  const budgetField=field('전체 예산');
  const budgetItems=[...[30000,50000,100000,150000].map(amount=>({label:amount/10000+'만',value:()=>String(amount),apply(){setUnlimited(false);setValue('budget',amount);}})),
    {label:'예산 무관',value:()=>'unlimited',apply(){setUnlimited(true);}}];
  const budgets=choices('budget',budgetField,'전체 예산',budgetItems,take('budget'),form.elements.budget,()=>[unlimited?.checked?'예산 무관으로 정했어요. 예산 상한 없이 코스를 찾아요.':`전체 예산을 ${budgetText(form.elements.budget.value)}에 맞췄어요.`,false],()=>setUnlimited(false));
  budgetField.append(node('p','두 사람 합계예요. 인원을 바꾸면 해당 인원 전체의 예산으로 계산해요.','hint'));
  const preview=document.querySelector('.price-input-preview');if(preview)budgetField.append(preview);
  const rest=field('인원 · 장소 수 · 이동'),restGrid=node('div',undefined,'field-grid');
  for(const name of ['people','count','transport'])restGrid.append(take(name));
  rest.append(restGrid);
  // 오늘인데 기본(또는 고른) 시작 시각이 지났으면 아직 가능한 다음 시간대로, 없으면 내일로 맞춘다. 맞춘 내용을 돌려준다.
  function fitTimeToToday(){
    const from=form.elements.start.value;
    if(!startPassed(from))return null;
    const next=timeWindows.find(item=>!startPassed(item.start));
    if(next){next.apply();manual.time=false;return {from,time:next.value()};}
    setValue('visit_date',dayAfter(1));return {date:true};
  }
  if(form.elements.visit_date.value===today()&&form.elements.start.value==='11:00'&&form.elements.end.value==='19:00'){
    const next=timeWindows.find(item=>!startPassed(item.start));
    if(startPassed('11:00')){if(next){form.elements.start.value=next.start;form.elements.end.value=next.end;}else form.elements.visit_date.value=dayAfter(1);}
  }
  function dateText(value){
    if(!value)return '날짜를 정해 주세요';
    const d=new Date(value+'T00:00');if(Number.isNaN(d.getTime()))return value;
    const relative=value===today()?'오늘 ':value===dayAfter(1)?'내일 ':'';
    return `${relative}${d.getMonth()+1}월 ${d.getDate()}일 (${'일월화수목금토'[d.getDay()]})`;
  }
  function budgetText(value,free=false){if(free)return '예산 무관';const n=Number(value);if(value===''||!Number.isFinite(n))return '예산 미정';return n>=10000&&n%10000===0?n/10000+'만 원':n.toLocaleString('ko-KR')+'원';}
  const transportText=value=>[...form.elements.transport.options].find(option=>option.value===value)?.textContent||value;
  function sync(set,kind,current){
    const last=pressed[kind];
    const match=last&&set.chips.includes(last)&&last.item.value()===current?last:set.chips.find(item=>item.item.value()===current);
    for(const item of set.chips)item.setAttribute('aria-pressed',String(item===match&&!manual[kind]));
    const direct=manual[kind]||!match;
    set.direct.setAttribute('aria-pressed',String(direct));set.box.hidden=!direct;
  }
  function refresh(){
    const f=form.elements,origin=locationState.origin;
    syncOrigin();
    for(const item of areaChips){const card=areaCards.find(c=>c.dataset.preset===item.dataset.area);
      item.setAttribute('aria-pressed',String(Boolean(origin&&origin.name===card.dataset.origin&&Math.abs(origin.lat-Number(card.dataset.lat))<1e-6&&Math.abs(origin.lon-Number(card.dataset.lon))<1e-6)));}
    // 예산 무관을 켠 채 금액을 직접 고치면 금액이 우선이다.
    if(unlimited?.checked&&manual.budget)setUnlimited(false);
    sync(dates,'date',f.visit_date.value);sync(times,'time',f.start.value+'–'+f.end.value);sync(budgets,'budget',unlimited?.checked?'unlimited':f.budget.value);
    for(const item of times.chips){const passed=startPassed(item.item.start);item.disabled=passed;item.title=passed?'오늘은 이미 시작 시각이 지났어요':'';}
    const parts=[`${f.start.value}–${f.end.value}`,`${f.people.value}명`,budgetText(f.budget.value,unlimited?.checked),`${f.count.value}곳`,transportText(f.transport.value)];
    const text=dateText(f.visit_date.value)+' · '+parts.join(' · ');
    if(summaryText.dataset.text!==text){summaryText.dataset.text=text;summaryText.replaceChildren(node('span','기본 조건','quick-summary-label'),node('strong',dateText(f.visit_date.value)),document.createTextNode(' · '+parts.join(' · ')));}
  }
  // 숨긴 입력칸 값이 잘못되면 펼쳐서 바로 고칠 수 있게 한다.
  form.addEventListener('invalid',event=>{
    if(!panel.contains(event.target))return;
    setOpen(true);
    for(const [kind,set] of [['date',dates],['time',times],['budget',budgets]])if(set.box.contains(event.target))manual[kind]=true;
    refresh();
  },true);

  const preference=group('2. 어떤 하루를 원하세요? (선택)');
  const request=take('request');request.firstChild.textContent='원하는 활동이나 피하고 싶은 것을 알려주세요';
  form.elements.request.placeholder='예: 카페 투어 하고 싶어요 / 전시 보고 산책, 실내 위주로 / 매운 음식은 제외';
  const ideas=node('div',undefined,'simple-activity-ideas');ideas.setAttribute('aria-label','원하는 활동 입력 예시');
  for(const [label,text] of [['카페','카페 투어'],['맛집','맛집 탐방'],['산책','산책'],['전시','전시 관람'],['체험','공방 체험']]){
    ideas.append(button(label,()=>{const input=form.elements.request;input.value=input.value.trim()?input.value.trim()+', '+text:text;input.dispatchEvent(new Event('input',{bubbles:true}));input.focus();},'secondary'));
  }
  preference.append(ideas,request,document.getElementById('parse-notice'));
  const optional=node('details',undefined,'simple-extra-options');optional.append(node('summary','식사·실내외·이동 세부 설정 (선택)'));
  const extras=node('div',undefined,'field-grid');
  extras.append(take('setting'));
  optional.append(extras,take('include_meal'));
  const feedback=take('use_feedback');if(feedback)optional.append(feedback);
  const buffer=node('label','이동 구간별 여유시간'),bufferSelect=node('select');bufferSelect.name='transition_buffer_minutes';
  for(const [value,title] of [[0,'기본 · 추가 여유 없음'],[5,'구간마다 5분 여유'],[10,'느긋하게 · 구간마다 10분 여유']]){const option=node('option',title);option.value=value;bufferSelect.append(option);}buffer.append(bufferSelect);optional.append(buffer);
  const hard=retained.querySelector('.experience-controls details');
  if(hard)optional.append(hard);
  const limits=node('details');limits.append(node('summary','이동 제한·가격 추정 설정'));
  for(const name of ['max_leg','max_walk','allow_price_estimates']){const label=take(name);if(label)limits.append(label);}
  optional.append(limits);
  PlanningStudy.mount(optional);
  form.append(optional,document.getElementById('submit-plan'),node('p','조건에 맞는 후보가 부족하면 범위를 넓혀 찾고, 바뀐 조건을 알려드려요. 비용·이동 시간은 추정이 포함될 수 있어요.','hint'));
  // These are automatic planning defaults, not additional choices the user has to make.
  form.elements.trust_mode.value='balanced';form.elements.mbti.value='';form.elements.use_mbti.checked=false;
  retained.querySelectorAll('[required]').forEach(input=>input.required=false);

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
  function useSaved(saved){
    if(!ready())return;
    if(document.getElementById('submit-plan').disabled){toast('코스를 찾는 중이에요. 끝난 뒤 다시 눌러 주세요.');return;}
    applyArea(saved.region,saved.origin);
    setValue('visit_date',today());
    for(const name of ['start','end','budget','people','count','transport'])setValue(name,saved[name]);
    setUnlimited(saved.budget_unlimited===true);
    let note='';
    if(startPassed(saved.start)){setValue('visit_date',dayAfter(1));note=' 오늘은 시작 시각이 지나 내일로 맞췄어요.';}
    manual.date=manual.time=manual.budget=false;
    for(const set of [dates,times,budgets])announce(set,'');
    refresh();
    document.getElementById('parse-notice').textContent='지난번 조건으로 추천해요.'+note;
    form.requestSubmit();
  }
  LastConditions.changed=renderAgain;renderAgain();

  // 다른 화면(테마 카드·지도 창·축제)이 값을 바꾼 뒤에도 요약과 칩 상태를 맞춘다.
  for(const type of ['input','change','submit'])form.addEventListener(type,()=>setTimeout(refresh));
  document.addEventListener('click',()=>setTimeout(refresh));
  document.getElementById('dialog').addEventListener('close',()=>setTimeout(refresh));
  refresh();
});
