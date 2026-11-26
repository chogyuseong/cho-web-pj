/* 빠른 검색(⌘K / Ctrl+K) 명령 팔레트 — 2026-11-26 사용자 시안(Gemini Canvas, Downloads\datemate-시안-2026-11-26)의 '빠른 검색 ⌘K'.
   머리글 오른쪽 단추(#quick-search-open) 또는 Cmd/Ctrl+K 로 연다. 입력하면 아래 네 묶음을 거른다:
     · 페이지: 코스 만들기·테마 추천·장소 둘러보기·코스 결과·피드백 → 머리글 메뉴(#nav-*)를 누르는 것과 같다.
     · 상황 테마: 테마 구역의 카드(.curation-card[data-situation]) → 그 카드를 누르는 것과 같다(theme-cards.js pickSituation).
     · 인기 동네: 코스 만들기의 동네 칩(.area-group 안 단추) → 그 칩을 누르는 것과 같다(simple-form.js HOTSPOTS).
     · 시·도: '전국 17 시·도' 고르기(.region-pick select) → 그 값을 고르는 것과 같다(중심가 위치 검색이 이어진다).
   새 동작을 만들지 않고 화면에 이미 있는 단추·칸을 대신 눌러서, 그쪽 규칙(서버 준비 기다리기, 토스트, 배너)이 그대로 적용된다.
   그래서 목록은 열 때마다 화면에서 다시 읽는다 — 테마 카드·동네 칩을 더하거나 이름을 바꾸면 여기는 고칠 필요가 없다.
   키보드: ↑↓ 로 고르고 Enter 로 실행, Esc(대화상자 기본 동작)로 닫는다. 화면 읽기: 입력칸이 combobox, 목록이 listbox(aria-activedescendant).
   안 한 것: 초성 검색(ㅅㅅ → 성수), 최근 검색 기억 — 필요하면 matches() 와 open() 에 더한다. 테스트 tests/test_quick_search_ui.py. */
