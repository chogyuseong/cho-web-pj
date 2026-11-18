/* 대중교통 구간의 지하철·버스 비교(서버 app/transit_compare.py, TMAP 대중교통 API). 2026-11-18 사용자 요청.
   흐름: 일정 위 「지하철·버스 비교하기」 단추(transitCompareIntro)를 누르면 코스(plan id)마다 한 번 요청하고,
         각 대중교통 구간 줄 아래 패널(transitComparePanel)과 지도(maps.js watchTransit)가 같은 응답을 구독한다(parking.js 와 같은 구조).
   사용자 결정: 단추를 눌렀을 때만 조회(구간당 TMAP 1건, 건당 0.88원), 고른 경로는 화면 미리보기뿐 — 저장 코스·공유·인쇄는 그대로 추정.
   약관: TMAP 데이터는 저장 후 24시간 이상 쓸 수 없다 → 서버 캐시 6시간 + 이 화면은 응답의 expires_in(17시간) 지나면 버리고 다시 받는다.
   키가 없으면(statusData.transit_compare_available false) 아무것도 그리지 않는다.
   함께 맞출 것: 선택지 이름(subway·bus·mixed)과 path 조각 kind(walk·bus·subway)는 서버 KINDS·LEG_MODES 와 같다.
                 지도 선 색은 TRANSIT_LINE_COLORS 하나에서 정하고 패널의 색 점(.transit-kind-dot)도 같은 값을 쓴다. */
const transitCompareState = new Map();
const TRANSIT_KIND_NAMES = {subway: '지하철', bus: '버스', mixed: '버스+지하철'};
const TRANSIT_KIND_ORDER = ['subway', 'bus', 'mixed'];
// 지도 선 색: 구간 조각 종류별(도보는 회색 짧은 점선). 패널의 선택지 색 점은 그 선택지의 대표 색(혼합은 보라).
const TRANSIT_LINE_COLORS = {subway: '#1f5fbf', bus: '#2e8b57', walk: '#55606b', mixed: '#7b4bb3'};
// 꼬리표: 선택지 값의 이름 → [꼬리표 글자, 비교할 값]. transitBadges 가 '혼자 가장 좋은' 선택지에만 붙인다.
const TRANSIT_BADGES = [['가장 빠름', o => o.minutes], ['덜 걸음', o => o.walk_minutes], ['환승 적음', o => o.transfers]];

// 이 선택지에 붙일 꼬리표. 선택지가 둘 이상이고 그 값이 다른 모든 선택지보다 작을 때만(같으면 붙이지 않음).
// 2026-11-18 운영 첫 조회에서 선택지가 하나뿐인 구간에 꼬리표 3개가 다 붙고, 지하철·버스 모두 환승 0회인데 지하철에만 '환승 적음'이 붙어 고쳤다.
// 서버의 best(가장 빠른 것)는 처음 고를 선택지를 정하는 데만 쓴다(loadTransitCompare).
function transitBadges(leg, kind) {
  const others = TRANSIT_KIND_ORDER.filter(k => k !== kind && leg.options?.[k]).map(k => leg.options[k]);
  if (!others.length) return [];
  const mine = leg.options[kind];
  return TRANSIT_BADGES.filter(([, value]) => others.every(o => value(mine) < value(o))).map(([label]) => label);
}

function transitCompareEntry(planId) {
  if (!transitCompareState.has(planId)) transitCompareState.set(planId, {request: null, data: null, error: null, receivedAt: 0, choices: new Map(), listeners: new Set()});
  return transitCompareState.get(planId);
}

// 대중교통 구간 순번(plan.legs 기준, 귀가 구간 포함). 실제 장소 모드만.
function transitLegIndexes(plan) {
  if (plan?.conditions?.mode !== 'real') return [];
  return (plan.legs || []).map((leg, i) => legMode(plan, leg) === 'transit' ? i : -1).filter(i => i >= 0);
}

function transitCompareAvailable(plan) {
  return Boolean(statusData?.transit_compare_available) && transitLegIndexes(plan).length > 0;
}

function notifyTransit(entry) {
  entry.listeners.forEach(listener => listener(entry.data, entry.error));
}

