const PlanSearch={
  key:'datemate-active-search',
  remember(id){try{sessionStorage.setItem(this.key,id);}catch{}},
  forget(){try{sessionStorage.removeItem(this.key);}catch{}},
  pending(){try{return sessionStorage.getItem(this.key);}catch{return null;}},
  async wait(id){
    const deadline=Date.now()+300000;let failures=0;
    while(Date.now()<deadline){
      let state;
      try{state=await api('/plan-jobs/'+encodeURIComponent(id));failures=0;}
      catch(error){
        if(++failures>=3){this.forget();throw error;}
        const copy=document.querySelector('#progress .search-progress-copy');
        if(copy)copy.append(node('small','연결을 다시 확인하고 있어요. 검색 요청은 중복하지 않아요.'));
        await new Promise(resolve=>setTimeout(resolve,1500));continue;
      }
      if(state.status==='complete'){this.forget();return state.result;}
      if(state.status==='failed'){this.forget();throw Error(state.message);}
      const copy=document.querySelector('#progress .search-progress-copy');
      if(copy){
        copy.replaceChildren(node('strong',state.stage),node('p',state.message),node('small','장소 검색 → 코스 구성 → 가격 확인 · 사진과 후기는 따로 불러와요.'));
        if(state.preview?.length){const preview=node('div',undefined,'candidate-preview');preview.append(node('strong','찾은 후보 · 최종 확인 후 달라질 수 있어요'));state.preview.forEach((names,i)=>preview.append(node('p',`${i+1}. ${names.join(' → ')}`)));copy.append(preview);}
      }
      await new Promise(resolve=>setTimeout(resolve,1000));
    }
    throw Error('검색이 오래 걸리고 있어요. 새로고침하면 진행 중인 검색에 다시 연결합니다.');
  }
};
async function createPlanWithProgress(data){const job=await api('/plan-jobs',data);PlanSearch.remember(job.id);return PlanSearch.wait(job.id);}
async function resumePlanSearch(){
  const id=PlanSearch.pending();if(!id||new URLSearchParams(location.search).has('plan'))return;
  const submit=document.querySelector('#submit-plan');submit.disabled=true;
  beginPlanSearch();setTab(false);showPlannerPage(true);
  try{
    const result=await PlanSearch.wait(id);plans=result.plans;selected=plans[0]||null;
    renderResults(result);renderDetail();document.querySelector('#progress').textContent=`검색 복원 완료 · ${plans.length}개 일정`;
  }catch(error){showSearchFailure(error);}
  finally{submit.disabled=false;document.querySelector('#progress').classList.remove('is-searching');document.querySelector('#results').setAttribute('aria-busy','false');}
}
function showSearchFailure(error){
  const root=document.querySelector('#progress');root.replaceChildren(node('strong','검색을 완료하지 못했어요'),node('p',error.message));
  root.append(button('조건 확인하고 다시 검색',()=>showPlannerPage(false)));
  document.querySelector('#result-count').textContent='다시 검색할 수 있어요';
}
