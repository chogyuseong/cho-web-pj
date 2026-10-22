(()=>{
  let region='성수',mood='편안한 데이트';
  const points={성수:{name:'성수역 지역 중심',lat:37.5446,lon:127.0559},연남:{name:'홍대입구역 지역 중심',lat:37.5572,lon:126.9254},종로:{name:'안국역 지역 중심',lat:37.5765,lon:126.9855},강남:{name:'강남역 지역 중심',lat:37.4979,lon:127.0276}};
  const regions=document.querySelectorAll('[data-region]'),moods=document.querySelectorAll('[data-quick-mood]');
  function sync(){regions.forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.region===region)));moods.forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.quickMood===mood)));}
  regions.forEach(b=>b.onclick=()=>{region=b.dataset.region;sync();});
  moods.forEach(b=>{if(b.dataset.quickMood==='활동적인 데이트')b.dataset.quickMood='활동적인';b.onclick=()=>{mood=b.dataset.quickMood;sync();};});
  const slider=document.getElementById('quick-budget'),budget=form.elements.budget;
  function displayBudget(){document.getElementById('quick-budget-value').textContent=Number(budget.value).toLocaleString('ko-KR')+'원';slider.value=budget.value;}
  slider.oninput=()=>{budget.value=slider.value;budget.dispatchEvent(new Event('input',{bubbles:true}));displayBudget();};
  budget.addEventListener('input',displayBudget);form.addEventListener('change',displayBudget);
  document.getElementById('quick-start').onclick=()=>{
    if(!document.querySelector('[name=themes]')){toast('장소 정보를 준비 중이에요. 잠시 후 다시 눌러 주세요.');return;}
    if(form.elements.mode.value!=='real'){form.elements.mode.value='real';form.elements.mode.dispatchEvent(new Event('change',{bubbles:true}));}
    locationState.origin={...points[region]};form.elements.origin_name.value=points[region].name;
    setDateClassification(['사교적인','활동적인'].includes(mood)?'타입별':'콘셉트별',mood);
    document.getElementById('nav-plan').click();

    form.requestSubmit();
  };
  document.querySelectorAll('[data-preset]').forEach(b=>b.onclick=()=>{region=b.dataset.preset;mood=region==='연남'?'편안한 데이트':'지적인 데이트';sync();document.querySelector('.quick-builder').scrollIntoView({behavior:'smooth',block:'center'});toast(region+'에서 시작하는 취향을 골랐어요. 예산을 확인하고 코스를 만들어 보세요.');});
})();