// 응답이 오면 구간마다 기본 선택 = 가장 빠른 선택지. 사용자가 이미 고른 구간은 그대로 둔다.
function loadTransitCompare(plan, refresh = false) {
  const entry = transitCompareEntry(plan.id);
  const stale = entry.data && Date.now() - entry.receivedAt > (entry.data.expires_in || 0) * 1000;
  if (stale) { entry.data = null; entry.choices.clear(); }
  if (refresh || stale) entry.request = null;
  if (!entry.request) {
    entry.error = null;
    entry.request = api('/plans/' + encodeURIComponent(plan.id) + '/transit-compare').then(data => {
      entry.data = data; entry.receivedAt = Date.now(); entry.error = null;
      for (const leg of data.legs || []) if (!entry.choices.has(leg.index) && leg.best?.fastest) entry.choices.set(leg.index, leg.best.fastest);
      notifyTransit(entry);
      return data;
    }).catch(error => {
      entry.request = null; entry.error = error;
      notifyTransit(entry);
      throw error;
    });
    notifyTransit(entry);  // '찾는 중' 표시
  }
  return entry.request;
}

// 요청을 시작하지 않고 결과·선택 변경을 기다린다(패널·지도). 이미 받았으면 바로 부른다. 돌려준 함수로 구독을 끝낸다.
function onTransitCompare(plan, listener) {
  const entry = transitCompareEntry(plan.id);
  entry.listeners.add(listener);
  if (entry.data || entry.error || entry.request) listener(entry.data, entry.error);
  return () => entry.listeners.delete(listener);
}

function chooseTransit(plan, index, kind) {
  const entry = transitCompareEntry(plan.id);
  entry.choices.set(index, kind);
  notifyTransit(entry);
}

// 지도에 그릴 고른 경로들: [{index, kind, parts:[{kind, points:[[경도,위도]…]}]}].
function transitChosenRoutes(plan) {
  const entry = transitCompareEntry(plan.id);
  if (!entry.data) return [];
  return (entry.data.legs || []).flatMap(leg => {
    const kind = entry.choices.get(leg.index), option = kind && leg.options?.[kind];
    return option?.path?.length ? [{index: leg.index, kind, parts: option.path}] : [];
  });
}

function addMinutes(clock, minutes) {
  const [h, m] = String(clock || '').split(':').map(Number);
  if (!Number.isFinite(h) || !Number.isFinite(m) || !Number.isFinite(minutes)) return null;
  const total = ((h * 60 + m + minutes) % 1440 + 1440) % 1440;
  return String(Math.floor(total / 60)).padStart(2, '0') + ':' + String(total % 60).padStart(2, '0');
}

// 그 구간만 바꿨을 때의 도착 미리보기. 출발 = 앞 장소를 떠나는 시각(첫 구간은 시작 시각), 여유시간도 일정과 같게 더한다.
// 이후 일정은 다시 계산하지 않는다(저장 코스는 그대로라는 사용자 결정).
function transitPreviewText(plan, index, option) {
  const leg = plan.legs[index], buffer = plan.conditions.transition_buffer_minutes || 0;
  const departure = index === 0 ? plan.conditions.start : plan.timeline[index - 1]?.departure;
  const arrival = addMinutes(departure, option.minutes + buffer);
  if (!arrival) return '';
  const diff = option.minutes - (leg.minutes ?? option.minutes);
  const compared = diff === 0 ? '일정의 추정과 같음' : `일정의 추정보다 ${Math.abs(diff)}분 ${diff < 0 ? '빠름' : '늦음'}`;
  return `이 경로로 가면 ${leg.destination} 도착 약 ${arrival} (${compared}). 저장된 일정·비용은 바뀌지 않아요.`;
}

function transitOptionButton(plan, leg, kind, chosen) {
  const option = leg.options[kind], name = TRANSIT_KIND_NAMES[kind];
  const card = node('button', undefined, 'transit-option');
  card.type = 'button';
  card.setAttribute('aria-pressed', String(chosen));
  card.dataset.kind = kind;
  const head = node('span', undefined, 'transit-option-head');
  const dot = node('span', '', 'transit-kind-dot');
  dot.style.background = TRANSIT_LINE_COLORS[kind];
  head.append(dot, node('strong', `${name} ${option.minutes}분`));
  const badges = transitBadges(leg, kind).map(label => node('span', label, 'tag transit-badge'));
  head.append(...badges);
  const facts = [`환승 ${option.transfers}회`, `도보 ${option.walk_minutes}분`];
  if (Number.isFinite(option.fare_per_person)) facts.push(`1인 ${won(option.fare_per_person)}`);
  card.append(head, node('span', facts.join(' · '), 'transit-option-facts'));
  if (option.lines?.length) card.append(node('span', option.lines.map(line => line.name).join(' → '), 'transit-option-lines'));
  card.addEventListener('click', () => chooseTransit(plan, leg.index, kind));
  return card;
}

