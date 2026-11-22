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
