function courseTitle(plan){
  if(plan.decision_summary?.title)return plan.decision_summary.title;
  if(plan.option_purpose)return plan.option_purpose+' · '+courseTitle({...plan,option_purpose:null});
  const kinds=new Set(plan.places.map(p=>p.category));
  if(kinds.has('체험·제작'))return '함께 만들며 추억을 쌓는 하루';
  if(kinds.has('산책·풍경')&&kinds.has('문화·예술'))return '자연과 문화를 천천히 즐기며';
  if(kinds.has('산책·풍경'))return kinds.has('카페·미식')?'자연을 즐기며 맛보는 하루':'풍경 따라 여유롭게 걷는 하루';
  if(kinds.has('문화·예술'))return kinds.has('카페·미식')?'문화와 맛집을 잇는 하루':'새로운 취향을 발견하는 하루';
  if(kinds.has('오락·놀이')||kinds.has('레저·활동'))return '함께 웃고 신나게 즐기는 하루';
  if(kinds.has('휴식·힐링'))return '잠시 쉬어가며 가까워지는 하루';
  return '맛있는 대화로 채우는 하루';
}
function compactConditionSummary(plan){
  const root=node('div',undefined,'compact-condition-summary'),checks=plan.condition_checks||[];
  const labelList=rows=>[...new Set(rows.map(r=>{
    if(r.condition==='budget')return r.state==='unmet'?`예산 ${won(Math.max(0,plan.total[1]-plan.conditions.budget))} 초과`:`비용 ${range(plan.total)}`;
    if(r.condition==='people')return plan.conditions.people+'명';
    if(r.condition==='end')return plan.finish+' 종료';
    if(r.condition==='count')return plan.places.length+'곳 방문';
    if(r.condition==='neighborhood')return '반경 '+plan.conditions.neighborhood_radius_km+'km';
    if(r.condition==='meal')return r.state==='unmet'?'식사 시간 조정 필요':'식사 포함';
    return r.label;
  }))].join(' · ')||'없음';
  const groups=[['요청과 다른 조건',checks.filter(r=>r.state==='unmet'),'condition-alert'],['방문 전 확인',checks.filter(r=>r.state==='unknown'),'condition-pending'],['추정으로 계산',checks.filter(r=>r.state==='estimated'),''],['맞춰진 조건',checks.filter(r=>r.state==='met'),'']];
  for(const [title,rows,cls] of groups){const line=node('p',undefined,cls);line.append(node('strong',title+' '),node('span',labelList(rows)));line.title=rows.map(r=>r.message).join('\n');root.append(line);}
  return root;
}
function conditionDifferences(plan){
  if(plan.search_adjustments){
    const box=node('section',undefined,'condition-differences search-adjustments');
    box.append(node('strong','이렇게 조건을 조정해 찾았어요'));
    const change=plan.search_adjustments;
    const messages=change.messages||[],brief=messages.length>3?[messages[0],messages.at(-1)]:messages;
    box.append(node('p','선택한 위치는 유지했어요. '+brief.join(' '),'condition-summary'));
    if(change.attempts?.length)box.append(node('p',change.attempts.length+'단계까지 조건을 넓혀 검색했어요. 원래 입력은 그대로 유지됩니다.','hint'));
    const details=node('details');details.append(node('summary','요청과 달라진 조건 확인'));
    for(const message of messages)details.append(node('p',message,'hint'));
    for(const row of change.differences)details.append(node('p',row.label+' · '+row.message));
    if(change.differences.length||messages.length)box.append(details);
    return box;
  }
  if(!(plan.deviations||[]).some(item=>item.state==='unmet'))return document.createDocumentFragment();
  const box=node('section',undefined,'condition-differences');
  box.append(node('strong','조건 차이와 방문 준비'));
  const labels={weather:'날씨',setting:['비 오는 날','눈 오는 날'].includes(plan.conditions.date_subcategory)?'날씨·실내외':'실내·실외',themes:'테마',date_subcategory:'데이트 분류',max_leg:'이동 시간',end:'종료 시간',budget:'예산',max_walk:'도보 시간',count:'장소 수',reservation:'예약',theme_mode:'테마 구성',allow_estimates:'추정 사용'};
  const names=[...new Set((plan.deviations||[]).map(item=>item.label||labels[item.condition]||'기타'))];
  box.append(node('p',plan.condition_summary||(names.join('·')+' 조건을 함께 확인해 주세요.'),'condition-summary'));
  const list=node('ul');
  const pending=node('ul');
  for(const item of plan.deviations||[]){const row=node('li');row.append(node('b','['+(item.label||labels[item.condition]||'기타')+(item.state==='unknown'?' · 확인 필요':' · 불일치')+'] '),node('span',item.message));(item.state==='unknown'?pending:list).append(row);}
  if(!list.children.length)list.append(node('li','계산된 일정에서 입력 조건을 넘긴 항목은 없어요.'));
  box.append(list);
  if((plan.deviations||[]).some(item=>item.condition==='meal'&&item.state==='unmet'))box.append(mealRescuePanel(plan));
  if(plan.confirmed_facts?.length){const facts=node('details',undefined,'verified-facts');facts.append(node('summary','공식 자료로 확인한 장소 정보 '+plan.confirmed_facts.length+'곳'));for(const item of plan.confirmed_facts){const row=node('p');row.append(link(item.name+' · 자료 '+item.checked_at,item.source),node('span',' — '+item.scope));facts.append(row);}box.append(facts);}
  if(pending.children.length){const notes=node('details',undefined,'verification-notes');notes.append(node('summary','방문 전 확인할 사항 '+pending.children.length+'건'),pending);box.append(notes);}
  if(plan.condition_checks?.length){
    const all=node('details',undefined,'all-condition-checks');all.append(node('summary','전체 조건 확인'));
    all.append(compactConditionSummary(plan));box.append(all);
  }
  return box;
}
function emptyRecommendation(result){
  const box=node('div',undefined,'empty-state');
  const titles={data_incomplete:'실제 장소의 운영정보가 아직 부족해요',origin_too_far:'출발지가 데모 시연 구역에서 멀어요',no_candidates:'선택한 조건에 맞는 장소가 없어요',constraints_unmet:'시간·예산·이동 조건에 맞는 일정이 없어요'};
  box.append(node('h3',titles[result.status]||'조건에 맞는 일정을 찾지 못했어요'));
  if(result.reasons?.length)box.append(node('p',result.reasons.join(' ')));
  if(result.suggestions?.length)box.append(node('p',result.suggestions.join(' '),'hint'));
  if(['data_incomplete','origin_too_far'].includes(result.status))box.append(button('데모 기본 조건으로 시연하기',runDemoSample,'primary'));
  return box;
}

