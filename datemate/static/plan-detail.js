// 상세는 일정 → 확인 → 결정·공유 순서로 #plan-detail에, 부가 정보는 축제 뒤 #plan-extras에 그린다.
function renderDetail() {
  const root = $('#plan-detail'),
    extras = $('#plan-extras');
  root.replaceChildren();
  extras?.replaceChildren();
  renderPlanMapCard();
  if (!selected) return;
  const p = selected,
    box = node('section', undefined, 'detail panel');
  const head = node('div', undefined, 'detail-header');
  head.append(node('h2', '우리 하루, 자세히 보기'));
  box.append(head, node('p', `${p.conditions.visit_date} · ${p.conditions.start} ~ ${p.finish} · ${p.conditions.people}명`, 'hint'));
  if (p.delta) box.append(node('p', `${p.change_reason} 시간 ${p.delta.minutes>=0?'+':''}${p.delta.minutes}분 · 비용 변화 ${p.delta.cost.map(won).join(' ~ ')}`, 'warning'));
  if (p.conditions.mode === 'demo') box.append(node('p', '모든 장소와 운영·가격 조건은 가상입니다. 이동선은 직선거리로 만든 개략도이며 실제 경로가 아닙니다.', 'warning'));
  if (p.conditions.mode === 'real' && p.conditions.allow_estimates) box.append(estimatedPlanNotice());
  if (p.parent && p.can_edit !== false) {
    const undo = node('div', undefined, 'actions undo-actions');
    undo.append(button(p.transport_change ? '수단 변경 되돌리기' : '교체 되돌리기', async () => {
      const restored = await api('/plans/' + p.id + '/undo', {});
      if (commitPlanChange(p.id, restored)) restoreUndoLocks(p, restored);
    }));
    box.append(undo);
  }
  box.append(transportOverview(p));
  const links = node('div', undefined, 'map-link-list');
  p.places.forEach((place, i) => links.append(placeMapLink(`${i+1}. 네이버에서 찾기`, place)));
  box.append(links);
  p.places.forEach((place, i) => {
    box.append(routeLine(p, i, `${p.legs[i].origin} → ${place.name}`));
    const stop = node('article', undefined, 'stop');
    const stamp = node('div', undefined, 'timeline-stamp');
    stamp.append(node('strong', p.timeline[i].arrival), node('small', p.timeline[i].departure + '까지'), node('span', String(i + 1), 'stop-number'));
    stop.append(stamp);
    const body = node('div', undefined, 'timeline-card');
    body.append(node('span', `STEP ${i+1} · ${place.category}`, 'step-category'));
    const cost = p.costs.find(c => c.name === place.name);
    if (cost) body.append(node('div', `${p.conditions.people}인 장소 비용 · ${range(cost.amount)}`, 'stop-cost'));
    body.append(node('h4', place.name), node('div', `${p.timeline[i].arrival} ~ ${p.timeline[i].departure} · ${place.category}`, 'small'), linkedText('p', p.reasons[i], 'hint'));
    const buttons = node('div', undefined, 'actions');
    buttons.append(button(locks.has(i) ? '● 고정됨' : '○ 장소 고정', () => togglePlanLock(p, i)), button('↻ 다른 장소로 변경', () => showAlternatives(i)), button('장소 정보 · 질문', () => showPlace(place.id, p.conditions.mode)), link('도착지 지도·길찾기 확인', p.legs[i].link));
    body.append(placeEvidencePanel(p, i));
    if (p.conditions.mode === 'real' && hasPlaceMenu(place)) body.append(restaurantMenuPanel(place));
    body.append(placePhotoPanel(place, p.conditions.mode, false, true), placeBlogPanel(place, p.conditions.mode), buttons);
    if (p.can_edit === false) {
      buttons.children[0].disabled = true;
      buttons.children[1].disabled = true;
    }
    stop.append(body);
    box.append(stop, mealSuggestionPanel(p, i));
  });
  if (p.conditions.return_home && p.legs.length > p.places.length) {
    const r = p.legs.at(-1);
    box.append(routeLine(p, p.legs.length - 1, `귀가: ${r.origin} → ${r.destination}`));
  }
  // 확인: 네 가지 확인, 비용표(접힘), 합계와 미확인 비용 경고(접힘 밖)
  box.append(executionSummary(p), node('h3', '비용은 투명하게'));
  const scroll = node('div', undefined, 'table-scroll'),
    table = node('table', undefined, 'cost-table'),
    thead = node('thead'),
    tr = node('tr');
  [
    ['구분 / 장소·구간', ''],
    ['단가', 'num'],
    ['수량', 'num'],
    ['계산식', ''],
    ['금액', 'num'],
    ['상태', ''],
    ['출처 / 확인 시점', '']
  ].forEach(([h, cls]) => {
    const th = node('th', h, cls || undefined);
    th.scope = 'col';
    tr.append(th);
  });
  thead.append(tr);
  table.append(thead);
  const tbody = node('tbody');
  for (const c of p.costs) {
    const r = node('tr');
    [`${c.category} / ${c.name}`, range(c.unit), String(c.quantity), c.formula, range(c.amount), {
      confirmed: '확정',
      estimated: '추정',
      unknown: '미확인'
    } [c.status] || c.status, `${c.source} / ${c.checked_at||'시점 미확인'}`].forEach(v => r.append(node('td', v)));
    const cells = r.children;
    for (const [index, value] of [
        [1, c.unit],
        [4, c.amount]
      ]) {
      cells[index].className = 'num';
      cells[index].replaceChildren(rangeLines(value));
    }
    cells[2].className = 'num';
    r.lastElementChild.replaceChildren();
    appendPriceEvidence(r.lastElementChild, c);
    tbody.append(r);
  }
  table.append(tbody);
  scroll.append(table);
  scroll.tabIndex = 0;
  scroll.setAttribute('role', 'region');
  scroll.setAttribute('aria-label', '장소별 비용 표 · 가로로 넘겨 확인');
  const costs = node('details', undefined, 'cost-table-details');
  costs.append(node('summary', `장소·구간별 비용 표 ${p.costs.length}항목`), priceRefreshControl(p), node('p', '표가 잘리면 좌우로 넘겨 단가와 출처를 확인하세요.', 'hint'), scroll);
  box.append(costs);
  for (const [label, value] of [
      ['확인된 비용', range(p.confirmed)],
      ['추정 비용', range(p.estimated)],
      ['예산 대비 차액 (미확인 비용 제외)', range(p.remaining)]
    ]) {
    const row = node('div', undefined, 'total-row');
    row.append(node('span', label), node('span', value));
    box.append(row);
  }
  if (p.unknown.length) box.append(node('p', '추가 확인 필요: ' + p.unknown.join(', ') + ' · 0원으로 처리하지 않았습니다.', 'warning'));
  // 결정·공유: 결정 패널과 공유 버튼을 한 구역에 둔다. 주 버튼은 '이 코스로 결정' 하나다.
  const share = node('section', undefined, 'plan-share');
  share.setAttribute('aria-label', '코스 결정과 공유');
  const actions = node('div', undefined, 'actions share-actions');
  actions.append(button('코스 카드 저장', () => showShareCard(p)), button('공유 링크 복사', () => copyPlanShare(p)), button('공유 취소', () => revokePlanShares(p)), button('인쇄 / PDF', () => window.print()));
  share.append(decisionPanel(p), node('h3', '코스 저장·공유'), actions);
  box.append(share);
  root.append(box);
  // 부가 정보: 축제 구역 뒤 #plan-extras
  const more = node('section', undefined, 'detail panel plan-extras-panel');
  more.setAttribute('aria-label', '더 둘러보기');
  more.append(leisureCoursePanel(p), regionalRestaurantPanel(p));
  if (p.course_search) {
    const research = node('details', undefined, 'course-evidence'),
      panel = courseSearchPanel(p.course_search, p);
    research.append(node('summary', `추천에 참고한 블로그·장소 정보 (글 ${p.course_search.posts?.length || 0}개)`), panel);
    // 경고는 닫힌 접힘 안에 두지 않는다.
    for (const warning of panel.querySelectorAll('.warning')) more.append(warning);
    more.append(research);
  }
  more.append(node('p', '외부 장소 평점: 확보한 평가 자료가 없습니다. 아래 자체 후기와 별도입니다.', 'hint'));
  more.append(node('h3', '이 일정에 대해 물어보세요'), chatWidget('plan', p.id, p.conditions.mode));
  const reviews = node('div');
  more.append(reviews);
  more.append(experiencePanel(p));
  (extras || root).append(more);
  loadReviews(reviews, p).catch(e => reviews.append(node('p', e.message, 'warning')));
}

function replaceInList(oldId, p) {
  const i = plans.findIndex(x => x.id === oldId);
  if (i < 0) return false;
  plans[i] = p;
  return true;
}
