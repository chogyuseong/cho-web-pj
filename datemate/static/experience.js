function updateExperienceValues(data, f) {
  Object.assign(data, {
    meeting_type: f.get('meeting_type') || 'regular',
    priority: f.get('priority') || 'balanced',
    trust_mode: f.get('trust_mode') || 'balanced',
    hard_constraints: f.getAll('hard_constraints'),
    use_feedback: f.has('use_feedback')
  });
}

function restoreUndoLocks(changed, parent) {
  if (changed.undo_locks) locks = new Set(Object.keys(changed.undo_locks).map(Number));
  else if (changed.places.length !== parent.places.length) locks = new Set(Object.keys(parent.conditions.locked || {}).map(Number));
  form.elements.count.value = parent.conditions.count;
}
const planLockQueue = new Map();
async function togglePlanLock(plan, index) {
  if (plan.can_edit === false) return;
  const task = (planLockQueue.get(plan.id) || Promise.resolve()).catch(() => {}).then(async () => {
    const current = plans.find(p => p.id === plan.id);
    if (!current) return;
    const next = new Set(Object.keys(current.conditions.locked || {}).map(Number));
    next.has(index) ? next.delete(index) : next.add(index);
    const updated = await api('/plans/' + plan.id + '/locks', {
      locked: [...next]
    });
    commitPlanChange(plan.id, updated);
  });
  planLockQueue.set(plan.id, task);
  try {
    return await task;
  } finally {
    if (planLockQueue.get(plan.id) === task) planLockQueue.delete(plan.id);
  }
}

function experienceSelect(label, name, options) {
  const row = node('label', label),
    select = node('select');
  select.name = name;
  for (const [value, text] of options) {
    const option = node('option', text);
    option.value = value;
    select.append(option);
  }
  row.append(select);
  return row;
}

function mountExperienceControls() {
  const box = node('fieldset', undefined, 'experience-controls');
  box.append(node('legend', '우리에게 중요한 기준'));
  box.append(experienceSelect('어떤 만남인가요?', 'meeting_type', [
    ['regular', '평소 데이트'],
    ['first', '첫 만남 · 짧은 이동 우선'],
    ['anniversary', '기념일 · 예약·운영 확인 필요']
  ]), experienceSelect('가장 중요한 것은?', 'priority', [
    ['balanced', '균형 있게'],
    ['talk', '대화 · 카페·휴식 유형 선호'],
    ['food', '맛있는 음식'],
    ['photo', '사진 · 산책·문화 유형 선호'],
    ['activity', '새로운 체험']
  ]), experienceSelect('장소 정보와 새로운 발견', 'trust_mode', [
    ['balanced', '기존 장소와 새로운 장소 함께'],
    ['operating_sources', '유효기간 내 운영 자료가 있는 장소만'],
    ['discovery', '블로그에서 발견한 새 장소 우선']
  ]));
  const details = node('details');
  details.append(node('summary', '반드시 지킬 조건 선택'), node('p', '선택한 항목은 계산상 불일치하거나 확인할 수 없으면 추천·변경 적용을 막아요. 선택하지 않은 항목은 차이를 알리고 대안을 제시해요. 이동·가격의 추정은 실제 보장이 아닙니다.', 'hint'));
  const chips = node('div', undefined, 'chips');
  for (const [value, title] of [
      ['budget', '예산 상한'],
      ['end', '종료 시간'],
      ['max_leg', '구간 이동'],
      ['max_walk', '총 도보'],
      ['setting', '실내·실외'],
      ['reservation', '예약 여부'],
      ['themes', '선택 테마'],
      ['meal', '식사 시간'],
      ['neighborhood', '동네 범위'],
      ['avoid', '피할 활동']
    ]) {
    const label = node('label'),
      input = node('input');
    input.type = 'checkbox';
    input.name = 'hard_constraints';
    input.value = value;
    label.append(input, node('span', title));
    chips.append(label);
  }
  details.append(chips);
  box.append(details);
  const consent = node('label', undefined, 'check'),
    input = node('input');
  input.type = 'checkbox';
  input.name = 'use_feedback';
  consent.append(input, node('span', '이 브라우저의 방문·교체 피드백을 다음 추천에 반영'));
  box.append(consent, node('p', '대기·소음·촬영 가능 여부는 확인된 자료가 없으면 충족으로 표시하지 않아요.', 'hint'));
  form.querySelector('[name=request]').closest('label').before(box);
}

