/* 모바일 폭에서 지금 보고 있는 구역의 소제목을 상단 헤더 바로 아래에 보여준다.
   화면 읽기 프로그램은 본문의 실제 제목을 읽으므로 이 줄은 aria-hidden으로 둔다. */
(() => {
  const media = matchMedia('(max-width: 800px)');
  const selector = 'main h2, main h3, main legend, main .timeline-card h4, #plan-map-rail h2';
  const bar = document.createElement('div');
  bar.className = 'section-indicator';
  bar.setAttribute('aria-hidden', 'true');
  const parent = document.createElement('span');
  parent.className = 'section-indicator-parent';
  const current = document.createElement('strong');
  current.className = 'section-indicator-current';
  bar.append(parent, current);
  document.body.append(bar);
  let frame = 0;

  function headingText(heading) {
    // '필수' 표시 같은 보조 배지는 빼고 제목 글자만 쓴다.
    return [...heading.childNodes]
      .filter(child => !(child.nodeType === 1 && child.matches('.field-requirement,.tag,.selection-indicator')))
      .map(child => child.textContent).join('').replace(/\s+/g, ' ').trim();
  }

  function update() {
    frame = 0;
    if (!media.matches) {
      bar.classList.remove('is-visible');
      return;
    }
    const header = document.querySelector('body > header');
    const headerBottom = Math.max(0, header ? header.getBoundingClientRect().bottom : 0);
    // 헤더가 줄바꿈되거나 일부만 보일 때도 바로 아래에 붙도록 실제 위치를 쓴다.
    bar.style.top = headerBottom + 'px';
    const line = headerBottom + 12;
    let active = null,
      section = null,
      activeTop = -Infinity,
      sectionTop = -Infinity;
    for (const heading of document.querySelectorAll(selector)) {
      // 닫힌 접힘 안의 제목은 브라우저에 따라 상자가 남아 있어도 보이지 않으므로 건너뛴다.
      if (heading.closest('dialog,.hero,details:not([open])')) continue;
      const rects = heading.getClientRects();
      // 숨겨졌거나 닫힌 펼침 안의 제목은 건너뛴다.
      if (!rects.length) continue;
      const top = rects[0].top;
      if (top > line) continue;
      if (top >= activeTop) {
        active = heading;
        activeTop = top;
      }
      if (heading.tagName === 'H2' && top >= sectionTop) {
        section = heading;
        sectionTop = top;
      }
    }
    const text = active ? headingText(active) : '';
    if (!text) {
      bar.classList.remove('is-visible');
      return;
    }
    // 축제·부가 정보 구역은 상세(h2) 밖에 있으므로 위쪽 h2를 상위 이름으로 붙이지 않는다.
    const own = active?.closest('#festival-section,#plan-extras');
    const context = section && section !== active && (!own || own.contains(section)) ? headingText(section) : '';
    parent.textContent = context;
    parent.hidden = !context;
    current.textContent = text;
    bar.classList.add('is-visible');
  }

  function schedule() {
    if (!frame) frame = requestAnimationFrame(update);
  }
  window.addEventListener('scroll', schedule, {
    passive: true
  });
  window.addEventListener('resize', schedule);
  if (media.addEventListener) media.addEventListener('change', schedule);
  schedule();
})();
