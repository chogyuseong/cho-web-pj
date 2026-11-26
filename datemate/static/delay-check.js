// '지금 N분 늦으면 어디서 처음 문제가 생기나' 읽기 전용 확인(GET /api/plans/{id}/delay-check, app/delay_check.py).
// 일정 위에 접힌 상자로 둔다. 남은 첫 장소와 늦는 시간을 고르면, 방문 순서를 그대로 두고 남은 시간표를 다시 평가한 결과를 보여 준다.
// 화면이 답할 질문: 그대로 가도 되는가 → 영향(끝나는 시각, 각 장소 이용 시작이 얼마나 밀리나),
// 어렵다면 → 처음 문제가 생기는 장소·시각·이유, 자료가 없으면 → 무엇을 먼저 확인할지. 확인 자체는 코스를 바꾸지 않는다.
// 늦어서 맞출 수 없게 된 장소가 있으면 그 줄 아래 '대신 갈 곳'과 [빼고 진행](app/delay_recovery.py)을 둔다. 누르면 새 코스로 저장된다.
// 마지막 지각 복구의 안내. 그 결과로 만든 코스(planId)를 보고 있을 때만 상자 위에 보여 준다(plan-actions.js transportNotice 와 같은 방식).
let delayRecoveryNotice = null;

/* 다시 그려도 상자 상태를 잃지 않게(2026-11-24 점검 F7). 고정 토글·제보 저장은 같은 코스(같은 id)를 다시 받아 상세 전체를 새로 그린다.
   예전에는 그때마다 이 상자와 순서 제안 상자(order-suggestion.js)가 접히고 입력·결과가 사라졌다.
   - 마지막으로 그린 코스 하나의 상태(열림·입력·받은 결과)를 기억한다. 같은 코스·같은 고정이면 그대로 되살리고 서버에 다시 묻지 않는다.
   - 같은 코스에서 고정만 바뀌었으면 받은 결과가 낡았다(지각 확인의 대신 갈 곳, 순서 제안 모두 고정한 장소를 본다).
     열려 있고 결과가 있었으면 같은 입력으로 다시 계산하고 그렇다고 한 줄 적는다 — '고정을 풀면 대신 갈 곳을 고를 수 있어요'를 따라 푼 경우.
   - 다른 코스(장소·수단·순서를 바꿔 새 id 를 받음, 탭 전환, 되돌리기)는 예전처럼 새 상자다. 지각 복구 뒤의 안내(delayRecoveryNotice)도 예전 그대로.
   '+30분 늦어지면?' 토글(아래 delaySim)도 코스 id 별로 결과를 기억한다. 그 토글은 코스가 바뀌어도 켜 둔 채 다시 계산하고, 이 상자들은 같은 코스일 때만 이어 간다. */
function planLockSig(plan) {
  return Object.keys(plan?.conditions?.locked || {}).map(Number).sort((a, b) => a - b).join(',');
}

// 기억한 상태(memo)와 지금 그리는 코스의 관계: 'same'(같은 코스·같은 고정) · 'locks'(같은 코스, 고정만 바뀜) · 'none'(다른 코스).
function planPanelRelation(memo, plan) {
  if (!memo || !plan?.id || memo.planId !== plan.id) return 'none';
  return memo.lockSig === planLockSig(plan) ? 'same' : 'locks';
}

// 지금 화면에 있는 그 코스의 상자(다시 그린 뒤 늦게 온 응답은 새 상자에 적는다).
function livePlanPanel(selector, planId) {
  return [...document.querySelectorAll(`#plan-detail ${selector}`)].find(box => box.dataset.planId === planId) || null;
}

let delayCheckMemo = null;