function showPlaceReport(plan, index) {
  const root = openDialog(plan.places[index].name + ' 정보 제보'),
    generation = dialogGeneration,
    select = experienceSelect('어떤 정보가 달랐나요?', 'report_reason', [
      ['closed', '폐업 의심'],
      ['moved', '이전·주소'],
      ['hours', '영업·휴무'],
      ['price', '가격'],
      ['other', '기타']
    ]),
    label = node('label', '설명 또는 확인한 출처 (선택)'),
    note = node('textarea');
  note.maxLength = 500;
  label.append(note);
  root.append(select, label, node('p', '제보만으로 사실을 확정하지 않습니다. 확인 대기 표시와 추천 우선순위에 반영합니다.', 'hint'), button('제보 저장', async () => {
    const result = await api('/plans/' + plan.id + '/place-report', {
      place_id: plan.places[index].id,
      reason: select.querySelector('select').value,
      note: note.value
    });
    if (generation === dialogGeneration) $('#dialog').close();
    toast(result.message);
    const refreshed = await api('/plans/' + plan.id);
    commitPlanChange(plan.id, refreshed);
  }, 'primary'));
}
async function showMealChange(food, plan, afterIndex = 0) {
  const root = openDialog(food.name + ' · 식사 일정에 넣기'),
    generation = dialogGeneration,
    location = experienceSelect('어디에 넣을까요?', 'meal_position', []),
    select = location.querySelector('select');
  const protectedIds = new Set([...locks, ...Object.keys(plan.conditions.locked || {}).map(Number)]);
  if (plan.places.length < 5)
    for (let i = -1; i < plan.places.length; i++) {
      const option = node('option', i < 0 ? '출발 후 첫 장소로 추가' : plan.places[i].name + ' 뒤에 추가');
      option.value = 'add:' + i;
      select.append(option);
    }
  plan.places.forEach((p, i) => {
    if (!protectedIds.has(i)) {
      const option = node('option', p.name + ' 대신 식당으로 교체');
      option.value = 'replace:' + i;
      select.append(option);
    }
  });
  const mealIndex = plan.places.findIndex(p => p.meal || p.id.startsWith('food:'));
  const preferred = mealIndex >= 0 && !protectedIds.has(mealIndex) ? 'replace:' + mealIndex : 'add:' + afterIndex;
  if ([...select.options].some(o => o.value === preferred)) select.value = preferred;
  const menu = experienceSelect('비용 계산에 사용할 메뉴', 'meal_menu', [
      ['0', '메뉴 가격 조회 중…']
    ]),
    menus = menu.querySelector('select');
  root.append(location, menu, node('p', '원래 코스 조건으로 다시 계산합니다. 메뉴는 1인 1개, 식사 체류는 기본 60분 가정이며 방문 수가 바뀔 수 있어요.', 'hint'));
  let loaded = false;
  const preview = button('이동·시간·비용 미리 계산', async () => {
    if (!loaded || !select.value || menus.value === '' || generation !== dialogGeneration || selected?.id !== plan.id) return;
    preview.disabled = true;
    try {
      const [action, index] = select.value.split(':');
      const draft = await api('/plans/' + plan.id + '/meal-preview', {
        restaurant_id: food.id,
        after_index: Number(index),
        replace_index: action === 'replace' ? Number(index) : null,
        locked: [...locks],
        menu_index: Number(menus.value)
      });
      if (generation === dialogGeneration && selected?.id === plan.id && $('#dialog').open) showDraft(plan, draft);
    } finally {
      preview.disabled = false;
    }
  }, 'primary');
  preview.disabled = true;
  root.append(preview);
  try {
    const data = await (restaurantMenuRequests.get(food.id) || api('/places/' + encodeURIComponent(food.id) + '/menu?mode=real'));
    if (generation !== dialogGeneration || selected?.id !== plan.id || !$('#dialog').open) return;
    menus.replaceChildren();
    const items = data.items.filter(item => item.amount != null && item.price_scope !== 'delivery').sort((a, b) => Number(/냉동|밀키트|택배|선물|포장|\d+\s*(?:g|kg)/i.test(a.name)) - Number(/냉동|밀키트|택배|선물|포장|\d+\s*(?:g|kg)/i.test(b.name)) || Number(!a.representative) - Number(!b.representative));
    if (items.length) {
      const placeholder = node('option', '가격 기준 메뉴를 직접 선택해 주세요 (1인 1개 가정)');
      placeholder.value = '';
      menus.append(placeholder);
      items.forEach((item, i) => {
        const option = node('option', item.name + ' · ' + item.display_price + ' / 1개');
        option.value = i;
        menus.append(option);
      });
    } else {
      const option = node('option', '확인된 메뉴 단가 없음 · 웹 참고/계획용 비용을 구분해 계산');
      option.value = 0;
      menus.append(option);
    }
  } catch {
    menus.replaceChildren(node('option', '가격 조회 실패 · 추정 비용과 구분해 계산'));
    menus.firstChild.value = 0;
  }
  if (generation !== dialogGeneration || selected?.id !== plan.id || !$('#dialog').open) return;
  loaded = true;
  const update = () => preview.disabled = !select.options.length || menus.value === '';
  menus.addEventListener('change', update);
  update();
}