(() => {
  const header = document.querySelector('body > header');
  if (!header || document.getElementById('quick-search-open')) return;
  const mac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
  const SEARCH_ICON = '<svg class="quick-search-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>';

  // 머리글 단추: 데스크톱은 '빠른 검색 ⌘K', 휴대폰(720px 이하)은 돋보기만(redesign.css 17)).
  const opener = document.createElement('button');
  opener.type = 'button';
  opener.id = 'quick-search-open';
  opener.className = 'quick-search-open';
  opener.setAttribute('aria-haspopup', 'dialog');
  opener.setAttribute('aria-keyshortcuts', 'Control+K Meta+K');
  opener.setAttribute('aria-label', '빠른 검색 (' + (mac ? '⌘K' : 'Ctrl+K') + ')');
  opener.innerHTML = SEARCH_ICON + '<span class="quick-search-label">빠른 검색</span><kbd aria-hidden="true">' + (mac ? '⌘K' : 'Ctrl K') + '</kbd>';
  const modeSwitch = document.getElementById('mode-switch');
  if (modeSwitch) modeSwitch.before(opener); else header.append(opener);

  const dialog = document.createElement('dialog');
  dialog.id = 'quick-search';
  dialog.className = 'quick-search';
  dialog.setAttribute('aria-label', '빠른 검색');
  dialog.innerHTML = '<div class="quick-search-bar">' + SEARCH_ICON +
    '<input id="quick-search-input" type="search" autocomplete="off" enterkeyhint="go" role="combobox" aria-expanded="true" aria-autocomplete="list" aria-controls="quick-search-list" aria-label="동네·상황·페이지 검색" placeholder="동네, 상황, 페이지 검색 (예: 성수, 비 오는 날, 둘러보기)">' +
    '<button type="button" class="quick-search-close" aria-label="빠른 검색 닫기">Esc</button></div>' +
    '<ul id="quick-search-list" class="quick-search-list" role="listbox" aria-label="검색 결과"></ul>' +
    '<p class="quick-search-help" aria-hidden="true">↑↓ 이동 · Enter 열기 · Esc 닫기</p>';
  document.body.append(dialog);
  const input = dialog.querySelector('input');
  const list = dialog.querySelector('ul');
  let items = [], shown = [], active = -1;

  const click = el => el && el.click();
  const text = el => (el?.textContent || '').replace(/\s+/g, ' ').trim();
  // 열 때마다 화면에서 항목을 다시 모은다(위 설명). keywords 는 걸러 낼 때만 쓰는 다른 이름.
  function collect() {
    const out = [];
    const page = (label, id, keywords) => { const el = document.getElementById(id); if (el) out.push({ group: '페이지', label, keywords, run: () => click(el) }); };
    page('코스 만들기', 'nav-plan', '조건 추천 만들기 시작');
    page('테마 추천', 'nav-home', '테마 큐레이션 처음');
    page('장소 둘러보기', 'nav-explore', '둘러보기 탐색 장소 팝업');
    if (typeof plans !== 'undefined' && plans.length) page('코스 결과', 'nav-results', '결과 일정 비교');
    const feedback = document.getElementById('nav-feedback');
    if (feedback) out.push({ group: '페이지', label: '피드백', keywords: '의견 문의', run: () => { location.href = feedback.href; } });
    document.querySelectorAll('.curation-card[data-situation]').forEach(card => {
      const title = text(card.querySelector('.curation-mood')) || text(card);
      out.push({ group: '상황 테마', label: title, keywords: text(card), run: () => click(card) });
    });
    const seen = new Set();
    document.querySelectorAll('.area-group .quick-chips button').forEach(chip => {
      const label = text(chip);
      if (!label || seen.has(label) || /현재 위치/.test(label)) return;
      seen.add(label);
      out.push({ group: '인기 동네', label, keywords: label.replace(/·/g, ' '), run: () => { click(document.getElementById('nav-plan')); click(chip); } });
    });
    const select = document.querySelector('.region-pick select');
    if (select) [...select.options].filter(o => o.value).forEach(o => out.push({
      group: '시·도', label: o.value + ' (시·도)', keywords: o.value,
      run: () => { click(document.getElementById('nav-plan')); select.value = o.value; select.dispatchEvent(new Event('change', { bubbles: true })); }
    }));
    return out;
  }
  const norm = s => String(s || '').toLowerCase().replace(/[\s·()]/g, '');
  function matches(item, q) { return !q || norm(item.label).includes(q) || norm(item.keywords).includes(q) || norm(item.group).includes(q); }

  function render() {
    const q = norm(input.value);
    shown = items.filter(item => matches(item, q));
    list.replaceChildren();
    if (!shown.length) {
      const empty = document.createElement('li');
      empty.className = 'quick-search-empty';
      empty.setAttribute('role', 'presentation');
      empty.textContent = '맞는 항목이 없어요. 동네 이름이나 상황(예: 실내, 야경)으로 찾아보세요.';
      list.append(empty);
      setActive(-1);
      return;
    }
    let group = '';
    shown.forEach((item, i) => {
      if (item.group !== group) {
        group = item.group;
        const head = document.createElement('li');
        head.className = 'quick-search-group';
        head.setAttribute('role', 'presentation');
        head.textContent = group;
        list.append(head);
      }
      const li = document.createElement('li');
      li.id = 'quick-search-option-' + i;
      li.className = 'quick-search-option';
      li.setAttribute('role', 'option');
      li.textContent = item.label;
      li.addEventListener('mousedown', event => event.preventDefault()); // 입력칸 포커스를 지킨다
      li.addEventListener('click', () => choose(i));
      li.addEventListener('mousemove', () => { if (active !== i) setActive(i); });
      list.append(li);
    });
    setActive(0);
  }
  function setActive(i) {
    active = i;
    list.querySelectorAll('[role=option]').forEach(li => li.setAttribute('aria-selected', String(li.id === 'quick-search-option-' + i)));
    const el = document.getElementById('quick-search-option-' + i);
    if (el) { input.setAttribute('aria-activedescendant', el.id); el.scrollIntoView({ block: 'nearest' }); }
    else input.removeAttribute('aria-activedescendant');
  }
  function choose(i) {
    const item = shown[i];
    if (!item) return;
    close();
    // 대화상자가 닫히고 포커스가 돌아간 뒤에 누른다 — 누른 결과(스크롤·포커스 이동)가 대화상자 닫기에 덮이지 않게.
    requestAnimationFrame(() => item.run());
  }
  function open() {
    if (dialog.open) return;
    items = collect();
    input.value = '';
    render();
    dialog.showModal();
    input.focus();
  }
  function close() { if (dialog.open) dialog.close(); }

  opener.addEventListener('click', open);
  dialog.querySelector('.quick-search-close').addEventListener('click', close);
  // 바깥(배경)을 누르면 닫는다 — dialog 자신이 눌린 것은 상자 밖 여백뿐이다.
  dialog.addEventListener('click', event => { if (event.target === dialog) close(); });
  dialog.addEventListener('close', () => opener.focus({ preventScroll: true }));
  input.addEventListener('input', render);
  input.addEventListener('keydown', event => {
    if (event.isComposing || event.keyCode === 229) return; // 한글 조합 중 Enter·화살표는 글자 확정용
    if (event.key === 'ArrowDown') { event.preventDefault(); if (shown.length) setActive((active + 1) % shown.length); }
    else if (event.key === 'ArrowUp') { event.preventDefault(); if (shown.length) setActive((active - 1 + shown.length) % shown.length); }
    else if (event.key === 'Enter') { event.preventDefault(); choose(active); }
    // 검색칸(type=search)에서 Esc 는 글자 지우기로 먼저 쓰여 대화상자가 닫히지 않는다 — 바로 닫는다(글자를 지우려면 지우기 단추나 Backspace).
    else if (event.key === 'Escape') { event.preventDefault(); close(); }
  });
  addEventListener('keydown', event => {
    if ((event.metaKey || event.ctrlKey) && !event.altKey && !event.shiftKey && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      if (dialog.open) close(); else open();
    }
  });
  window.QuickSearch = { open, close };
})();
