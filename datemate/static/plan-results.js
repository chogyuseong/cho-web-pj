// 결과 화면은 사용자 흐름 순서대로 DOM을 붙인다(보이는 순서 = 탭 순서 = 낭독 순서).
// 조건 안내 → 코스 카드 → 비교 표 → 선택한 코스 → 지도(모바일) → 상세(#plan-detail). 축제와 부가 정보는 그 뒤 고정 자리.
const RESULTS_MOBILE=matchMedia('(max-width:800px)');
function sameActivities(a,b){const kinds=p=>p.places.map(x=>x.category).sort().join('|');return kinds(a)===kinds(b);}
/* ── 1안 대비 델타 배지(리디자인 3단계, datemate_2026.md §2.5) ──────────────────────────────
   값을 모르면 배지를 붙이지 않는다(거짓 수치 금지). 차이가 0 이어도 붙이지 않는다.
   - 도보: plan.walking(분)은 서버가 구간 도보를 더한 값인데, 도보를 모르는 구간(자동차 실제 길찾기 등, walking=null)은 0 으로 더해진다.
     그래서 코스의 모든 구간(축제 행사장 구간 포함)에 도보 값이 있을 때만 '안다'고 본다(app/condition_audit.py 총 도보 판정과 같은 기준).
   - 예산: total 은 [최소, 최대] 범위다. 최대(상한)끼리 비교한다 — 서버의 예산 판정('예산 초과 (가격 범위 상한 기준)', remaining)이 상한을 쓰기 때문이다.
     최소끼리의 차이와 방향이 반대면(한쪽 범위가 다른 쪽을 감싸면) 어느 쪽이 싼지 말할 수 없어 붙이지 않는다.
     합계에서 빠진 미확인 비용(unknown)이 어느 한쪽에라도 있으면 빠진 금액을 몰라 붙이지 않는다.
   - 이동: 구간 이동 분(travelMinutes). 이동 분을 모르는 구간이 있으면 붙이지 않는다. */
