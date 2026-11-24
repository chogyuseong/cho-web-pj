// 약속 당일 도구(개선안 24·39·43). 모두 저장된 코스(selected)만 읽고, 서버에 묻지 않는다(신호가 약해도 동작).
//  - lastDepartureNote: 정한 종료 시각에 맞추려면 마지막 장소에서 늦어도 언제 나서야 하는지(귀가를 정한 경우·안 정한 경우를 나눔).
//  - showStepDialog: 지금 갈 곳 하나만 크게(장소명·도착/이용 시각·짧은 주소·지도 열기), 이전·다음으로 넘긴다. 축제도 한 단계(F5).
//  - fieldItineraryText: 현장용 한 장 일정(날짜·장소별 이용 시각·짧은 주소·구간 이동). 링크·공유 없이 글로만 복사한다.
function dayClockMinutes(text) {
  const [h, m] = String(text || '').split(':').map(Number);
  return Number.isFinite(h) && Number.isFinite(m) ? h * 60 + m : null;
}

function dayClock(minutes) {
  return String(Math.floor(minutes / 60)).padStart(2, '0') + ':' + String(minutes % 60).padStart(2, '0');
}

function lastDepartureNote(plan) {
  // 코스 끝에 둔 저녁 축제(app/festival_time.py)면 마지막 일정은 축제이고 귀가는 행사장에서 떠난다.
  const festival = plan.festival_visit?.position === 'last' ? plan.festival_visit : null,
    where = festival ? '축제' : '마지막 장소';
  const end = dayClockMinutes(plan.conditions?.end),
    last = festival || plan.timeline?.at(-1),
    planned = dayClockMinutes(last?.departure);
  if (end === null || planned === null) return '';
  const home = plan.conditions.return_home && plan.legs?.length > plan.places.length ? plan.legs.at(-1) : null;
  if (!home) return `종료 ${plan.conditions.end} 기준 · 귀가를 정하지 않아 ${where}를 ${plan.conditions.end}까지 마치면 돼요(지금 계획은 ${last.departure}에 마침).`;
  if (!Number.isFinite(home.minutes)) return `종료 ${plan.conditions.end} 기준 · 귀가 시간을 몰라 마지막 출발 시각은 계산하지 않았어요.`;
  const latest = end - home.minutes - (home.buffer_minutes || 0);
  const slack = latest - planned;
  const basis = home.status === 'api' ? '길찾기 조회' : '추정';
  return `종료 ${plan.conditions.end}에 맞추려면 ${festival ? '축제 행사장' : '마지막 장소'}에서 늦어도 ${dayClock(Math.max(0, latest))}에 출발해야 해요(귀가 ${home.minutes}분 · ${basis}). ` + (slack >= 0 ? `지금 계획은 ${last.departure} 출발 · 여유 ${slack}분.` : `지금 계획(${last.departure} 출발)은 ${-slack}분 늦어요.`);
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

// 당일 도구 두 개(현장용 일정 복사·한 곳씩 크게 보기)가 같이 쓰는 '하루 순서'. 장소와 축제를 실제로 들르는 순서대로 늘어놓는다.
// 왜(2026-11-24 점검 F5): 한 곳씩 크게 보기가 plan.places 만 돌아 축제 단계를 건너뛰었고, 중간 축제 뒤 장소의
// '여기까지 도보 15분'(행사장 → 그 장소)이 앞 장소에서 온 것처럼 읽혔다. 현장용 일정 복사에는 축제 줄이 있어 두 도구가 어긋났다.
// 두 도구가 이 함수 하나만 보게 해 다시 어긋나지 않게 한다.
// 축제 자리 규칙(app/festival_time.py visit_record). 같은 판단이 plan-detail.js·plan-results.js·action-card.js 에도 복사돼 있다 —
// 자리 종류가 새로 생기면 그쪽과 이 함수를 함께 바꿀 것:
//  - 맨 앞(position 'first', 예전 기록처럼 position 이 없거나 중간 자리가 잘못 저장된 경우도): 코스가 행사장에서 시작한다.
//    축제로 가는 구간이 없고 plan.legs[0] 이 행사장 → 첫 장소다.
//  - 중간(position 'middle', after=i. 자리가 맞는지는 festivalMiddleAfter(maps.js)가 본다): 장소 i 뒤.
//    들어가는 구간은 festival.leg, 나오는 구간(행사장 → 장소 i+1)은 plan.legs[i+1].
//  - 끝(position 'last'): 마지막 장소 뒤. 들어가는 구간은 festival.leg(plan.legs 밖), 귀가는 행사장에서 떠난다.
// 단계 모양: 장소 {place, index, time, leg, fromVenue}, 축제 {festival, leg, note}. leg 는 '이 단계까지 오는' 구간(없으면 null/undefined).
// note 는 현장용 일정 글의 괄호 문구다(바꾸면 그 글도 바뀐다).
function dayOfSteps(plan) {
  const festival = plan.festival_visit,
    last = festival?.position === 'last',
    middle = typeof festivalMiddleAfter === 'function' ? festivalMiddleAfter(plan) : null,
    first = !!festival && !last && middle === null,
    steps = [];
  if (first) steps.push({
    festival,
    leg: null,
    note: '운영 시간에 맞춰 고정'
  });
  plan.places.forEach((place, i) => {
    // fromVenue: 이 장소로 오는 구간이 행사장에서 출발한다(맨 앞 축제 뒤 첫 장소, 중간 축제 바로 뒤 장소).
    const fromVenue = (first && i === 0) || (middle !== null && i === middle + 1);
    steps.push({
      place,
      index: i,
      time: plan.timeline[i],
      leg: plan.legs?.[i],
      fromVenue
    });
    if (i === middle) steps.push({
      festival,
      leg: festival.leg,
      note: '운영 시간에 맞춰 중간에 들름'
    });
  });
  if (last) steps.push({
    festival,
    leg: festival.leg,
    note: '운영 시간에 맞춰 마무리'
  });
  return steps;
}

function fieldItineraryText(plan) {
  const lines = [`${plan.conditions.visit_date} 데이트 일정 (${plan.conditions.start} 출발)`];
  // 순서와 축제 자리는 dayOfSteps 가 정하고, 여기서는 글 모양만 정한다. F5 때 이 함수를 dayOfSteps 로 옮기면서 글은 한 글자도 바꾸지 않았다.
  for (const step of dayOfSteps(plan)) {
    const leg = step.leg;
    if (step.festival) {
      // 맨 앞 축제는 leg 가 없어 구간 줄이 없다. 중간·끝 축제는 '행사장으로' 구간 줄을 먼저 적는다.
      if (Number.isFinite(leg?.minutes)) lines.push('  ↓ 행사장으로 ' + dayLegText(plan, leg));
      lines.push(`${step.festival.arrival}~${step.festival.departure} 축제 · ${step.festival.title} (${step.note})`);
      continue;
    }
    if (Number.isFinite(leg?.minutes)) lines.push('  ↓ ' + dayLegText(plan, leg));
    const address = shortAddress(step.place);
    lines.push(`${step.index + 1}. ${step.time.arrival}~${step.time.departure} ${step.place.name}` + (address ? ` · ${address}` : ''));
  }
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

// 지금 갈 곳 하나만 크게. 단계는 dayOfSteps 순서(장소와 축제). start 는 단계 번호(맨 앞 축제가 있으면 0 이 축제) — 지금 부르는 곳은 처음부터 연다.
function showStepDialog(plan, start = 0) {
  const steps = dayOfSteps(plan);
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
    index = Math.max(0, Math.min(steps.length - 1, i));
    const step = steps[index],
      legText = Number.isFinite(step.leg?.minutes) ? dayLegText(plan, step.leg) : '';
    if (step.festival) {
      // 위쪽 표시는 번호 대신 '축제'. 'N / 전체'의 N 은 화면 어디서나(지각 확인·지도·'N번 장소') 축제를 세지 않는 장소 번호라,
      // 축제를 세어 넣으면 같은 장소가 화면마다 다른 번호가 된다.
      // 지도 링크는 달지 않는다: 저장된 축제 기록(festival_visit)에는 행사장 주소·좌표가 없고, 이름만으로 찾으면 다른 곳이 나올 수 있다.
      // (행사장 지도를 넣으려면 festival_time.visit_record 에 주소를 싣는 일부터 해야 한다.)
      view.replaceChildren(
        node('p', '축제', 'step-count'),
        node('h3', step.festival.title, 'step-name'),
        node('p', `도착 ${step.festival.arrival} · ${step.festival.departure}까지`, 'step-time'),
        node('p', step.note, 'step-address'),
        node('p', legText ? '행사장까지 ' + legText : '', 'hint'));
    } else {
      // 행사장에서 출발하는 구간은 그렇게 적는다. 안 적으면 앞 장소에서 온 구간처럼 읽힌다(F5).
      view.replaceChildren(
        node('p', `${step.index + 1} / ${plan.places.length}`, 'step-count'),
        node('h3', step.place.name, 'step-name'),
        node('p', `도착 ${step.time.arrival} · ${step.time.departure}까지`, 'step-time'),
        node('p', shortAddress(step.place) || '주소 정보 없음', 'step-address'),
        node('p', legText ? (step.fromVenue ? '축제 행사장에서 여기까지 ' : '여기까지 ') + legText : '', 'hint'),
        placeMapLink('지도에서 열기 ↗', step.place));
      // 장소 사진(2026-11-24 사용자 요청): 현장에서 '여기가 맞나'를 바로 알아보게 이름 아래에 둔다.
      // 코스 화면과 같은 사진 패널(place-photos.js placePhotoPanel)이라 출처 표시·크게 보기·사진 없을 때의 지도 링크가 같고,
      // 같은 장소의 사진 목록은 fetchPlacePhotos 가 캐시해 이전·다음으로 오가도 다시 받지 않는다.
      // 가상 장소(데모)는 붙일 사진이 없어 넣지 않는다. 신호가 약하면 패널이 '다시 불러오기'를 보여 줄 뿐 나머지 정보는 그대로다.
      // 사진 높이는 results.css '.step-view .place-photo-panel' 에서 정한다.
      if (typeof placePhotoPanel === 'function' && plan.conditions?.mode !== 'demo' && !step.place.demo) {
        view.querySelector('.step-name').after(placePhotoPanel(step.place, plan.conditions.mode, false, true));
      }
    }
    prev.disabled = index === 0;
    next.disabled = index === steps.length - 1;
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
