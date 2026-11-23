/* Late responses update their own option without taking over another course. */
function commitPlanChange(oldId, updated) {
  if (!replaceInList(oldId, updated)) return false;
  if (selected?.id !== oldId) return false;
  selected = updated;
  locks = new Set(Object.keys(updated.conditions.locked || {}).map(Number));
  renderResults();
  renderDetail();
  return true;
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
  if (!plan || plan.can_edit === false || changePlanTransport.busy) return;
  changePlanTransport.busy = true;
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
    if (commitPlanChange(plan.id, updated)) {
      live.textContent = [...transportNotice.messages, ...transportNotice.warnings].join(' ');
      requestAnimationFrame(() => document.querySelector(`[data-transport-toggle="${focusKey}"]`)?.focus());
    }
  } catch (error) {
    status.textContent = live.textContent = error.message;
    choices.forEach(choice => choice.disabled = false);
  } finally {
    changePlanTransport.busy = false;
  }
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

function routeLine(plan, index, label) {
  const leg = plan.legs[index],
    // 노선 띠의 구간 선 모양은 지도 범례와 같다: 자동차 실제 경로 실선, 도보 짧은 점선, 그 밖 긴 점선.
    wrap = node('div', undefined, 'route-line-block route-leg-' + (typeof legLineStyle === 'function' ? legLineStyle(plan, leg) : 'long')),
    line = node('div', undefined, 'route-line');
  line.append(node('span', `${label} · ${legModeLabel(plan, leg)}`, 'route-line-text'));
  const directions = naverDirectionsUrl(plan, leg);
  if (directions) {
    const mode = legMode(plan, leg);
    const anchor = link(mode === 'transit' ? '네이버 지도 대중교통 길찾기 ↗' : '네이버 지도 길찾기 ↗', directions);
    anchor.className = 'route-directions-link';
    anchor.title = `${leg.origin} → ${leg.destination} · 새 탭에서 네이버 지도 길찾기 열기`;
    line.append(anchor);
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