function planTotalLegs(p){return [...(p.legs||[]),...(p.festival_visit?.leg?[p.festival_visit.leg]:[])];}
function knownWalking(p){return Number.isFinite(p.walking)&&planTotalLegs(p).every(leg=>Number.isFinite(leg?.walking))?p.walking:null;}
function knownTravel(p){const legs=p.legs||[];return Number.isFinite(p.decision_summary?.travel_minutes)||(legs.length&&legs.every(leg=>Number.isFinite(leg?.minutes)))?travelMinutes(p):null;}
function knownBudget(p){const t=p.total;return Array.isArray(t)&&t.every(Number.isFinite)&&!(p.unknown||[]).length?t:null;}
const deltaSign=value=>value>0?'+':'−';
function wonDelta(value){const abs=Math.abs(value);return deltaSign(value)+(abs>=1000?(abs/10000).toFixed(1).replace(/\.0$/,'')+'만원':abs.toLocaleString('ko-KR')+'원');}
// [{kind,text}] — 1안(base) 대비. kind: walk·budget·travel. less=true 면 줄었다(도보·예산·이동 모두 적을수록 가볍다).
function optionDeltas(p,base){
  const out=[];if(!base||p===base)return out;
  const walk=[knownWalking(p),knownWalking(base)];
  if(walk.every(v=>v!==null)&&walk[0]!==walk[1]){const d=walk[0]-walk[1];out.push({kind:'walk',less:d<0,text:`도보 ${deltaSign(d)}${Math.abs(d)}분`});}
  const [a,b]=[knownBudget(p),knownBudget(base)];
  if(a&&b){const high=a[1]-b[1],low=a[0]-b[0];if(high&&!(Math.sign(low)&&Math.sign(low)!==Math.sign(high)))out.push({kind:'budget',less:high<0,text:'예산 '+wonDelta(high)});}
  const travel=[knownTravel(p),knownTravel(base)];
  if(travel.every(v=>v!==null)&&travel[0]!==travel[1]){const d=travel[0]-travel[1];out.push({kind:'travel',less:d<0,text:`이동 ${deltaSign(d)}${Math.abs(d)}분`});}
  return out;
}
function optionDeltaBadges(p,i){
  const box=node('span',undefined,'option-deltas');
  if(!i){box.append(node('span','비교 기준','delta-badge delta-base'));return box;}
  const deltas=optionDeltas(p,plans[0]);
  if(!deltas.length)return null;
  // 화면 읽기: '코스 1 대비 도보 −10분, 예산 상한 −1.4만원'. 예산은 상한끼리 비교했다는 것을 함께 읽는다.
  box.append(node('span','코스 1 대비 ','visually-hidden'));
  deltas.forEach(d=>{const badge=node('span',d.text,`delta-badge is-${d.less?'less':'more'}`);badge.dataset.delta=d.kind;
    if(d.kind==='budget'){badge.title='예상 비용 범위의 최대 금액끼리 비교했어요';badge.append(node('span',' (최대 금액 기준)','visually-hidden'));}
    box.append(badge);});
  return box;
}
// 코스 카드(탭 버튼) 안의 요약. 서버가 준 값으로만 계산하고 없는 차이를 지어내지 않는다.
// 탭 이름은 '코스 N · {서버가 붙인 option_purpose}'. 고정 이름('밸런스'·'최소 도보')은 실제 코스와 다를 수 있어 쓰지 않는다.
// 2026-11-25 사용자 결정: 예전 '안 N' 을 지도 탭·비교 표·서버 문구(option_description)·시안과 같은 '코스 N' 으로 맞췄다.
function optionTabContent(p,i,active){
  const label=node('span',`코스 ${i+1}`,'option-label');
  if(p.option_purpose)label.append(node('span','· '+p.option_purpose,'option-purpose'));
  if(active)label.append(node('span','선택됨','selection-indicator'));
  if(p.best_effort||p.search_adjustments)label.append(node('span','조건 넓힘','option-relaxed'));
  const route=node('strong',p.places.map(x=>x.name).join(' → '),'option-route');
  // 미니 노선: 장소 수만큼 역 원을 잇는다(그림이라 낭독하지 않음).
  const line=node('span',undefined,'option-line');line.setAttribute('aria-hidden','true');line.style.setProperty('--stops',String(p.places.length));
  p.places.forEach(()=>line.append(node('i')));
  // 3줄은 하루 구성만 보여 준다. 이동 시간은 4줄에 있으므로 서버 제목의 "도보 이동 약 8분 · " 같은 앞부분을 다시 쓰지 않는다.
  const title=node('span',p.decision_summary?.activity_label||p.decision_summary?.title||courseTitle(p),'option-title');
  const mode=travelMode(p),basis=mode.basis==='네이버 길찾기'?'길찾기':mode.basis.startsWith('일부')?'일부 추정':'추정';
  const unknown=p.decision_summary?.unknown_prices??p.unknown?.length??0;
  const facts=node('span',undefined,'option-facts');
  // 맨 앞에 고정한 축제가 있으면 그 시작이 코스의 첫 시각이다(app/festival_time.py). 코스 끝·중간에 둔 축제는 첫 장소가 첫 시각이다.
  const leading=p.festival_visit&&p.festival_visit.position!=='last'&&festivalMiddleAfter(p)===null;
  const parts=[`${(leading&&p.festival_visit.arrival)||p.timeline?.[0]?.arrival||p.conditions.start}–${p.finish}`,`${mode.name} ${travelMinutes(p)}분(${basis})`];
  parts.forEach(text=>facts.append(node('span',text,'nowrap'),document.createTextNode(' · ')));
  facts.append(rangeLines(p.total));
  if(unknown)facts.append(document.createTextNode(' · '),node('span','가격 미확인 '+unknown,'nowrap'));
  // 1안은 '비교 기준' 배지만 둔다(차이 설명 줄 없음). 이동 분 차이는 배지(optionDeltaBadges)로 옮겼다.
  const base=plans[0],content=[label,optionDeltaBadges(p,i),line,route,title,facts].filter(Boolean);
  if(i&&base){
    const same=p.difference?!p.difference.composition_changed:sameActivities(p,base);
    let diff=p.option_description||(same?'코스 1과 활동 구성이 같아요':'코스 1과 활동 구성이 달라요');
    if(same&&p.option_description&&!p.option_description.includes('같'))diff='활동 구성 같음 · '+diff;
    content.push(node('span',diff,'option-difference'));
  }
  return content;
}
// 탭을 빠르게 연달아 누르면 마지막 것만 그린다(plan-results choose).
let chooseTurn=0;
function renderResults(result={}){
  const root=$('#results'),detail=$('#plan-detail')||node('div');detail.id='plan-detail';
  // 다시 그려도 사용자가 펼치거나 접은 상태는 유지한다. 처음에는 모바일에서 접고 데스크톱에서 편다.
  const wasOpen=selector=>{const box=root.querySelector(selector);return box?box.open:!RESULTS_MOBILE.matches;};
  const photosOpen=wasOpen('.plan-photo-details');
  root.replaceChildren();$('#result-count').textContent=`추천 일정 ${plans.length}개`;
  // 머리말(2026-11-25 상세 결과 시안): '{지역} 맞춤 데이트 코스 N가지를 찾았어요' + 조건 칩 줄. 세 코스가 같은 조건으로 나온다.
  const c=(selected||plans[0])?.conditions;
  const title=$('#results-title');
  if(title)title.textContent=c&&plans.length?`${resultsArea(c)} 맞춤 ${document.body.classList.contains('mode-travel')?'여행':'데이트'} 코스 ${plans.length}가지를 찾았어요`:'맞춤 코스 비교';
  const meta=$('#results-meta');if(meta)meta.replaceChildren(...(c?resultsConditionChips(c):[]));
  // 탭을 누르면 탭 표시만 바로 바꿔 화면에 내보내고(INP), 결과 전체·상세·지도는 다음 화면 갱신 뒤에 그린다.
  // 전에는 누른 순간 결과 전체와 지도를 다시 만들고 장소마다 패널을 붙여, 중급 휴대폰에서 누른 뒤 화면이 멈춰 보였다.
  // 상세가 어느 코스를 그린 것인지는 #plan-detail 의 data-plan-id 로 알 수 있다(renderDetail).
  function choose(p,showDetail=false){if(selected?.id!==p.id)locks=new Set(Object.keys(p.conditions.locked||{}).map(Number));selected=p;api('/plans/'+p.id+'/feedback',{kind:'selection'}).catch(()=>{});
    const inTabs=Boolean(document.activeElement?.closest?.('#results .plan-option-tabs'));
    root.querySelectorAll('.plan-option-tabs > button').forEach((tab,i)=>{if(!plans[i])return;const on=plans[i].id===p.id;tab.className=on?'primary':'secondary';tab.setAttribute('aria-pressed',String(on));tab.replaceChildren(...optionTabContent(plans[i],i,on));});
    root.setAttribute('aria-busy','true');
    const turn=++chooseTurn;
    requestAnimationFrame(()=>setTimeout(()=>{if(turn!==chooseTurn)return;
      renderResults();renderDetail();root.setAttribute('aria-busy','false');
      // 다시 그리며 탭 단추가 새로 만들어져도 포커스는 고른 코스의 탭에 둔다. 탭에 포커스가 있었을 때뿐 아니라, 누른 단추가
      // 포커스를 받지 않아(Safari·자동화 도구의 클릭) 다시 그린 뒤 포커스가 BODY 로 빠졌을 때도 돌려준다(2026-11-25 운영 QA-04).
      // '일정 살펴보기'(showDetail)는 상세로 가므로 탭으로 돌리지 않는다. 스크롤은 아래 scrollIntoView 가 맡아 preventScroll.
      const lost=!document.activeElement||document.activeElement===document.body||!document.activeElement.isConnected;
      if(inTabs||(lost&&!showDetail))root.querySelector('.plan-option-tabs > button[aria-pressed="true"]')?.focus({preventScroll:true});
      requestAnimationFrame(()=>{const target=showDetail?$('#plan-detail'):$('#results .plan-option-tabs');target?.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});});
    },0));}
  const current=selected||plans[0];
  // 1. 가격 확인 전에 보여 준 후보와 확정된 코스가 다르면 무엇이 달라졌는지 먼저 적는다(plan-progress.js PlanPreview).
  const previewChanges=typeof PlanPreview!=='undefined'?PlanPreview.notice(result):null;
  if(previewChanges)root.append(previewChanges);
  // 1-1. 선택한 코스의 핵심 수치(2026-11-25 HTML 시안 머리말 오른쪽): 예산 사용률 막대 · 총 도보 · 총 소요. 값은 서버 코스 그대로, 모르면 '모름'.
  if(current)root.append(resultsKpis(current));
  // 2. 조건을 넓히거나 달라진 조건 안내는 코스 카드보다 먼저, 항상 펼쳐 보여 준다.
  if(current)root.append(conditionDifferences(current));
  if(plans.length&&result.reasons?.length)root.append(node('p',result.reasons.join(' · '),'hint'));
  if(plans.length&&result.suggestions?.length)root.append(node('p',result.suggestions.join(' '),'hint'));
  // 3. 코스 카드
  if(plans.length){const tabs=node('div',undefined,'plan-option-tabs');tabs.setAttribute('aria-label','데이트 코스 옵션');plans.forEach((p,i)=>{const active=selected?.id===p.id,tab=button('',()=>choose(p),active?'primary':'secondary');tab.append(...optionTabContent(p,i,active));tab.dataset.option=String(i+1);tab.setAttribute('aria-pressed',String(active));tabs.append(tab);});root.append(tabs);const checks=current?resultsCheckChips(current):null;if(checks)root.append(checks);}
  // 4. 비교 표
  // 비교 표는 2026-11-25 상세 결과 시안대로 일정 뒤로 옮겼다(plan-detail.js planComparison).
  // 5. 선택한 코스 카드: 수치와 태그
  if(current){const p=current,i=plans.findIndex(item=>item.id===p.id);
    const card=node('article',undefined,'plan-card'+(selected?.id===p.id?' selected':''));
    // 탭과 겹치는 것(코스 번호, 목적 태그·차이 설명, 조건 넓힘 태그, 방문 장소 수)은 카드에서 뺐다(2026-11-17 가독성 3단계).
    // 카드에는 탭에 없는 것만 남긴다: 제목(인쇄 제목), 이 코스가 맞는 이유, 가격 미확인 안내, 비용·이동 근거·전체 시간, 장소 사진.
    card.dataset.option=String(i+1);
    card.setAttribute('aria-label',`선택한 코스 ${i+1} 요약`);
    card.append(node('h3',p.decision_summary?.title||courseTitle(p)));
    if(p.conditions.festival)card.append(node('p',p.festival_visit?`‘${p.conditions.festival.title}’ ${p.festival_visit.arrival}~${p.festival_visit.departure} 축제${p.festival_visit.position==='last'?'로 마무리하는':festivalMiddleAfter(p)!==null?'를 장소 사이에 들르는':'부터 시작하는'} 코스`:festivalVenueApart(p)?`‘${p.conditions.festival.title}’ 축제는 지금 코스 시간에 맞지 않아 일정에서 빠졌어요`:`‘${p.conditions.festival.title}’ 축제 장소에서 출발하는 코스`,'festival-course-tag'));
    if(p.fresh_place)card.append(node('p',`새로운 곳: ${p.places[p.fresh_place.index]?.name}(${p.fresh_place.label}) · 최근 코스에 드물던 종류`,'hint fresh-place-note'));
    if(p.decision_summary){const summary=p.decision_summary;const fit=node('div',undefined,'fit-reasons');for(const reason of summary.fit_reasons||[summary.reason])fit.append(node('p',reason));card.append(fit);if(summary.unknown_prices||summary.assumed_prices)card.append(node('p',`가격 미확인 ${summary.unknown_prices}항목 · 계획용 가정 ${summary.assumed_prices}항목`,'hint'));}
    if(p.diversity_note)card.append(node('p',p.diversity_note,'hint'));
    const stats=node('div',undefined,'stats');
    const mode=travelMode(p);
    for(const [value,label] of [[range(p.total),p.unknown?.length?'확인한 항목의 예상 비용':p.costs.some(x=>x.status!=='confirmed')?'예상 전체 비용 · 추정 포함':'등록 단가 기준 비용'],[`${travelMinutes(p)}분`,`이동 시간 · ${mode.label}`],[`${p.minutes}분`,'이동 + 체류 전체']]){const box=node('div');box.append(node('b',value),node('small',label));stats.append(box);}
    card.append(stats);
    // 사진 미리보기는 접어 두고 접힘 제목에 장소 수를 적는다.
    const photos=planPhotoPreview(p);
    if(photos.children.length){const box=node('details',undefined,'plan-photo-details');box.append(node('summary',`장소 사진 ${photos.children.length}곳`),photos);box.open=photosOpen;card.append(box);}
    card.append(button('일정 살펴보기 ↓',()=>choose(p,true),'secondary inspect-plan'));
    root.append(card);
    // 6. 휴대폰 지도 자리는 일정 뒤(#plan-detail 안)로 옮겼다(renderDetail).
  }
  if(!plans.length){root.append(emptyRecommendation(result));}
  // 7~9. 일정 · 확인 · 결정과 공유
  root.append(detail);
}

