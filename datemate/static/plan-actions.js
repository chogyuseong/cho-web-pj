/* Late responses update their own option without taking over another course. */
function commitPlanChange(oldId, updated) {
  if (!replaceInList(oldId, updated)) return false;
  if (selected?.id !== oldId) {
    // 그 사이 다른 코스 탭을 보고 있으면 화면은 그대로 두고, 탭만 새 코스를 가리키게 다시 그린다(탭 단추가 옛 코스를 쥐고 있지 않게).
    renderResults();
    return false;
  }
  selected = updated;
  locks = new Set(Object.keys(updated.conditions.locked || {}).map(Number));
  renderResults();
  renderDetail();
  return true;
}

/* 코스를 새 버전으로 바꾸는 동작(수단·장소 교체·레저·지각 복구·순서·식사/합의 초안 확정·되돌리기)은 이 잠금 하나를 같이 쓴다
   (2026-11-24 점검 F3). 예전에는 기능마다 잠금이 따로였고 되돌리기에는 잠금이 없어, 수단 변경을 기다리는 사이 되돌리면
   늦게 온 새 코스가 목록에 없는 채로 말없이 버려졌다. 바쁠 때 누른 동작은 보내지 않고 알린다(undefined 를 돌려준다).
   같은 코스 id 를 다시 받는 고정 토글·제보 새로고침은 코스를 새로 만들지 않아 이 잠금 밖에 둔다(togglePlanLock 은 자체 순서 큐). */
const PLAN_CHANGE_BUSY = '코스를 바꾸는 중이에요. 끝난 뒤 다시 눌러 주세요.';
let planChangeRunning = false;

async function runPlanChange(task) {
  if (planChangeRunning) {
    toast(PLAN_CHANGE_BUSY);
    return undefined;
  }
  planChangeRunning = true;
  try {
    return await task();
  } finally {
    planChangeRunning = false;
  }
}

// 바뀐 코스를 화면에 올린다. 못 올리면(그 사이 다른 코스 탭을 보고 있거나 코스 목록이 새로 바뀜) 알리고 false.
// done: 서버에서 끝난 일(되돌리기는 '되돌렸어요').
function commitNewPlan(oldId, updated, done = '새 코스를 저장했어요') {
  if (commitPlanChange(oldId, updated)) return true;
  toast(plans.some(p => p.id === updated.id) ?
    `${done}. 그 사이 다른 코스를 보고 있어 바로 열지 않았어요. 위 코스 탭에서 확인해 주세요.` :
    `${done}. 그 사이 코스 목록이 바뀌어 화면에는 넣지 못했어요.`);
  return false;
}

/* 이동 수단 바꾸기: 구간마다 또는 한 번에. 누를 때만 요청하고(라디오·select 없음) 결과는 aria-live로 알린다. */
const TRANSPORT_ORDER = ['walk', 'transit', 'car', 'bicycle'];
// 마지막 변경의 안내. 그 결과로 만든 코스(planId)를 보고 있을 때만 일정 위에 보여 준다.
let transportNotice = null;
// '대중교통'만 받침이 있다: 대중교통이에요 / 도보예요.
const transportIs = mode => TRANSPORT_NAMES[mode] + (mode === 'transit' ? '이에요' : '예요');

function transportLive() {
  let live = document.getElementById('transport-live');
  if (!live) {
    live = node('p', undefined, 'visually-hidden');
    live.id = 'transport-live';
    live.setAttribute('role', 'status');
    live.setAttribute('aria-live', 'polite');
    document.body.append(live);
  }
  return live;
}

function transportButtons(current, pick) {
  const box = node('div', undefined, 'actions transport-options');
  for (const mode of TRANSPORT_ORDER) {
    const choice = button(TRANSPORT_NAMES[mode], () => pick(mode), 'secondary');
    choice.dataset.mode = mode;
    choice.setAttribute('aria-pressed', String(mode === current));
    box.append(choice);
  }
  return box;
}

function transportChooser(legend, current, request, focusKey) {
  const box = node('fieldset', undefined, 'transport-chooser');
  const status = node('p', undefined, 'hint transport-status');
  box.append(node('legend', legend), transportButtons(current, mode => {
    if (mode === current) {
      status.textContent = `지금 ${transportIs(mode)}.`;
      return;
    }
    return changePlanTransport(request(mode), focusKey, box, status);
  }), status);
  return box;
}

async function changePlanTransport(body, focusKey, box, status) {
  const plan = selected;
  if (!plan || plan.can_edit === false) return;
  return runPlanChange(async () => {
    const choices = [...box.querySelectorAll('button')];
    choices.forEach(choice => choice.disabled = true);
    const live = transportLive();
    status.textContent = live.textContent = '이동 시간을 다시 계산하고 있어요.';
    try {
      const updated = await api('/plans/' + plan.id + '/transport', body);
      const change = updated.transport_change || {};
      transportNotice = {
        planId: updated.id,
        messages: change.messages || [],
        warnings: change.warnings || []
      };
      if (commitNewPlan(plan.id, updated)) {
        live.textContent = [...transportNotice.messages, ...transportNotice.warnings].join(' ');
        requestAnimationFrame(() => document.querySelector(`[data-transport-toggle="${focusKey}"]`)?.focus());
      } else live.textContent = '';
    } catch (error) {
      status.textContent = live.textContent = error.message;
      choices.forEach(choice => choice.disabled = false);
      // 그 사이 상세를 다시 그렸으면 상태 줄이 화면에 없다. 그때는 토스트로 알린다.
      if (!status.isConnected) toast(error.message);
    }
  });
}

