// 확정 전 후보(가격 확인 단계). 서버가 준 preview_options(안별 이름과 장소)로만 그리는 읽기 전용 카드다.
// 버튼·비용·조건 확인은 넣지 않는다: 저장·공유·장소 바꾸기는 확정된 코스(id)가 있어야 하고, 가격은 아직 확인 중이다.
// 확정되면 결과가 이 카드를 대신하고, 확정 전 후보와 달라진 점(빠짐·자리·순서·이름)이 있으면 결과 위에 적는다.
const PlanPreview={
  options:null,key:'',changes:[],planKey:null,result:null,
  reset(){this.options=null;this.key='';this.changes=[];this.planKey=null;this.result=null;this.remove();},
  remove(){document.querySelector('#results .plan-preview')?.remove();},
  route(places){return places.map(p=>p.name).join(' → ');},
  show(options){
    const key=JSON.stringify(options);if(key===this.key)return false;
    this.key=key;this.options=options;
    const root=document.querySelector('#results');if(!root)return true;
    const box=node('section',undefined,'plan-preview');box.setAttribute('aria-labelledby','plan-preview-title');
    const title=node('h3','확정 전 후보 · 가격 확인 중');title.id='plan-preview-title';
    box.append(title,node('p','가격과 필수 조건을 확인하면 코스가 확정돼요. 확인 뒤 빠지거나 바뀐 후보가 있으면 무엇이 달라졌는지 알려 드려요. 저장·공유·장소 바꾸기는 확정된 뒤에 할 수 있어요.','hint'));
    const list=node('ol',undefined,'plan-preview-list');
    options.forEach((option,i)=>{
      const item=node('li',undefined,'plan-preview-card'),label=node('span',`후보 ${i+1}`,'option-label');
      if(option.purpose)label.append(node('span',' · '+option.purpose,'option-purpose'));
      item.append(label,node('strong',this.route(option.places),'option-route'),node('span','비용 · 가격 확인 중','plan-preview-pending'));
      list.append(item);
    });
    box.append(list);this.remove();root.prepend(box);
    return true;
  },
  // 확정된 코스와 확정 전 후보를 장소 id 로 맞춰 본다. 달라진 것만 적고, 서버가 알려 주지 않은 이유는 지어내지 않는다.
  compare(result){
    const options=this.options||[],plans=result?.plans||[];this.changes=[];this.result=result;
    this.planKey=plans.map(p=>p.id).join('|');
    const ids=places=>places.map(p=>p.id),set=places=>ids(places).sort().join('|');
    options.forEach((option,i)=>{
      const j=plans.findIndex(plan=>set(plan.places)===set(option.places));
      if(j<0){this.changes.push(`후보 ${i+1}(${this.route(option.places)}) · 최종 코스에서 빠졌어요.`);return;}
      const plan=plans[j],parts=[];
      if(j!==i)parts.push(`코스 ${j+1} 자리로 옮겼어요`);
      if(ids(plan.places).join('|')!==ids(option.places).join('|'))parts.push('방문 순서가 바뀌었어요');
      if((plan.option_purpose||'')!==(option.purpose||''))parts.push(`이름이 ‘${option.purpose||'없음'}’에서 ‘${plan.option_purpose||'없음'}’(으)로 바뀌었어요`);
      if(parts.length)this.changes.push(`후보 ${i+1} · `+parts.join(' · ')+'.');
    });
    if(options.length)plans.forEach((plan,j)=>{if(!options.some(option=>set(option.places)===set(plan.places)))this.changes.push(`코스 ${j+1}(${this.route(plan.places)}) · 가격 확인 뒤 새로 들어온 코스예요.`);});
    return this.changes;
  },
  // renderResults 가 부른다. 이 검색의 결과를 보여 줄 때만(코스를 바꾸거나 다른 결과로 바뀌면 보이지 않음).
  notice(result){
    if(!this.changes.length)return null;
    const current=typeof plans!=='undefined'?plans:[];
    if(current.length?current.map(p=>p.id).join('|')!==this.planKey:result!==this.result)return null;
    const box=node('div',undefined,'plan-preview-changes');
    box.append(node('strong','가격 확인 전에 보여 드린 후보와 달라진 점'));
    const list=node('ul');this.changes.forEach(text=>list.append(node('li',text)));box.append(list);
    return box;
  },
  // 완료 안내(role=status)에 덧붙일 말.
  summary(){return this.changes.length?' · 가격 확인 전 후보와 달라진 점이 있어요':'';},
  // 실패·취소 때: 확정 전 후보를 지우고, 확정되지 않았다는 것을 실패 안내에 함께 적는다.
  abandon(){const shown=!!document.querySelector('#results .plan-preview');this.reset();return shown;}
};
const PlanSearch={
  key:'datemate-active-search',
  generation:0,
  // 축제 구역용 조건(지역·방문일, 고른 축제)도 같은 탭에 함께 남겨 새로고침 뒤 다시 그린다.
  remember(id,festival){try{sessionStorage.setItem(this.key,id);if(festival)sessionStorage.setItem(this.key+'-festival',JSON.stringify(festival));else sessionStorage.removeItem(this.key+'-festival');}catch{}},
  forget(){try{sessionStorage.removeItem(this.key);sessionStorage.removeItem(this.key+'-festival');}catch{}},
  pending(){try{return sessionStorage.getItem(this.key);}catch{return null;}},
  festival(){try{return JSON.parse(sessionStorage.getItem(this.key+'-festival'))||null;}catch{return null;}},
  async wait(id){
    const generation=++this.generation;
    const controller=new AbortController();this.controller=controller;
    const deadline=Date.now()+300000;let failures=0;let seen=null;let shown='';
    PlanPreview.reset();
    while(Date.now()<deadline){
      let state;const asked=Date.now();
      // 긴 폴링: 마지막으로 본 단계를 보내면 서버가 단계가 바뀔 때까지 최대 8초 기다렸다 답한다(app/plan_jobs.py).
      const query=seen===null?'':'?wait=8&stage='+encodeURIComponent(seen);
      try{state=await api('/plan-jobs/'+encodeURIComponent(id)+query,undefined,undefined,{signal:controller.signal});failures=0;}
      catch(error){
        if(generation!==this.generation)throw Error('검색을 취소했어요.');
        if([404,410].includes(error.status)){this.forget();throw error;}
        if(++failures>=3)throw error;
        const copy=document.querySelector('#progress .search-progress-copy');
        if(copy)copy.append(node('small','연결을 다시 확인하고 있어요. 검색 요청은 중복하지 않아요.'));
        await new Promise(resolve=>setTimeout(resolve,1500));continue;
      }
      if(generation!==this.generation)throw Error('검색을 취소했어요.');
      if(state.status==='complete'){this.forget();PlanPreview.compare(state.result);return state.result;}
      if(state.status==='cancelled'){this.forget();throw Error(state.message);}
      if(state.status==='failed'){this.forget();throw Error(state.message);}
      const options=state.preview_options?.length?state.preview_options:null;
      if(options)PlanPreview.show(options);
      // 진행 안내(role=status)는 내용이 바뀔 때만 다시 그린다. 같은 단계의 응답마다 다시 그리면 화면 낭독기가 같은 말을 되풀이한다.
      const copy=document.querySelector('#progress .search-progress-copy');
      const text=JSON.stringify([state.stage,state.message,options?options.length:state.preview||null]);
      if(copy&&(text!==shown||copy.querySelector(':scope>small+small'))){
        shown=text;
        copy.replaceChildren(node('strong',state.stage),node('p',state.message),node('small','장소 검색 → 코스 구성 → 가격 확인 · 사진과 후기는 따로 불러와요.'));
        if(options)copy.append(node('p',`찾은 후보 ${options.length}개를 아래에 먼저 보여 드려요. 가격 확인이 끝나면 확정돼요.`,'candidate-preview'));
        else if(state.preview?.length){const preview=node('div',undefined,'candidate-preview');preview.append(node('strong','찾은 후보 · 최종 확인 후 달라질 수 있어요'));state.preview.forEach((names,i)=>preview.append(node('p',`${i+1}. ${names.join(' → ')}`)));copy.append(preview);}
      }
      // 단계가 바뀌었으면 바로 다음 대기를 건다. 같은 단계로 1초 안에 돌아왔으면(기다려 주지 않는 서버) 전처럼 1초 쉰다.
      const changed=state.stage!==seen;seen=state.stage;
      if(!changed&&Date.now()-asked<1000)await new Promise(resolve=>setTimeout(resolve,1000));
    }
    throw Error('검색이 오래 걸리고 있어요. 새로고침하면 진행 중인 검색에 다시 연결합니다.');
  },
  async cancel(){
    this.generation++;this.controller?.abort();
    const id=this.pending();if(!id)return;
    await api('/plan-jobs/'+encodeURIComponent(id),null,'DELETE');
    this.forget();
  }
};
async function createPlanWithProgress(data,festival){
  const generation=PlanSearch.generation;
  const job=await api('/plan-jobs',data);
  if(generation!==PlanSearch.generation){await api('/plan-jobs/'+encodeURIComponent(job.id),null,'DELETE');throw Error('검색을 취소했어요.');}
  PlanSearch.remember(job.id,festival);return PlanSearch.wait(job.id);
}
async function resumePlanSearch(){
  const id=PlanSearch.pending();if(!id||new URLSearchParams(location.search).has('plan'))return;
  const submit=document.querySelector('#submit-plan');submit.disabled=true;
  beginPlanSearch();setTab(false);showPlannerPage(true);
  // 새 추천 때처럼 축제는 코스 검색과 나란히 조회한다. 조건이 남아 있지 않으면 받은 코스의 조건으로 조회한다.
  const festival=PlanSearch.festival();
  try{if(festival)FestivalPanel.restore(festival);}catch{}
  try{
    const result=await PlanSearch.wait(id);plans=result.plans;selected=plans[0]||null;
    try{if(!festival&&selected)FestivalPanel.restore(selected.conditions);}catch{}
    renderResults(result);renderDetail();document.querySelector('#progress').textContent=`검색 복원 완료 · ${plans.length}개 일정`+PlanPreview.summary();
  }catch(error){showSearchFailure(error);}
  finally{submit.disabled=false;document.querySelector('#progress').classList.remove('is-searching');document.querySelector('#results').setAttribute('aria-busy','false');}
}
function showSearchFailure(error){
  const root=document.querySelector('#progress');root.replaceChildren(node('strong','검색을 완료하지 못했어요'),node('p',error.message));
  if(PlanPreview.abandon())root.append(node('p','가격 확인 전에 보여 드린 후보는 확정되지 않아 지웠어요.','hint'));
  root.append(button('조건 확인하고 다시 검색',()=>showPlannerPage(false)));
  document.querySelector('#result-count').textContent='다시 검색할 수 있어요';
}
