/* 머리글(2026-11-25 사용자 시안 Downloads/screencapture-gemini-*.png, 가이드 datemate_2026.md §2.1).
   1) 메뉴 표시: '홈 · 테마'·'코스 만들기'·'장소 둘러보기' 가운데 지금 보는 곳 하나만 진한 알약으로.
      - 장소 둘러보기: body.show-explore(app.js setTab).
      - 코스 만들기: 결과 화면(body.show-date-plan)이거나, 조건 화면(#planner-section) 위쪽이 화면 가운데보다 위로 올라왔을 때.
      - 나머지(히어로·테마 구역)는 홈 · 테마.
      화면 읽기 프로그램에는 링크·단추 모두 aria-current="true" 로 알린다(QA-11). app.js setTab 이 끝에 syncHeaderNav() 를 부른다.
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
  // '추천 결과' 탭(2026-11-26 요구 문서 Phase 1): 만든 코스가 있으면 데스크톱 메뉴에도 보이고 코스 개수 배지를 단다(redesign.css 19)).
  // plans 는 app.js 의 전역 목록. 결과 화면을 오갈 때 body 클래스가 바뀌며 syncHeaderNav 가 불리므로 여기서 함께 맞춘다.
  function syncResultsTab() {
    const tab = document.getElementById('nav-results');
    if (!tab) return;
    const count = typeof plans !== 'undefined' && Array.isArray(plans) ? plans.length : 0;
    tab.classList.toggle('has-plans', count > 0);
    const badge = tab.querySelector('.nav-count');
    if (badge) { badge.textContent = String(count); badge.hidden = count === 0; }
    tab.setAttribute('aria-label', count ? `추천 결과 · 코스 ${count}개` : '추천 결과');
    placeNavIndicator(); // 탭이 생기거나 사라지면 메뉴 폭이 바뀌어 미끄럼 표시 자리를 다시 잰다.
  }
  window.syncResultsTab = syncResultsTab;
  function syncHeaderNav() {
    syncResultsTab();
    const now = current();
    if (now === last) return;
    last = now;
    // '추천 결과'(휴대폰 하단 바 · 코스가 있으면 데스크톱 메뉴)는 결과 화면(body.show-date-plan)에 있는 동안 현재 위치.
    const results = document.getElementById('nav-results');
    // 결과 화면에서는 '추천 결과'만 현재 위치다(2026-11-26 — 예전에는 결과 화면도 '코스 만들기'가 함께 켜졌다. 결과 탭이 데스크톱에도 생겨 하나로).
    const onResults = body.classList.contains('show-date-plan');
    for (const [item, on] of [[home, now === 'home'], [plan, now === 'plan' && !onResults], [explore, now === 'explore'], [results, onResults]]) {
      if (!item) continue;
      item.classList.toggle('active', on);
      // 현재 위치는 링크·단추 모두 aria-current 하나로 알린다(2026-11-25 운영 QA-11 — 예전에는 단추만 aria-pressed 였다).
      if (on) item.setAttribute('aria-current', 'true'); else item.removeAttribute('aria-current');
      item.removeAttribute('aria-pressed');
    }
    placeNavIndicator();
  }
  // 메뉴 미끄럼 표시(2026-11-26 시안 '상단 내비게이션의 활성 탭 필이 부드럽게 슬라이딩'). 데스크톱 메뉴에서 고른 칸 뒤에 흰 알약 하나를 두고
  // 고른 칸이 바뀌면 그 자리로 옮긴다(redesign.css 17) 의 transition). 표시는 메뉴(nav) 밖, 머리글의 자식으로 둔다 — 메뉴 안 항목 수를
  // 세는 테스트·화면 읽기 순서를 바꾸지 않으려고. 위치 = 메뉴의 위치(offsetLeft/Top, 머리글 기준) + 고른 칸의 위치(메뉴 기준).
  // 휴대폰 하단 바(720px 이하)는 CSS 가 표시를 숨기고 예전 모양을 쓴다.
  function placeNavIndicator() {
    const nav = document.querySelector('body > header nav');
    if (!nav) return;
    let mark = document.querySelector('body > header > .nav-indicator');
    if (!mark) {
      mark = document.createElement('span');
      mark.className = 'nav-indicator';
      mark.setAttribute('aria-hidden', 'true');
      nav.after(mark); // 메뉴 뒤에 둬야 메뉴 바탕(회색) 위, 글자(z-index 1) 아래에 그려진다.
      nav.classList.add('has-indicator');
    }
    const on = nav.querySelector(':scope > .active');
    if (!on || !on.offsetWidth || getComputedStyle(mark).display === 'none') { mark.style.opacity = '0'; return; }
    mark.style.opacity = '1';
    mark.style.width = on.offsetWidth + 'px';
    mark.style.height = on.offsetHeight + 'px';
    mark.style.transform = `translate(${nav.offsetLeft + on.offsetLeft}px, ${nav.offsetTop + on.offsetTop}px)`;
  }
  addEventListener('resize', placeNavIndicator);
  document.fonts?.ready?.then(placeNavIndicator);
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
  // 처음 화면 문구(2026-11-26 시안: 제목 한 줄 '어디서 만날까요?', 설명 '지역·시간·예산만 정하면 …'). 제목은 넓은 화면에서 한 줄, 좁으면 저절로 줄바꿈.
  // placeholder: 한 줄 입력이 코스 만들기 카드 맨 위(simple-form.js .simple-dream 의 textarea)로 옮겨 가서 그 칸에 넣는다.
  //   textarea 라 긴 문구도 줄바꿈되어 잘리지 않는다(예전 히어로 input 의 짧은 문구 바꾸기 syncHeroPlaceholder 는 필요 없어져 뺐다).
  const COPY = {
    date: { title: '어디서 만날까요?', description: '지역·시간·예산만 정하면, 동선과 비용까지 계산된 하루 코스 3개를 비교해요.',
      placeholder: '예: 비 오는 날 성수에서 덜 걷고 분위기 좋은 저녁 코스' },
    travel: { title: '어디로 떠날까요?', description: '여행지·이동 수단·예산만 정하면, 동선과 비용까지 계산된 하루 코스 3개를 비교해요.',
      placeholder: '예: 강릉에서 바다 보며 드라이브하고 저녁은 시장에서' }
  };
  function syncRequestPlaceholder() {
    const request = document.getElementById('conditions')?.elements?.request;
    if (request) request.placeholder = COPY[body.classList.contains('mode-travel') ? 'travel' : 'date'].placeholder;
  }
  window.syncRequestPlaceholder = syncRequestPlaceholder; // simple-form.js 가 카드를 다 그린 뒤 부른다.
  const KEY = 'datemate-mode';
  // 여행 기본값. 칸 이름은 index.html·simple-form.js 의 form 칸(name). 값을 바꾸면 tests/test_travel_mode_ui.py 도 함께 고친다.
  const TRIP_DEFAULTS = { start: '10:00', end: '20:00', count: '5', max_leg: '60', stay_minutes: '75', include_meal: true };
  const tripForm = document.getElementById('conditions'); // 조건 화면 form(id=conditions)
  const fieldOf = name => tripForm?.elements?.[name];
  const valueOf = el => el?.type === 'checkbox' ? el.checked : el?.value;
  // 데이트 기본값: 조건 화면을 다 그린 뒤, 사용자가 손대기 전의 값. 처음 여행으로 바꿀 때 읽는다 — 이 스크립트가 돌 때 읽으면
  // 오늘 시작 시각이 지나 화면이 시간대를 맞추기(simple-form.js, 서버 상태를 받은 뒤) 전의 11:00~19:00 이 남아, 오후에 연 화면에서
  // 여행 → 데이트로 돌아오면 이미 지난 시간대로 되돌렸다(2026-11-25 브랜치 CI 의 test_travel_mode_ui 오후 실패로 발견).
  // 사용자가 그사이 바꾼 칸은 touched 로 따로 남아 어느 쪽으로도 건드리지 않는다.
  const readValues = () => Object.fromEntries(Object.keys(TRIP_DEFAULTS).map(name => [name, valueOf(fieldOf(name))]));
  let dateDefaults = null;
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
    if (mode === 'travel' && !dateDefaults) dateDefaults = readValues();
    const target = mode === 'travel' ? TRIP_DEFAULTS : dateDefaults || readValues(), changed = [];
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
    // 디자인 토큰(tokens.css html[data-mode="travel"])의 포인트색 전환. 예전 규칙은 body.mode-travel 을 보므로 둘 다 둔다.
    document.documentElement.dataset.mode = mode;
    switcher?.querySelectorAll('[data-mode]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.mode === mode)));
    const copy = COPY[mode];
    const h1 = document.querySelector('.hero-copy h1');
    if (h1) h1.textContent = copy.title;
    const description = document.querySelector('.hero-copy .hero-description');
    if (description) description.textContent = copy.description;
    syncRequestPlaceholder(); // 코스 만들기 카드 맨 위 한 줄 입력의 예시 문구(위 COPY.placeholder)
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
  else syncRequestPlaceholder(); // 데이트로 열 때도 한 줄 입력 예시 문구를 맞춘다(여행이면 apply 가 맞춤).
})();
