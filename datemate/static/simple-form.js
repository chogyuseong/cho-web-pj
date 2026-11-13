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

  // 1. 지역: 홈 테마 카드의 동네를 그대로 칩으로 쓰고, 현재 위치와 ‘다른 곳 찾기’(주소 검색·지도)를 함께 둔다.
  const region=group('1. 어디에서 만날까요?',true);
  const areaRow=chipRow('인기 동네'),areaStatus=node('p','','hint area-status');areaStatus.setAttribute('role','status');
  const areaCards=[...document.querySelectorAll('.curation-card[data-preset]')];
  function ready(){if(statusData)return true;toast('장소 정보를 준비 중이에요. 잠시 후 다시 눌러 주세요.');return false;}
  const areaChips=areaCards.map(card=>{const item=chip(card.dataset.preset,()=>{if(!ready())return;applyPresetArea(card);areaStatus.textContent=card.dataset.preset+'을(를) 데이트할 지역으로 골랐어요.';refresh();});item.dataset.area=card.dataset.preset;return item;});
  const here=button('현재 위치',useCurrentLocation,'quick-chip current-location');
  areaRow.append(...areaChips,here);
  form.elements.origin_name.placeholder='위에서 동네를 골라 주세요';
  region.append(areaRow,areaStatus,document.getElementById('origin-location'),node('p','목록에 없는 곳은 ‘다른 곳 찾기’로 주소를 검색하거나 지도에서 골라 주세요. 고른 위치가 코스의 시작 기준이 돼요.','hint'));
  function readPosition(){return new Promise((resolve,reject)=>navigator.geolocation.getCurrentPosition(resolve,reject,{enableHighAccuracy:false,timeout:15000,maximumAge:300000}));}
  async function useCurrentLocation(){
    if(!ready()||here.disabled)return;
    // 위치를 쓰지 못하면 이유를 알리고 기존 지도 창을 연다.
    const fallback=text=>{areaStatus.textContent=text+' 지도에서 데이트할 지역을 골라 주세요.';openLocationPicker('origin');};
    if(!navigator.geolocation){fallback('이 브라우저에서는 현재 위치를 쓸 수 없어요.');return;}
    here.disabled=true;areaStatus.textContent='현재 위치를 확인하고 있어요…';
    try{
      let position;
      try{position=await readPosition();}
      catch(error){fallback(error?.code===1?'위치 권한이 허용되지 않았어요.':'현재 위치를 확인하지 못했어요.');return;}
      const lat=position.coords.latitude,lon=position.coords.longitude;
      let data=null;
      try{data=await api('/locations/region',{lat,lon});}catch{}
      if(data?.status!=='ok'||!data.region){fallback(data?.status==='outside'?'현재 위치가 국내가 아니에요.':'현재 위치의 시·도를 확인하지 못했어요.');return;}
      // 출발지 이름은 시·도로 시작한다(서버의 시·도·주소 일치 검증).
      const label=String(data.label||'').trim();
      applyArea(data.region,{name:(regionFromAddress(label)===data.region?label:data.region)+' · 현재 위치',lat,lon});
      areaStatus.textContent='현재 위치('+form.elements.origin_name.value.replace(/ · 현재 위치$/,'')+')를 데이트할 지역으로 골랐어요.';
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
  function choices(kind,section,label,items,box,input){
    const row=chipRow(label);
    const chips=items.map(item=>{const own=chip(item.label,()=>{manual[kind]=false;item.apply();refresh();});own.item=item;return own;});
    const direct=chip('직접',()=>{manual[kind]=true;refresh();input.focus();});
    row.append(...chips,direct);section.append(row,box);
    return {chips,direct,box};
  }
  const dateField=field('날짜');
  const dates=choices('date',dateField,'방문 날짜',[['오늘',0],['내일',1],['이번 토요일',null]].map(([label,offset])=>({label,value:()=>dayAfter(offset??(6-new Date().getDay()+7)%7),apply(){setValue('visit_date',this.value());dateNote.textContent=fitTimeToToday();}})),take('visit_date'),form.elements.visit_date);
  const dateNote=node('p','','hint date-note');dateNote.setAttribute('role','status');dateField.append(dateNote);
  const timeField=field('시간대'),timeBox=node('div',undefined,'field-grid');timeBox.append(take('start'),take('end'));
  const timeWindows=[['하루 종일 11–19','11:00','19:00'],['점심부터 11–17','11:00','17:00'],['오후 13–19','13:00','19:00'],['저녁 17–22','17:00','22:00']].map(([label,start,end])=>({label,start,end,value:()=>start+'–'+end,apply(){setValue('start',start);setValue('end',end);}}));
  const times=choices('time',timeField,'시간대',timeWindows,timeBox,form.elements.start);
  const budgetField=field('전체 예산');
  const budgets=choices('budget',budgetField,'전체 예산',[30000,50000,100000,150000].map(amount=>({label:amount/10000+'만',value:()=>String(amount),apply(){setValue('budget',amount);}})),take('budget'),form.elements.budget);
  budgetField.append(node('p','두 사람 합계예요. 인원을 바꾸면 해당 인원 전체의 예산으로 계산해요.','hint'));
  const preview=document.querySelector('.price-input-preview');if(preview)budgetField.append(preview);
  const rest=field('인원 · 장소 수 · 이동'),restGrid=node('div',undefined,'field-grid');
  for(const name of ['people','count','transport'])restGrid.append(take(name));
  rest.append(restGrid);
  // 오늘인데 기본(또는 고른) 시작 시각이 지났으면 아직 가능한 다음 시간대로, 없으면 내일로 맞춘다.
  function fitTimeToToday(){
    if(!startPassed(form.elements.start.value))return '';
    const next=timeWindows.find(item=>!startPassed(item.start));
    if(next){next.apply();return `오늘은 ${form.elements.start.value} 이후로 맞췄어요.`;}
    setValue('visit_date',dayAfter(1));return '오늘은 시작 시각이 지나 내일로 맞췄어요.';
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
  function budgetText(value){const n=Number(value);if(value===''||!Number.isFinite(n))return '예산 미정';return n>=10000&&n%10000===0?n/10000+'만 원':n.toLocaleString('ko-KR')+'원';}
  const transportText=value=>[...form.elements.transport.options].find(option=>option.value===value)?.textContent||value;
  function sync(set,kind,current){
    const match=set.chips.find(item=>item.item.value()===current);
    for(const item of set.chips)item.setAttribute('aria-pressed',String(item===match&&!manual[kind]));
    const direct=manual[kind]||!match;
    set.direct.setAttribute('aria-pressed',String(direct));set.box.hidden=!direct;
  }
  function refresh(){
    const f=form.elements,origin=locationState.origin;
    for(const item of areaChips){const card=areaCards.find(c=>c.dataset.preset===item.dataset.area);
      item.setAttribute('aria-pressed',String(Boolean(origin&&origin.name===card.dataset.origin&&Math.abs(origin.lat-Number(card.dataset.lat))<1e-6&&Math.abs(origin.lon-Number(card.dataset.lon))<1e-6)));}
    sync(dates,'date',f.visit_date.value);sync(times,'time',f.start.value+'–'+f.end.value);sync(budgets,'budget',f.budget.value);
    for(const item of times.chips){const passed=startPassed(item.item.start);item.disabled=passed;item.title=passed?'오늘은 이미 시작 시각이 지났어요':'';}
    const parts=[`${f.start.value}–${f.end.value}`,`${f.people.value}명`,budgetText(f.budget.value),`${f.count.value}곳`,transportText(f.transport.value)];
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
    return [area,`${saved.start}–${saved.end}`,`${saved.people}명`,budgetText(saved.budget),`${saved.count}곳`,transportText(saved.transport)].join(' · ');
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
    let note='';
    if(startPassed(saved.start)){setValue('visit_date',dayAfter(1));note=' 오늘은 시작 시각이 지나 내일로 맞췄어요.';}
    manual.date=manual.time=manual.budget=false;refresh();
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