/* ── 오른쪽 고정 패널의 코스 요약·공유(리디자인 3단계, datemate_2026.md §2.5 '우측 스티키 패널') ──────────────
   데스크톱(801px 이상)의 지도 카드(#plan-map-rail .plan-map-card) 안, 지도 탭 바로 아래에 maps.js renderPlanMapCard 가 붙인다.
   휴대폰은 지도가 일정 뒤(#plan-map-slot)로 내려가고 같은 값이 선택한 코스 카드·공유 구역에 이미 있으므로 붙이지 않는다(중복 금지).
   값은 선택한 코스(selected) 그대로다. 코스 탭을 바꾸거나 장소를 바꾸면 renderDetail → renderPlanMapCard 가 다시 그리므로 따로 갱신하지 않는다.
   공유 단추는 일정 아래 공유 구역(plan-detail.js .plan-share)과 같은 함수(copyKakaoItinerary·copyPlanShare)를 부른다 — 복사 글·링크 만드는 법을 여기서 다시 만들지 않는다.
   단추 이름은 공유 구역과 같은 글자에 코스 번호를 붙인다(같은 이름의 단추가 둘이면 화면 읽기 목록에서 구분되지 않는다). */
function durationText(minutes){
  if(!Number.isFinite(minutes)||minutes<0)return '';
  const h=Math.floor(minutes/60),m=minutes%60;
  return h?(m?`${h}시간 ${m}분`:`${h}시간`):`${m}분`;
}
// 머리말 조건 칩에 쓰는 지역 이름: 출발지 이름의 앞부분(' · 현재 위치'·' 지역 중심' 뗌), 없으면 시·도.
function resultsArea(c){return (c.origin?.name||c.region||'').split(' · ')[0].replace(/ 지역 중심$/,'').replace(/ (?:\S+역)$/,'')||c.region||'';}
// 조건 칩: [지역] [날짜(요일) 시작~끝] [N인] [예산 N원|예산 무관] [도보 N분 제한](도보 제한을 정했을 때만, 초록).
function resultsConditionChips(c){
  const d=c.visit_date?new Date(c.visit_date+'T00:00'):null,day=d&&!Number.isNaN(d.getTime())?`${d.getMonth()+1}.${d.getDate()}(${'일월화수목금토'[d.getDay()]}) `:'';
  const won=n=>n>=10000&&n%10000===0?`${n/10000}만원`:Number(n).toLocaleString('ko-KR')+'원';
  const chips=[[resultsArea(c),'is-area'],[`${day}${c.start}~${c.end}`,''],[`${c.people||2}인`,''],[c.budget_unlimited?'예산 무관':`예산 ${won(Number(c.budget)||0)}`,'']];
  if(c.max_walk)chips.push([`도보 ${c.max_walk}분 제한`,'is-safe']);
  return chips.filter(([t])=>t).map(([text,cls])=>node('span',text,'condition-chip '+cls));
}
// 조건 충족 칩(시안 '예산 12만원 이내 충족 · 전체 도보 25분 제한 충족 · 식사 1회 균형 배치'): 서버 판정(condition_checks)만 옮긴다.
// met·estimated 는 충족(초록), unmet 은 '확인 필요'(주황). 판정이 없으면 칩을 만들지 않는다.
function resultsCheckChips(p){
  const checks=p.condition_checks||[],by=k=>checks.filter(x=>x.condition===k),ok=x=>x&&['met','estimated'].includes(x.state);
  const won=n=>n>=10000&&n%10000===0?`${n/10000}만원`:Number(n).toLocaleString('ko-KR')+'원';
  const out=[],c=p.conditions||{};
  const budget=by('budget')[0];
  if(budget&&!c.budget_unlimited)out.push(ok(budget)?[`예산 ${won(Number(c.budget)||0)} 이내 충족`,true]:['예산 확인 필요',false]);
  const walk=by('max_walk')[0];
  if(walk&&c.max_walk)out.push(ok(walk)?[`전체 도보 ${c.max_walk}분 제한 충족`,true]:[`전체 도보 ${c.max_walk}분 제한 확인 필요`,false]);
  const legs=by('max_leg');
  if(legs.length&&c.max_leg&&c.max_leg<180)out.push(legs.every(ok)?[`구간 이동 ${c.max_leg}분 이내`,true]:['구간 이동 시간 확인 필요',false]);
  const end=by('end')[0];
  if(end)out.push(ok(end)?[`${c.end} 이내 종료`,true]:['종료 시간 확인 필요',false]);
  const meals=(p.places||[]).filter(x=>x.meal||x.is_meal).length;
  if(meals)out.push([`식사 ${meals}회 배치`,true]);
  if(!out.length)return null;
  const box=node('div',undefined,'results-checks');box.setAttribute('aria-label','조건 확인');
  const list=node('div',undefined,'results-check-chips');
  for(const [text,good] of out)list.append(node('span',(good?'✓ ':'! ')+text,'check-chip '+(good?'is-met':'is-unmet')));
  box.append(list,node('p','영업시간·휴무는 방문 전 각 카드의 네이버 지도 버튼에서 확인해 주세요.','hint results-checks-note'));
  return box;
}
// 예산 사용률: 예상 비용 상한(total[1]) ÷ 예산(conditions.budget). 예산 무관이면 막대 없이 금액만. 가격 미확인 항목이 있으면 '제외'라고 적는다.
// 상한이 예산을 넘으면 막대를 주황(is-over)으로. 막대는 장식이라 숫자 글자가 같은 내용을 말한다.
function resultsKpis(p){
  const box=node('div',undefined,'results-kpis');box.setAttribute('aria-label','선택한 코스 요약');
  const won=n=>Number(n).toLocaleString('ko-KR')+'원';
  const budget=Number(p.conditions?.budget),free=Boolean(p.conditions?.budget_unlimited),hi=Array.isArray(p.total)?p.total[1]:null,unknown=(p.unknown||[]).length;
  const meter=node('div',undefined,'kpi kpi-budget'),text=node('div',undefined,'kpi-text');
  text.append(node('span','예산 사용률','kpi-label'));
  const amount=hi==null?'모름':free||!budget?`${won(hi)}${free?' (예산 무관)':''}`:`${won(hi)} / ${won(budget)}`;
  text.append(node('strong',amount+(unknown?` · 미확인 ${unknown}항목 제외`:''),'kpi-value'));
  meter.append(text);
  if(hi!=null&&!free&&budget>0){
    const bar=node('span',undefined,'kpi-bar'),fill=node('i');bar.setAttribute('aria-hidden','true');
    fill.style.width=Math.min(100,Math.round(hi/budget*100))+'%';if(hi>budget)bar.classList.add('is-over');bar.append(fill);meter.append(bar);
  }
  const walk=knownWalking(p);
  box.append(meter,node('div',walk===null?'총 도보 모름':`총 도보 ${walk}분`,'kpi kpi-walk'),node('div',durationText(p.minutes)?`총 ${durationText(p.minutes)}`:'총 소요 모름','kpi kpi-time'));
  return box;
}
// 막대: [이름, 값 글자, 비율(0~1, 모르면 null), 넘침 여부, 초록 여부]. 막대는 장식(aria-hidden) — 값 글자가 같은 내용을 말한다.
function railBars(p){
  const box=node('div',undefined,'rail-bars'),c=p.conditions||{},won=n=>Number(n).toLocaleString('ko-KR')+'원';
  const hi=Array.isArray(p.total)?p.total[1]:null,budget=Number(c.budget),walk=knownWalking(p),limit=Number(c.max_walk);
  const rows=[[`${c.people||2}인 예상 비용 합계`,hi==null?'모름':c.budget_unlimited||!budget?won(hi):`${won(hi)} / ${won(budget)}`,hi!=null&&!c.budget_unlimited&&budget?hi/budget:null,hi!=null&&budget&&hi>budget,false],
    ['전체 도보 이동 시간',walk===null?'모름':limit?`${walk}분 / ${limit}분 제한`:`${walk}분 · 제한 없음`,walk!==null&&limit?walk/limit:null,walk!==null&&limit&&walk>limit,true]];
  for(const [label,value,ratio,over,safe] of rows){
    const row=node('div',undefined,'rail-bar'+(safe?' is-safe':'')+(over?' is-over':''));
    const top=node('div',undefined,'rail-bar-top');top.append(node('span',label),node('strong',value));row.append(top);
    if(ratio!==null){const bar=node('span',undefined,'rail-bar-track'),fill=node('i');bar.setAttribute('aria-hidden','true');fill.style.width=Math.min(100,Math.round(ratio*100))+'%';bar.append(fill);row.append(bar);}
    box.append(row);
  }
  return box;
}
// 항목별 예상 지출(시안 '식사 · 카페 · 전시·체험 · 교통'): 코스 비용 줄(p.costs)을 분류로 묶어 상한끼리 더한다. 금액을 모르는 줄은 빼고 '미확인'으로 센다.
function railSpend(p){
  const groups=new Map(),label=c=>/음식|식당|맛집/.test(c)?'식사':c==='카페·미식'?'카페·식사':/문화|체험|오락|레저/.test(c)?'전시·체험':/교통|주차|귀가|택시/.test(c)?'교통':c||'기타';
  let unknown=0;
  for(const row of p.costs||[]){if(!Array.isArray(row.amount)){unknown++;continue;}const key=label(row.category||'');groups.set(key,(groups.get(key)||0)+(row.amount[1]||0));}
  if(!groups.size)return null;
  const box=node('div',undefined,'rail-spend');box.append(node('p',`항목별 예상 지출 (${p.conditions?.people||2}인 기준, 상한)`,'rail-spend-title'));
  const grid=node('dl',undefined,'rail-spend-grid');
  for(const [key,sum] of groups){const row=node('div');row.append(node('dt',key),node('dd',sum?Number(sum).toLocaleString('ko-KR')+'원':'무료'));grid.append(row);}
  box.append(grid);if(unknown)box.append(node('p',`가격 미확인 ${unknown}항목은 빼고 더했어요.`,'hint'));
  return box;
}
function planRailSummary(p){
  const index=plans.findIndex(item=>item.id===p.id),number=index+1;
  const box=node('section',undefined,'plan-rail-summary');
  box.setAttribute('aria-label',`코스 ${number} 요약과 공유`);
  // 2026-11-25 상세 결과 시안: '실시간 예산 · 도보 피로도' 카드 — 막대 두 개(예산 대비 비용 상한, 도보 제한 대비 총 도보)와 항목별 예상 지출.
  const head=node('div',undefined,'rail-head');head.append(node('h3','실시간 예산 · 도보 피로도'),node('span',`코스 ${number}${p.option_purpose?' · '+p.option_purpose:''}`,'rail-badge'));
  box.append(head,railBars(p));
  // 영수증처럼 [이름 · 덧말 | 값] 세 줄. 덧말: 인원(또는 합계에서 빠진 미확인 항목 수), 도보를 모르는 구간, 출발–끝 시각.
  const stats=node('dl',undefined,'rail-stats');
  const stat=(label,note,value,kind)=>{const row=node('div',undefined,'rail-stat'),dt=node('dt',label),dd=node('dd');row.dataset.stat=kind;
    if(note)dt.append(node('span',' · '+note,'rail-stat-note'));dd.append(value);row.append(dt,dd);stats.append(row);};
  const unknown=(p.unknown||[]).length,walk=knownWalking(p);
  stat('예상 예산',unknown?`미확인 ${unknown}항목 제외`:`${p.conditions?.people||2}명`,p.total?rangeLines(p.total):'모름','budget');
  stat('총 도보',walk===null?'일부 구간 모름':'',walk===null?'모름':`${walk}분`,'walk');
  stat('총 소요',p.conditions?.start&&p.finish?`${p.conditions.start}–${p.finish}`:'',durationText(p.minutes)||'모름','time');
  box.append(stats);
  const spend=railSpend(p);if(spend)box.append(spend);
  if(p.id){
    const share=node('div',undefined,'rail-share'),label=(text,cls,action)=>{const b=button(text,action,cls);b.setAttribute('aria-label',`${text} · 코스 ${number}`);return b;};
    share.append(label('공유 티켓 보기','primary rail-ticket',()=>showPlanTicket(p)),linkCopyHint(label('카톡용 일정·링크 복사','secondary rail-kakao-copy',()=>copyKakaoItinerary(p))));
    // 한 줄로 둔다: 1440×900 에서 패널 아래 지도가 첫 화면에 다 들어와야 한다(tests/test_redesign_results_ui.py scrollTop 0).
    box.append(node('p','이 코스가 마음에 드셨나요?','rail-share-title'),share);
  }
  return box;
}