function showDraft(original, draft) {
  const root = openDialog('변경 전후를 확인해 주세요'),
    generation = dialogGeneration;
  root.append(node('p', draft.summary), node('p', draft.plan.places.map(p => p.name).join(' → '), 'path-text'));
  const table = node('table');
  for (const [label, before, after] of [
      ['방문 수', original.places.length + '곳', draft.plan.places.length + '곳'],
      ['종료 시간', original.finish, draft.plan.finish],
      ['이동+체류', original.minutes + '분', draft.plan.minutes + '분'],
      ['전체 비용', range(original.total), range(draft.plan.total)]
    ]) {
    const row = node('tr');
    row.append(node('th', label), node('td', before), node('td', '→ ' + after));
    table.append(row);
  }
  root.append(table);
  if (draft.plan.route_verification) root.append(node('p', draft.plan.route_verification, 'hint'));
  for (const c of draft.plan.costs.filter(c => c.price_kind === 'naver_menu')) root.append(node('p', c.name + ' · ' + c.price_basis, 'hint'));
  const differences = draft.plan.deviations?.filter(d => d.state === 'unmet') || [];
  if (differences.length) root.append(node('p', '변경 후 조건 차이: ' + differences.map(d => d.message).join(' / '), 'warning'));
  if (draft.blocking.length) root.append(node('p', '필수 조건 때문에 적용할 수 없어요: ' + draft.blocking.map(c => c.label).join(' · '), 'warning'));
  const apply = button('이 변경안으로 확정', async () => {
    apply.disabled = true;
    try {
      if (selected?.id !== original.id) {
        toast('선택한 코스가 바뀌었어요. 현재 코스에서 다시 시도해 주세요.');
        return;
      }
      const next = await api('/plans/' + original.id + '/draft-apply', {
        token: draft.token
      });
      if (!commitPlanChange(original.id, next) || generation !== dialogGeneration) return;
      form.elements.count.value = next.conditions.count;
      $('#dialog').close();
      $('#plan-detail').scrollIntoView({
        behavior: 'smooth'
      });
      toast('시간·동선·비용을 반영했어요. 교체 되돌리기로 원래 코스로 돌아갈 수 있어요.');
    } finally {
      apply.disabled = false;
    }
  }, 'primary');
  apply.disabled = !draft.can_apply;
  root.append(node('p', '운영·예약·대기 등 미확인 정보는 확정되지 않습니다. 초안은 10분간 유효해요.', 'hint'), apply);
}

function partnerAgreementPanel(plan) {
  const agreement = node('details', undefined, 'partner-agreement');
  agreement.append(node('summary', '둘이 함께 코스 고르기'), node('p', '공유 링크를 상대방에게 보내세요. 서로 다른 브라우저 두 곳에서 의견을 저장할 수 있어요.', 'hint'));
  const content = node('div');
  agreement.append(content);
  let opened = false;
  async function loadAgreement() {
    content.replaceChildren(node('p', '의견을 확인하고 있어요…', 'hint'));
    try {
      const status = await api('/plans/' + plan.id + '/agreement');
      content.replaceChildren(node('p', `의견 저장 ${status.participants}/2 · ` + status.verification, 'hint'));
      if (status.conflicts?.length) content.append(node('p', '의견 조정 필요: ' + status.conflicts.join(' · '), 'warning'));
      const fields = [];
      for (const place of plan.places) {
        const row = experienceSelect(place.name, 'vote_' + place.id, [
          ['neutral', '상관없어요'],
          ['yes', '좋아요'],
          ['must', '꼭 가고 싶어요'],
          ['no', '빼주세요']
        ]);
        row.querySelector('select').value = status.mine[place.id] || 'neutral';
        const counts = status.places[place.id];
        row.append(node('small', `꼭 가고 싶음 ${counts.must||0} · 좋아요 ${counts.yes} · 빼주세요 ${counts.no}`, 'hint'));
        fields.push([place.id, row.querySelector('select')]);
        content.append(row);
      }
      content.append(button('내 의견 저장', async () => {
        await api('/plans/' + plan.id + '/agreement', {
          choices: Object.fromEntries(fields.map(([id, input]) => [id, input.value]))
        });
        await loadAgreement();
        toast('의견을 저장했어요.');
      }, 'primary'), button('상대방 의견 새로고침', loadAgreement));
      if (status.can_replan) {
        const replan = button('합의한 취향으로 다시 계산', async () => {
          replan.disabled = true;
          try {
            const generation = dialogGeneration;
            const draft = await api('/plans/' + plan.id + '/agreement-preview', {
              locked: [...locks]
            });
            if (selected?.id === plan.id && generation === dialogGeneration) showDraft(plan, draft);
          } finally {
            replan.disabled = false;
          }
        }, 'secondary');
        replan.disabled = status.participants < 2 || Boolean(status.conflicts?.length);
        content.append(replan);
      } else content.append(node('p', '코스를 만든 브라우저에서 변경안을 계산·확정할 수 있어요.', 'hint'));
    } catch (e) {
      content.replaceChildren(node('p', e.message, 'warning'), button('다시 확인', loadAgreement));
    }
  }
  agreement.addEventListener('toggle', () => {
    if (agreement.open && !opened) {
      opened = true;
      loadAgreement();
    }
  });
  return agreement;
}

