function mountPriceControls() {
  const label = node('label', undefined, 'check'),
    input = node('input');
  input.type = 'checkbox';
  input.name = 'allow_price_estimates';
  input.checked = true;
  label.append(input, node('span', '등록된 단가가 없는 곳은 계획용 예산 범위 사용'));
  const note = node('p', '등록된 단가에 입력한 인원을 곱해 비용을 계산해요. 등록 단가와 계획용 가정을 구분해 표시해요. 블로그 글에 적힌 가격은 읽지 않아요.', 'hint');
  document.querySelector('#submit-plan').before(label, note);
  const preview = node('p', '코스를 추천받으면 인원·예산 입력에 따라 예상 비용을 바로 비교할 수 있어요.', 'hint price-input-preview');
  form.elements.budget.closest('label').after(preview);
  for (const name of ['people', 'budget']) form.elements[name].addEventListener('input', () => updatePricePreview(selected));
  form.elements.budget_unlimited?.addEventListener('change', () => updatePricePreview(selected));
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
  // 예산 무관이면 예산 금액과 비교하지 않는다.
  const budgetPart = form.elements.budget_unlimited?.checked ? ' · 예산 무관' : ' · 입력 예산 ' + won(budget) + ' · 상한 대비 ' + won(budget - totals[1]);
  preview.textContent = '현재 코스 ' + people + '명 기준 ' + range(totals) + (partial ? ' (일부 비용 별도)' : '') + budgetPart;
}

// 비용 표 '출처 / 확인 시점' 칸. place 는 그 줄의 장소(이동·주차 줄은 없음).
// 등록된 단가가 없는 실제 장소(가정 금액·미확인)에는 네이버 지도에서 직접 확인하는 링크만 둔다(검색 API 를 부르지 않는 단순 링크).
function appendPriceEvidence(cell, cost, place) {
  if (cost.price_basis) cell.append(node('small', cost.price_basis, 'price-basis'));
  if (/^https?:\/\//i.test(cost.source || '')) cell.append(sourceLinks('단가 출처 ↗', cost.source, cost.name + ' 가격'));
  else cell.append(node('span', cost.source || '등록 출처 없음'));
  if (cost.checked_at) cell.append(node('small', '조회·확인 ' + cost.checked_at, 'price-basis'));
  if (place && !place.demo && !place.naver_expired && (cost.amount == null || cost.price_kind === 'planning_assumption')) {
    const check = link('네이버 지도에서 가격 확인 ↗', placeMapUrl(place));
    check.classList.add('price-map-check');
    cell.append(check);
  }
}

// 비용 표 아래 한 줄: 합계가 어떤 금액으로 이루어졌는지. 가상 장소 데모(모두 가상 단가)에는 적지 않는다.
function costBasisNote(plan) {
  if (plan.conditions?.mode !== 'real') return null;
  const places = (plan.costs || []).slice(0, plan.places.length),
    assumed = places.filter(c => c.price_kind === 'planning_assumption').length,
    unknown = places.filter(c => c.amount == null).length;
  if (!assumed && !unknown) return null;
  const head = assumed ?
    `이 합계는 실제 가격이 아니라 계획용 가정 범위예요. 장소 ${places.length}곳 중 ${assumed}곳이 가정 금액` + (unknown ? `, ${unknown}곳이 미확인(합계에서 빠짐)이에요.` : '이에요.') :
    `이 합계에는 가격을 모르는 장소 ${unknown}곳이 빠져 있어요.`;
  return node('p', head + ' 블로그 글에 적힌 가격은 읽지 않아요(네이버 검색 API 약관). 실제 가격은 각 장소의 네이버 지도에서 확인해 주세요.', 'hint cost-basis-note');
}