/* 공유 티켓(2026-11-25 HTML 시안 'DATEMATE PASS'): 선택한 코스를 탑승권처럼 한 장에 — 날짜·지역·모드, 예산·도보·장소 수, 장소별 도착 시각.
   공유 대화상자(#dialog, place-dialog.js openDialog)를 쓴다. 단추는 공유 링크 복사(copyPlanShare)·텍스트 복사(copyKakaoItinerary) — 새로 만들지 않는다.
   값은 서버 코스 그대로(가격 모르면 '모름'). 모드(데이트/여행)는 머리글 스위치(header-mode.js body.mode-travel). */
function showPlanTicket(p){
  const root=openDialog('공유 티켓'),number=plans.findIndex(item=>item.id===p.id)+1;
  const ticket=node('article',undefined,'plan-ticket'),top=node('div',undefined,'ticket-top');
  const travel=document.body.classList.contains('mode-travel');
  top.append(node('span','DATEMATE PASS','ticket-badge'),
    node('p',[p.conditions?.visit_date,(p.conditions?.origin?.name||'').split(' · ')[0].replace(/ 지역 중심$/,''),travel?'여행 플랜':'데이트 플랜'].filter(Boolean).join(' · '),'ticket-sub'),
    node('h3',`코스 ${number}${p.option_purpose?' · '+p.option_purpose:''}`,'ticket-title'));
  const facts=node('dl',undefined,'ticket-facts'),walk=knownWalking(p);
  for(const [label,value] of [['예산',Array.isArray(p.total)?range(p.total):'모름'],['도보',walk===null?'모름':`${walk}분`],['장소',`${p.places.length}곳`]]){const row=node('div');row.append(node('dt',label),node('dd',value));facts.append(row);}
  top.append(facts);
  const cut=node('div',undefined,'ticket-cut');cut.setAttribute('aria-hidden','true');
  const list=node('ol',undefined,'ticket-stops');
  p.places.forEach((place,i)=>{const row=node('li');row.append(node('strong',place.name),node('span',p.timeline?.[i]?.arrival||'','ticket-time'),node('small',placeKind(place),'hint'));list.append(row);});
  const actions=node('div',undefined,'ticket-actions');
  actions.append(button('공유 링크 복사',()=>copyPlanShare(p),'primary'),button('텍스트 복사',()=>copyKakaoItinerary(p),'secondary'));
  ticket.append(top,cut,list,actions);
  root.append(ticket);
}

