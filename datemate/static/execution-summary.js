function executionSummary(plan) {
  const box = node('section', undefined, 'execution-summary'),
    heading = node('div', undefined, 'detail-header');
  heading.append(node('h3', '이대로 방문하기 전, 네 가지 확인'));
  const v = plan.verification,
    known = v?.places.filter(p => p.current_operating_source).length || 0;
  const interpreted = plan.request_interpretation;
  if (interpreted?.intents.length) box.append(node('p', '입력 요청 반영: ' + interpreted.intents.join(' · ') + (interpreted.excluded.length ? ' / 제외: ' + interpreted.excluded.join(' · ') : ''), 'hint'));
  for (const warning of interpreted?.warnings || []) box.append(node('p', warning, 'hint'));
  if (plan.resource_notice) box.append(node('p', plan.resource_notice, 'warning'));
  if (plan.personalization) {
    for (const message of plan.personalization.messages) box.append(node('p', message, 'hint'));
    box.append(node('p', plan.personalization.scope, 'hint'));
  }
  if (plan.conditions.transition_buffer_minutes) box.append(node('p', `이동 구간마다 여유 ${plan.conditions.transition_buffer_minutes}분을 전체 일정에 반영했어요. 대기·주차 시간의 실제 관측값은 아닙니다.`, 'hint'));
  const meal = plan.condition_checks?.find(c => c.condition === 'meal');
  const values = [
    ['영업·예약', `${known}/${plan.places.length}곳 최근 운영 자료 · 예약은 장소별 확인`],
    ['이동', `${plan.legs.every(r=>r.status==='api')?'경로 조회':'추정 포함'} · 가장 긴 구간 ${Math.max(...plan.legs.map(r=>r.minutes||0))}분`],
    ['예산', `${range(plan.total)} · ${plan.unknown.length?'추가 확인 비용 있음':'계산한 항목 기준'}`],
    ['식사', meal?.message || (plan.conditions.include_meal ? '현재 시간대는 식사 포함 우선 대상이 아니에요.' : '식사 자유 선택')]
  ];
  box.append(heading);
  const grid = node('div', undefined, 'execution-grid');
  for (const [label, value] of values) {
    const item = node('div');
    item.append(node('strong', label), node('p', value));
    grid.append(item);
  }
  box.append(grid);
  for (const note of v?.notes || []) box.append(node('p', note, 'hint'));
  if (plan.can_edit === false) box.append(node('p', '공유받은 코스입니다. 의견·피드백을 남길 수 있고, 일정 변경은 만든 브라우저에서 확정합니다.', 'hint'));
  const places = node('details', undefined, 'verification-places');
  places.append(node('summary', '장소별 확인 자료와 변경 제보'));
  for (const [i, p] of plan.places.entries()) {
    const state = v?.places.find(s => s.id === p.id),
      row = node('div', undefined, 'verification-place');
    row.append(node('strong', p.name), node('span', state?.label || '운영 정보 추가 확인', 'tag'));
    if (state?.source) row.append(link('운영 자료 · ' + state.checked_at, state.source));
    if (state?.coverage?.missing.length) row.append(node('p', '방문 전 확인: ' + state.coverage.missing.join(' · '), 'hint'));
    const labels = {
      hours: '영업시간',
      closed_days: '정기 휴무',
      price: '가격',
      reservation: '예약'
    };
    for (const [key, source] of Object.entries(state?.field_sources || {}))
      if (labels[key]) {
        const item = node('p', undefined, 'hint');
        item.append(link(labels[key] + ' 출처 · ' + source.checked_at, source.source), document.createTextNode(' · ' + (source.current ? '확인 자료 유효기간 내' : '재확인 필요') + ' · ' + source.scope));
        row.append(item);
      }
    row.append(button('정보 변경 제보', () => showPlaceReport(plan, i)));
    places.append(row);
  }
  const estimates = plan.legs.filter(r => r.planning_minutes_range);
  if (estimates.length) {
    const details = node('details', undefined, 'route-assumptions');
    details.append(node('summary', '이동시간에 여유를 두려면'));
    for (const r of estimates) details.append(node('p', `${r.origin} → ${r.destination}: 기본 ${r.minutes}분 / 여유 ${r.planning_minutes_range[1]}분`));
    details.append(node('p', estimates[0].planning_note, 'hint'));
    box.append(details);
  }
  box.append(places);
  return box;
}
