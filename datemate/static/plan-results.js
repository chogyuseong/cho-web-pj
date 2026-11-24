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
  // 화면 읽기: '안 1 대비 도보 −10분, 예산 상한 −1.4만원'. 예산은 상한끼리 비교했다는 것을 함께 읽는다.
  box.append(node('span','안 1 대비 ','visually-hidden'));
  deltas.forEach(d=>{const badge=node('span',d.text,`delta-badge is-${d.less?'less':'more'}`);badge.dataset.delta=d.kind;
    if(d.kind==='budget'){badge.title='예상 비용 범위의 최대 금액끼리 비교했어요';badge.append(node('span',' (최대 금액 기준)','visually-hidden'));}
    box.append(badge);});
  return box;
}
// 코스 카드(탭 버튼) 안의 요약. 서버가 준 값으로만 계산하고 없는 차이를 지어내지 않는다.
// 탭 이름은 '안 N · {서버가 붙인 option_purpose}'(리디자인 3단계). 고정 이름('밸런스'·'최소 도보')은 실제 코스와 다를 수 있어 쓰지 않는다.
function optionTabContent(p,i,active){
  const label=node('span',`안 ${i+1}`,'option-label');
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
  const compareOpen=wasOpen('.comparison-details'),photosOpen=wasOpen('.plan-photo-details');
  root.replaceChildren();$('#result-count').textContent=`추천 일정 ${plans.length}개`;
  // 탭을 누르면 탭 표시만 바로 바꿔 화면에 내보내고(INP), 결과 전체·상세·지도는 다음 화면 갱신 뒤에 그린다.
  // 전에는 누른 순간 결과 전체와 지도를 다시 만들고 장소마다 패널을 붙여, 중급 휴대폰에서 누른 뒤 화면이 멈춰 보였다.
  // 상세가 어느 코스를 그린 것인지는 #plan-detail 의 data-plan-id 로 알 수 있다(renderDetail).
  function choose(p,showDetail=false){if(selected?.id!==p.id)locks=new Set(Object.keys(p.conditions.locked||{}).map(Number));selected=p;api('/plans/'+p.id+'/feedback',{kind:'selection'}).catch(()=>{});
    const focused=document.activeElement?.closest?.('#results .plan-option-tabs > button')?.dataset.option||null;
    root.querySelectorAll('.plan-option-tabs > button').forEach((tab,i)=>{if(!plans[i])return;const on=plans[i].id===p.id;tab.className=on?'primary':'secondary';tab.setAttribute('aria-pressed',String(on));tab.replaceChildren(...optionTabContent(plans[i],i,on));});
    root.setAttribute('aria-busy','true');
    const turn=++chooseTurn;
    requestAnimationFrame(()=>setTimeout(()=>{if(turn!==chooseTurn)return;
      renderResults();renderDetail();root.setAttribute('aria-busy','false');
      // 다시 그리며 탭 단추가 새로 만들어져도 키보드 포커스는 같은 탭에 둔다.
      if(focused)root.querySelector(`.plan-option-tabs > button[data-option="${focused}"]`)?.focus({preventScroll:true});
      requestAnimationFrame(()=>{const target=showDetail?$('#plan-detail'):$('#results .plan-option-tabs');target?.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});});
    },0));}
  const current=selected||plans[0];
  // 1. 가격 확인 전에 보여 준 후보와 확정된 코스가 다르면 무엇이 달라졌는지 먼저 적는다(plan-progress.js PlanPreview).
  const previewChanges=typeof PlanPreview!=='undefined'?PlanPreview.notice(result):null;
  if(previewChanges)root.append(previewChanges);
  // 2. 조건을 넓히거나 달라진 조건 안내는 코스 카드보다 먼저, 항상 펼쳐 보여 준다.
  if(current)root.append(conditionDifferences(current));
  if(plans.length&&result.reasons?.length)root.append(node('p',result.reasons.join(' · '),'hint'));
  if(plans.length&&result.suggestions?.length)root.append(node('p',result.suggestions.join(' '),'hint'));
  // 3. 코스 카드
  if(plans.length){const tabs=node('div',undefined,'plan-option-tabs');tabs.setAttribute('aria-label','데이트 코스 옵션');plans.forEach((p,i)=>{const active=selected?.id===p.id,tab=button('',()=>choose(p),active?'primary':'secondary');tab.append(...optionTabContent(p,i,active));tab.dataset.option=String(i+1);tab.setAttribute('aria-pressed',String(active));tabs.append(tab);});root.append(tabs);}
  // 4. 비교 표
  if(plans.length){const compare=node('details',undefined,'comparison-details');compare.append(node('summary',`코스 ${plans.length}개 비용·이동 시간 비교 표`),optionComparison(plans));compare.open=compareOpen;root.append(compare);}
  // 5. 선택한 코스 카드: 수치와 태그
  if(current){const p=current,i=plans.findIndex(item=>item.id===p.id);
    const card=node('article',undefined,'plan-card'+(selected?.id===p.id?' selected':''));
    // 탭과 겹치는 것(코스 번호, 목적 태그·차이 설명, 조건 넓힘 태그, 방문 장소 수)은 카드에서 뺐다(2026-11-17 가독성 3단계).
    // 카드에는 탭에 없는 것만 남긴다: 제목(인쇄 제목), 이 코스가 맞는 이유, 가격 미확인 안내, 비용·이동 근거·전체 시간, 장소 사진.
    card.dataset.option=String(i+1);
    card.setAttribute('aria-label',`선택한 코스 ${i+1} 요약`);
    card.append(node('h3',p.decision_summary?.title||courseTitle(p)));
    if(p.conditions.festival)card.append(node('p',p.festival_visit?`‘${p.conditions.festival.title}’ ${p.festival_visit.arrival}~${p.festival_visit.departure} 축제${p.festival_visit.position==='last'?'로 마무리하는':festivalMiddleAfter(p)!==null?'를 장소 사이에 들르는':'부터 시작하는'} 코스`:`‘${p.conditions.festival.title}’ 축제 장소에서 출발하는 코스`,'festival-course-tag'));
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
function planRailSummary(p){
  const index=plans.findIndex(item=>item.id===p.id),number=index+1;
  const box=node('section',undefined,'plan-rail-summary');
  box.setAttribute('aria-label',`코스 ${number} 요약과 공유`);
  // 영수증처럼 [이름 · 덧말 | 값] 세 줄. 덧말: 인원(또는 합계에서 빠진 미확인 항목 수), 도보를 모르는 구간, 출발–끝 시각.
  const stats=node('dl',undefined,'rail-stats');
  const stat=(label,note,value,kind)=>{const row=node('div',undefined,'rail-stat'),dt=node('dt',label),dd=node('dd');row.dataset.stat=kind;
    if(note)dt.append(node('span',' · '+note,'rail-stat-note'));dd.append(value);row.append(dt,dd);stats.append(row);};
  const unknown=(p.unknown||[]).length,walk=knownWalking(p);
  stat('예상 예산',unknown?`미확인 ${unknown}항목 제외`:`${p.conditions?.people||2}명`,p.total?rangeLines(p.total):'모름','budget');
  stat('총 도보',walk===null?'일부 구간 모름':'',walk===null?'모름':`${walk}분`,'walk');
  stat('총 소요',p.conditions?.start&&p.finish?`${p.conditions.start}–${p.finish}`:'',durationText(p.minutes)||'모름','time');
  box.append(stats);
  if(p.id){
    const share=node('div',undefined,'rail-share'),label=(text,cls,action)=>{const b=button(text,action,cls);b.setAttribute('aria-label',`${text} · 코스 ${number}`);return b;};
    share.append(label('카톡용 일정 복사','primary rail-kakao-copy',()=>copyKakaoItinerary(p)),label('공유 링크 복사','secondary rail-link-copy',()=>copyPlanShare(p)));
    box.append(share);
  }
  return box;
}