/* 결과 화면 고정 윗줄·휴대폰 아래 막대(2026-11-25 Gemini Canvas 시안 share.gemini.google/NMTZYFdUBrws, 사용자 선택 두 가지).
   ① 윗줄(#results-bar, index.html): 「← 조건 수정하기」·조건 칩(#results-meta)·「공유 티켓」·「일정·링크 복사」. 머리글 바로 아래에 붙는다(redesign.css 12)).
   ② 휴대폰(720px 이하) 아래 막대(#results-actionbar): 코스가 있으면 메뉴 바 대신 「지도 보기 / 일정·링크 복사 / 공유 티켓」.
      메뉴 바는 처음 화면·둘러보기에서는 그대로다(결과가 보일 때만 바꾼다 — CSS 가 #results-actionbar 가 보이는지로 정한다).
      「지도 보기」는 일정 뒤 휴대폰 지도 자리(#plan-map-slot)로 가고, 지도가 화면에 보이는 동안은 「일정 보기」(첫 장소로)로 바뀐다.
   공유·복사는 오른쪽 패널과 같은 함수(showPlanTicket·copyKakaoItinerary)를 부른다 — 새로 만들지 않는다.
   renderDetail(plan-detail.js) 끝에서 코스가 바뀔 때마다 다시 그린다. 저장되지 않은 코스(id 없음)는 공유할 것이 없어 단추를 두지 않는다. */