function runDemoSample(){
  // 사용자가 이 버튼을 눌렀을 때만 명시적으로 시연 조건을 적용한다.
  form.elements.mode.value='demo';mode='demo';selected=null;locks.clear();plans=[];clearLocationsForMode();
  const defaults={region:statusData?.region||'서울',visit_date:today(),start:'11:00',end:'19:00',people:2,budget:100000,transport:'walk',count:3,theme_mode:'mix',setting:'any',avoid:'',max_leg:30,max_walk:'',mbti:'',request:''};
  for(const [key,value] of Object.entries(defaults))form.elements[key].value=value;
  for(const key of ['reservation','return_home','use_mbti'])form.elements[key].checked=false;
  setDateClassification('콘셉트별','');document.querySelectorAll('[name=themes]').forEach(input=>input.checked=false);
  $('#mode-badge').textContent='DEMO SPACE';$('#parse-notice').textContent='가상 장소·출발지와 기본 조건으로 시연합니다. 실제 방문 일정이 아닙니다.';
  form.requestSubmit();
}

document.addEventListener('DOMContentLoaded',()=>{
  form.addEventListener('invalid',event=>{
    const input=event.target;const label=input.closest('label')?.childNodes[0]?.textContent?.trim()||'입력';
    $('#progress').textContent=label+' 항목을 확인해 주세요. '+input.validationMessage;
  },true);
});
