/* 머리글(2026-11-25 사용자 시안 Downloads/screencapture-gemini-*.png, 가이드 datemate_2026.md §2.1).
   1) 메뉴 표시: '홈 · 테마'·'코스 만들기'·'장소 둘러보기' 가운데 지금 보는 곳 하나만 진한 알약으로.
      - 장소 둘러보기: body.show-explore(app.js setTab).
      - 코스 만들기: 결과 화면(body.show-date-plan)이거나, 조건 화면(#planner-section) 위쪽이 화면 가운데보다 위로 올라왔을 때.
      - 나머지(히어로·테마 구역)는 홈 · 테마.
      화면 읽기 프로그램에는 단추는 aria-pressed, 홈 링크는 aria-current 로 알린다. app.js setTab 이 끝에 syncHeaderNav() 를 부른다.
   2) 데이트 / 여행 스위치: body.mode-travel 로 포인트 색(redesign.css 8)), 히어로 제목·설명·입력 예시, 바로 시작 칩(theme-cards.js
      renderHeroQuick), 테마 구역의 첫 탭을 바꾼다.
      2026-11-25 사용자 결정('여행 기본 조건 적용'): 여행을 고르면 조건 화면의 기본값도 하루 여행에 맞춘다(TRIP_DEFAULTS — 10:00~20:00,
      장소 5곳, 구간 이동 60분, 장소당 75분, 식사 포함). 데이트로 돌아가면 처음 화면의 값(dateDefaults)으로 되돌린다.
      사용자가 직접 바꾼 칸(touched)은 어느 쪽으로도 건드리지 않는다. 오늘 날짜인데 10시가 이미 지났으면 시작·종료는 그대로 둔다(지난 시각 금지).
      서버 조건 이름·계산은 그대로다 — 기본값만 바뀌므로 데이트 모드에서도 같은 값을 직접 넣으면 같은 코스가 나온다.
      고른 모드는 이 브라우저에만 기억한다(localStorage 'datemate-mode', 못 쓰면 매번 데이트로 시작).
   바꿀 때 함께 볼 곳: index.html 머리글·히어로 문구, redesign.css 2)·8), tests/test_redesign_mockup_ui.py. */
