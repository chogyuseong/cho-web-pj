/* 나중 묶음 로더(QA-19 첫 화면 JS 나눠 받기, 2026-11-28). 전역 DatemateLater.

   왜: 첫 화면이 스크립트 47개(묶음 하나, 약 720KB)를 다 받아야 DOMContentLoaded 가 났는데, 첫 화면에서 실제 도는 코드는 5분의 1쯤이다.
       느린 회선에서는 이 묶음이 글꼴(약 270KB 네 개)과 회선을 나눠 써 받는 데만 몇 초가 걸렸다(측정: tests/js_split_measure.py).
   무엇을: 결과 화면·둘러보기·지도·장소 정보 창용 스크립트는 index.html 의 <template id="later-scripts"> 안에 적는다. template 안의 script 는
       브라우저가 받지도 실행하지도 않는다. 이 파일이 DOMContentLoaded 뒤에 그 주소들을 적힌 순서대로 붙인다
       (배포: 묶음 static/bundles/index-2.js 하나, 묶음이 없거나 오래된 개발 중: 원본 파일들 — 두 경우 모두 같은 길).
       모듈이 아니라 전역을 함께 쓰는 일반 스크립트 그대로다(파일 사이 약속은 바뀌지 않는다).
   첫 묶음에서 나중 묶음의 이름을 쓰는 곳(진입점)은 먼저 기다린다:
       await DatemateLater.need()   사용자가 누른 동작. 0.4초 넘게 걸리면 '준비하고 있어요' 알림을 띄운다. 실패하면 Error(사용자용 문장).
       DatemateLater.ready()        알림 없이 기다림(처음 화면 준비 중 자동으로 도는 곳).
       DatemateLater.whenReady(fn)  기다리지 않는 곳. 이미 실행됐으면 바로, 아니면 실행된 때 한 번 fn 을 부른다(받기에 실패했다가 나중에 성공해도 부른다).
       DatemateLater.loaded         이미 실행됐는지(동기). 진입점 목록과 새 참조 검사는 tests/test_js_split.py.
       같은 이름을 미리 빈 값으로 선언해 두는 방식은 쓰지 않는다 — 나중 묶음이 const·function 으로 선언하므로 중복 선언 오류로 묶음 전체가 멈춘다.
   실패: 받기 실패(연결 끊김·404)면 그 태그를 지우고 처음 상태로 돌아가, 다음 need()/ready() 가 실패한 주소만 다시 붙인다
       (이미 실행된 파일을 다시 붙이면 중복 선언 오류). 받았는데 실행 중 오류로 약속한 이름이 없으면 'broken' — 다시 받아도 같으므로 새로고침을 안내한다.
   DOMContentLoaded 전에는 붙이지 않는다: 그 전에 붙이면 첫 묶음과 회선을 나눠 쓰고, 묶음 없이 원본을 쓰는 개발 중에는 첫 화면 파일들 사이에 끼어 실행될 수 있다.
   되돌리기: template 안의 태그를 첫 덩어리 끝으로 옮기고 template 을 지우면 예전처럼 한 묶음이다(이 파일과 진입점의 기다림은 바로 통과한다). */
const DatemateLater = (() => {
  const LOAD_FAILED = '코스 화면을 불러오지 못했어요. 연결을 확인하고 다시 시도해 주세요.';
  const BROKEN = '화면 일부를 불러오지 못했어요. 새로고침해 주세요.';
  const WAITING = '화면을 준비하고 있어요. 준비되면 바로 이어 갈게요.';
  let state = 'idle'; // idle → loading → ready | broken (받기 실패는 idle 로 돌아간다)
  let pending = null;
  let started = false;
  const done = new Set(); // 실행까지 끝난 주소
  const domReady = new Promise(resolve => {
    if (document.readyState === 'complete') resolve();
    else {
      document.addEventListener('DOMContentLoaded', resolve, {
        once: true
      });
      addEventListener('load', resolve, {
        once: true
      });
    }
  });

  function sources() {
    const box = document.getElementById('later-scripts');
    return box ? [...box.content.querySelectorAll('script[src]')].map(script => script.getAttribute('src')) : [];
  }

  // 첫 묶음이 부르는 나중 묶음 이름(진입 약속). 선언 도중 멈춘 const 는 typeof 도 오류를 내므로 try 안에서 본다.
  function contractMet() {
    try {
      return [typeof renderResults, typeof renderDetail, typeof renderPlanMapCard, typeof openDialog, typeof loadNaverMaps, typeof loadLeaflet,
        typeof ExploreView, typeof FestivalPanel, typeof PopupView, typeof PopupCourse
      ].every(kind => kind !== 'undefined');
    } catch {
      return false;
    }
  }

  function attach(src) {
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = src;
      script.async = false; // 받는 것은 함께, 실행은 붙인 순서대로
      script.onload = () => {
        done.add(src);
        resolve();
      };
      script.onerror = () => {
        script.remove();
        reject(Error(LOAD_FAILED));
      };
      document.head.append(script);
    });
  }

  function mark(name) {
    try {
      performance.mark(name);
    } catch {}
  }

  async function load() {
    await domReady;
    if (!started) mark('later:start');
    started = true;
    // 하나가 실패해도 나머지가 끝날 때까지 기다린다(아직 받는 중인 파일을 다시 붙이지 않게).
    const results = await Promise.allSettled(sources().filter(src => !done.has(src)).map(attach));
    const failed = results.find(result => result.status === 'rejected');
    if (failed) {
      state = 'idle';
      throw failed.reason;
    }
    if (!contractMet()) {
      state = 'broken';
      throw Error(BROKEN);
    }
    state = 'ready';
    mark('later:ready');
    document.dispatchEvent(new CustomEvent('datemate:later-ready'));
  }

  function ready() {
    if (state === 'ready') return Promise.resolve();
    if (state === 'broken') return Promise.reject(Error(BROKEN));
    if (!pending) {
      state = 'loading';
      pending = load().finally(() => {
        pending = null;
      });
    }
    return pending;
  }

  async function need() {
    if (state === 'ready') return;
    const timer = setTimeout(() => {
      if (typeof toast === 'function') toast(WAITING);
    }, 400);
    try {
      await ready();
    } finally {
      clearTimeout(timer);
    }
  }

  function whenReady(run) {
    if (state === 'ready') run();
    else document.addEventListener('datemate:later-ready', () => run(), {
      once: true
    });
  }
  // 첫 화면 준비(DOMContentLoaded) 뒤 바로 받기 시작한다. 실패는 진입점이 다시 부를 때 알린다.
  ready().catch(() => {});
  return {
    ready,
    need,
    whenReady,
    get loaded() {
      return state === 'ready';
    },
    get state() {
      return state;
    }
  };
})();