// 일정의 구간 줄: "A → B · 도보 18분 · 추정" + [수단 바꾸기]. 누르면 바로 아래에 수단 4개가 펼쳐진다.
/* 구간마다 「네이버 지도 길찾기」 링크(2026-11-19, 예전 TMAP 지하철·버스 비교를 대신함).
   네이버 지도 API 에는 공개된 대중교통 길찾기가 없어(자동차 Directions 만) 앱 안에서 노선을 보여 주지 않고,
   출발·도착이 채워진 네이버 지도 길찾기 화면을 연다. 지하철·버스·환승·요금·실시간 도착은 거기서 본다.
   좌표·이름은 서버가 구간마다 만든 leg.link(routes.app_link 의 nmap://route/...?slat=&slng=&sname=&dlat=&dlng=&dname=)에서 읽는다.
   주소 형식(2026-11-19 브라우저로 확인): https://map.naver.com/p/directions/{출발 경도},{위도},{이름},,/{도착 경도},{위도},{이름},,/-/{수단}
   수단 값: transit(대중교통)·car·walk·bicycle. 형식이 바뀌면 이 함수 하나만 고치면 된다.
   가상 장소 데모(conditions.mode==='demo')는 좌표가 실제 장소가 아니라 링크를 달지 않는다. */
const NAVER_DIRECTION_MODES = {
  transit: 'transit',
  car: 'car',
  walk: 'walk',
  bicycle: 'bicycle'
};

function naverDirectionsUrl(plan, leg) {
  if (plan.conditions?.mode === 'demo' || !leg?.link) return null;
  let q;
  try {
    q = new URL(leg.link).searchParams;
  } catch {
    return null;
  }
  const point = (lat, lon, name) => {
    const y = Number(q.get(lat)),
      x = Number(q.get(lon));
    return Number.isFinite(x) && Number.isFinite(y) && (x || y) ? `${x},${y},${encodeURIComponent(q.get(name) || '')},,` : null;
  };
  const from = point('slat', 'slng', 'sname'),
    to = point('dlat', 'dlng', 'dname'),
    mode = NAVER_DIRECTION_MODES[legMode(plan, leg)] || 'transit';
  return from && to ? `https://map.naver.com/p/directions/${from}/${to}/-/${mode}` : null;
}

/* 같은 구간의 카카오맵 길찾기(2026-11-24 UX P1, 사용자 결정 '길찾기 ▾ 로 둘 다'). 우리 좌표를 그대로 넣어 이름이 같은 다른 곳으로 가지 않는다.
   형식(2026-11-24 curl 로 확인, 302 → 출발·도착이 채워진 카카오맵): https://map.kakao.com/link/from/{이름},{위도},{경도}/to/{이름},{위도},{경도}
   수단은 고를 수 없고 자동차로 열린다(/by/… 는 무시됨) — 링크 title 에 '수단은 카카오맵에서 고르세요'를 적는다.
   이름의 쉼표·빗금은 주소를 깨뜨려 빈칸으로 바꾼다. 카카오의 자료를 받아 쓰지 않고 사용자를 보내기만 한다(카카오 로컬 API 는 쓰지 않음 — 2026-11-20 Q4). */
function kakaoDirectionsUrl(plan, leg) {
  if (plan.conditions?.mode === 'demo' || !leg?.link) return null;
  let q;
  try {
    q = new URL(leg.link).searchParams;
  } catch {
    return null;
  }
  const point = (lat, lon, name) => {
    const y = Number(q.get(lat)),
      x = Number(q.get(lon));
    const label = String(q.get(name) || '위치').replace(/[,/]/g, ' ').trim() || '위치';
    return Number.isFinite(x) && Number.isFinite(y) && (x || y) ? `${encodeURIComponent(label)},${y},${x}` : null;
  };
  const from = point('slat', 'slng', 'sname'),
    to = point('dlat', 'dlng', 'dname');
  return from && to ? `https://map.kakao.com/link/from/${from}/to/${to}` : null;
}

