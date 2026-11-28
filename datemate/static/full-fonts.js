/* 전체 글꼴 나중 받기(2026-11-28, perf/font-loading). 전역 DatemateFullFonts.

   왜: Pretendard 부분집합 네 굵기(각 약 270KB)를 처음부터 받으면 느린 회선에서 첫 화면 CSS·JS 와 회선을 나눠 써 화면이 늦게 움직였다.
       그래서 line.css 가 굵기마다 @font-face 를 둘 적는다: 전체 파일(범위 = 그 파일에 있는 글자)과, 그 뒤에 자주 쓰는 글자만 담은 작은 core 파일(더 좁은 범위).
       브라우저는 뒤에 적힌 core 를 먼저 보고, core 에 없는 글자가 화면에 나올 때만 전체 파일을 받는다(스크립트 없이도 글자는 빠지지 않는다).
   무엇을: 모든 기능이 준비된 뒤(첫 화면은 나중 묶음 실행 뒤, 다른 화면은 load 뒤) 브라우저가 한가할 때 전체 파일 넷을 하나씩 받고,
       다 받으면 범위 없는 FontFace 로 document.fonts 에 더한다. 스크립트로 더한 글꼴은 CSS 의 것보다 먼저 쓰이므로 그때부터 모든 글자를
       전체 파일로 그린다 = 예전과 같은 파일·같은 모양. core 는 전체 파일에서 글리프와 문맥 규칙을 그대로 떼어 낸 것이라 바뀌는 순간 눈에 보이는 차이가 없다
       (core 에 없는 글자 옆의 문장부호 높이처럼 두 파일에 걸친 문맥만 이때 맞춰진다). 만든 법·검사: scripts/build_core_fonts.py, tests/test_core_fonts.py.
   주소·굵기는 여기 적지 않고 line.css 의 @font-face(가족 이름 Pretendard)에서 읽는다: 같은 굵기의 규칙이 둘이면 먼저 적힌 것이 전체 파일이다.
       거기 적힌 순서(본문 → 제목 → 단추 → 칩)대로 받는다. 더하는 FontFace 에는 범위를 주지 않는다(이미 받은 파일이라 어떤 글자를 물어도 더 받을 것이 없다).
   미리 받기(preload)는 본문 굵기의 core 하나뿐이다 — 더 미리 받으면 첫 화면 CSS·JS 가 그만큼 늦어진다(측정: 배포-이어가기.txt 의 perf/font-loading 기록).
   실패(연결 끊김 등): 아무것도 더하지 않는다 — CSS 만으로 core + 필요할 때 전체 파일이 계속 쓰인다.
   DatemateFullFonts.state: waiting → loading → full | failed | none(받을 것이 없음), DatemateFullFonts.done: 끝나면 state 로 풀리는 약속(테스트·측정용).
   되돌리기: 이 파일의 태그를 빼면 CSS 만으로 동작한다. core 까지 되돌리려면 line.css 의 core 네 줄과 preload 주소를 예전으로. */
const DatemateFullFonts = (() => {
  const FAMILY = 'Pretendard';
  const LATER_LIMIT = 20000; // 나중 묶음이 끝내 오지 않아도 이만큼 뒤에는 받는다
  const api = {
    state: 'waiting',
    done: null
  };

  function fullRules() {
    const byWeight = new Map(); // 굵기 → 그 굵기의 규칙들(적힌 순서)
    for (const sheet of document.styleSheets) {
      let rules;
      try {
        rules = sheet.cssRules;
      } catch {
        continue; // 다른 출처의 시트
      }
      for (const rule of rules) {
        if (!(rule instanceof CSSFontFaceRule)) continue;
        const style = rule.style;
        if (style.getPropertyValue('font-family').replace(/["']/g, '').trim() !== FAMILY) continue;
        const key = style.getPropertyValue('font-weight') + '/' + style.getPropertyValue('font-style');
        if (!byWeight.has(key)) byWeight.set(key, []);
        byWeight.get(key).push(style);
      }
    }
    // 규칙이 하나뿐인 굵기는 바꿀 것이 없다(core 를 쓰지 않는 예전 구성).
    return [...byWeight.values()].filter(rules => rules.length > 1).map(rules => rules[0]);
  }

  async function load() {
    const rules = typeof FontFace === 'function' && document.fonts?.add ? fullRules() : [];
    if (!rules.length) return 'none';
    api.state = 'loading';
    const faces = [];
    for (const style of rules) {
      const face = new FontFace(FAMILY, style.getPropertyValue('src'), {
        weight: style.getPropertyValue('font-weight') || 'normal',
        style: style.getPropertyValue('font-style') || 'normal',
        display: 'swap'
      });
      await face.load(); // 하나씩: 한꺼번에 받으면 그동안의 다른 요청(추천·사진)과 회선을 크게 나눠 쓴다
      faces.push(face);
    }
    for (const face of faces) document.fonts.add(face); // 넷을 한 번에 더해 다시 그리기가 한 번이다
    try {
      performance.mark('fonts:full');
    } catch {}
    return 'full';
  }

  const loaded = new Promise(resolve => {
    if (document.readyState === 'complete') resolve();
    else addEventListener('load', resolve, {
      once: true
    });
  });
  const later = new Promise(resolve => {
    if (typeof DatemateLater === 'undefined') return resolve();
    DatemateLater.whenReady(resolve);
    loaded.then(() => setTimeout(resolve, LATER_LIMIT));
  });
  const idle = () => new Promise(resolve => {
    if (typeof requestIdleCallback === 'function') requestIdleCallback(resolve, {
      timeout: 3000
    });
    else setTimeout(resolve, 300);
  });
  api.done = Promise.all([loaded, later]).then(idle).then(load).catch(() => 'failed').then(state => {
    api.state = state;
    return state;
  });
  return api;
})();
