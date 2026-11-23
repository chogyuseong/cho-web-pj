// 방문 순서 제안(GET /api/plans/{id}/order-suggestion, POST /api/plans/{id}/reorder — app/order_suggestion.py).
// 일정 위에 접힌 상자로 둔다. 펼치면 같은 장소를 다른 순서로 돌 때 이동이 줄어드는지 서버에 한 번 묻고,
// 줄어드는 순서가 있으면 그 순서 하나와 [이 순서로 바꾸기]를 보여 준다. 없으면 서버가 적은 까닭을 그대로 보여 준다.
// - 왜 접어 두나: 순서 계산(최대 120가지)은 펼친 사람에게만 필요하다. 코스를 열 때마다 하지 않는다.
// - 문구·판단은 서버가 한다(줄어드는 분, 고정·예약한 장소는 제자리, 영업시간을 지키는 순서만). 여기서는 받은 값을 적기만 한다.
// - 누르면 새 코스로 저장되고(되돌리기 가능), 화면은 장소 바꾸기와 같은 방식(commitNewPlan)으로 새 코스를 보여 준다.
// - 공유받은 코스·보관 기한이 지난 코스·장소가 한 곳인 코스에는 상자를 두지 않는다(plan-detail.js 가 이 함수의 null 을 건너뛴다).
function orderSuggestionPanel(plan) {
  if (!plan?.id || plan.can_edit === false || (plan.places || []).length < 2) return null;
  if (typeof planHistoryExpired === 'function' && planHistoryExpired(plan)) return null;
  // 클래스는 지각 확인(.delay-check)과 따로 둔다 — 그 이름으로 상자를 찾는 코드·테스트와 겹치지 않게. 모양만 results.css 에서 같이 쓴다.
  const box = node('details', undefined, 'order-suggestion');
  box.append(node('summary', '순서를 바꾸면 이동이 줄어들까?'));
  const result = node('div', undefined, 'order-suggestion-result');
  result.setAttribute('role', 'status');
  box.append(result);
  let asked = false;
  box.addEventListener('toggle', async () => {
    if (!box.open || asked) return;
    asked = true;
    result.replaceChildren(node('p', '가능한 순서를 계산하고 있어요…', 'hint'));
    try {
      const data = await api(`/plans/${encodeURIComponent(plan.id)}/order-suggestion`);
      if (selected?.id !== plan.id) return;
      result.replaceChildren(...orderSuggestionView(plan, data, result));
    } catch (error) {
      asked = false; // 실패하면 다시 펼쳤을 때 한 번 더 묻는다
      result.replaceChildren(node('p', error.message, 'warning'));
    }
  });
  return box;
}

function orderSuggestionView(plan, data, result) {
  const found = data.suggestion;
  if (!found) return [node('p', data.reason || '더 짧은 순서를 찾지 못했어요.', 'hint order-suggestion-none')];
  const parts = [
    node('p', `${found.names.map((name, i) => `${i + 1}. ${name}`).join(' → ')} 순서로 돌면 이동이 약 ${found.saved_minutes}분 줄어요.`, 'order-suggestion-order'),
    node('p', `이동 ${found.travel_before}분 → ${found.travel_after}분 · 끝나는 시각 ${found.finish_before} → ${found.finish_after}`, 'hint')
  ];
  // 순서를 바꾸면 축제 자리가 달라지는 경우(app/festival_time.change_note — 서버가 쓴 글).
  if (found.festival_change) parts.push(node('p', found.festival_change, 'warning festival-change-note'));
  const status = node('p', undefined, 'hint order-suggestion-status');
  // 코스 변경 잠금은 다른 변경·되돌리기와 같이 쓴다(plan-actions.js runPlanChange). 못 연 새 코스는 commitNewPlan 이 토스트로 알린다.
  const apply = button('이 순서로 바꾸기', () => {
    if (apply.disabled || selected?.id !== plan.id) return;
    return runPlanChange(async () => {
      apply.disabled = true;
      status.textContent = '새 코스를 저장하고 있어요…';
      try {
        const updated = await api(`/plans/${encodeURIComponent(plan.id)}/reorder`, {
          order: found.order
        });
        if (!commitNewPlan(plan.id, updated)) status.textContent = '';
      } catch (error) {
        status.textContent = error.message;
        apply.disabled = false;
        if (!status.isConnected) toast(error.message);
      }
    });
  }, 'secondary');
  parts.push(node('p', `${data.basis} 고정했거나 예약한 장소는 제자리에 두고, 영업시간과 종료 시각을 지키는 순서만 봤어요. 누르면 새 코스로 저장하고 위의 되돌리기로 돌아갈 수 있어요.`, 'hint'), apply, status);
  return parts;
}
