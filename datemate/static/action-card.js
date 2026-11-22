// 실행 카드 '할 일 순서'(docs/superpowers/specs/2026-11-22-action-card-design.md). 흩어진 확인 항목을 시점 순서로 한 장에 모은다:
// 지금·전날(영업·휴무·예약·가격·축제 시간) → 출발 전 → 도착 전(자동차 구간 주차) → 마무리(귀가 출발).
// 저장된 코스만 읽고 서버에 묻지 않는다(day-of.js 와 같은 원칙). 체크 표시는 이 브라우저(localStorage)에만 남긴다.
const ACTION_CARD_WHEN = [
  ['before', '지금·전날'],
  ['depart', '출발 전'],
  ['arrive', '도착 전'],
  ['finish', '마무리']
];

function actionCardItems(plan) {
  const items = [],
    c = plan.conditions || {},
    places = plan.places || [],
    timeline = plan.timeline || [],
    legs = plan.legs || [],
    visit = plan.festival_visit;
  const label = i => `${i + 1}. ${places[i].name}`;
  // 지금·전날: 장소마다 최근 운영 자료로 확인하지 못한 것(verification, app/data_quality.place_coverage)과 예약이 필요한 곳.
  places.forEach((place, i) => {
    const missing = plan.verification?.places?.find(row => row.id === place.id)?.coverage?.missing || [];
    if (missing.length) items.push({
      id: `check:${place.id}`,
      when: 'before',
      text: `${label(i)} — ${missing.join('·')} 확인`
    });
    if (place.reservation === true) items.push({
      id: `reserve:${place.id}`,
      when: 'before',
      text: `${label(i)} 예약하기 (${timeline[i]?.arrival} 도착 기준)`
    });
  });
  if (c.festival) items.push({
    id: 'festival',
    when: 'before',
    text: `‘${c.festival.title}’ 개최·운영 시간 확인 (주최 측 안내)`
  });
  // 출발 전: 맨 앞에 고정한 축제가 있으면 그 시각이 코스의 시작이다(app/festival_time.py).
  if (visit && visit.position !== 'last') items.push({
    id: 'depart',
    when: 'depart',
    text: `${visit.arrival}까지 ${visit.title} 행사장 도착 (코스 시작)`
  });
  else if (places.length) items.push({
    id: 'depart',
    when: 'depart',
    text: `${c.start} 출발 · ${label(0)} ${timeline[0]?.arrival} 도착 예정`
  });
  // 도착 전: 자동차로 도착하는 장소(구간 i 는 장소 i 에 도착). 주차비는 계산에 넣지 않는다(planner.evaluate).
  places.forEach((place, i) => {
    if (legs[i]?.mode === 'car') items.push({
      id: `parking:${place.id}`,
      when: 'arrive',
      text: `${label(i)} 도착(${timeline[i]?.arrival}) 전 주차장 확인 · 주차비는 계산에 없어요`
    });
  });
  // 코스 끝에 둔 저녁 축제로 자동차로 돌아오면 행사장 주차(planner.evaluate 가 '행사장 주차비'를 미확인 비용에 넣는다).
  if (visit?.position === 'last' && visit.leg?.mode === 'car') items.push({
    id: 'parking:festival',
    when: 'arrive',
    text: `${visit.title} 행사장 도착(${visit.arrival}) 전 주차장 확인 · 주차비는 계산에 없어요`
  });
  // 마무리: 마지막 일정(코스 끝 축제면 축제 행사장)에서 언제 나서야 하는지. day-of.js lastDepartureNote 와 같은 계산.
  if (places.length) {
    const where = visit?.position === 'last' ? `${visit.title} 행사장` : label(places.length - 1);
    const home = c.return_home && legs.length > places.length ? legs.at(-1) : null;
    const end = dayClockMinutes(c.end);
    let text = `${c.end}까지 ${where} 마치기`;
    if (home && Number.isFinite(home.minutes) && end !== null) text = `늦어도 ${dayClock(Math.max(0, end - home.minutes - (home.buffer_minutes || 0)))}에 ${where}에서 귀가 출발 (종료 ${c.end})`;
    else if (home) text = `귀가 시간을 몰라 종료 ${c.end}에 맞춰 ${where}에서 여유 있게 출발`;
    items.push({
      id: 'finish',
      when: 'finish',
      text
    });
  }
  return items;
}

// 체크한 항목 id 목록. 사생활 보호 모드 등에서 저장소가 막혀도 카드는 그대로 동작한다(저장만 안 됨).
function actionCardKey(plan) {
  return plan.id ? 'datemate:action-card:' + plan.id : null;
}

// 장소에 묶인 체크(확인·예약·주차)만 바뀐 코스로 이어받는다. 출발·마무리·축제는 바꾼 뒤 시각이 달라질 수 있어 새로 체크한다.
const ACTION_CARD_CARRIED = /^(check|reserve|parking):/;

function actionCardRead(key) {
  const saved = JSON.parse(localStorage.getItem(key) || 'null');
  return Array.isArray(saved) ? saved : null;
}

function actionCardChecked(plan) {
  const key = actionCardKey(plan);
  if (!key) return new Set();
  try {
    const saved = actionCardRead(key);
    if (saved) return new Set(saved);
    // 코스를 바꾸면(수단·장소 교체·되돌리기) 새 id 로 저장된다(store.save_plan). 바꾸기 전 코스(parent)의 체크를 이어받는다.
    const parent = plan.parent ? actionCardRead('datemate:action-card:' + plan.parent) : null;
    if (!parent) return new Set();
    const current = new Set(actionCardItems(plan).map(item => item.id));
    const carried = new Set(parent.filter(id => ACTION_CARD_CARRIED.test(id) && current.has(id)));
    saveActionCardChecked(plan, carried);
    return carried;
  } catch {
    return new Set();
  }
}

function saveActionCardChecked(plan, checked) {
  const key = actionCardKey(plan);
  if (!key) return;
  try {
    if (checked.size) localStorage.setItem(key, JSON.stringify([...checked]));
    else localStorage.removeItem(key);
  } catch {}
}

function actionCard(plan) {
  const box = node('section', undefined, 'action-card'),
    items = actionCardItems(plan),
    checked = actionCardChecked(plan);
  box.append(node('h3', '할 일 순서'), node('p', '확인할 것을 언제 할지 순서대로 모았어요. 체크 표시는 이 브라우저에만 남아요.', 'hint'));
  for (const [when, title] of ACTION_CARD_WHEN) {
    const rows = items.filter(item => item.when === when);
    if (!rows.length) continue;
    const group = node('div', undefined, 'action-card-group');
    group.append(node('h4', title));
    for (const item of rows) {
      const label = node('label', undefined, 'check action-card-item'),
        input = node('input');
      input.type = 'checkbox';
      input.checked = checked.has(item.id);
      input.addEventListener('change', () => {
        if (input.checked) checked.add(item.id);
        else checked.delete(item.id);
        saveActionCardChecked(plan, checked);
      });
      label.append(input, node('span', item.text));
      group.append(label);
    }
    box.append(group);
  }
  return box;
}