function experiencePanel(plan) {
  const box = node('section', undefined, 'experience-panel');
  const feedback = node('details', undefined, 'visit-feedback');
  feedback.append(node('summary', '다녀온 뒤 3가지 피드백'));
  const visit = experienceSelect('이 코스를 실제 이용했나요?', 'visit_used', [
      ['planned', '아직 계획 중이에요'],
      ['yes', '이용했어요 (자기 신고)'],
      ['no', '이용하지 않았어요']
    ]),
    issue = experienceSelect('가장 불편했던 점은?', 'visit_issue', [
      ['none', '없음'],
      ['closed', '휴무·폐업'],
      ['price', '비용'],
      ['distance', '이동'],
      ['waiting', '웨이팅'],
      ['taste', '취향'],
      ['other', '기타']
    ]),
    reuse = experienceSelect('다음 데이트에도 쓰고 싶나요?', 'visit_reuse', [
      ['unsure', '아직 모르겠어요'],
      ['yes', '네'],
      ['no', '아니요']
    ]);
  feedback.append(visit, issue, reuse, button('방문 피드백 저장', async () => {
    await api('/plans/' + plan.id + '/feedback', {
      kind: 'visit',
      visited: visit.querySelector('select').value,
      obstacle: issue.querySelector('select').value,
      reuse: reuse.querySelector('select').value
    });
    toast('피드백을 저장했어요. 실제 방문 인증과는 구분합니다.');
  }, 'primary'), node('p', '동일 브라우저의 이 코스 피드백은 한 건으로 갱신됩니다. 다음 추천 반영 여부는 조건에서 직접 선택해 주세요.', 'hint'));
  let feedbackLoaded = false;
  feedback.addEventListener('toggle', async () => {
    if (!feedback.open || feedbackLoaded) return;
    feedbackLoaded = true;
    const controls = [...feedback.querySelectorAll('select,button')];
    controls.forEach(c => c.disabled = true);
    try {
      const data = await api('/plans/' + plan.id + '/feedback');
      if (data.visit) {
        visit.querySelector('select').value = data.visit.visited;
        issue.querySelector('select').value = data.visit.obstacle;
        reuse.querySelector('select').value = data.visit.reuse;
      }
    } catch {
      feedbackLoaded = false;
    } finally {
      controls.forEach(c => c.disabled = false);
    }
  });
  feedback.append(button('이 코스의 내 피드백 삭제', async () => {
    await api('/plans/' + plan.id + '/feedback', null, 'DELETE');
    PlanningStudy.refreshDecision(plan.id);
    visit.querySelector('select').value = 'planned';
    issue.querySelector('select').value = 'none';
    reuse.querySelector('select').value = 'unsure';
    toast('이 코스에 남긴 내 선택·교체 이유·방문 피드백을 삭제했어요.');
  }), button('이 브라우저의 피드백 집계', async () => {
    const data = await api('/my/feedback-summary');
    const root = openDialog('내 피드백 집계');
    root.append(node('p', `완료된 추천 ${data.recommendations}건 · 코스 선택 ${data.selections}건`), node('p', `이용했다고 답한 코스 ${data.self_reported_visits}건 · 재사용 의향 있음 ${data.reuse_yes}건`), node('p', data.verification, 'hint'));
    if (data.planning_study) {
      const study = data.planning_study;
      root.append(node('p', `측정 참여 ${study.enrolled_sessions}회 · 코스 결정 ${study.decided_sessions}회`), node('p', `추가 검색 응답 ${study.extra_search_answered}회 중 검색 없이 결정 ${study.no_extra_search}회`), node('p', '참여한 브라우저 검색 기준이며 실제 방문·전체 이용자 전환율과는 달라요.', 'hint'));
    }
  }));
  box.append(feedback);
  return box;
}
document.addEventListener('DOMContentLoaded', mountExperienceControls);
