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
  // 구간 줄마다 「네이버 지도 대중교통 길찾기」 링크가 있다(plan-actions.js naverDirectionsUrl). 가상 데모에는 없어 장소 카드 링크로 안내한다.
  const where=plan.conditions?.mode==='demo'?'장소 카드의 「도착지 지도·길찾기 확인」':'구간마다 있는 「네이버 지도 대중교통 길찾기」';
  return node('p','대중교통: '+basis+' 실제 지하철·버스 노선과 요금은 '+where+'에서 확인해 주세요.','hint transit-basis-note');
}
function travelMinutes(plan){return plan.decision_summary?.travel_minutes??plan.legs.reduce((n,x)=>n+(x.minutes||0),0);}
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
  [['코스',''],['예상 전체 비용','num'],['이동 시간','num travel-time','총 이동 시간 (수단 · 근거)'],['주요 활동',''],['장소 차이','']].forEach(([text,cls,label])=>{const th=node('th',text,cls||undefined);th.scope='col';if(label){th.setAttribute('aria-label',label);th.title=label;}head.append(th);});
  thead.append(head);table.append(caption,thead,body);
  items.forEach((p,i)=>{const row=node('tr');const others=p.places.filter(x=>!items[0].places.some(y=>y.id===x.id)).length;const mode=travelMode(p);
    const course=node('th',`코스 ${i+1}`);course.scope='row';course.append(node('span',p.decision_summary?.title||p.option_purpose||'추천','comparison-course-title'));
    const cost=node('td',undefined,'num');cost.append(rangeLines(p.total));const fit=budgetFitLabel(p);if(fit)cost.append(node('small',fit,'comparison-basis'));
    // "도보 2구간·자동차 1구간 34분": 수단마다 줄을 바꾸지 않고 가운뎃점에서만 바꾼다.
    const time=node('td',undefined,'num'),parts=mode.countLabel.split('·');parts[parts.length-1]+=` ${travelMinutes(p)}분`;
    time.append(nowrapList(parts,'·'),node('small',Number.isFinite(p.walking)?`도보 ${p.walking}분`:'도보 시간 모름','comparison-basis comparison-walk'),node('small',mode.basis,'comparison-basis'));
    const activity=node('td');activity.append(nowrapList([...new Set(p.places.map(placeKind))]));
    row.append(course,cost,time,activity,node('td',i?`코스 1과 ${others}곳 다름`+(p.difference?.composition_changed?` · 활동 ${p.difference.composition_changed}곳 바뀜`:''):'비교 기준'));body.append(row);
  });scroll.append(table);scroll.tabIndex=0;scroll.setAttribute('role','region');scroll.setAttribute('aria-label','코스 비교 표 · 가로로 넘겨 확인');wrap.append(node('p','비용과 이동 시간을 비교해 보세요. 도보·대중교통·자전거는 직선거리로 추정한 시간이고, 자동차는 네이버 길찾기로 조회한 구간만 길찾기로 표시해요. 표는 좌우로 넘길 수 있어요.','hint'),scroll);return wrap;
}
// 확인 상태를 쉬운 말의 항목으로 보여준다. state: ok(확인됨) · check(확인 필요) · info(참고)
// '위치' 확인(2026-11-19 규칙 변경): 예전에는 늘 '같은 지점인지 확인하지 못했어요'로 고정이었다.
// 사진 요청(/media)이 네이버 지도에서 이름이 같고 400m 안·같은 시·도의 업체 하나를 찾으면(app/menus.py identified)
// naver_place_id_verified 가 오고, app.js rememberVerifiedMapTarget 이 지도 링크를 그 업체로 바꾼다. 그때 이 줄도 '확인됨'으로 바꾼다.
// 사진 요청은 카드가 화면에 가까워질 때 가므로, 처음에는 '확인 필요'로 그렸다가 확인되면 markIdentityVerified 가 바꾼다.
const IDENTITY_UNVERIFIED='등록된 주소로 지도 위치를 찾았어요. 같은 지점인지는 확인하지 못했으니 지도 링크에서 확인해 주세요.';
const IDENTITY_VERIFIED='네이버 지도에서 이름이 같고 400m 안에 있는 업체 하나를 찾아 연결했어요. 지도 링크가 그 업체로 열려요.';
function identityEvidence(place){
  const verified=place.naver_place_id_verified===true||(typeof verifiedMapTargets!=='undefined'&&verifiedMapTargets.has(place.id));
  const item=evidenceItem('위치',verified?'ok':'check',verified?IDENTITY_VERIFIED:IDENTITY_UNVERIFIED);
  item.dataset.identityPlaceId=place.id;
  return item;
}
function markIdentityVerified(placeId){
  for(const item of document.querySelectorAll('li[data-identity-place-id]')){
    if(item.dataset.identityPlaceId!==placeId||item.classList.contains('evidence-ok'))continue;
    const fresh=evidenceItem('위치','ok',IDENTITY_VERIFIED);fresh.dataset.identityPlaceId=placeId;item.replaceWith(fresh);
  }
}
function evidenceItem(label,state,text){
  const item=node('li',undefined,'evidence-item evidence-'+state);
  item.append(node('span',{ok:'확인됨',check:'확인 필요',info:'참고'}[state],'evidence-badge'),node('strong',label),node('span',text,'evidence-text'));
  return item;
}
const PRICE_EVIDENCE={web_reference:['check','블로그 글에 나온 가격이에요. 지금 가격인지는 확인하지 못했어요.'],
  planning_assumption:['check','예산을 짜려고 넣은 가정 금액이에요. 실제 메뉴 가격이 아니에요.'],
  naver_menu:['check','모아 둔 메뉴 가격이에요. 지금 가격은 원문에서 확인해 주세요.'],
  confirmed:['ok','등록된 가격 자료가 있어요.'],estimated:['check','추정한 가격이에요. 실제 가격과 다를 수 있어요.'],unknown:['check','가격을 확인하지 못했어요.']};
