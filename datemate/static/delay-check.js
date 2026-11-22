// '지금 N분 늦으면 어디서 처음 문제가 생기나' 읽기 전용 확인(GET /api/plans/{id}/delay-check, app/delay_check.py).
// 일정 위에 접힌 상자로 둔다. 남은 첫 장소와 늦는 시간을 고르면, 방문 순서를 그대로 두고 남은 시간표를 다시 평가한 결과를 보여 준다.
// 화면이 답할 질문: 그대로 가도 되는가 → 영향(끝나는 시각, 각 장소 이용 시작이 얼마나 밀리나),
// 어렵다면 → 처음 문제가 생기는 장소·시각·이유, 자료가 없으면 → 무엇을 먼저 확인할지. 코스는 바꾸지 않는다.
function delayCheckPanel(plan) {
  const box = node('details', undefined, 'delay-check');
  box.append(node('summary', '늦어지면 어디서 문제가 생길까?'));
  const form = node('div', undefined, 'delay-check-form');
  const placeLabel = node('label', '남은 첫 장소'),
    place = node('select');
  plan.places.forEach((p, i) => {
    const option = node('option', `${i + 1}. ${p.name}`);
    option.value = String(i);
    place.append(option);
  });
  placeLabel.append(place);
  const minutesLabel = node('label', '늦는 시간(분)'),
    minutes = node('input');
  Object.assign(minutes, {
    type: 'number',
    min: '0',
    max: '180',
    step: '1',
    value: '10',
    inputMode: 'numeric'
  });
  minutesLabel.append(minutes);
  const result = node('div', undefined, 'delay-check-result');
  result.setAttribute('role', 'status');
  let generation = 0;
  const check = button('확인', async () => {
    const value = Number(minutes.value);
    if (!Number.isInteger(value) || value < 0 || value > 180) {
      result.replaceChildren(node('p', '늦는 시간은 0~180분 사이의 정수로 입력해 주세요.', 'warning'));
      return;
    }
    const mine = ++generation;
    check.disabled = true;
    result.replaceChildren(node('p', '다시 계산하고 있어요…', 'hint'));
    try {
      const data = await api(`/plans/${encodeURIComponent(plan.id)}/delay-check?index=${place.value}&minutes=${value}`);
      if (mine === generation) result.replaceChildren(...delayCheckView(data));
    } catch (error) {
      if (mine === generation) result.replaceChildren(node('p', error.message, 'warning'));
    } finally {
      check.disabled = false;
    }
  }, 'secondary');
  form.append(placeLabel, minutesLabel, check);
  box.append(node('p', '지연은 고른 장소의 원래 도착 예정 시각을 기준으로 더해요. 개점 대기·휴게 시간·마지막 입장·영업 종료를 다시 따져요. 이 확인은 코스를 바꾸지 않아요.', 'hint'), form, result);
  return box;
}

function delayCheckView(data) {
  const parts = [node('p', data.basis, 'hint delay-check-basis')];
  // 영업시간·휴무 자료가 없는 곳은 서버가 '연다'고 가정하고 계속 계산한다(app/delay_check.py). 그 사실과 먼저 확인할 곳을 밝힌다.
  const wait = (data.pending || []).map(p => `${p.place}(${p.fields.join('·')})`).join(', ');
  const later = data.finish && data.original_finish && data.finish !== data.original_finish;
  const finishText = later ? `끝나는 시각 ${data.original_finish} → ${data.finish}.` : data.finish ? `끝나는 시각은 ${data.finish} 그대로예요.` : '';
  if (data.status === 'unknown') {
    parts.push(node('p', `${data.delay}분 늦어도 시간표로는 갈 수 있어요. ${finishText} 다만 ${wait} 자료가 없어 그곳은 문을 연다고 가정했어요. 출발 전에 먼저 확인할 것: ${wait}.`, 'warning delay-check-unchecked'));
  } else if (data.status === 'problem') {
    const p = data.first_problem;
    const what = p.kind === 'last_entry' ? `마지막 입장 ${p.limit}보다 ${p.over}분 늦어요` : p.kind === 'closing' ? `영업 종료 ${p.limit}까지 마치지 못해요(${p.over}분 넘김)` : p.kind === 'festival' ? `축제 운영 종료 ${p.limit}까지 마치지 못해요(${p.over}분 넘김)` : `정한 종료 시각 ${p.limit}보다 ${p.over}분 늦게 끝나요`;
    parts.push(node('p', `처음 문제가 생기는 곳: ${p.place} · ${p.time} · ${what}. 이 장소에 먼저 연락하거나 순서를 다시 정해 보세요.`, 'warning delay-check-problem'));
    if (wait) parts.push(node('p', `그 앞에 자료가 없어 문을 연다고 가정한 곳: ${wait}.`, 'hint'));
  } else {
    parts.push(node('p', `${data.delay}분 늦어도 그대로 갈 수 있어요. ${finishText}`, 'delay-check-ok'));
  }
  const list = node('ol', undefined, 'delay-check-rows');
  for (const row of data.rows) {
    const item = node('li');
    // state='unknown'(자료 없어 멈춤)은 2026-11-19 이전 응답 모양이다. 지금 서버는 보내지 않지만 화면이 깨지지 않게 남긴다.
    if (row.state === 'unknown') item.append(node('strong', row.name), document.createTextNode(` · 도착 ${row.arrival} · 자료 없음(${row.missing.join('·')})`));
    else {
      const shift = row.shift === 0 ? (row.wait ? `개점·휴게 대기 ${row.wait}분으로 흡수, 시작 시각 그대로` : '시작 시각 그대로') : `원래보다 ${row.shift}분 늦게 시작`;
      item.append(node('strong', row.name), document.createTextNode(` · 도착 ${row.arrival} → 이용 ${row.start}~${row.departure} · ${shift}` + (row.stay_assumed ? ' · 체류 시간은 가정값' : '') + (row.state === 'unchecked' ? ` · ${row.missing.join('·')} 자료 없음(연다고 가정)` : '')));
      if (row.state === 'problem') item.classList.add('delay-check-bad');
    }
    list.append(item);
  }
  parts.push(list);
  if (data.estimated_legs.length) parts.push(node('p', '이동 시간은 추정값이에요: ' + data.estimated_legs.map(e => `${e.leg} ${e.minutes}분(${e.basis})`).join(' / '), 'hint'));
  if (data.no_last_entry.length) parts.push(node('p', '마지막 입장 시각 자료가 없는 곳은 영업 종료만 보고 판단했어요: ' + data.no_last_entry.join(', '), 'hint'));
  return parts;
}
