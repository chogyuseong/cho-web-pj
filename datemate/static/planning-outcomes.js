/* Decisions work for everyone; timing and research answers require explicit opt-in. */
const PlanningStudy = {
  async showDecisions() {
    const root = openDialog('내가 결정한 코스');
    root.append(node('p', '현재 브라우저에서 결정한 최근 코스 최대 10개예요.', 'hint'));
    try {
      const data = await api('/my/decisions');
      if (!data.items.length) root.append(node('p', '아직 결정한 코스가 없어요. 추천받은 뒤 마음에 드는 코스를 결정해 보세요.'));
      for (const item of data.items) {
        const row = node('article', undefined, 'saved-decision'),
          a = link(item.title, '/?plan=' + encodeURIComponent(item.id));
        a.target = '_self';
        row.append(a, node('p', (item.visit_date || '') + ' · ' + item.places.join(' → '), 'hint'));
        root.append(row);
      }
    } catch (error) {
      root.append(node('p', error.message, 'warning'), button('다시 불러오기', () => this.showDecisions()));
    }
  },
  refreshDecision(id) {
    for (const box of document.querySelectorAll('.planning-decision'))
      if (box.dataset.planId === id) box.reloadDecision?.();
  },
  mount(optional) {
    const details = node('details', undefined, 'planning-study');
    details.append(node('summary', '계획 경험 측정 참여 (선택)'));
    const label = node('label', undefined, 'check'),
      input = node('input');
    input.type = 'checkbox';
    input.name = 'measure_planning';
    label.append(input, document.createTextNode('추천 요청부터 코스 결정까지의 시간을 측정해도 좋아요'));
    details.append(label, node('p', '참여하면 요청 시각·코스 결정 시각과 선택한 답변을 기록해요. 대기·자리 비움도 포함됩니다. 입력한 요청 내용은 측정 기록에 넣지 않아요. 이 브라우저의 데이터 삭제로 기록을 지울 수 있어요.', 'hint'));
    optional.append(details);
  },
  async prepare(data) {
    if (!form.elements.measure_planning?.checked) return;
    try {
      const session = await api('/planning-sessions', {
        consented: true
      }, undefined, {
        timeout: 5000
      });
      data.planning_session_id = session.session_id;
    } catch {
      toast('측정에 연결하지 못해 코스 추천만 진행해요.');
    }
  }
};

function decisionPanel(plan) {
  if (plan.can_edit === false) return document.createDocumentFragment();
  const box = node('section', undefined, 'planning-decision');
  box.dataset.planId = plan.id;
  box.setAttribute('aria-label', '코스 결정과 함께 고르기');
  const initial = '코스를 결정해 두면 나중에 확인할 수 있어요. 결정 후에도 장소를 바꿀 수 있어요.';
  const status = node('p', initial, 'hint');
  status.setAttribute('role', 'status');
  box.append(node('h3', '마음에 드는 코스를 결정해 보세요'), status);
  const measured = Boolean(plan.conditions.planning_session_id);
  let extra = null,
    baseline = null;
  if (measured) {
    const survey = node('details', undefined, 'decision-survey');
    survey.append(node('summary', '계획 경험 남기기 (선택)'));
    const label = node('label', '이 코스를 고르기 위해 따로 검색했나요?');
    extra = node('select');
    extra.name = 'decision_extra_search';
    for (const [value, title] of [
        ['unknown', '응답하지 않을게요'],
        ['none', '추가 검색 없이 골랐어요'],
        ['some', '일부 정보를 더 검색했어요'],
        ['many', '대부분 다시 검색했어요']
      ]) {
      const option = node('option', title);
      option.value = value;
      extra.append(option);
    }
    label.append(extra);
    const manual = node('label', '평소 직접 코스를 짜는 데 걸리는 시간 (분, 선택)');
    baseline = node('input');
    baseline.type = 'number';
    baseline.min = '0';
    baseline.max = '240';
    baseline.step = '1';
    baseline.name = 'manual_planning_minutes';
    baseline.placeholder = '기억나는 경우에만 입력';
    manual.append(baseline);
    survey.append(label, manual, node('p', '평소 시간과 추가 검색 여부는 자기 신고예요. 자동으로 측정한 시간과 따로 집계해요.', 'hint'));
    box.append(survey);
  }
  const actions = node('div', undefined, 'actions');
  const confirm = button('이 코스로 결정', async () => {
    if (baseline && !baseline.reportValidity()) return;
    confirm.disabled = true;
    try {
      const value = {
        extra_search: extra?.value || 'unknown',
        manual_planning_minutes: baseline?.value ? Number(baseline.value) : null
      };
      const result = await api('/plans/' + plan.id + '/decision', value);
      if (!box.isConnected) return;
      show(result.decision);
      toast('이 코스로 결정했어요. 변경이 필요하면 장소를 바꿀 수 있어요.');
    } catch (error) {
      status.textContent = '코스 결정을 저장하지 못했어요. ' + error.message;
    } finally {
      confirm.disabled = false;
    }
  }, 'primary');
  confirm.disabled = true;
  const together = button('상대와 함께 고르기', async () => {
    await copyPlanShare(plan);
    agreement.open = true;
  });
  actions.append(confirm, together);
  box.append(actions);
  const agreement = partnerAgreementPanel(plan);
  box.append(agreement);

  function show(decision) {
    if (!decision) return;
    const duration = decision.elapsed_seconds != null ? (Math.floor(decision.elapsed_seconds / 60) + '분 ' + decision.elapsed_seconds % 60 + '초') : '';
    status.textContent = '✓ 이 코스로 결정했어요.' + (duration ? ' 추천 요청부터 ' + duration + '가 걸렸어요. 대기·자리 비움 포함.' : '');
    confirm.textContent = measured ? '결정 내용 저장' : '결정 완료';
    if (extra) extra.value = decision.extra_search || 'unknown';
    if (baseline) baseline.value = decision.manual_planning_minutes ?? '';
  }
  box.reloadDecision = () => api('/plans/' + plan.id + '/decision').then(result => {
    if (box.isConnected) {
      status.textContent = initial;
      confirm.textContent = '이 코스로 결정';
      show(result.decision);
    }
  }).catch(() => {
    if (box.isConnected) status.textContent = '결정 기록을 불러오지 못했어요. 아래 버튼으로 다시 저장할 수 있어요.';
  }).finally(() => confirm.disabled = false);
  box.reloadDecision();
  return box;
}
