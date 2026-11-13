// 결과 화면은 사용자 흐름 순서대로 DOM을 붙인다(보이는 순서 = 탭 순서 = 낭독 순서).
// 조건 안내 → 코스 카드 → 비교 표 → 선택한 코스 → 지도(모바일) → 상세(#plan-detail). 축제와 부가 정보는 그 뒤 고정 자리.
const RESULTS_MOBILE=matchMedia('(max-width:800px)');
function sameActivities(a,b){const kinds=p=>p.places.map(x=>x.category).sort().join('|');return kinds(a)===kinds(b);}
// 코스 카드(탭 버튼) 안의 요약. 서버가 준 값으로만 계산하고 없는 차이를 지어내지 않는다.
function optionTabContent(p,i,active){
  const base=plans[0],label=node('span',`코스 ${i+1}`,'option-label');
  if(active)label.append(node('span','선택됨','selection-indicator'));
  if(p.option_purpose)label.append(node('span','· '+p.option_purpose,'option-purpose'));
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
  const parts=[`${p.timeline?.[0]?.arrival||p.conditions.start}–${p.finish}`,`${mode.name} ${travelMinutes(p)}분(${basis})`];
  parts.forEach(text=>facts.append(node('span',text,'nowrap'),document.createTextNode(' · ')));
  facts.append(rangeLines(p.total));
  if(unknown)facts.append(document.createTextNode(' · '),node('span','가격 미확인 '+unknown,'nowrap'));
  let diff='비교 기준';
  if(i&&base){
    const same=p.difference?!p.difference.composition_changed:sameActivities(p,base),delta=travelMinutes(p)-travelMinutes(base);
    diff=p.option_description||(same?'코스 1과 활동 구성이 같아요':'코스 1과 활동 구성이 달라요');
    if(same&&p.option_description&&!p.option_description.includes('같'))diff='활동 구성 같음 · '+diff;
    if(delta)diff+=` · 이동 ${delta>0?'+':'−'}${Math.abs(delta)}분`;
  }
  return [label,line,route,title,facts,node('span',diff,'option-difference')];
}
function renderResults(result={}){
  const root=$('#results'),detail=$('#plan-detail')||node('div');detail.id='plan-detail';
  // 다시 그려도 사용자가 펼치거나 접은 상태는 유지한다. 처음에는 모바일에서 접고 데스크톱에서 편다.
  const wasOpen=selector=>{const box=root.querySelector(selector);return box?box.open:!RESULTS_MOBILE.matches;};
  const compareOpen=wasOpen('.comparison-details'),photosOpen=wasOpen('.plan-photo-details');
  root.replaceChildren();$('#result-count').textContent=`추천 일정 ${plans.length}개`;
  function choose(p,showDetail=false){if(selected?.id!==p.id)locks=new Set(Object.keys(p.conditions.locked||{}).map(Number));selected=p;api('/plans/'+p.id+'/feedback',{kind:'selection'}).catch(()=>{});renderResults();renderDetail();requestAnimationFrame(()=>{const target=showDetail?$('#plan-detail'):$('#results .plan-option-tabs');target?.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});});}
  const current=selected||plans[0];
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
    const heading=node('div',undefined,'option-heading');
    card.dataset.option=String(i+1);
    heading.append(node('div',`코스 ${i+1}`,'number'),button('일정 살펴보기',()=>choose(p,true),'secondary inspect-plan'));
    card.append(heading,node('h3',p.decision_summary?.title||courseTitle(p)));
    if(p.conditions.festival)card.append(node('p',`‘${p.conditions.festival.title}’ 축제 장소에서 출발하는 코스`,'festival-course-tag'));
    if(p.decision_summary){const summary=p.decision_summary;const fit=node('div',undefined,'fit-reasons');for(const reason of summary.fit_reasons||[summary.reason])fit.append(node('p',reason));card.append(fit);if(summary.unknown_prices||summary.assumed_prices)card.append(node('p',`가격 미확인 ${summary.unknown_prices}항목 · 계획용 가정 ${summary.assumed_prices}항목`,'hint'));}
    if(p.option_purpose)card.append(node('strong',p.option_purpose,'tag'),node('p',p.option_description,'hint'));
    if(p.diversity_note)card.append(node('p',p.diversity_note,'hint'));
    card.append(node('span',p.best_effort?'조건 차이가 있는 대안':'조건 비교 완료','tag'));
    const stats=node('div',undefined,'stats');
    const mode=travelMode(p);
    for(const [value,label] of [[range(p.total),p.unknown?.length?'확인한 항목의 예상 비용':p.costs.some(x=>x.status!=='confirmed')?'예상 전체 비용 · 추정 포함':'등록 단가 기준 비용'],[`${travelMinutes(p)}분`,`이동 시간 · ${mode.label}`],[`${p.minutes}분`,'이동 + 체류 전체'],[`${p.places.length}곳`,'방문 장소']]){const box=node('div');box.append(node('b',value),node('small',label));stats.append(box);}
    card.append(stats);
    // 사진 미리보기는 접어 두고 접힘 제목에 장소 수를 적는다.
    const photos=planPhotoPreview(p);
    if(photos.children.length){const box=node('details',undefined,'plan-photo-details');box.append(node('summary',`장소 사진 ${photos.children.length}곳`),photos);box.open=photosOpen;card.append(box);}
    root.append(card);
    // 6. 모바일 지도 자리. 데스크톱에서는 오른쪽 패널(#plan-map-rail)에 그린다.
    const slot=node('div',undefined,'plan-map-slot');slot.id='plan-map-slot';slot.hidden=true;root.append(slot);
  }
  if(!plans.length){root.append(emptyRecommendation(result));}
  // 7~9. 일정 · 확인 · 결정과 공유
  root.append(detail);
}