let resultsMapSeen = false,
  resultsMapObserver = null;

function syncResultsBars(p = selected) {
  const actions = document.getElementById('results-bar-actions'),
    bar = document.getElementById('results-actionbar');
  if (actions) {
    actions.replaceChildren();
    if (p?.id) actions.append(button('공유 티켓', () => showPlanTicket(p), 'secondary results-bar-ticket'), linkCopyHint(button('일정·링크 복사', () => copyKakaoItinerary(p), 'primary results-bar-copy')));
  }
  if (!bar) return;
  bar.replaceChildren();
  bar.hidden = !p?.id;
  if (!p?.id) return;
  const icon = path => `<svg aria-hidden="true" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${path}</svg>`;
  const make = (label, cls, svg, action) => {
    const b = button('', action, cls);
    b.innerHTML = icon(svg);
    b.append(node('span', label));
    return b;
  };
  const mapButton = make('지도 보기', 'secondary results-actionbar-map', '<path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2z"/><path d="M9 4v14M15 6v14"/>', () => {
    const target = resultsMapSeen ? document.querySelector('#plan-detail .stop') : document.getElementById('plan-map-slot');
    target?.scrollIntoView({
      behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth',
      block: 'start'
    });
  });
  mapButton.dataset.view = 'map';
  bar.append(mapButton,
    linkCopyHint(make('일정·링크 복사', 'results-actionbar-copy', '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>', () => copyKakaoItinerary(p))),
    make('공유 티켓', 'results-actionbar-ticket', '<path d="M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v3a2 2 0 0 0 0 4v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-3a2 2 0 0 0 0-4z"/>', () => showPlanTicket(p)));
  // 지도가 보이면 단추를 「일정 보기」로. 지도 자리는 상세를 다시 그릴 때마다 새로 생기므로 관찰도 다시 건다.
  resultsMapObserver?.disconnect();
  resultsMapSeen = false;
  const slot = document.getElementById('plan-map-slot');
  if (slot && 'IntersectionObserver' in window) {
    resultsMapObserver = new IntersectionObserver(entries => {
      resultsMapSeen = entries.some(entry => entry.isIntersecting);
      const label = mapButton.querySelector('span');
      if (label) label.textContent = resultsMapSeen ? '일정 보기' : '지도 보기';
      mapButton.dataset.view = resultsMapSeen ? 'timeline' : 'map';
    }, {
      threshold: 0.25
    });
    resultsMapObserver.observe(slot);
  }
}