// 일정 위: 단추와 외부 전송 안내. 키가 없거나 대중교통 구간이 없으면 빈 조각.
function transitCompareIntro(plan) {
  if (!transitCompareAvailable(plan)) return document.createDocumentFragment();
  const box = node('section', undefined, 'transit-compare-intro');
  box.setAttribute('aria-label', '대중교통 지하철·버스 비교');
  const start = button('지하철·버스 비교하기', () => loadTransitCompare(plan).catch(() => {}), 'secondary transit-compare-start');
  // 개인정보: 출발지(집일 수 있음)를 포함한 좌표가 외부로 나간다는 것을 누르기 전에 밝힌다.
  box.append(start, node('p', '누르면 대중교통 구간의 출발·도착 좌표를 TMAP(티맵모빌리티)에 보내 실제 노선을 찾아요. 구간마다 지하철·버스 중 골라 지도와 도착 시각을 미리 볼 수 있어요.', 'hint'));
  const status = node('p', '', 'hint transit-compare-status');
  status.setAttribute('role', 'status');
  box.append(status);
  let attached = false;
  const stop = onTransitCompare(plan, (data, error) => {
    if (attached && !box.isConnected) { stop(); return; }
    const entry = transitCompareEntry(plan.id);
    start.disabled = Boolean(entry.request && !data && !error);
    if (error) status.textContent = error.status === 429 ? '대중교통 비교는 잠시 후 다시 시도해 주세요.' : '대중교통 경로에 연결하지 못했어요.';
    else if (!data) status.textContent = '대중교통 경로를 찾고 있어요…';
    else if (data.status === 'available') status.textContent = `${data.source} 조회 ${data.checked_at}`;
    else status.textContent = data.message || '대중교통 경로를 찾지 못했어요.';
    start.textContent = data || error ? '다시 비교' : '지하철·버스 비교하기';
  });
  attached = true;
  return box;
}

// 대중교통 구간 줄 바로 아래 자리. 비교 전에는 비어 있고(보이지 않음), 응답이 오면 선택지를 그린다.
function transitComparePanel(plan, index) {
  if (!transitCompareAvailable(plan) || !transitLegIndexes(plan).includes(index)) return document.createDocumentFragment();
  const panel = node('div', undefined, 'transit-compare-panel');
  panel.hidden = true;
  let attached = false;
  const stop = onTransitCompare(plan, data => {
    if (attached && !panel.isConnected) { stop(); return; }
    const leg = data?.legs?.find(l => l.index === index);
    if (!leg) { panel.hidden = true; panel.replaceChildren(); return; }
    panel.hidden = false;
    const title = `${leg.origin} → ${leg.destination}`;
    panel.setAttribute('aria-label', title + ' 대중교통 경로 비교');
    if (leg.status !== 'available') {
      const reason = leg.status === 'limited' ? '오늘 비교 한도를 다 써서 이 구간은 찾지 못했어요.' : '이 구간의 대중교통 경로를 찾지 못했어요. 일정은 추정 시간 그대로예요.';
      panel.replaceChildren(node('p', reason, 'hint'));
      return;
    }
    const chosen = transitCompareEntry(plan.id).choices.get(index);
    const list = node('div', undefined, 'transit-options');
    list.setAttribute('role', 'group');
    list.setAttribute('aria-label', title + ' 경로 고르기');
    for (const kind of TRANSIT_KIND_ORDER) {
      if (leg.options?.[kind]) list.append(transitOptionButton(plan, leg, kind, kind === chosen));
      else if (kind !== 'mixed') list.append(node('p', `${TRANSIT_KIND_NAMES[kind]}만으로 가는 경로가 없어요.`, 'hint transit-option-missing'));
    }
    const option = leg.options?.[chosen];
    const preview = node('p', option ? transitPreviewText(plan, index, option) : '', 'transit-preview');
    preview.setAttribute('aria-live', 'polite');
    panel.replaceChildren(list, preview);
  });
  attached = true;
  return panel;
}

// 지도 아래 안내 한 줄(maps.js). 고른 경로가 없으면 숨긴다.
function transitMapNote(note, routes) {
  note.hidden = !routes.length;
  note.textContent = routes.length ? `대중교통: 고른 경로 ${routes.length}구간을 실선으로 표시(파랑 지하철 · 초록 버스 · 회색 점선 도보, TMAP 조회 시점 기준)` : '';
}
