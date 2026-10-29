function mountPriceControls() {
  const label = node('label', undefined, 'check'),
    input = node('input');
  input.type = 'checkbox';
  input.name = 'allow_price_estimates';
  input.checked = true;
  label.append(input, node('span', '실제 단가 검색이 안 되면 계획용 예산 범위 사용'));
  const note = node('p', '추천 시 가격을 조회하고, 입력한 인원을 곱해 비용을 계산해요. 공식 등록 단가·웹 참고 단가·계획용 가정을 구분해 표시해요.', 'hint');
  document.querySelector('#submit-plan').before(label, note);
  const preview = node('p', '코스를 추천받으면 인원·예산 입력에 따라 예상 비용을 바로 비교할 수 있어요.', 'hint price-input-preview');
  form.elements.budget.closest('label').after(preview);
  for (const name of ['people', 'budget']) form.elements[name].addEventListener('input', () => updatePricePreview(selected));
}

function updatePricePreview(plan) {
  const preview = document.querySelector('.price-input-preview');
  if (!preview || !plan) return;
  const people = Number(form.elements.people.value),
    budget = Number(form.elements.budget.value);
  if (!Number.isFinite(people) || people < 1 || !Number.isFinite(budget)) return;
  const totals = [0, 0];
  let partial = false;
  plan.costs.forEach((cost, index) => {
    if (!cost.unit) {
      partial = true;
      return;
    }
    const person = index < plan.places.length && (cost.price_kind || plan.places[index].price_unit === 'person');
    const factor = person ? people : index >= plan.places.length && plan.conditions.transport === 'transit' ? people / plan.conditions.people : cost.quantity;
    totals[0] += cost.unit[0] * factor;
    totals[1] += cost.unit[1] * factor;
  });
  preview.textContent = '현재 코스 ' + people + '명 기준 ' + range(totals) + (partial ? ' (일부 비용 별도)' : '') + ' · 입력 예산 ' + won(budget) + ' · 상한 대비 ' + won(budget - totals[1]) + ' / 단가 조회는 추천·재검색 시 갱신';
}

function priceRefreshControl(plan) {
  const box = node('div', undefined, 'price-refresh-control');
  if (plan.conditions.mode === 'demo' || plan.can_edit === false) return box;
  const status = node('span', plan.pricing_checked_at ? '최근 계산 ' + new Date(plan.pricing_checked_at).toLocaleString('ko-KR') : '추천 시 단가 조회', 'hint');
  const refresh = button('현재 단가 다시 검색', async () => {
    refresh.disabled = true;
    status.textContent = '장소별 단가 검색·인원별 합계 재계산 중…';
    try {
      const updated = await api('/plans/' + plan.id + '/prices', {});
      commitPlanChange(plan.id, updated);
    } catch (error) {
      status.textContent = error.message;
    } finally {
      refresh.disabled = false;
    }
  });
  box.append(refresh, status);
  return box;
}

function appendPriceEvidence(cell, cost) {
  if (cost.price_basis) cell.append(node('small', cost.price_basis, 'price-basis'));
  if (/^https?:\/\//i.test(cost.source || '')) cell.append(sourceLinks('단가 출처 ↗', cost.source, cost.name + ' 가격'));
  else cell.append(node('span', cost.source || '등록 출처 없음'));
  if (cost.checked_at) cell.append(node('small', '조회·확인 ' + cost.checked_at, 'price-basis'));
  const sources = [...new Set((cost.price_evidence || []).map(quote => quote.source).filter(Boolean))];
  if (sources.length) {
    const blogs = node('div', undefined, 'price-blog-evidence');
    blogs.append(node('strong', '참고한 블로그'));
    for (const source of sources) blogs.append(sourceLinks(source, source, cost.name + ' 메뉴 가격'));
    cell.append(blogs);
  }
}
