'use strict';
/* 서버가 잠들어 있던 첫 접속. 운영에서는 화면(HTML·CSS·JS)이 엣지에서 바로 뜨고, 서버(API)는 컨테이너가 켜지는
   수십 초 뒤에야 답한다. 첫 서버 요청(load)을 끝날 때까지 다시 묻고, 늦어지면 차분한 안내를 보여 준다.
   그동안 다른 API 요청(api-client.js)은 보내지 않고 준비될 때까지 기다렸다가 이어 간다.
   - 다시 묻는 경우: 응답이 없거나(시간 초과·연결 끊김), 502·503·504, JSON 이 아닌 5xx.
     그 밖의 답(429, 앱의 오류 JSON)은 준비된 서버의 답이라 그대로 넘긴다.
   - ready() 는 load 를 부른 쪽이 결과를 반영한 뒤(다음 작업 차례)에 풀린다. */
const ServerWake = (() => {
  const NOTICE_AFTER_MS = 1500;
  const ATTEMPT_TIMEOUT_MS = 20000;
  const GIVE_UP_MS = 5 * 60 * 1000;
  const WAITING_TEXT = '서버를 준비하고 있어요. 한동안 접속이 없으면 첫 화면 뒤 30초~1분쯤 걸릴 수 있어요. 준비되면 저절로 이어져요.';
  const FAILED_TEXT = '서버 준비가 늦어지고 있어요. 잠시 후 새로고침해 주세요.';
  let waiting = false, banner = null, resolveReady;
  const readyPromise = new Promise(resolve => { resolveReady = resolve; });

  function preparing(error) {
    if (!error?.status || [502, 503, 504].includes(error.status)) return true;
    // 앱의 오류는 JSON 이다. JSON 이 아닌 5xx 는 앞단(Cloudflare·Worker)이 낸 것이라 서버가 아직 준비되지 않은 것으로 본다.
    return !!error.unreadable && error.status >= 500;
  }
  function show(text) {
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'server-wake';
      banner.className = 'server-wake';
      banner.setAttribute('role', 'status');
      banner.setAttribute('aria-live', 'polite');
      const header = document.querySelector('body > header');
      if (header) header.after(banner);
      else (document.querySelector('main') || document.body).prepend(banner);
    }
    if (banner.textContent !== text) banner.textContent = text;
    banner.classList.toggle('stalled', text === FAILED_TEXT);
    banner.hidden = false;
  }
  function hide() {
    if (banner) banner.hidden = true;
  }
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

  // request(timeoutMs) → Promise. 성공한 값을 돌려주고, 준비 문제가 아닌 오류는 그대로 던진다.
  async function load(request) {
    waiting = true;
    const started = Date.now();
    const notice = setTimeout(() => show(WAITING_TEXT), NOTICE_AFTER_MS);
    let ok = false;
    try {
      for (let attempt = 0; ; attempt++) {
        try {
          const value = await request(ATTEMPT_TIMEOUT_MS);
          ok = true;
          return value;
        } catch (error) {
          if (!preparing(error) || Date.now() - started > GIVE_UP_MS) throw error;
          show(WAITING_TEXT);
          await sleep(Math.min(1000 * 2 ** attempt, 5000));
        }
      }
    } finally {
      clearTimeout(notice);
      if (ok) hide();
      else if (banner && !banner.hidden) show(FAILED_TEXT);
      waiting = false;
      setTimeout(resolveReady);
    }
  }

  return {
    load,
    preparing,
    get waiting() { return waiting; },
    ready: () => waiting ? readyPromise : Promise.resolve(),
  };
})();
