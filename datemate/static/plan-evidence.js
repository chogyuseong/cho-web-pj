const TRANSPORT_NAMES={walk:'도보',transit:'대중교통',car:'자동차',bicycle:'자전거'};
// 구간의 수단. 예전 코스처럼 구간에 수단이 없으면 코스 기본 수단을 쓴다.
function legMode(plan,leg){return leg?.mode??plan.conditions?.transport;}
// 이동 시간의 수단과 근거. 구간 자료(mode·status)만 보고 정하며 없는 정보를 만들지 않는다.
// 수단이 섞이면 이름은 "도보·자동차", countLabel은 "도보 2구간·자동차 1구간"이 된다(서버 travel_mode와 같은 규칙).
function travelMode(plan){
  const legs=plan.legs||[],statuses=new Set(legs.map(leg=>leg.status));
  const modes=legs.length?legs.map(leg=>legMode(plan,leg)):[plan.conditions?.transport],used=[...new Set(modes)];
  const name=used.map(mode=>TRANSPORT_NAMES[mode]||'이동').join('·');
  const basis=plan.conditions?.mode==='demo'?'가상 직선거리 추정':legs.length&&[...statuses].every(s=>s==='api')?'네이버 길찾기':statuses.has('api')?'일부 네이버 길찾기 · 일부 추정':'추정';
  const countLabel=used.length>1?used.map(mode=>`${TRANSPORT_NAMES[mode]||'이동'} ${modes.filter(m=>m===mode).length}구간`).join('·'):name;
  return {name,basis,label:name+' · '+basis,mixed:used.length>1,modes:used,countLabel};
}
// 구간 한 줄의 수단 표시(예: '도보 17분 · 추정', '자동차 12분 · 네이버 길찾기').
// 대중교통은 실제 노선을 조회하지 않는 추정이라 '(지하철·버스 구분 없음)'을 덧붙인다(2026-11-18 사용자 요청: 지하철인지 버스인지 분명히).
// 가정값(시속·대기·요금)은 서버가 구간에 넣는 transit_basis 를 일정 위에 한 번 보여 준다(transitBasisNote). 실제 노선 조회가 붙어
// status==='api' 가 되면 이 덧붙임은 저절로 빠진다. test_leg_modes_ui 가 '· 대중교통 ' 을, test_transit_basis_ui 가 덧붙임을 확인한다.
function legModeLabel(plan,leg){
  const mode=legMode(plan,leg),name=TRANSPORT_NAMES[mode]||'이동';
  const basis=plan.conditions?.mode==='demo'?'가상 추정':leg.status==='api'?'네이버 길찾기':'추정';
  return name+' '+(leg.minutes??'?')+'분 · '+basis+(mode==='transit'&&leg.status!=='api'?' (지하철·버스 구분 없음)':'');
}
// 대중교통 추정 구간이 하나라도 있으면 그 계산 기준 한 줄(없으면 null). 서버 문장(routes.TRANSIT_BASIS)을 쓰고,
// 그 키가 없던 예전에 저장한 코스는 숫자 없이 구분 없음만 말한다(없는 가정값을 화면에서 만들지 않음).
function transitBasisNote(plan){
  const legs=(plan.legs||[]).filter(leg=>legMode(plan,leg)==='transit'&&leg.status!=='api');
  if(!legs.length)return null;
  const basis=legs.find(leg=>leg.transit_basis)?.transit_basis||'지하철·버스를 구분하지 않은 추정이에요.';
  // 구간 줄마다 「길찾기 ▾」(네이버 지도·카카오맵, plan-actions.js routeLine)가 있다. 체험 코스(가상 장소)에는 길찾기가 없어 일반 지도 앱으로 안내한다.
  const where=plan.conditions?.mode==='demo'?'지도 앱':'구간마다 있는 「길찾기 ▾」';
  return node('p','대중교통: '+basis+' 실제 지하철·버스 노선과 요금은 '+where+'에서 확인해 주세요.','hint transit-basis-note');
}
// 이동 합계(분). 서버 decision_summary.travel_minutes(app/recommendation_summary.travel_minutes)를 먼저 쓰고, 없을 때만 같은 식으로 센다:
// 구간(legs) + 행사장으로 가는 축제 구간(festival_visit.leg — legs 밖). 둘을 함께 바꿔야 카드·지도·순서 제안의 '이동 N분'이 맞는다(점검 F9).
function travelMinutes(plan){return plan.decision_summary?.travel_minutes??((plan.legs||[]).reduce((n,x)=>n+(x.minutes||0),0)+(plan.festival_visit?.leg?.minutes||0));}
// 금액 범위를 "23,000원 ~"과 "43,000원" 두 줄로 나눈다. 각 줄 안에서는 줄을 바꾸지 않는다.
function rangeLines(value){
  const box=node('span',undefined,'range-lines');
  if(value==null||value[0]===value[1]){box.append(node('span',range(value),'nowrap'));return box;}
  box.append(node('span',won(value[0])+' ~','nowrap'),node('span',won(value[1]),'nowrap'));
  return box;
}
// 목록을 항목마다 줄바꿈 금지로 감싸 가운뎃점 사이에서만 줄이 바뀌게 한다.
function nowrapList(items,separator=' · '){
  const box=node('span');
  items.forEach((item,i)=>{if(i)box.append(document.createTextNode(separator));box.append(node('span',item,'nowrap'));});
  return box;
}
// 비교 표 위에 붙일 '확실한 차이만' 문장(개선안 2·27). 코스 1을 기준으로, 값이 모두 있을 때만 차이를 말한다.
// 비용: 두 범위가 겹치면 어느 쪽이 싼지 단정하지 않는다. 미확인 비용이 있으면 그 사실을 함께 적는다.
// 도보: 도보 분(walking)이 없는 코스(옛 저장본 등)가 있으면 비교하지 않고 모른다고 적는다. 0분으로 보이지 않는다.
function courseComparisonNotes(items){
  if(items.length<2)return [];
  const base=items[0],notes=[];
  const walk=p=>Number.isFinite(p.walking)?p.walking:null;
  items.slice(1).forEach((p,k)=>{
    const i=k+2,parts=[];
    const [a0,a1]=base.total||[],[b0,b1]=p.total||[];
    if([a0,a1,b0,b1].every(Number.isFinite)){
      if(b1<a0)parts.push(`비용이 확실히 적어요(최대 ${won(b1)} < 코스 1 최소 ${won(a0)})`);
      else if(b0>a1)parts.push(`비용이 확실히 많아요(최소 ${won(b0)} > 코스 1 최대 ${won(a1)})`);
      else if(a0===b0&&a1===b1)parts.push('비용 범위가 같아요');
      else parts.push('비용 범위가 코스 1과 겹쳐 어느 쪽이 싼지 단정할 수 없어요');
    }
    if((p.unknown||[]).some(u=>!u.includes('교통'))||(base.unknown||[]).some(u=>!u.includes('교통')))parts.push('미확인 비용이 있어 빠진 금액이 있어요');
    const wa=walk(base),wb=walk(p);
    if(wa===null||wb===null)parts.push('도보 시간을 모르는 코스가 있어 도보는 비교하지 않았어요');
    else parts.push(wa===wb?'도보 시간이 같아요':wb<wa?`도보 ${wa-wb}분 적어요`:`도보 ${wb-wa}분 많아요`);
    notes.push(`코스 ${i}: `+parts.join(' · '));
  });
  return notes;
}
// 비용 칸 아래 한 줄: 예산과 비교한 상태. 서버의 예산 판정(condition_checks)과 가격 근거만 쓴다.
function budgetFitLabel(p){
  if(budgetUnlimited(p))return '';
  const check=(p.condition_checks||[]).find(c=>c.condition==='budget'&&c.state!=='info');
  const assumed=(p.costs||[]).some(c=>c.price_kind==='planning_assumption');
  if(!check)return '';
  if(check.state==='unmet')return `예산 ${won(Math.max(0,p.total[1]-p.conditions.budget))} 초과`;
  if(check.state==='unknown')return '예산 안인지 모름(미확인 비용)';
  return assumed?'예산 안 · 가정 가격 포함':'예산 안';
}
function optionComparison(items){
  const wrap=node('section',undefined,'option-comparison');wrap.setAttribute('aria-label','옵션 한눈에 비교');
  wrap.append(node('h3','어떤 코스가 더 끌리나요?'));
  const notes=courseComparisonNotes(items);
  if(notes.length){const list=node('ul',undefined,'comparison-notes');notes.forEach(text=>list.append(node('li',text)));wrap.append(list);}
  const scroll=node('div',undefined,'table-scroll'),table=node('table'),caption=node('caption','세 코스 비용·이동 시간 비교','visually-hidden'),thead=node('thead'),head=node('tr'),body=node('tbody');
  // 머리글은 390px에서도 한 줄로 짧게 두고, 뜻(총 이동 시간 · 수단 · 근거)은 접근성 이름과 표 설명에 남긴다.
  [['코스',''],['예상 전체 비용','num'],['이동 시간','num travel-time','총 이동 시간 (수단 · 근거)'],['주요 활동',''],['장소 차이',''],['선택','comparison-choose-head']].forEach(([text,cls,label])=>{const th=node('th',text,cls||undefined);th.scope='col';if(label){th.setAttribute('aria-label',label);th.title=label;}head.append(th);});
  thead.append(head);table.append(caption,thead,body);
  items.forEach((p,i)=>{const row=node('tr');const others=p.places.filter(x=>!items[0].places.some(y=>y.id===x.id)).length;const mode=travelMode(p);
    const course=node('th',`코스 ${i+1}`);course.scope='row';course.append(node('span',p.decision_summary?.title||p.option_purpose||'추천','comparison-course-title'));
    const cost=node('td',undefined,'num');cost.append(rangeLines(p.total));const fit=budgetFitLabel(p);if(fit)cost.append(node('small',fit,'comparison-basis'));
    // "도보 2구간·자동차 1구간 34분": 수단마다 줄을 바꾸지 않고 가운뎃점에서만 바꾼다.
    const time=node('td',undefined,'num'),parts=mode.countLabel.split('·');parts[parts.length-1]+=` ${travelMinutes(p)}분`;
    time.append(nowrapList(parts,'·'),node('small',Number.isFinite(p.walking)?`도보 ${p.walking}분`:'도보 시간 모름','comparison-basis comparison-walk'),node('small',mode.basis,'comparison-basis'));
    const activity=node('td');activity.append(nowrapList([...new Set(p.places.map(placeKind))]));
    row.append(course,cost,time,activity,node('td',i?`코스 1과 ${others}곳 다름`+(p.difference?.composition_changed?` · 활동 ${p.difference.composition_changed}곳 바뀜`:''):'비교 기준'));
    // 마지막 칸 '선택'(2026-11-25 Gemini Canvas 시안): 지금 보는 코스는 표시만, 다른 코스는 「이 코스 보기」 — 위 코스 탭(.plan-option-tabs)을 누른 것과 같다
    // (탭 단추의 click 을 부른다: 고정·선택 기록·다시 그리기를 plan-results.js choose 한 곳에 둔다). 고른 코스는 표 위치에서 바로 보이도록 상세로 스크롤.
    const pick=node('td',undefined,'comparison-choose'),current=typeof selected!=='undefined'&&selected?.id===p.id;
    if(current)pick.append(node('span','현재 보고 있는 코스','comparison-current'));
    else{const go=button('이 코스 보기',()=>{const tab=document.querySelector(`#results .plan-option-tabs > button[data-option="${i+1}"]`);if(tab)tab.click();},'secondary comparison-pick');go.setAttribute('aria-label',`코스 ${i+1} 보기`);pick.append(go);}
    row.append(pick);body.append(row);
  });scroll.append(table);scroll.tabIndex=0;scroll.setAttribute('role','region');scroll.setAttribute('aria-label','코스 비교 표 · 가로로 넘겨 확인');wrap.append(node('p','비용과 이동 시간을 비교해 보세요. 도보·대중교통·자전거는 직선거리로 추정한 시간이고, 자동차는 네이버 길찾기로 조회한 구간만 길찾기로 표시해요. 표는 좌우로 넘길 수 있어요.','hint'),scroll);return wrap;
}
// 확인 상태를 쉬운 말의 항목으로 보여준다. state: ok(확인됨) · check(확인 필요) · info(참고)
// '위치' 줄(2026-11-20): 공공 자료 판정만 보여 준다(app/place_identity.py — 소상공인 상가정보, 행안부 인허가 일반음식점·휴게음식점).
// 예전에는 네이버 지역 검색 결과로 계산한 '위치 확인됨'을 보여 줬는데, 검색 결과에서 만든 판정을 우리 표시로 쓰지 않기로 했다(특약 1.2·1.3).
// 판정은 사진 요청(/media)의 identity 로 온다. 공공 API 가 느려 서버가 '확인 중'(pending)으로 답하면 /identity 를 몇 번 다시 묻는다.
// 판정이 없으면(자료에 없음·키 없음·실패·네이버 검색 장소) 판정 없이 '네이버 지도에서 확인' 링크만 둔다.
// 문구의 '200m'는 app/place_identity.py STORE_RADIUS_M 과 같아야 한다.
const identityViews=new Map(),identityPlaces=new Map(),identityRechecks=new Map();
// 다시 묻는 간격(앞 물음이 끝난 뒤부터, 누적 4초·34초·79초·139초). 상가정보는 몇 초 안에, 인허가는 한 곳에 40~80초씩 차례로 온다
// (2026-11-20 실제 조회). 그 뒤에는 묻지 않고, 다음에 코스를 열 때 저장된 판정을 보여 준다. 테스트가 줄일 수 있게 let 으로 둔다.
let IDENTITY_RECHECK_MS=[4000,30000,45000,60000];
function identityText(identity){
  const ago=identity?.age_days==null?'':identity.age_days===0?' · 오늘 조회':` · ${identity.age_days}일 전 조회`;
  const day=value=>String(value||'').replaceAll('-','.');
  if(identity?.status==='open')return ['ok',`영업 중 · 행안부 인허가 자료(${identity.license_kind||'음식점'}) 기준${ago}. 이름과 도로명 주소가 같은 업소예요.`];
  if(identity?.status==='closed')return ['check',`폐업으로 등록됨${identity.closed_on?`(${day(identity.closed_on)})`:''} · 행안부 인허가 자료(${identity.license_kind||'음식점'}) 기준${ago}. 이름을 바꿔 다시 연 곳일 수 있어요.`];
  if(identity?.status==='located'){
    const month=/^\d{6}$/.test(identity.data_month||'')?`(${identity.data_month.slice(0,4)}년 ${Number(identity.data_month.slice(4))}월 자료)`:'';
    return ['ok',`위치 확인 · 소상공인 상가정보${month} 기준${ago}. 이름이 같은 업소가 200m 안에 한 곳 있어요.`];
  }
  // reason 'unavailable': 공공 API 조회가 실패했다(자료에 없다는 뜻이 아님). 서버는 30분 뒤 이 장소를 다시 볼 때 새로 조회한다(app/place_identity.py RETRY_SECONDS).
  if(!identity?.pending&&identity?.reason==='unavailable')return ['check','공공 자료에 지금 연결하지 못했어요. 나중에 다시 조회해요.'];
  return ['check',identity?.pending?'공공 자료를 확인하고 있어요.':''];
}
function identityEvidence(place){
  identityPlaces.set(place.id,place);
  const identity=identityViews.get(place.id),[state,text]=identityText(identity);
  const item=evidenceItem('위치',state,text);
  item.dataset.identityPlaceId=place.id;item.dataset.identityStatus=identity?.status||'unknown';
  // 링크는 글 칸 안에 이어 붙인다(판정이 없으면 이 링크가 글 칸의 전부다).
  if(typeof placeMapLink==='function'){const map=placeMapLink('네이버 지도에서 확인 ↗',place);map.classList.add('evidence-map-link');item.querySelector('.evidence-text').append(text?' ':'',map);}
  if(identity?.pending)watchIdentity(place);
  return item;
}
function refreshEvidenceCount(item){
  const details=item.closest('details');if(!details)return;
  const pending=details.querySelectorAll('.evidence-list .evidence-check').length,summary=details.querySelector('summary');
  let count=summary?.querySelector('.evidence-summary-count');
  if(!pending){count?.remove();return;}
  if(!count&&summary){count=node('span','','evidence-summary-count');summary.append(count);}
  if(count)count.textContent=`방문 전 확인 ${pending}개`;
}
function showIdentity(place,identity){
  identityViews.set(place.id,identity);
  for(const item of document.querySelectorAll('li[data-identity-place-id]')){
    if(item.dataset.identityPlaceId!==place.id)continue;
    const fresh=identityEvidence(identityPlaces.get(place.id)||place);item.replaceWith(fresh);refreshEvidenceCount(fresh);
  }
}
// 사진 요청(/media)이 준 판정을 받는다(app.js rememberVerifiedMapTarget). '위치' 줄이 화면에 있으면 바로 바꾼다.
function markIdentity(place,identity){
  if(place&&identity)showIdentity(place,identity);
}
// 판정이 '확인 중'인 장소만, 그 장소의 '위치' 줄이 화면에 있는 동안 정해진 횟수만큼 다시 묻는다. 실패하면 조용히 다음 차례로 넘긴다(링크는 이미 있다).
// 끝까지 판정이 없으면 '확인하고 있어요' 문구를 내리고 링크만 남긴다(다음에 코스를 열 때 저장된 판정이 있으면 보인다).
function watchIdentity(place){
  if(identityRechecks.has(place.id))return;
  identityRechecks.set(place.id,true);
  let step=0;
  const shown=()=>[...document.querySelectorAll('li[data-identity-place-id]')].some(item=>item.dataset.identityPlaceId===place.id);
  const next=()=>{
    if(step>=IDENTITY_RECHECK_MS.length){
      identityRechecks.delete(place.id);
      const last=identityViews.get(place.id);
      if(last?.pending)showIdentity(place,{...last,pending:false});
      return;
    }
    setTimeout(async()=>{
      step+=1;
      if(!shown()){identityRechecks.delete(place.id);return;}
      let identity=null;
      try{identity=(await api('/places/'+encodeURIComponent(place.id)+'/identity?mode=real',null,'GET',{timeout:15000})).identity;}catch{}
      if(identity)showIdentity(place,identity);
      if(identity&&!identity.pending){identityRechecks.delete(place.id);return;}
      next();
    },IDENTITY_RECHECK_MS[step]);
  };
  next();
}
// 한국관광공사 TourAPI 의 영업 안내(app/tour_places.py tour_hours, /media 응답의 tour_hours). 관광공사에 제공된 글 그대로이고
// 언제 확인한 정보인지 모르므로 '확인 필요' 상태는 그대로 두고 안내 글과 출처만 덧붙인다.
// 2026-11-24: 쉬는 날 글에서 매주 쉬는 요일을 읽을 수 있으면(서버 tour_hours.closed_days, app/tour_places.rest_weekdays) 그 요일은
// 일정 계산에 넣는다(사용자 결정). 그때만 '휴무 요일은 일정 계산에 반영(관광공사 안내 기준)'을 덧붙인다. 영업 시간은 여전히 넣지 않는다.
const WEEKDAY_NAMES='월화수목금토일';
function tourRestNote(days){
  if(!Array.isArray(days))return '';
  if(!days.length)return ' 연중무휴로 보고 일정을 계산했어요(관광공사 안내 기준).';
  return ` 매주 ${days.map(d=>WEEKDAY_NAMES[d]).join('·')}요일 휴무는 일정 계산에 반영했어요(관광공사 안내 기준).`;
}
function markTourHours(placeId,tour){
  if(!tour||!(tour.hours||tour.rest))return;
  for(const item of document.querySelectorAll('li[data-operating-place-id]')){
    if(item.dataset.operatingPlaceId!==placeId||item.querySelector('.tour-hours'))continue;
    // 안내 글은 줄의 본문 칸(.evidence-text) 안에 넣는다. 줄은 3칸 격자(배지·이름·본문, results.css .evidence-item)라
    // li 에 넷째 자식으로 붙이면 다음 줄의 첫 칸으로 들어가 그 칸을 글 너비만큼 넓힌다 — 배지가 가로로 늘어나고 본문이
    // 한 글자씩 세로로 쌓였다(2026-11-24 사용자 스크린샷). 줄바꿈은 CSS(.evidence-text .tour-hours display:block)가 한다.
    const note=node('span',undefined,'tour-hours');
    note.append(document.createTextNode('한국관광공사 안내: '+[tour.hours,tour.rest&&('쉬는 날 '+tour.rest)].filter(Boolean).join(' · ')+' (언제 확인한 안내인지 알 수 없어요)'+tourRestNote(tour.closed_days)+' '));
    if(tour.source_url)note.append(link('출처 ↗',tour.source_url));
    item.querySelector('.evidence-text').append(note);
  }
}
function evidenceItem(label,state,text){
  const item=node('li',undefined,'evidence-item evidence-'+state);
  item.append(node('span',{ok:'확인됨',check:'확인 필요',info:'참고'}[state],'evidence-badge'),node('strong',label),node('span',text,'evidence-text'));
  return item;
}
// 블로그 글에서 읽은 가격(web_reference)은 더 이상 없다(네이버 검색 API 특약 1.2, app/pricing.py). operator_menu 는 운영자가 확인한 제공 메뉴.
const PRICE_EVIDENCE={planning_assumption:['check','예산을 짜려고 넣은 가정 금액이에요. 실제 가격이 아니에요. 네이버 지도에서 확인해 주세요.'],
  operator_menu:['check','운영자가 확인해 둔 메뉴 가격이에요. 지금 가격은 원문에서 확인해 주세요.'],
  naver_menu:['check','모아 둔 메뉴 가격이에요. 지금 가격은 원문에서 확인해 주세요.'],
  confirmed:['ok','등록된 가격 자료가 있어요.'],estimated:['check','추정한 가격이에요. 실제 가격과 다를 수 있어요.'],unknown:['check','가격을 확인하지 못했어요.']};