/* 축제 구역 필터 탭(2026-11-25 Gemini Canvas 시안: 전체 / 축제·행사 / 팝업스토어). index.html #festival-section 머리말의 .event-filter.
   축제(한국관광공사 카드, festivals.js)와 팝업(네이버 블로그 검색 블록, popups.js #popup-course)은 서로 다른 구역이라 섞지 않고,
   .results-area 의 data-event-filter 로 한쪽 구역을 숨긴다(redesign.css 13)). 팝업 구역이 없거나 숨어 있으면 탭 자체를 숨긴다(고를 것이 하나뿐).
   팝업 블록은 받은 그대로 보여 준다는 약관(특약 2.2) 때문에 글을 골라 카드로 만들지 않는다 — 탭은 구역을 통째로 보이거나 숨길 뿐이다. */
document.addEventListener('click', event => {
  const tab = event.target.closest?.('.event-filter [data-event-filter]');
  if (!tab) return;
  const area = tab.closest('.results-area'),
    value = tab.dataset.eventFilter;
  if (!area) return;
  if (value === 'all') delete area.dataset.eventFilter;
  else area.dataset.eventFilter = value;
  tab.parentElement.querySelectorAll('[data-event-filter]').forEach(b => b.setAttribute('aria-pressed', String(b === tab)));
});