(() => {
  const body = document.body;
  const home = document.getElementById('nav-home'), plan = document.getElementById('nav-plan'), explore = document.getElementById('nav-explore');
  const planner = document.getElementById('planner-section');

  // 메뉴를 눌러 옮겨 가는 중에는 누른 메뉴를 바로 표시한다(스크롤은 다음 그림 때 일어나 위치로 판단하면 한 박자 늦다).
  // 사용자가 직접 스크롤하면(휠·터치·키) 다시 위치로 판단한다.
  let intent = null;
  home?.addEventListener('click', () => { intent = 'home'; window.syncHeaderNav(); });
  plan?.addEventListener('click', () => { intent = 'plan'; window.syncHeaderNav(); });
  for (const type of ['wheel', 'touchmove', 'keydown']) addEventListener(type, () => { intent = null; }, { passive: true });
  function current() {
    if (body.classList.contains('show-explore')) return 'explore';
    if (body.classList.contains('show-date-plan')) return 'plan';
    if (intent) return intent;
    if (planner && !planner.hidden) {
      const top = planner.getBoundingClientRect().top;
      if (top < innerHeight * 0.5) return 'plan';
    }
    return 'home';
  }
  let last = '';
  function syncHeaderNav() {
    const now = current();
    if (now === last) return;
    last = now;
    if (home) {
      home.classList.toggle('active', now === 'home');
      if (now === 'home') home.setAttribute('aria-current', 'true'); else home.removeAttribute('aria-current');
    }
    // 휴대폰 하단 바의 '코스 결과'는 결과 화면(body.show-date-plan)에 있는 동안 눌린 상태.
    const results = document.getElementById('nav-results');
    if (results) { const on = body.classList.contains('show-date-plan'); results.classList.toggle('active', on); results.setAttribute('aria-pressed', String(on)); }
    for (const [button, key] of [[plan, 'plan'], [explore, 'explore']]) {
      if (!button) continue;
      button.classList.toggle('active', now === key);
      button.setAttribute('aria-pressed', String(now === key));
    }
  }
  // 강제로 다시 맞춘다(app.js setTab 이 클래스를 바꾼 뒤 부른다 — 같은 상태라도 단추 클래스를 되돌려 놓는다).
  window.syncHeaderNav = () => { last = ''; syncHeaderNav(); };
  let frame = 0;
  addEventListener('scroll', () => { if (!frame) frame = requestAnimationFrame(() => { frame = 0; syncHeaderNav(); }); }, { passive: true });
  addEventListener('resize', () => syncHeaderNav());
  addEventListener('hashchange', () => requestAnimationFrame(window.syncHeaderNav));
  new MutationObserver(() => syncHeaderNav()).observe(body, { attributes: true, attributeFilter: ['class'] });
  window.syncHeaderNav();
  // '코스 결과'(휴대폰 하단 바): 만든 코스가 있으면 결과 화면으로, 없으면 조건 화면으로 옮기고 알린다. plans 는 app.js 의 전역 목록.
  document.getElementById('nav-results')?.addEventListener('click', () => {
    if (typeof plans !== 'undefined' && plans.length) { setTab(false); showPlannerPage(true); }
    else { navigateHomeSection('#planner-section'); if (typeof toast === 'function') toast('아직 만든 코스가 없어요. 조건을 고르고 3가지 코스를 비교해 보세요.'); }
  });

  // ---------- 데이트 / 여행 ----------
  const COPY = {
    date: { title: ['어디서', '만날까요?'], description: '원하는 하루를 한 줄로 적거나 아래에서 골라 보세요. 지역·시간·예산에 맞는 코스 3개를 비교해요.',
      placeholder: '예: 비 오는 날 성수에서 덜 걷고 분위기 좋은 저녁 코스', shortPlaceholder: '예: 성수 실내 데이트' },
    travel: { title: ['어디로', '떠날까요?'], description: '가고 싶은 여행지를 한 줄로 적거나 아래에서 골라 보세요. 이동 수단·시간·예산에 맞는 코스 3개를 비교해요.',
      placeholder: '예: 강릉에서 바다 보며 드라이브하고 저녁은 시장에서', shortPlaceholder: '예: 강릉 바다 여행' }
  };
  // 히어로 입력칸 안내 문구(2026-11-26 사용자 지적: 휴대폰에서 '…덜 걷고' 근처에서 잘림).
  // 휴대폰 폭에서는 「코스 찾기」 단추와 한 줄을 나눠 칸이 좁다(390px 폭 → 칸 224px, 320px → 154px, 긴 문구는 약 335~356px).
  // 화면 폭 기준값 대신 실제 칸 폭과 문구 폭을 재서, 긴 문구가 안 들어가면 shortPlaceholder 를 쓴다(태블릿·두 칸 배치도 같은 규칙).
  // 짧은 문구는 320px 폭(칸 154px)에서 여유가 있게 골랐다(약 110~120px). 바꾸면 tests/test_hero_placeholder_ui.py 의 폭 검사가 지켜 준다.
  // 그래도 넘치는 글꼴이면 redesign.css 4) 의 text-overflow:ellipsis 가 '…'로 끝낸다.
  // 안 한 것: 두 줄로 감싸기(input 은 줄바꿈이 안 되고, textarea 로 바꾸면 Enter 로 찾기·막대 높이가 달라진다).
  const heroInput = document.getElementById('hero-command-input');
  const measureCtx = document.createElement('canvas').getContext('2d');
  function syncHeroPlaceholder() {
    if (!heroInput) return;
    const copy = COPY[body.classList.contains('mode-travel') ? 'travel' : 'date'];
    const style = getComputedStyle(heroInput);
    let fits = true;
    if (measureCtx && heroInput.clientWidth > 0) {
      measureCtx.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
      fits = measureCtx.measureText(copy.placeholder).width <= heroInput.clientWidth;
    }
    const next = fits ? copy.placeholder : copy.shortPlaceholder;
    if (heroInput.placeholder !== next) heroInput.placeholder = next;
  }
  if (heroInput && typeof ResizeObserver === 'function') new ResizeObserver(() => syncHeroPlaceholder()).observe(heroInput);
  else addEventListener('resize', () => syncHeroPlaceholder());
  // 웹 글꼴(Pretendard)이 늦게 오면 글자 폭이 달라지므로 다 받은 뒤 한 번 더 잰다.
  document.fonts?.ready?.then(() => syncHeroPlaceholder());
  const KEY = 'datemate-mode';
  // 여행 기본값. 칸 이름은 index.html·simple-form.js 의 form 칸(name). 값을 바꾸면 tests/test_travel_mode_ui.py 도 함께 고친다.
  const TRIP_DEFAULTS = { start: '10:00', end: '20:00', count: '5', max_leg: '60', stay_minutes: '75', include_meal: true };
  const tripForm = document.getElementById('conditions'); // 조건 화면 form(id=conditions)
  const fieldOf = name => tripForm?.elements?.[name];
  const valueOf = el => el?.type === 'checkbox' ? el.checked : el?.value;
  // 데이트 기본값: 이 스크립트가 돌 때(조건 화면을 다 그린 뒤, 사용자가 손대기 전)의 값.
  const dateDefaults = Object.fromEntries(Object.keys(TRIP_DEFAULTS).map(name => [name, valueOf(fieldOf(name))]));
  const touched = new Set();
  let applyingDefaults = false;
  for (const type of ['input', 'change']) tripForm?.addEventListener(type, event => {
    if (!applyingDefaults && event.target?.name in TRIP_DEFAULTS) touched.add(event.target.name);
  });
  function tenPassedToday() {
    const date = fieldOf('visit_date')?.value, now = new Date();
    const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    return date === today && now.getHours() * 60 + now.getMinutes() >= 10 * 60;
  }
  // 바꾼 칸의 이름 목록을 돌려준다(알림 문구용). 값을 넣은 뒤 input·change 를 보내 simple-form.js 의 칩·요약이 따라 바뀌게 한다.
  // 그 이벤트로 FormState.edited('사용자가 고른 조건', 자연어 해석보다 우선)에 들어가지 않게 원래 상태로 되돌린다.
  function applyDefaults(mode) {
    if (!tripForm) return [];
    const target = mode === 'travel' ? TRIP_DEFAULTS : dateDefaults, changed = [];
    const before = typeof FormState !== 'undefined' ? new Set(FormState.edited) : null;
    applyingDefaults = true;
    try {
      for (const [name, value] of Object.entries(target)) {
        const el = fieldOf(name);
        if (!el || touched.has(name) || value === undefined || valueOf(el) === value) continue;
        if ((name === 'start' || name === 'end') && mode === 'travel' && tenPassedToday()) continue;
        if (el.type === 'checkbox') el.checked = Boolean(value); else el.value = value;
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        changed.push(name);
      }
    } finally {
      applyingDefaults = false;
      if (before) { FormState.edited.clear(); before.forEach(name => FormState.edited.add(name)); }
    }
    return changed;
  }
  const switcher = document.getElementById('mode-switch');
  function saved() { try { return localStorage.getItem(KEY) === 'travel' ? 'travel' : 'date'; } catch { return 'date'; } }
  function apply(mode, fromUser) {
    body.classList.toggle('mode-travel', mode === 'travel');
    switcher?.querySelectorAll('[data-mode]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.mode === mode)));
    const copy = COPY[mode];
    const h1 = document.querySelector('.hero-copy h1');
    if (h1) h1.replaceChildren(copy.title[0], document.createElement('br'), copy.title[1]);
    const description = document.querySelector('.hero-copy .hero-description');
    if (description) description.textContent = copy.description;
    syncHeroPlaceholder(); // 모드에 맞는 긴/짧은 안내 문구(위 syncHeroPlaceholder)
    if (typeof window.renderHeroQuick === 'function') window.renderHeroQuick(mode);
    // 테마 구역: 여행은 '주말 떠나기 좋은 동네'부터, 데이트는 '오늘의 상황으로 고르기'부터. 사용자가 스위치를 누를 때만 탭을 옮긴다
    // (처음 열 때 여행으로 기억돼 있어도 탭은 옮긴다 — 같은 규칙). 탭 단추 click 은 theme-cards.js 의 탭 동작을 그대로 탄다.
    const tab = document.getElementById(mode === 'travel' ? 'curation-tab-areas' : 'curation-tab-situation');
    if (tab && tab.getAttribute('aria-selected') !== 'true') tab.click();
    const changed = applyDefaults(mode);
    if (fromUser) {
      try { localStorage.setItem(KEY, mode); } catch { /* 저장 못 하면 이번 화면에만 */ }
      const note = changed.length ? (mode === 'travel' ? ' 조건도 하루 여행에 맞췄어요(10:00~20:00 · 5곳 · 구간 60분 · 식사 포함, 직접 바꾼 칸은 그대로).' : ' 조건은 데이트 기본값으로 돌렸어요(직접 바꾼 칸은 그대로).') : '';
      if (typeof toast === 'function') toast((mode === 'travel' ? '여행 모드로 바꿨어요. 떠나기 좋은 동네부터 보여 드려요.' : '데이트 모드로 바꿨어요.') + note);
    }
  }
  switcher?.addEventListener('click', event => {
    const button = event.target.closest('[data-mode]');
    if (button && button.getAttribute('aria-pressed') !== 'true') apply(button.dataset.mode, true);
  });
  if (saved() === 'travel') apply('travel', false);
})();