function delayCheckPanel(plan) {
  const box = node('details', undefined, 'delay-check');
  box.dataset.planId = plan.id;
  box.append(node('summary', '늦어지면 어디서 문제가 생길까?'));
  const relation = planPanelRelation(delayCheckMemo, plan);
  const before = relation === 'none' ? null : delayCheckMemo;
  // 같은 코스·같은 고정이면 기억을 그대로 이어 쓴다(진행 중인 확인의 응답도 새 상자에 적힌다). 아니면 새로 기억한다.
  const memo = relation === 'same' ? before : {
    planId: plan.id,
    lockSig: planLockSig(plan),
    open: Boolean(before?.open),
    index: before?.index,
    minutes: before?.minutes,
    data: null,
    error: null,
    lead: '',
    pending: false,
    turn: 0
  };
  delayCheckMemo = memo;
  const notice = delayRecoveryNotice?.planId === plan.id ? delayRecoveryNotice : null;
  // 복구한 코스를 처음 그릴 때는 열어 두고 같은 장소·0분으로 둔다. 그 뒤 다시 그릴 때는 사용자가 둔 그대로.
  if (notice && relation === 'none') Object.assign(memo, {
    open: true,
    index: notice.index < plan.places.length ? String(notice.index) : undefined,
    minutes: '0'
  });
  if (memo.open) box.open = true;
  if (notice) {
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
  // 복구한 뒤에는 같은 장소·0분으로 두어, 다시 누르면 지금 시간표 그대로를 확인한다(위 memo). 다시 그릴 때는 사용자가 고른 값.
  if (memo.index !== undefined && Number(memo.index) < plan.places.length) place.value = memo.index;
  placeLabel.append(place);
  const minutesLabel = node('label', '늦는 시간(분)'),
    minutes = node('input');
  Object.assign(minutes, {
    type: 'number',
    min: '0',
    max: '180',
    step: '1',
    value: memo.minutes ?? '10',
    inputMode: 'numeric'
  });
  minutesLabel.append(minutes);
  place.addEventListener('change', () => memo.index = place.value);
  minutes.addEventListener('input', () => memo.minutes = minutes.value);
  box.addEventListener('toggle', () => memo.open = box.open);
  const result = node('div', undefined, 'delay-check-result');
  result.setAttribute('role', 'status');
  // 결과는 지금 화면의 상자에 적는다(확인을 기다리는 사이 같은 코스로 다시 그렸으면 새 상자). lead: 결과 위에 붙일 한 줄.
  const paint = () => {
    const live = livePlanPanel('.delay-check', plan.id);
    if (!live || delayCheckMemo !== memo) return;
    const target = live.querySelector('.delay-check-result'),
      liveCheck = live.querySelector('.delay-check-form button');
    if (liveCheck) liveCheck.disabled = memo.pending;
    if (memo.pending) target.replaceChildren(node('p', '다시 계산하고 있어요…', 'hint'));
    else if (memo.data) target.replaceChildren(...(memo.lead ? [node('p', memo.lead, 'hint delay-check-refreshed')] : []), ...delayCheckView(memo.data, selected?.id === plan.id ? selected : plan));
    else if (memo.error) target.replaceChildren(node('p', memo.error, 'warning'));
    else target.replaceChildren();
  };
  const run = async (lead = '') => {
    const value = Number(minutes.value);
    if (!Number.isInteger(value) || value < 0 || value > 180) {
      Object.assign(memo, {
        data: null,
        error: '늦는 시간은 0~180분 사이의 정수로 입력해 주세요.',
        lead: ''
      });
      paint();
      return;
    }
    const mine = ++memo.turn;
    Object.assign(memo, {
      pending: true,
      index: place.value,
      minutes: minutes.value
    });
    paint();
    try {
      const data = await api(`/plans/${encodeURIComponent(plan.id)}/delay-check?index=${place.value}&minutes=${value}`);
      if (mine !== memo.turn) return;
      Object.assign(memo, {
        data,
        error: null,
        lead,
        pending: false
      });
    } catch (error) {
      if (mine !== memo.turn) return;
      Object.assign(memo, {
        data: null,
        error: error.message,
        lead: '',
        pending: false
      });
    }
    paint();
  };
  const check = button('확인', () => run(), 'secondary');
  form.append(placeLabel, minutesLabel, check);
  box.append(node('p', '어디서부터 몇 분 늦을지 고르면, 남은 일정을 다시 따져 봐요. 문 여는 시간·쉬는 시간·마지막 입장·문 닫는 시간까지 봐요. 확인만 하고 코스는 바꾸지 않아요.', 'hint'), form, result);
  if (relation === 'same') {
    // 같은 코스 다시 그리기: 받은 결과·진행 중 표시를 그대로 둔다(상자가 문서에 붙은 뒤 적는다).
    if (memo.pending || memo.data || memo.error) queueMicrotask(paint);
  } else if (relation === 'locks' && memo.open && (before.data || before.pending)) {
    // 고정이 바뀌었다: 받은 결과(대신 갈 곳·막힌 까닭)가 낡았다. 같은 입력으로 다시 확인한다.
    queueMicrotask(() => run('고정한 장소가 바뀌어 같은 조건으로 다시 확인했어요.'));
  }
  return box;
}

function delayCheckView(data, plan) {
  const parts = [node('p', data.basis, 'hint delay-check-basis')];
  // 영업시간·휴무 자료가 없는 곳은 서버가 '연다'고 가정하고 계속 계산한다(app/delay_check.py). 그 사실과 먼저 확인할 곳을 밝힌다.
  // 결론 한 줄은 말하듯이 쓴다(2026-11-24 사용자: '답변이 너무 딱딱해'). 먼저 '괜찮은지'를 말하고, 무엇이 달라지는지, 무엇을 하면 되는지 순서로.
  // 시각·분·장소 이름은 그대로 두고 문장만 바꿨다. 아래 줄 목록(이용 시각 표)은 확인용이라 그대로 간결하게 둔다.
  // 테스트가 보는 문구: tests/test_delay_check_ui.py(결론 세 갈래), tests/test_delay_tone_ui.py.
  const wait = (data.pending || []).map(p => `${p.place}(${p.fields.join('·')})`).join(', ');
  const later = data.finish && data.original_finish && data.finish !== data.original_finish;
  const finishText = later ? `대신 끝나는 시간이 ${data.original_finish}에서 ${data.finish}로 늦어져요.` : data.finish ? `끝나는 시간도 ${data.finish} 그대로예요.` : '';
  if (data.status === 'unknown') {
    parts.push(node('p', `${data.delay}분 늦어도 시간표로는 괜찮아 보여요. ${finishText} 다만 ${wait}은 영업 정보가 없어서 문을 연다고 보고 계산했어요. 출발 전에 이곳부터 확인해 보세요.`, 'warning delay-check-unchecked'));
  } else if (data.status === 'problem') {
    const p = data.first_problem;
    // 무엇이 문제인지와, 그 문제에 맞는 다음 행동(점검 보고서 F10: 일정 종료·축제 종료에 '이 장소에 연락하라'고 하지 않는다).
    // 종류별 [무엇이 문제인지, 다음 행동]. 모르는 종류(kind)는 'end' 문장으로 둔다.
    const problemText = {
      last_entry: [`${p.place}에 ${p.time}에 닿는데, 마지막 입장(${p.limit})을 ${p.over}분 넘겨요.`, '들어갈 수 있는지 미리 전화해 보거나, 아래에서 대신 갈 곳을 골라 보세요.'],
      closing: [`${p.place}에서 ${p.time}에 시작하면 ${p.limit}에 문을 닫기 전에 다 못 보고 ${p.over}분 모자라요.`, '머무는 시간을 줄이거나, 아래에서 대신 갈 곳을 골라 보세요.'],
      festival: [`${p.time}에 축제에 닿으면 ${p.limit}에 끝나기 전에 ${p.over}분 모자라요.`, '축제를 먼저 들르도록 순서를 바꿔 보는 건 어때요?'],
      end: [`일정이 ${p.time}에 끝나서, 정한 종료 시간(${p.limit})보다 ${p.over}분 늦어요.`, '한 곳을 빼거나 종료 시간을 조금 늦춰 보세요.']
    };
    const [what, next] = problemText[p.kind] || problemText.end;
    parts.push(node('p', `${data.delay}분 늦으면 여기서 처음 문제가 생겨요. ${what} ${next}`, 'warning delay-check-problem'));
    if (wait) parts.push(node('p', `참고로 그 앞의 ${wait}은 영업 정보가 없어서 문을 연다고 보고 계산했어요.`, 'hint'));
  } else {
    parts.push(node('p', `${data.delay}분 늦어도 괜찮아요. 그대로 가면 돼요. ${finishText}`, 'delay-check-ok'));
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

/* ── '혹시 늦어지셨나요?' 지연 미리 보기(리디자인 3단계, 2026-11-25 HTML 시안: 정시 · +15분 · +30분 · +60분 알약) ──────────
   일정 바로 위의 알약 묶음(각 단추 aria-pressed). 고르면 위 접힌 상자와 같은 읽기 전용 확인(GET /api/plans/{id}/delay-check)을
   '첫 장소(index=0)에 N분 늦게 도착'으로 한 번 불러, 그 결과를 일정의 장소 칸에 겹쳐 보여 준다. '정시'는 겹친 것을 모두 떼어 원래대로.
   - 장소 칸: 시각 도장 아래 '늦으면 이용 시작 시각(±분)', 장소 이름 아래 배지 — 서버가 판단한 것만 쓴다.
     문제(row.state='problem'): 마지막 입장·영업 종료·축제 운영 종료(kind 그대로). 기다림(row.wait>0): 시작 시각이 그 장소의
     휴게 시간 끝과 같으면 '휴게 시간', 여는 시각과 같으면 '문 여는 시각', 둘 다 아니면 서버 문구와 같은 '개점·휴게 대기'.
     영업 자료 없음(state='unchecked'): 서버가 '연다'고 가정한 곳. 서버는 첫 문제에서 계산을 멈추므로 그 뒤 장소는 '계산하지 않았어요'.
     라스트오더(주문 마감) 자료는 없어 말하지 않는다. 시안의 '대체 장소로 자동 조정'은 만들지 않았다 — 대신 갈 곳은 서버가 고른
     후보를 사람이 확인하고 바꾸는 위 접힌 상자(delayCheckPanel, 지각 복구)로 안내한다.
   - 일정 종료 초과(kind='end')는 장소가 아니라 알약 옆 결론 줄에만 적는다.
   - 고른 분(delaySim.minutes)은 코스가 바뀌어도(탭 전환·장소 교체·되돌리기) 그대로 두고, 새 코스로 다시 계산한다(renderDetail → delaySimRefresh).
     결과는 '코스 id · 분' 별로 기억한다(코스 내용이 바뀌면 서버가 새 id 를 준다). 늦게 온 응답은 지금 보는 코스·분이 아니면 버린다.
   - 고를 수 있는 분을 바꾸려면 DELAY_SIM_CHOICES 만 고친다(0 = 정시). */
const DELAY_SIM_CHOICES = [0, 15, 30, 60];
/* 체류 시간 바꿔 보기(2026-11-26 시안 '−15분 · N분 · +15분', 장소 카드 위 줄의 .stay-stepper — plan-detail.js stayStepper).
   늦어짐과 같은 서버 계산(GET …/delay-check 의 stays='번호:분,…', app/delay_check.py)으로 남은 시간표를 다시 계산하고, 같은 자리에 겹쳐 보인다.
   늦어짐(분)과 함께 고를 수 있다 — 둘 다 고르면 '늦게 도착 + 바꾼 체류'로 계산한다. 저장하지 않는 미리 보기라 코스는 그대로다.
   stays 는 코스(id)마다 따로 기억한다(탭을 바꿨다 돌아와도 그대로). 원래 체류로 돌아온 장소는 지운다. STAY_STEP·STAY_LIMIT 은 서버 STAY_RANGE 와 맞춘다. */
const STAY_STEP = 15, STAY_LIMIT = [15, 360];
const delaySim = {
  minutes: 0,
  staysByPlan: new Map(),
  stays(plan) {
    return this.staysByPlan.get(plan?.id) || {};
  },
  hasStays(plan) {
    return Object.keys(this.stays(plan)).length > 0;
  },
  get on() {
    return this.minutes > 0 || (typeof selected !== 'undefined' && this.hasStays(selected));
  },
  turn: 0,
  cache: new Map()
};
const staysParam = plan => Object.entries(delaySim.stays(plan)).sort((a, b) => a[0] - b[0]).map(([i, m]) => `${i}:${m}`).join(',');
const delaySimKey = (plan, minutes) => `${plan.id}:${minutes}:${staysParam(plan)}`;
// 지금 미리 보기를 무엇으로 계산했는지 한 마디(배지·도장 앞 화면 읽기용, 진행 문구).
function delaySimWhat(plan) {
  const late = delaySim.minutes > 0, stays = delaySim.hasStays(plan);
  return late && stays ? `${delaySim.minutes}분 늦고 체류를 바꾸면` : late ? `${delaySim.minutes}분 늦으면` : '체류를 바꾸면';
}
// 장소 i 의 지금 체류(바꿔 본 값이 있으면 그 값). base: 코스에 저장된 체류.
function stayFor(plan, i, base) {
  return delaySim.stays(plan)[i] ?? base;
}
// 체류를 step(±15)만큼 바꾼다. 원래 값으로 돌아오면 지운다. 바꾼 뒤 미리 보기를 다시 계산하거나(켜짐) 지운다(꺼짐).
function changeStay(plan, i, base, step) {
  if (!plan?.id || !Number.isFinite(base)) return;
  const stays = { ...delaySim.stays(plan) };
  const next = Math.min(STAY_LIMIT[1], Math.max(STAY_LIMIT[0], stayFor(plan, i, base) + step));
  if (next === base) delete stays[i]; else stays[i] = next;
  if (Object.keys(stays).length) delaySim.staysByPlan.set(plan.id, stays); else delaySim.staysByPlan.delete(plan.id);
  syncStaySteppers(plan);
  refreshSimulation(plan);
}
function resetStays(plan) {
  delaySim.staysByPlan.delete(plan?.id);
  syncStaySteppers(plan);
  refreshSimulation(plan);
}
// 장소 카드의 체류 칸 글자·단추 상태를 지금 값으로 맞춘다(다시 그리지 않고 글자만).
function syncStaySteppers(plan) {
  document.querySelectorAll('#plan-detail .stay-stepper').forEach(box => {
    const i = Number(box.dataset.index), base = Number(box.dataset.base), now = stayFor(plan, i, base);
    box.querySelector('.stay-value').textContent = `${now}분`;
    box.classList.toggle('is-changed', now !== base);
    box.querySelector('.stay-minus').disabled = now <= STAY_LIMIT[0];
    box.querySelector('.stay-plus').disabled = now >= STAY_LIMIT[1];
  });
  const reset = document.querySelector('#plan-detail .delay-sim-reset');
  if (reset) reset.hidden = !delaySim.hasStays(plan);
  const help = document.querySelector('#plan-detail .delay-sim-help');
  if (help) help.hidden = delaySim.minutes > 0 || delaySim.hasStays(plan);
}
// 늦어짐·체류 중 하나라도 고른 게 있으면 다시 계산, 없으면 겹친 표시를 지운다.
function refreshSimulation(plan) {
  if (delaySim.on) { delaySimRefresh(plan); return; }
  delaySim.turn += 1;
  clearDelaySim();
  const parts = delaySimParts();
  if (parts) {
    parts.status.textContent = '';
    parts.status.className = 'delay-sim-status';
    parts.basis.hidden = true;
  }
}

function delaySimBar(plan) {
  const bar = node('div', undefined, 'delay-sim');
  bar.setAttribute('role', 'group');
  bar.setAttribute('aria-label', '늦어질 때 미리 보기');
  bar.dataset.planId = plan.id;
  const head = node('div', undefined, 'delay-sim-head');
  const title = node('span', '혹시 늦어지셨나요?', 'delay-sim-title');
  const pills = node('div', undefined, 'delay-sim-pills');
  for (const minutes of DELAY_SIM_CHOICES) {
    const pill = node('button', minutes ? `+${minutes}분` : '정시', 'delay-sim-pill');
    pill.type = 'button';
    pill.dataset.minutes = String(minutes);
    pill.setAttribute('aria-pressed', String(delaySim.minutes === minutes));
    pill.addEventListener('click', () => setDelaySim(minutes));
    pills.append(pill);
  }
  // 체류를 바꿔 본 것이 있으면 되돌리기(시안의 '되돌리기'). 늦어짐은 '정시'가 되돌리기다.
  const reset = button('체류 시간 되돌리기', () => resetStays(plan), 'secondary delay-sim-reset');
  reset.hidden = !delaySim.hasStays(plan);
  head.append(title, pills, reset);
  const help = node('p', '고른 만큼 첫 장소에 늦게 도착한다고 보고, 장소마다 밀린 시각과 주의할 점을 일정에 표시해요. 장소 카드의 −15분·+15분으로 머무는 시간도 바꿔 볼 수 있어요. 코스는 바꾸지 않아요.', 'hint delay-sim-help');
  help.hidden = delaySim.minutes > 0 || delaySim.hasStays(plan);
  const status = node('p', '', 'delay-sim-status');
  status.setAttribute('role', 'status');
  const basis = node('p', '', 'hint delay-sim-basis');
  basis.hidden = true;
  bar.append(head, help, status, basis);
  return bar;
}

function delaySimParts() {
  const detail = document.getElementById('plan-detail'),
    bar = detail?.querySelector('.delay-sim');
  if (!bar) return null;
  return {
    detail,
    bar,
    pills: [...bar.querySelectorAll('.delay-sim-pill')],
    help: bar.querySelector('.delay-sim-help'),
    status: bar.querySelector('.delay-sim-status'),
    basis: bar.querySelector('.delay-sim-basis')
  };
}

// minutes: 0(정시 — 끄기) 또는 DELAY_SIM_CHOICES 의 분. 예전 호출(true/false)도 받는다(true = 30분).
function setDelaySim(minutes) {
  if (minutes === true) minutes = 30;
  if (minutes === false) minutes = 0;
  delaySim.minutes = minutes;
  const parts = delaySimParts();
  if (parts) {
    parts.pills.forEach(pill => pill.setAttribute('aria-pressed', String(Number(pill.dataset.minutes) === minutes)));
    parts.help.hidden = minutes > 0 || delaySim.hasStays(selected);
  }
  if (selected) refreshSimulation(selected);
}

// renderDetail 이 상세를 다시 그린 뒤 부른다. 켜져 있으면 기억한 결과를 겹치거나 새로 불러온다.
function delaySimRefresh(plan) {
  if (!delaySim.on || !plan?.id) return;
  const parts = delaySimParts();
  if (!parts || parts.bar.dataset.planId !== plan.id) return;
  const cached = delaySim.cache.get(delaySimKey(plan, delaySim.minutes));
  if (cached) {
    clearDelaySim();
    applyDelaySim(plan, cached);
    return;
  }
  loadDelaySim(plan);
}

async function loadDelaySim(plan) {
  const turn = ++delaySim.turn,
    minutes = delaySim.minutes,
    parts = delaySimParts();
  clearDelaySim();
  if (parts) {
    parts.status.className = 'delay-sim-status';
    parts.status.textContent = `${delaySimWhat(plan)} 어떻게 되는지 다시 계산하고 있어요…`;
    parts.basis.hidden = true;
  }
  try {
    const stays = staysParam(plan), key = delaySimKey(plan, minutes);
    const data = await api(`/plans/${encodeURIComponent(plan.id)}/delay-check?index=0&minutes=${minutes}` + (stays ? `&stays=${encodeURIComponent(stays)}` : ''));
    delaySim.cache.set(key, data);
    if (delaySim.cache.size > 24) delaySim.cache.delete(delaySim.cache.keys().next().value);
    if (turn !== delaySim.turn || delaySimKey(plan, delaySim.minutes) !== key || selected?.id !== plan.id) return;
    applyDelaySim(plan, data);
  } catch (error) {
    if (turn !== delaySim.turn || selected?.id !== plan.id) return;
    // 계산하지 못하면 고른 채로 두지 않는다(일정은 원래 시각 그대로라 '늦음'이 거짓이 된다). 바꿔 본 체류도 되돌린다.
    delaySim.staysByPlan.delete(plan.id);
    syncStaySteppers(plan);
    setDelaySim(0);
    const after = delaySimParts();
    if (after) {
      after.status.className = 'delay-sim-status warning';
      after.status.textContent = `늦어질 때를 계산하지 못했어요. ${error.message}`;
    }
  }
}

function clearDelaySim() {
  document.querySelectorAll('#plan-detail .delay-sim-time, #plan-detail .delay-sim-badges').forEach(el => el.remove());
  document.querySelectorAll('#plan-detail .is-delay-sim').forEach(el => el.classList.remove('is-delay-sim'));
}

function delaySimMinutes(text) {
  const [h, m] = String(text || '').split(':').map(Number);
  return Number.isFinite(h) && Number.isFinite(m) ? h * 60 + m : null;
}

function delaySimClock(minutes) {
  return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;
}

// 배지 [글, 종류]. 종류: problem(문제) · caution(휴게 시간 기다림) · info(문 여는 시각 기다림) · unknown(자료 없음) · skipped(계산 안 함).
function delaySimBadges(row, place) {
  const out = [];
  if (row.state === 'problem') {
    const text = {
      last_entry: `마지막 입장 ${row.limit} · ${row.over}분 넘김`,
      closing: `영업 종료 ${row.limit} · ${row.over}분 모자람`,
      festival: `축제 운영 종료 ${row.limit} · ${row.over}분 모자람`
    } [row.festival ? 'festival' : row.kind_hint] || `${row.reason} · ${row.limit}`;
    out.push([text, 'problem']);
  }
  if (row.wait > 0) {
    const start = delaySimMinutes(row.start),
      rest = (place?.breaks || []).find(range => Array.isArray(range) && range[1] === start);
    if (row.festival) out.push([`축제 시작 ${row.start}까지 ${row.wait}분 기다림`, 'info']);
    else if (rest) out.push([`휴게 시간 ${delaySimClock(rest[0])}~${row.start} · ${row.wait}분 기다림`, 'caution']);
    else if (Array.isArray(place?.hours) && place.hours[0] === start) out.push([`문 여는 ${row.start}까지 ${row.wait}분 기다림`, 'info']);
    else out.push([`개점·휴게 대기 ${row.wait}분`, 'info']);
  }
  if (row.state === 'unchecked' && row.missing?.length) out.push([`${row.missing.join('·')} 자료 없음 · 연다고 보고 계산`, 'unknown']);
  return out;
}

function delaySimBadgeLine(badges) {
  const line = node('p', undefined, 'delay-sim-badges');
  line.append(node('span', `${typeof selected !== 'undefined' ? delaySimWhat(selected) : delaySim.minutes + '분 늦으면'}: `, 'visually-hidden'));
  badges.forEach(([text, kind]) => {
    const badge = node('span', text, `delay-sim-badge is-${kind}`);
    badge.dataset.kind = kind;
    line.append(badge);
  });
  return line;
}

function delaySimStamp(row) {
  const box = node('span', undefined, 'delay-sim-time');
  const shift = row.shift > 0 ? `+${row.shift}분` : row.shift < 0 ? `${-row.shift}분 일찍` : '그대로';
  box.append(node('span', `${typeof selected !== 'undefined' ? delaySimWhat(selected) : delaySim.minutes + '분 늦으면'} 이용 시작 `, 'visually-hidden'), node('b', row.start, 'delay-sim-start'), node('small', shift, 'delay-sim-shift'));
  // 체류를 바꾼 장소는 떠나는 시각도 달라져 '~떠남 (N분)'을 붙인다(늦어짐만이면 머무는 시간이 같아 시작 시각으로 충분하다).
  if (typeof selected !== 'undefined' && delaySim.hasStays(selected) && row.departure && !row.festival) box.append(node('small', `~ ${row.departure} (${row.stay}분)`, 'delay-sim-departure'));
  return box;
}

// 서버의 문제 종류(first_problem.kind)는 첫 문제 장소 줄에만 있다. 줄에는 reason 만 있어 kind 를 그 줄에 붙여 둔다.
function delaySimRows(data) {
  const kind = data.first_problem?.kind;
  return (data.rows || []).map(row => row.state === 'problem' ? {
    ...row,
    kind_hint: kind
  } : row);
}

function applyDelaySim(plan, data) {
  clearDelaySim();
  const parts = delaySimParts();
  if (!parts) return;
  const stops = [...parts.detail.querySelectorAll('.stop')];
  let placeIndex = data.index - 1;
  const done = new Set();
  for (const row of delaySimRows(data)) {
    if (row.festival) {
      const block = parts.detail.querySelector('.festival-visit');
      if (!block) continue;
      const badges = [
        [`늦으면 ${row.start} 시작${row.shift > 0 ? ` (+${row.shift}분)` : ''}`, 'info'], ...delaySimBadges(row, null)
      ];
      block.classList.add('is-delay-sim');
      block.querySelector('.festival-visit-title')?.after(delaySimBadgeLine(badges));
      continue;
    }
    placeIndex += 1;
    const stop = stops[placeIndex];
    if (!stop) continue;
    done.add(placeIndex);
    stop.classList.add('is-delay-sim');
    stop.querySelector('.timeline-stamp')?.append(delaySimStamp(row));
    const badges = delaySimBadges(row, plan.places[placeIndex]);
    if (badges.length) stop.querySelector('.timeline-card>h4')?.after(delaySimBadgeLine(badges));
  }
  // 첫 문제에서 서버가 계산을 멈춘 뒤 장소(첫 장소 앞은 index=0 이라 없다).
  if (data.status === 'problem') stops.forEach((stop, i) => {
    if (i < data.index || done.has(i)) return;
    stop.classList.add('is-delay-sim');
    stop.querySelector('.timeline-card>h4')?.after(delaySimBadgeLine([
      ['앞에서 문제가 생겨 계산하지 않았어요', 'skipped']
    ]));
  });
  parts.status.className = 'delay-sim-status' + (data.status === 'problem' ? ' is-problem' : '');
  parts.status.textContent = delaySimSummary(data);
  // 늦어짐 → 대신 갈 곳(2026-11-25 Gemini Canvas 시안은 문제 장소를 자동으로 바꾸고 되돌리기를 뒀다). 우리는 자동으로 바꾸지 않고,
  // 이미 있는 서버 지각 복구(접힌 '더 할 수 있는 것' 안 '늦어지면 어디서 문제가 생길까?', app/delay_recovery.py)를 같은 장소·같은 분으로 열어
  // 서버가 영업시간·구간·예산을 다시 맞춘 후보만 고르게 한다. 종료 시각 문제(kind 'end')는 바꿀 장소가 없어 단추를 두지 않는다.
  if (data.status === 'problem' && data.first_problem?.kind !== 'end' && delayRecoveryAllowed(plan) && !(data.stays && Object.keys(data.stays).length)) {
    const go = button('대신 갈 곳 찾기', () => openDelayRecovery(plan, data), 'secondary delay-sim-recover');
    parts.status.append(' ', go);
  }
  parts.basis.textContent = data.basis || '';
  parts.basis.hidden = !data.basis;
}

// 지각 확인 상자를 펼치고 같은 장소(지각 미리 보기는 첫 장소부터)·같은 분으로 확인을 누른다. 상자는 접힌 '더 할 수 있는 것' 안에 있어 그 칸도 연다.
function openDelayRecovery(plan, data) {
  const fold = document.querySelector('#plan-detail .plan-more');
  if (fold) fold.open = true;
  const box = livePlanPanel('.delay-check', plan.id);
  if (!box) return;
  box.open = true;
  const select = box.querySelector('.delay-check-form select'),
    minutes = box.querySelector('.delay-check-form input');
  if (select) select.value = String(Math.max(0, data.index || 0));
  if (minutes) minutes.value = String(data.delay);
  select?.dispatchEvent(new Event('change'));
  minutes?.dispatchEvent(new Event('input'));
  box.querySelector('.delay-check-form button')?.click();
  box.scrollIntoView({
    behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth',
    block: 'start'
  });
}

// 단추 옆 결론 한 줄(위 접힌 상자의 delayCheckView 와 같은 판단, 짧게).
function delaySimSummary(data) {
  const later = data.finish && data.original_finish && data.finish !== data.original_finish;
  const finish = later ? ` 끝나는 시간이 ${data.original_finish}에서 ${data.finish}로 바뀌어요.` : data.finish ? ` 끝나는 시간은 ${data.finish} 그대로예요.` : '';
  // 앞머리: '30분 늦으면' / '체류를 바꾸면' / '30분 늦고 체류를 바꾸면'. 서버가 받은 값(data.delay·data.stays)으로 정한다.
  const stays = data.stays && Object.keys(data.stays).length;
  const what = data.delay && stays ? `${data.delay}분 늦고 체류를 바꾸면` : data.delay ? `${data.delay}분 늦으면` : '체류를 바꾸면';
  const okWhat = data.delay && stays ? `${data.delay}분 늦고 체류를 바꿔도` : data.delay ? `${data.delay}분 늦어도` : '체류를 바꿔도';
  if (data.status === 'problem') {
    const p = data.first_problem;
    if (p.kind === 'end') return `${what} 일정이 ${p.time}에 끝나 정한 종료 시간(${p.limit})보다 ${p.over}분 늦어요.`;
    return `${what} ${p.place}에서 처음 문제가 생겨요(${p.reason}).` + (stays ? ' 체류를 줄이거나 되돌려 보세요.' : ' 「대신 갈 곳 찾기」를 누르면 바꿀 곳을 골라 볼 수 있어요.');
  }
  const waits = (data.pending || []).length;
  if (data.status === 'unknown') return `${okWhat} 시간표로는 괜찮아 보여요.${finish} 영업 정보가 없는 ${waits}곳은 연다고 보고 계산했어요.`;
  return `${okWhat} 괜찮아요.${finish}`;
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
      // 묶음 후보(app/delay_recovery._bundle): 이곳으로 바꿔도 뒤 장소 한 곳이 또 늦어, 그 장소까지 함께 바꾸거나 뺀 안이다.
      // 무엇을 왜 함께 처리하는지는 서버가 적은 글(also.text)을 그대로 보여 준다. 단추 문구로 한 번에 두 곳이 달라진다는 것을 알린다.
      // 한 곳짜리 후보는 also 가 없어 예전과 똑같이 보인다. 보내는 값도 같다(option.id — 서버가 같은 묶음을 다시 계산해 저장).
      const also = option.also;
      if (also) {
        info.append(node('span', also.text, 'delay-recovery-also'));
        if (also.action === 'replace' && !also.hours_known) info.append(node('span', `${also.name} 영업시간 미확인`, 'delay-recovery-unchecked'));
      }
      const choose = button(!also ? '이곳으로 바꾸기' : also.action === 'replace' ? '두 곳 함께 바꾸기' : '바꾸고 뒤 장소 빼기', () => applyDelayRecovery(plan, data, option.id, block, status), 'secondary');
      choose.setAttribute('aria-label', `${recovery.place} 대신 ${option.name}${delayRecoveryJosa(option.name, '으로', '로')} 바꾸기` + (!also ? '' : also.action === 'replace' ? `, ${also.place}${delayRecoveryJosa(also.place, '은', '는')} ${also.name}${delayRecoveryJosa(also.name, '으로', '로')} 함께 바꾸기` : `, ${also.place}${delayRecoveryJosa(also.place, '은', '는')} 함께 빼기`));
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

// 코스 변경 잠금은 다른 변경·되돌리기와 같이 쓴다(plan-actions.js runPlanChange). 못 연 새 코스는 commitNewPlan 이 토스트로 알린다.
async function applyDelayRecovery(plan, data, replacementId, block, status) {
  if (selected?.id !== plan.id) return;
  return runPlanChange(async () => {
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
      if (commitNewPlan(plan.id, updated)) requestAnimationFrame(() => document.querySelector('#plan-detail .delay-recovery-notice')?.focus());
      else status.textContent = '';
    } catch (error) {
      status.textContent = error.message;
      choices.forEach(choice => choice.disabled = false);
      if (!status.isConnected) toast(error.message);
    }
  });
}
