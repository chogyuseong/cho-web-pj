function renderResults(result={}){
  const root=$('#results'),detail=$('#plan-detail')||node('div');detail.id='plan-detail';
  root.replaceChildren();$('#result-count').textContent=`추천 일정 ${plans.length}개`;
  const evidence=result.course_search||selected?.course_search;
  function choose(p,showDetail=false){if(selected?.id!==p.id)locks=new Set(Object.keys(p.conditions.locked||{}).map(Number));selected=p;api('/plans/'+p.id+'/feedback',{kind:'selection'}).catch(()=>{});renderResults();renderDetail();requestAnimationFrame(()=>{const target=showDetail?$('#plan-detail'):$('#results .plan-option-tabs');target?.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});});}
  if(plans.length){const tabs=node('div',undefined,'plan-option-tabs');tabs.setAttribute('aria-label','데이트 코스 옵션');plans.forEach((p,i)=>{const tab=button('',()=>choose(p),selected?.id===p.id?'primary':'secondary');tab.append(node('span',`Option${i+1}`,'option-label'),node('strong',p.decision_summary?.title||courseTitle(p)),node('small',p.places.map(x=>x.name).join(' → ')));tab.dataset.option=String(i+1);tab.setAttribute('aria-pressed',String(selected?.id===p.id));tabs.append(tab);});root.append(tabs);}
  if(plans.length)root.append(optionComparison(plans));
  let placed=false;
  const ordered=selected?[selected]:plans.slice(0,1);
  ordered.forEach(p=>{const i=plans.findIndex(item=>item.id===p.id);
    const card=node('article',undefined,'plan-card'+(selected?.id===p.id?' selected':''));
    const heading=node('div',undefined,'option-heading');
    card.dataset.option=String(i+1);
    heading.append(node('div',`Option${i+1} / ${p.conditions.mode==='demo'?'가상 장소 데모':'실제 자료'}`,'number'),button('일정 살펴보기 ↗',()=>choose(p,true),'primary inspect-plan'));
    card.append(heading,node('h3',p.decision_summary?.title||courseTitle(p)));
    if(p.decision_summary){const summary=p.decision_summary;const fit=node('div',undefined,'fit-reasons');for(const reason of summary.fit_reasons||[summary.reason])fit.append(node('p',reason));card.append(fit);if(summary.unknown_prices||summary.assumed_prices)card.append(node('p',`가격 미확인 ${summary.unknown_prices}항목 · 계획용 가정 ${summary.assumed_prices}항목`,'hint'));} 
    if(p.option_purpose)card.append(node('strong',p.option_purpose,'tag'),node('p',p.option_description,'hint'));
    if(p.diversity_note)card.append(node('p',p.diversity_note,'hint'));
    card.append(node('span',p.best_effort?'조건 차이가 있는 대안':'조건 비교 완료','tag'),node('p',p.places.map(x=>x.name).join(' → '),'path-text'));
    const stats=node('div',undefined,'stats');
    for(const [value,label] of [[range(p.total),p.unknown?.length?'확인한 항목의 예상 비용':p.costs.some(x=>x.status!=='confirmed')?'예상 전체 비용 · 추정 포함':'등록 단가 기준 비용'],[`${p.minutes}분`,'이동 + 체류'],[`${p.places.length}곳`,'방문 장소']]){const box=node('div');box.append(node('b',value),node('small',label));stats.append(box);}
    card.append(planPhotoPreview(p),stats);
    if(p.id!==selected?.id)card.append(conditionDifferences(p));
    if(p.id===selected?.id&&evidence){const research=node('details',undefined,'course-evidence');research.append(node('summary','추천에 참고한 블로그·장소 정보'),courseSearchPanel(evidence,p));card.append(research);}
    root.append(card);
    if(selected?.id===p.id){root.append(leisureCoursePanel(p),detail);placed=true;}
  });
  if(!plans.length)root.append(emptyRecommendation(result));
  if(!placed)root.append(detail);
  if(result.reasons?.length)root.append(node('p',result.reasons.join(' · '),'hint'));
  if(result.suggestions?.length)root.append(node('p',result.suggestions.join(' '),'hint'));
}