function placeEvidencePanel(plan,index){
  const place=plan.places[index],fact=plan.place_evidence?.find(x=>x.place_id===place.id);
  const details=node('details',undefined,'place-evidence'),summary=node('summary','추천 이유 · 정보 확인');details.append(summary);
  details.append(linkedText('p',fact?.reason||plan.reasons?.[index]||'입력 조건으로 비교한 후보','hint'));
  details.append(node('p',fact?.address||place.address||'주소 미확인','hint'));
  if(fact){
    const list=node('ul',undefined,'evidence-list');list.setAttribute('aria-label','장소 정보 확인 상태');
    list.append(identityEvidence(place));
    const current=fact.operating_current??(fact.operating_age_days!=null&&fact.operating_age_days>=0&&fact.operating_age_days<=90);
    list.append(evidenceItem('영업 정보',current?'ok':'check',(current?'최근 90일 안에 확인한 영업 자료가 있어요.':'최근 영업 정보를 확인하지 못했어요. 방문 전 영업시간·휴무를 확인해 주세요.')+(fact.operating_age_days!=null?` (자료 확인 ${fact.operating_age_days}일 전)`:'')));
    list.append(evidenceItem('블로그 언급','info',fact.blog_match?'이번에 찾은 코스 블로그 글에 이 장소가 나와요. 평점이나 방문자 수를 확인한 것은 아니에요.':'이번에 찾은 블로그 글에는 나오지 않았어요. 입력한 조건에 맞춰 함께 추천한 곳이에요.'));
    const [state,text]=PRICE_EVIDENCE[fact.price_kind]||['check','가격 근거: '+fact.price_kind];
    list.append(evidenceItem('가격',state,text));
    details.append(list);
    const pending=list.querySelectorAll('.evidence-check').length;
    if(pending)summary.append(node('span',`방문 전 확인 ${pending}개`,'evidence-summary-count'));
    for(const q of fact.price_sources){details.append(sourceLinks('가격이 나온 블로그 글 보기 · '+(q.posted_at||'작성일 미확인'),q.source,place.name+' 메뉴 가격'),node('p',q.evidence||'','hint'));}
  }
  return details;
}
