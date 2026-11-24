// 홈의 '테마로 고르는 하루' 카드(data-preset 도 있음)는 theme-cards.js 가 지역까지 채워 처리한다. 여기서 또 처리하면 분류를 두 번 정하고
// 토스트가 겹쳤다(2026-11-24 UX P0). 그래서 클릭은 지역 없는 분위기 단추에만 붙이고, 눌림 표시(aria-pressed)는 모두에 맞춘다.
document.querySelectorAll('[data-mood]').forEach(button=>{
  button.setAttribute('aria-pressed','false');
  if(button.hasAttribute('data-preset'))return;
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


// The navigation wraps on mobile; use its measured height for anchor/map offsets.
(() => {
  const header = document.querySelector('body > header');
  if (!header) return;
  const measure = () => document.documentElement.style.setProperty(
    '--site-header-height', Math.ceil(header.getBoundingClientRect().height) + 'px'
  );
  measure();
  if ('ResizeObserver' in window) new ResizeObserver(measure).observe(header);
  else window.addEventListener('resize', measure);
  // compactHeader: 800px 이하에서 아래로 읽는 동안 소개 문구를 숨겨 머리말을 낮춘다(shell.css header.is-compact).
  // 160px 넘게 내려가면 붙이고 40px 이내로 돌아오면 뗀다. 두 값 사이에서는 그대로 둬 경계에서 깜빡이지 않는다.
  const narrow = window.matchMedia('(max-width:800px)');
  let ticking = false;
  const compact = () => {
    ticking = false;
    const y = window.scrollY;
    if (!narrow.matches || y < 40) header.classList.remove('is-compact');
    else if (y > 160) header.classList.add('is-compact');
  };
  window.addEventListener('scroll', () => {
    if (!ticking) {
      ticking = true;
      requestAnimationFrame(compact);
    }
  }, {passive: true});
  narrow.addEventListener?.('change', compact);
  compact();
})();
