// 약속 당일 도구(개선안 24·39·43). 모두 저장된 코스(selected)만 읽고, 서버에 묻지 않는다(신호가 약해도 동작).
//  - lastDepartureNote: 정한 종료 시각에 맞추려면 마지막 장소에서 늦어도 언제 나서야 하는지(귀가를 정한 경우·안 정한 경우를 나눔).
//  - showStepDialog: 지금 갈 곳 하나만 크게(장소명·도착/이용 시각·짧은 주소·지도 열기), 이전·다음으로 넘긴다.
//  - fieldItineraryText: 현장용 한 장 일정(날짜·장소별 이용 시각·짧은 주소·구간 이동). 링크·공유 없이 글로만 복사한다.
function dayClockMinutes(text) {
  const [h, m] = String(text || '').split(':').map(Number);
  return Number.isFinite(h) && Number.isFinite(m) ? h * 60 + m : null;
}

function dayClock(minutes) {
  return String(Math.floor(minutes / 60)).padStart(2, '0') + ':' + String(minutes % 60).padStart(2, '0');
}

function lastDepartureNote(plan) {
  const end = dayClockMinutes(plan.conditions?.end),
    last = plan.timeline?.at(-1),
    planned = dayClockMinutes(last?.departure);
  if (end === null || planned === null) return '';
  const home = plan.conditions.return_home && plan.legs?.length > plan.places.length ? plan.legs.at(-1) : null;
  if (!home) return `종료 ${plan.conditions.end} 기준 · 귀가를 정하지 않아 마지막 장소를 ${plan.conditions.end}까지 마치면 돼요(지금 계획은 ${last.departure}에 마침).`;
  if (!Number.isFinite(home.minutes)) return `종료 ${plan.conditions.end} 기준 · 귀가 시간을 몰라 마지막 출발 시각은 계산하지 않았어요.`;
  const latest = end - home.minutes - (home.buffer_minutes || 0);
  const slack = latest - planned;
  const basis = home.status === 'api' ? '길찾기 조회' : '추정';
  return `종료 ${plan.conditions.end}에 맞추려면 마지막 장소에서 늦어도 ${dayClock(Math.max(0, latest))}에 출발해야 해요(귀가 ${home.minutes}분 · ${basis}). ` + (slack >= 0 ? `지금 계획은 ${last.departure} 출발 · 여유 ${slack}분.` : `지금 계획(${last.departure} 출발)은 ${-slack}분 늦어요.`);
}

// 구간 한 줄: legModeLabel(plan-evidence.js)이 이미 '도보 8분 · 추정'처럼 분과 근거를 붙인다. 여기서 다시 붙이지 않는다
// (2026-11-19 모바일 점검에서 '도보 2분 · 가상 추정 2분(추정)'으로 겹쳐 보이던 것을 고침).
function dayLegText(plan, leg) {
  if (typeof legModeLabel === 'function') return legModeLabel(plan, leg);
  return `${leg.mode || '이동'} ${leg.minutes}분${leg.status === 'api' ? '' : ' · 추정'}`;
}

function shortAddress(place) {
  return typeof streetAddressText === 'function' ? streetAddressText(place.address) || place.address || '' : place.address || '';
}

function fieldItineraryText(plan) {
  const lines = [`${plan.conditions.visit_date} 데이트 일정 (${plan.conditions.start} 출발)`];
  plan.places.forEach((place, i) => {
    const leg = plan.legs?.[i],
      t = plan.timeline[i];
    if (leg && Number.isFinite(leg.minutes)) lines.push('  ↓ ' + dayLegText(plan, leg));
    lines.push(`${i + 1}. ${t.arrival}~${t.departure} ${place.name}` + (shortAddress(place) ? ` · ${shortAddress(place)}` : ''));
  });
  const home = plan.conditions.return_home && plan.legs?.length > plan.places.length ? plan.legs.at(-1) : null;
  if (home && Number.isFinite(home.minutes)) lines.push(`  ↓ 귀가 ${home.minutes}분${home.status === 'api' ? '' : '(추정)'} · ${plan.finish} 도착 예정`);
  lines.push('영업·예약·이동 시간은 방문 전 확인해 주세요.');
  return lines.join('\n');
}

async function copyFieldItinerary(plan) {
  const text = fieldItineraryText(plan);
  try {
    await navigator.clipboard.writeText(text);
    toast('현장용 일정을 복사했어요. 메모나 메시지에 붙여 두면 신호가 약해도 볼 수 있어요.');
  } catch {
    const root = openDialog('현장용 일정');
    const area = node('textarea');
    area.value = text;
    area.readOnly = true;
    area.rows = Math.min(14, text.split('\n').length + 1);
    area.setAttribute('aria-label', '현장용 일정 글');
    root.append(area);
    area.select();
  }
}

function showStepDialog(plan, start = 0) {
  const root = openDialog('한 곳씩 크게 보기');
  const view = node('div', undefined, 'step-view');
  view.setAttribute('aria-live', 'polite');
  const prev = button('← 이전', () => draw(index - 1)),
    next = button('다음 →', () => draw(index + 1), 'primary');
  const nav = node('div', undefined, 'step-nav');
  nav.append(prev, next);
  root.append(view, nav);
  let index = 0;

  function draw(i) {
    index = Math.max(0, Math.min(plan.places.length - 1, i));
    const place = plan.places[index],
      t = plan.timeline[index],
      leg = plan.legs?.[index];
    view.replaceChildren(
      node('p', `${index + 1} / ${plan.places.length}`, 'step-count'),
      node('h3', place.name, 'step-name'),
      node('p', `도착 ${t.arrival} · ${t.departure}까지`, 'step-time'),
      node('p', shortAddress(place) || '주소 정보 없음', 'step-address'),
      node('p', leg && Number.isFinite(leg.minutes) ? '여기까지 ' + dayLegText(plan, leg) : '', 'hint'),
      placeMapLink('지도에서 열기 ↗', place));
    prev.disabled = index === 0;
    next.disabled = index === plan.places.length - 1;
  }
  draw(start);
}

// 일정 위에 붙일 당일 도구 줄: 마지막 출발 시각 한 줄 + 두 단추.
function dayOfTools(plan) {
  const box = node('div', undefined, 'day-of-tools');
  const note = lastDepartureNote(plan);
  if (note) box.append(node('p', note, 'hint last-departure'));
  const actions = node('div', undefined, 'day-of-actions');
  actions.append(button('한 곳씩 크게 보기', () => showStepDialog(plan)), button('현장용 일정 복사', () => copyFieldItinerary(plan)));
  box.append(actions);
  return box;
}