function routeLine(plan, index, label) {
  const leg = plan.legs[index],
    // 노선 띠의 구간 선 모양은 지도 범례와 같다: 자동차 실제 경로 실선, 도보 짧은 점선, 그 밖 긴 점선.
    wrap = node('div', undefined, 'route-line-block route-leg-' + (typeof legLineStyle === 'function' ? legLineStyle(plan, leg) : 'long')),
    line = node('div', undefined, 'route-line');
  line.append(node('span', `${label} · ${legModeLabel(plan, leg)}`, 'route-line-text'));
  // 2026-11-25 상세 결과 시안: 구간 이동 제한(max_leg)을 정했고 이 구간이 그 안이면 '✓ 구간 제한 충족'(서버 판정과 같은 비교 — minutes ≤ max_leg).
  const limit = Number(plan.conditions?.max_leg);
  if (limit && limit < 180 && Number.isFinite(leg?.minutes) && leg.minutes <= limit) line.append(node('span', '✓ 구간 제한 충족', 'route-line-ok'));
  // 길찾기 ▾: 누르면 네이버 지도·카카오맵 중에서 고른다(2026-11-24 UX P1). 단추 수는 예전(네이버 링크 하나)과 같다.
  const directions = naverDirectionsUrl(plan, leg),
    kakao = kakaoDirectionsUrl(plan, leg);
  if (directions || kakao) {
    const mode = legMode(plan, leg);
    const menu = node('details', undefined, 'route-directions');
    menu.append(node('summary', '길찾기 ▾'));
    const choices = node('div', undefined, 'route-directions-choices');
    if (directions) {
      const anchor = link(mode === 'transit' ? '네이버 지도 대중교통 길찾기 ↗' : '네이버 지도 길찾기 ↗', directions);
      anchor.className = 'route-directions-link';
      anchor.title = `${leg.origin} → ${leg.destination} · 새 탭에서 네이버 지도 길찾기 열기`;
      choices.append(anchor);
    }
    if (kakao) {
      const anchor = link('카카오맵 길찾기 ↗', kakao);
      anchor.className = 'route-directions-kakao';
      anchor.title = `${leg.origin} → ${leg.destination} · 새 탭에서 카카오맵 길찾기 열기(이동 수단은 카카오맵에서 골라 주세요)`;
      choices.append(anchor);
    }
    menu.append(choices);
    line.append(menu);
  }
  wrap.append(line);
  // 보관 기간(21일)이 지나 좌표를 지운 장소가 있는 코스는 수단을 바꿀 수 없다(서버 409, naver-attribution.js planHistoryExpired).
  if (plan.can_edit !== false && !planHistoryExpired(plan)) {
    const id = 'transport-chooser-' + index,
      toggle = button('수단 바꾸기', () => {
        const open = toggle.getAttribute('aria-expanded') === 'true';
        toggle.setAttribute('aria-expanded', String(!open));
        if (open) {
          document.getElementById(id)?.remove();
          return;
        }
        const chooser = transportChooser(`${leg.origin} → ${leg.destination} 이동 수단`, legMode(plan, leg), mode => ({
          legs: [{
            index,
            mode
          }]
        }), String(index));
        chooser.id = id;
        wrap.append(chooser);
        chooser.querySelector('[aria-pressed="true"]')?.focus();
      }, 'secondary route-mode-toggle');
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-controls', id);
    toggle.setAttribute('aria-label', `${leg.origin} → ${leg.destination} 이동 수단 바꾸기`);
    toggle.dataset.transportToggle = String(index);
    line.append(toggle);
  }
  if (leg.source && !sharedLegSource(plan)) line.append(node('small', leg.source, 'route-line-source'));
  return wrap;
}

// 일정 위: 바꾼 결과 안내, 차 위치 안내, "이동 수단 한 번에 바꾸기".
function transportOverview(plan) {
  const box = node('div', undefined, 'transport-overview');
  if (transportNotice?.planId === plan.id) {
    const notice = node('div', undefined, 'transport-notice');
    transportNotice.messages.forEach(text => notice.append(node('p', text)));
    transportNotice.warnings.forEach(text => notice.append(node('p', text, 'warning')));
    box.append(notice);
  }
  for (const check of plan.condition_checks || [])
    if (check.condition === 'car_position') box.append(node('p', check.message, 'hint car-position-note'));
  if (plan.can_edit !== false && plan.legs.length && !planHistoryExpired(plan)) {
    // 코스 끝·중간 축제로 가는 구간(festival_visit.leg — plan.legs 밖)도 지금 수단에 센다. 전체 수단을 바꾸면 이 구간도 바뀐다.
    const visit = plan.festival_visit,
      legs = (visit?.position === 'last' || festivalMiddleAfter(plan) !== null) && visit.leg ? [...plan.legs, visit.leg] : plan.legs;
    const modes = new Set(legs.map(leg => legMode(plan, leg))),
      current = modes.size === 1 ? [...modes][0] : null;
    const bulk = node('details', undefined, 'transport-bulk'),
      summary = node('summary', '이동 수단 한 번에 바꾸기');
    summary.dataset.transportToggle = 'bulk';
    bulk.append(summary, node('p', current ? `지금은 모든 구간이 ${transportIs(current)}.` : `지금은 ${travelMode({ ...plan, legs }).countLabel}이에요. 하나를 고르면 따로 고른 구간 설정은 지워져요.`, 'hint'), transportChooser('모든 구간 이동 수단', current, mode => ({
      default: mode
    }), 'bulk'));
    box.append(bulk);
  }
  return box;
}
