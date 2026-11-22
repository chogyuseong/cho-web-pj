// '지금 N분 늦으면 어디서 처음 문제가 생기나' 읽기 전용 확인(GET /api/plans/{id}/delay-check, app/delay_check.py).
// 일정 위에 접힌 상자로 둔다. 남은 첫 장소와 늦는 시간을 고르면, 방문 순서를 그대로 두고 남은 시간표를 다시 평가한 결과를 보여 준다.
// 화면이 답할 질문: 그대로 가도 되는가 → 영향(끝나는 시각, 각 장소 이용 시작이 얼마나 밀리나),
// 어렵다면 → 처음 문제가 생기는 장소·시각·이유, 자료가 없으면 → 무엇을 먼저 확인할지. 확인 자체는 코스를 바꾸지 않는다.
// 늦어서 맞출 수 없게 된 장소가 있으면 그 줄 아래 '대신 갈 곳'과 [빼고 진행](app/delay_recovery.py)을 둔다. 누르면 새 코스로 저장된다.
// 마지막 지각 복구의 안내. 그 결과로 만든 코스(planId)를 보고 있을 때만 상자 위에 보여 준다(plan-actions.js transportNotice 와 같은 방식).
let delayRecoveryNotice = null;

function delayCheckPanel(plan) {
  const box = node('details', undefined, 'delay-check');
  box.append(node('summary', '늦어지면 어디서 문제가 생길까?'));
  const notice = delayRecoveryNotice?.planId === plan.id ? delayRecoveryNotice : null;
  if (notice) {
    box.open = true;
    const text = node('div', undefined, 'delay-recovery-notice');
    text.tabIndex = -1;
    notice.messages.forEach(line => text.append(node('p', line)));
    notice.warnings.forEach(line => text.append(node('p', line, 'warning')));
    box.append(text);
  }
  const form = node('div', undefined, 'delay-check-form');
  const placeLabel = node('label', '남은 첫 장소'),
    place = node('select');
  plan.places.forEach((p, i) => {
    const option = node('option', `${i + 1}. ${p.name}`);
    option.value = String(i);
    place.append(option);
  });
  // 복구한 뒤에는 같은 장소·0분으로 두어, 다시 누르면 지금 시간표 그대로를 확인한다.
  if (notice && notice.index < plan.places.length) place.value = String(notice.index);
  placeLabel.append(place);
  const minutesLabel = node('label', '늦는 시간(분)'),
    minutes = node('input');
  Object.assign(minutes, {
    type: 'number',
    min: '0',
    max: '180',
    step: '1',
    value: notice ? '0' : '10',
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
      if (mine === generation) result.replaceChildren(...delayCheckView(data, plan));
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

function delayCheckView(data, plan) {
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
  const recovery = delayRecoveryAllowed(plan) ? data.recovery : null;
  // 장소 번호는 장소 줄만 센다(코스 중간·끝 축제 줄 festival=true 는 세지 않는다, app/delay_recovery._target).
  let placeRow = -1;
  for (const row of data.rows) {
    const item = node('li');
    if (!row.festival) placeRow += 1;
    // state='unknown'(자료 없어 멈춤)은 2026-11-19 이전 응답 모양이다. 지금 서버는 보내지 않지만 화면이 깨지지 않게 남긴다.
    if (row.state === 'unknown') item.append(node('strong', row.name), document.createTextNode(` · 도착 ${row.arrival} · 자료 없음(${row.missing.join('·')})`));
    else {
      const shift = row.shift === 0 ? (row.wait ? `개점·휴게 대기 ${row.wait}분으로 흡수, 시작 시각 그대로` : '시작 시각 그대로') : `원래보다 ${row.shift}분 늦게 시작`;
      item.append(node('strong', row.name), document.createTextNode(` · 도착 ${row.arrival} → 이용 ${row.start}~${row.departure} · ${shift}` + (row.stay_assumed ? ' · 체류 시간은 가정값' : '') + (row.state === 'unchecked' ? ` · ${row.missing.join('·')} 자료 없음(연다고 가정)` : '')));
      if (row.state === 'problem') item.classList.add('delay-check-bad');
    }
    // 문제 장소 줄 = 남은 첫 장소부터 센 번호가 recovery.index 인 장소 줄(서버가 그 줄에서 계산을 멈춘다).
    if (recovery && row.state === 'problem' && !row.festival && data.index + placeRow === recovery.index) item.append(delayRecoveryBlock(plan, data, recovery));
    list.append(item);
  }
  parts.push(list);
  if (data.estimated_legs.length) parts.push(node('p', '이동 시간은 추정값이에요: ' + data.estimated_legs.map(e => `${e.leg} ${e.minutes}분(${e.basis})`).join(' / '), 'hint'));
  if (data.no_last_entry.length) parts.push(node('p', '마지막 입장 시각 자료가 없는 곳은 영업 종료만 보고 판단했어요: ' + data.no_last_entry.join(', '), 'hint'));
  return parts;
}

// 공유받은 코스·보관 기한(21일)이 지난 코스에서는 바꾸는 단추를 두지 않는다(서버도 404·409).
function delayRecoveryAllowed(plan) {
  return Boolean(plan?.id) && plan.can_edit !== false && !(typeof planHistoryExpired === 'function' && planHistoryExpired(plan));
}

// 받침이 있으면 with_final(으로), 없으면 without_final(로). 'ㄹ' 받침은 '로'(app/leg_modes.josa 는 을/를·이/가만 다뤄 여기서 따로 둔다).
function delayRecoveryJosa(word, withFinal, withoutFinal) {
  const last = String(word || '').trim().slice(-1),
    code = last.charCodeAt(0) - 0xAC00;
  if (!(code >= 0 && code < 11172)) return `${withFinal}(${withoutFinal})`;
  const final = code % 28;
  if (!final || (withFinal === '으로' && final === 8)) return withoutFinal;
  return withFinal;
}

function delayRecoveryMove(minutes) {
  if (!Number.isFinite(minutes) || minutes === 0) return '이동 시간 그대로';
  return minutes > 0 ? `이동 ${minutes}분 늘어남` : `이동 ${-minutes}분 줄어듦`;
}

// 문제 장소 줄 아래: 대신 갈 곳(최대 3곳) + [이곳으로 바꾸기], 그리고 [빼고 진행]. 예약·고정한 곳은 안내만.
function delayRecoveryBlock(plan, data, recovery) {
  const block = node('div', undefined, 'delay-recovery');
  block.setAttribute('role', 'group');
  block.setAttribute('aria-label', `${recovery.place} 대신할 방법`);
  if (recovery.blocked) {
    block.append(node('p', recovery.blocked, 'hint delay-recovery-blocked'));
    return block;
  }
  const status = node('p', undefined, 'hint delay-recovery-status');
  status.setAttribute('role', 'status');
  block.append(node('p', `대신 갈 곳 · 같은 종류(${recovery.kind})`, 'delay-recovery-title'));
  if (recovery.options.length) {
    const list = node('ul', undefined, 'delay-recovery-options');
    for (const option of recovery.options) {
      const item = node('li'),
        info = node('div', undefined, 'delay-recovery-info');
      const hours = option.hours_known ? `${option.closes}까지 영업` : '영업시간 미확인(연다고 가정)';
      const details = [`${recovery.place}에서 직선 ${option.distance_m.toLocaleString('ko-KR')}m`, delayRecoveryMove(option.extra_minutes), hours, `${option.start}~${option.departure} 이용`];
      if (option.over_end) details.push(`종료 ${option.over_end}분 넘김`);
      info.append(node('strong', option.name), node('span', details.join(' · '), 'delay-recovery-meta'));
      if (!option.hours_known) info.append(node('span', '영업시간 미확인', 'delay-recovery-unchecked'));
      const choose = button('이곳으로 바꾸기', () => applyDelayRecovery(plan, data, option.id, block, status), 'secondary');
      choose.setAttribute('aria-label', `${recovery.place} 대신 ${option.name}${delayRecoveryJosa(option.name, '으로', '로')} 바꾸기`);
      item.append(info, choose);
      list.append(item);
    }
    block.append(list);
  } else {
    block.append(node('p', `대체 후보 없음 — ${recovery.note || '조건에 맞는 곳을 찾지 못했어요.'}`, 'hint delay-recovery-none'));
  }
  if (recovery.skip) {
    const skip = node('div', undefined, 'delay-recovery-skip');
    skip.append(node('p', recovery.skip.reason, recovery.skip.allowed ? 'hint' : 'hint delay-recovery-blocked'));
    if (recovery.skip.allowed) {
      const leave = button('빼고 진행', () => applyDelayRecovery(plan, data, null, block, status), 'secondary');
      leave.setAttribute('aria-label', `${recovery.place} 빼고 진행`);
      skip.append(leave);
    }
    block.append(skip);
  }
  block.append(node('p', '누르면 지연을 반영해 남은 시간표를 다시 짠 새 코스로 저장해요. 위의 되돌리기로 원래 코스로 돌아갈 수 있어요.', 'hint'), status);
  return block;
}

async function applyDelayRecovery(plan, data, replacementId, block, status) {
  if (applyDelayRecovery.busy || selected?.id !== plan.id) return;
  applyDelayRecovery.busy = true;
  const choices = [...block.querySelectorAll('button')];
  choices.forEach(choice => choice.disabled = true);
  status.textContent = '새 코스를 저장하고 있어요…';
  try {
    const updated = await api(`/plans/${encodeURIComponent(plan.id)}/delay-recovery`, {
      index: data.index,
      minutes: data.delay,
      target: data.recovery.index,
      replacement_id: replacementId
    });
    const result = updated.delay_recovery_result || {};
    delayRecoveryNotice = {
      planId: updated.id,
      index: data.index,
      messages: result.message ? [result.message] : [],
      warnings: result.warnings || []
    };
    if (commitPlanChange(plan.id, updated)) requestAnimationFrame(() => document.querySelector('#plan-detail .delay-recovery-notice')?.focus());
    else status.textContent = '새 코스를 저장했어요. 코스 목록에서 확인해 주세요.';
  } catch (error) {
    status.textContent = error.message;
    choices.forEach(choice => choice.disabled = false);
  } finally {
    applyDelayRecovery.busy = false;
  }
}
