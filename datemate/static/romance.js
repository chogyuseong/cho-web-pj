document.querySelectorAll('[data-mood]').forEach(button=>{
  button.setAttribute('aria-pressed','false');
  button.addEventListener('click',()=>{
    if(!document.querySelector('[name=themes]')){toast('데이트 테마를 준비하고 있어요. 잠시 후 다시 골라주세요.');return;}
    const theme=button.dataset.mood;
    setDateClassification(theme==='사교적인'?'타입별':'콘셉트별',theme);
    document.querySelectorAll('[data-mood]').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));
    document.getElementById('nav-plan').click();
    document.getElementById('planner-section').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
    toast(theme+' 테마를 골랐어요. 날짜와 예산을 확인하고 추천받아 보세요.');
  });
});
document.getElementById('conditions').addEventListener('change',event=>{
  if(['themes','date_subcategory'].includes(event.target.name)){
    const selected=form.querySelector('[name=date_subcategory]:checked')?.value;
    document.querySelectorAll('[data-mood]').forEach(button=>button.setAttribute('aria-pressed',String(selected===button.dataset.mood)));
  }
});