function placeEvidencePanel(plan,index){
  const place=plan.places[index],fact=plan.place_evidence?.find(x=>x.place_id===place.id);
  const details=node('details',undefined,'place-evidence'),summary=node('summary','추천 이유 · 정보 확인');details.append(summary);
  details.append(linkedText('p',fact?.reason||plan.reasons?.[index]||'입력 조건으로 비교한 후보','hint'));
  details.append(node('p',fact?.address||place.address||'주소 미확인','hint'));
  // 공공 자료에서 찾은 곳은 '확인 필요'가 많은 까닭을 한 줄로 밝힌다(naver-attribution.js publicDataNote).
  const dataNote=typeof publicDataNote==='function'?publicDataNote(place):null;
  if(dataNote)details.append(dataNote);
  if(fact){
    const list=node('ul',undefined,'evidence-list');list.setAttribute('aria-label','장소 정보 확인 상태');
    list.append(identityEvidence(place));
    const current=fact.operating_current??(fact.operating_age_days!=null&&fact.operating_age_days>=0&&fact.operating_age_days<=90);
    const operating=evidenceItem('영업 정보',current?'ok':'check',(current?'최근 90일 안에 확인한 영업 자료가 있어요.':'최근 영업 정보를 확인하지 못했어요. 방문 전 영업시간·휴무를 확인해 주세요.')+(fact.operating_age_days!=null?` (자료 확인 ${fact.operating_age_days}일 전)`:''));
    // 확인된 자료가 없을 때만, 사진 요청이 한국관광공사 안내를 받아 오면 그 글을 덧붙인다(markTourHours).
    if(!current)operating.dataset.operatingPlaceId=place.id;
    list.append(operating);
    const [state,text]=PRICE_EVIDENCE[fact.price_kind]||['check','가격 근거: '+fact.price_kind];
    list.append(evidenceItem('가격',state,text));
    details.append(list);
    const pending=list.querySelectorAll('.evidence-check').length;
    if(pending)summary.append(node('span',`방문 전 확인 ${pending}개`,'evidence-summary-count'));
  }
  return details;
}
