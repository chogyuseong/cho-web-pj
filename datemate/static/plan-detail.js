// 모든 구간의 설명(source)이 같으면 그 문장, 아니면 null. 같을 때는 일정 위에 한 번만 적고 구간마다 반복하지 않는다.
// 비용 표 '상태' 칸. 합계에 들어갔는지까지 한 칸에 적는다(개선안 22).
// 금액이 없으면 합계에서 빠진 미확인, 계획용 가정 범위면 합계에 들어간 가정(실제 단가 아님), 나머지는 확정·추정.
function costStatusLabel(c) {
  if (c.amount == null) return '미확인 · 합계에서 빠짐';
  if (c.price_kind === 'planning_assumption') return '가정 · 실제 단가 아님 · 합계에 포함';
  return {
    confirmed: '확정',
    estimated: '추정'
  } [c.status] || c.status;
}

// 고정한 축제 방문 한 칸. 장소 칸(article.stop)이 아니다: 장소 순번·지도 표시·장소 단추(maps.js·place-dialog.js 는 .stop 만 센다)에 끼지 않는다.
// 요금은 주최 측 자유 글이라 비용에 넣지 않는다(festivals.js 와 같은 원칙).
// 코스 끝에 둔 저녁 축제(position 'last')는 마지막 장소에서 행사장으로 돌아오는 구간(visit.leg)을 같이 적는다. 그 구간은 plan.legs 에 없다.
function festivalVisitBlock(plan, visit) {
  const last = visit.position === 'last';
  const block = node('section', undefined, 'festival-visit');
  block.setAttribute('aria-label', last ? '운영 시간에 맞춰 코스 끝에 둔 축제 방문' : '운영 시간에 맞춰 고정한 축제 방문');
  if (last && visit.leg && Number.isFinite(visit.leg.minutes)) block.append(node('p', `${plan.places.at(-1)?.name || '마지막 장소'} → 축제 행사장 · ${legModeLabel(plan, visit.leg)}`, 'hint festival-visit-leg'));
  const wait = visit.wait ? ` · ${last ? '행사장에 닿은 뒤 ' : ''}시작까지 ${visit.wait}분 기다림` : '';
  const after = last ? '마지막 장소를 둘러본 뒤 행사장으로 돌아와 축제로 하루를 마무리해요.' : '축제가 끝나면 행사장에서 아래 첫 장소로 이동해요.';
  block.append(node('strong', `${visit.arrival}~${visit.departure} 축제 · ${visit.title}`, 'festival-visit-title'),
    node('p', `안내된 운영 시간 ${visit.hours} 기준으로 시각을 고정했어요${wait}. ${after} 개최·시간은 방문 전 주최 측에서 다시 확인해 주세요.`, 'hint'));
  return block;
}

function sharedLegSource(plan) {
  const sources = (plan.legs || []).map(leg => leg.source).filter(Boolean);
  return sources.length > 1 && sources.every(source => source === sources[0]) ? sources[0] : null;
}

// 상세는 일정 → 확인 → 결정·공유 순서로 #plan-detail에, 부가 정보는 축제 뒤 #plan-extras에 그린다.
function renderDetail() {
  const root = $('#plan-detail'),
    extras = $('#plan-extras');
  root.replaceChildren();
  // 어느 코스의 상세인지(코스 탭은 상세를 다음 화면 갱신 뒤에 그림, plan-results choose).
  root.dataset.planId = selected ? selected.id : '';
  extras?.replaceChildren();
  if (!selected) {
    renderPlanMapCard();
    return;
  }
  const p = selected,
    box = node('section', undefined, 'detail panel');
  const head = node('div', undefined, 'detail-header');
  head.append(node('h2', '우리 하루, 자세히 보기'));
  box.append(head, node('p', `${p.conditions.visit_date} · ${p.conditions.start} ~ ${p.finish} · ${p.conditions.people}명`, 'hint'));
  if (p.delta) box.append(node('p', `${p.change_reason} 시간 ${p.delta.minutes>=0?'+':''}${p.delta.minutes}분 · ${costChangeText(totalBefore(p), p.total)}`, 'warning'));
  if (p.conditions.mode === 'demo') box.append(node('p', '모든 장소와 운영·가격 조건은 가상입니다. 이동선은 직선거리로 만든 개략도이며 실제 경로가 아닙니다.', 'warning'));
  if (p.conditions.mode === 'real' && p.conditions.allow_estimates) box.append(estimatedPlanNotice());
  // 보관 기한(21일)이 지나 좌표까지 지운 네이버 검색 장소가 있으면 다시 계산하는 기능(바꾸기·주변 찾기)을 그리지 않는다.
  const expired = planHistoryExpired(p);
  if (expired) box.append(planHistoryExpiredNote());
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
  links.append(node('span', '네이버 지도에서 찾기', 'map-link-label'));
  // 이름·주소를 지운 장소(보관 기간 지남)는 지도에서 찾을 말이 없어 빼고, 번호는 일정 순서 그대로 둔다.
  p.places.forEach((place, i) => {
    if (!place.naver_expired) links.append(placeMapLink(`${i+1}. ${place.name}`, place));
  });
  box.append(links);
  // 구간마다 같은 설명(예: '직선거리 × 1.35 기반 이동 추정 · 실제 길찾기 미반영')이면 여기서 한 번만 적는다(routeLine 은 생략).
  const legSource = sharedLegSource(p);
  if (legSource) box.append(node('p', '이동 시간: ' + legSource, 'hint route-source-note'));
  // 대중교통 구간이 있으면 지하철·버스 구분 없는 추정이라는 것과 가정값을 일정 위에 한 번 적는다(plan-evidence.js transitBasisNote).
  const transitNote = transitBasisNote(p);
  if (transitNote) box.append(transitNote);
  // 지금 늦으면 어디서 처음 문제가 생기는지(읽기 전용, delay-check.js). 저장된 코스(id)가 있을 때만.
  if (p.id && typeof delayCheckPanel === 'function') box.append(delayCheckPanel(p));
  // 약속 당일 도구(day-of.js): 마지막 출발 시각, 한 곳씩 크게 보기, 현장용 일정 복사. 서버에 묻지 않는다.
  if (typeof dayOfTools === 'function') box.append(dayOfTools(p));
  // 운영 시간에 맞춰 맨 앞에 고정한 축제 방문(app/festival_time.py). 첫 구간 줄(행사장 → 첫 장소) 바로 앞에 둔다.
  if (p.festival_visit && p.festival_visit.position !== 'last') box.append(festivalVisitBlock(p, p.festival_visit));
  p.places.forEach((place, i) => {
    box.append(routeLine(p, i, `${p.legs[i].origin} → ${place.name}`));
    const stop = node('article', undefined, 'stop');
    const stamp = node('div', undefined, 'timeline-stamp');
    stamp.append(node('strong', p.timeline[i].arrival), node('small', p.timeline[i].departure + '까지'), node('span', String(i + 1), 'stop-number'));
    stop.append(stamp);
    const body = node('div', undefined, 'timeline-card');
    // 읽는 순서: 장소 이름 → 한 줄 요약(분류 · 2인 비용 · 머무는 시간) → 후기에서 읽은 정보. 도착·떠나는 시각은 왼쪽 도장에 있다.
    // 분류·체류·확인 방법·근거 링크를 이은 긴 문장(reasons)은 '정보 출처' 접기 안으로 옮긴다(2026-11-17 가독성 정리).
    body.append(node('h4', place.name));
    // 네이버 지역 검색으로 찾은 장소: '네이버 검색결과' 표시와 원본 링크(특약 2.1·2.2). 21일이 지나 지운 장소는 안내만.
    if (place.naver_expired) body.append(naverExpiredNote());
    else if (isNaverResult(place)) body.append(naverAttribution('지역 검색', place.place_source || place.source));
    const meta = node('p', undefined, 'stop-meta');
    meta.append(node('span', placeKind(place), 'step-category'));
    const cost = p.costs.find(c => c.name === place.name);
    if (cost) meta.append(node('span', `${p.conditions.people}인 ${range(cost.amount)}`, 'stop-cost'));
    const stay = p.timeline[i]?.stay;
    // 구분점 없이 간격으로 나눈다(비용이 길어 줄이 바뀌면 점이 새 줄 맨 앞에 홀로 남았다).
    if (Number.isFinite(stay)) meta.append(node('span', `${stay}분 머묾`, 'stop-stay'));
    body.append(meta, reviewFactsLine(place, p.conditions.mode));
    if (p.reasons[i]) {
      const source = node('details', undefined, 'stop-source');
      source.append(node('summary', '정보 출처'), linkedText('p', p.reasons[i], 'hint'));
      body.append(source);
    }
    const buttons = node('div', undefined, 'actions');
    buttons.append(button(locks.has(i) ? '● 고정됨' : '○ 장소 고정', () => togglePlanLock(p, i)), button('↻ 다른 장소로 변경', () => showAlternatives(i)), button('장소 정보 · 질문', () => showPlace(place.id, p.conditions.mode)));
    // 길찾기 링크가 없는 구간(보관 기간이 지나 좌표를 지운 장소)은 링크 자리를 두지 않는다.
    if (p.legs[i].link) buttons.append(link('도착지 지도·길찾기 확인', p.legs[i].link));
    body.append(placeEvidencePanel(p, i));
    if (p.can_edit === false) {
      buttons.children[0].disabled = true;
      buttons.children[1].disabled = true;
    }
    // 보관 기간이 지난 장소가 있는 코스는 장소를 바꿀 수 없다(서버가 409, 위 planHistoryExpiredNote).
    if (expired) buttons.children[1].disabled = true;
    // 보관 기간이 지난 네이버 검색 장소는 장소 정보(사진·블로그·메뉴)를 다시 찾지 않는다(이름·주소가 지워짐).
    if (place.naver_expired) {
      body.append(buttons);
      stop.append(body);
      box.append(stop);
      return;
    }
    if (p.conditions.mode === 'real' && hasPlaceMenu(place)) body.append(restaurantMenuPanel(place));
    body.append(placePhotoPanel(place, p.conditions.mode, false, true), placeBlogPanel(place, p.conditions.mode), buttons);
    stop.append(body);
    // 자동차로 도착하는 장소는 바로 아래에 근처 주차장을 둔다(일정·비용에는 넣지 않음).
    box.append(stop, parkingPanel(p, i), mealSuggestionPanel(p, i));
  });
  // 코스 끝에 둔 저녁 축제: 마지막 장소 뒤, 귀가 구간(행사장 → 귀가지) 앞.
  if (p.festival_visit?.position === 'last') box.append(festivalVisitBlock(p, p.festival_visit));
  if (p.conditions.return_home && p.legs.length > p.places.length) {
    const r = p.legs.at(-1);
    box.append(routeLine(p, p.legs.length - 1, `귀가: ${r.origin} → ${r.destination}`));
  }
  // 휴대폰 지도 자리: 일정을 먼저 읽고 지도를 보도록 일정 바로 뒤에 둔다(2026-11-17 가독성 정리, 전에는 일정 앞).
  // 데스크톱은 오른쪽 패널(#plan-map-rail)에 그린다. 지도는 상세를 문서에 붙인 뒤 renderPlanMapCard 가 채운다.
  const slot = node('div', undefined, 'plan-map-slot');
  slot.id = 'plan-map-slot';
  slot.hidden = true;
  box.append(slot);
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
    [`${c.category} / ${c.name}`, range(c.unit), String(c.quantity), c.formula, range(c.amount), costStatusLabel(c), `${c.source} / ${c.checked_at||'시점 미확인'}`].forEach(v => r.append(node('td', v)));
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
    appendPriceEvidence(r.lastElementChild, c, p.places[p.costs.indexOf(c)]);
    tbody.append(r);
  }
  table.append(tbody);
  scroll.append(table);
  scroll.tabIndex = 0;
  scroll.setAttribute('role', 'region');
  scroll.setAttribute('aria-label', '장소별 비용 표 · 가로로 넘겨 확인');
  const costs = node('details', undefined, 'cost-table-details');
  costs.append(node('summary', `장소·구간별 비용 표 ${p.costs.length}항목`), node('p', '표가 잘리면 좌우로 넘겨 단가와 출처를 확인하세요.', 'hint'), scroll);
  box.append(costs);
  // 합계의 성격을 표 바로 아래에 한 줄로 밝힌다(실제 장소 코스만). 블로그 글의 금액은 읽지 않으므로 등록 단가가 없는 곳은 가정 범위나 미확인이다.
  const basisNote = costBasisNote(p);
  if (basisNote) box.append(basisNote);
  for (const [label, value] of [
      ['확인된 비용', range(p.confirmed)],
      ['추정 비용', range(p.estimated)],
      budgetUnlimited(p) ? ['예산', '예산 무관 · 예산과 비교하지 않아요'] : ['예산 대비 차액 (미확인 비용 제외)', range(p.remaining)]
    ]) {
    const row = node('div', undefined, 'total-row');
    row.append(node('span', label), node('span', value));
    box.append(row);
  }
  // 합계에 무엇이 들어갔고 무엇이 빠졌는지(개선안 22). 가정 가격은 합계에 '들어간' 추정이고, 미확인은 합계에서 '빠진' 항목이다.
  const assumed = p.costs.filter(c => c.price_kind === 'planning_assumption');
  if (assumed.length) box.append(node('p', '합계에 들어간 가정 가격(실제 단가 아님): ' + assumed.map(c => `${c.name} ${range(c.amount)}`).join(', '), 'hint cost-assumed'));
  if (p.unknown.length) box.append(node('p', '합계에서 빠진 항목(추가 확인 필요): ' + p.unknown.join(', ') + ' · 0원으로 처리하지 않았습니다.', 'warning'));
  // 결정·공유: 결정 패널과 공유 버튼을 한 구역에 둔다. 주 버튼은 '이 코스로 결정' 하나다.
  const share = node('section', undefined, 'plan-share');
  share.setAttribute('aria-label', '코스 결정과 공유');
  const actions = node('div', undefined, 'actions share-actions');
  // 인쇄는 누른 그 순간(같은 click 처리 안)에 부른다. button() 은 동작을 Promise 로 한 단계 미뤄 실행하는데,
  // 아이폰 Safari 에서는 이 단추를 눌러도 아무 반응이 없었다(2026-11-17 사용자 신고). 사용자 조작 안에서 바로 부르는 것이 알려진 해법이다.
  const printButton = node('button', '인쇄 / PDF', 'secondary');
  printButton.type = 'button';
  printButton.addEventListener('click', () => {
    window.print();
  });
  actions.append(button('코스 카드 저장', () => showShareCard(p)), button('공유 링크 복사', () => copyPlanShare(p)), button('공유 취소', () => revokePlanShares(p)), printButton);
  // 공유 링크 현황(개선안 31·32): 이 코스와 바뀌기 전 코스의 열린 링크, 만료 시각. 상자가 문서에 붙은 뒤 채운다.
  const shareStatus = node('p', undefined, 'hint share-status');
  shareStatus.dataset.plan = p.id || '';
  shareStatus.setAttribute('aria-live', 'polite');
  share.append(decisionPanel(p), node('h3', '코스 저장·공유'), actions, shareStatus);
  // 아이폰·아이패드: 그래도 인쇄 창이 뜨지 않는 경우가 있어 Safari 공유 시트의 프린트 경로를 함께 알린다(인쇄 때는 숨김).
  if (/iP(hone|ad|od)/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)) {
    share.append(node('p', '아이폰에서 인쇄 창이 뜨지 않으면 Safari의 공유(□↑) → 프린트에서 인쇄하거나 PDF로 저장할 수 있어요.', 'hint ios-print-hint'));
  }
  box.append(share);
  if (p.id) queueMicrotask(() => refreshShareStatus(p));
  root.append(box);
  renderPlanMapCard();
  // 부가 정보: 축제 구역 뒤 #plan-extras
  const more = node('section', undefined, 'detail panel plan-extras-panel');
  more.setAttribute('aria-label', '더 둘러보기');
  more.append(leisureCoursePanel(p));
  // 네이버 블로그 글은 받은 그대로의 독립 블록으로만 보여 준다(course-search.js). 예전 형식(우리가 고른 5건, format 없음)은 그리지 않는다.
  if (p.course_search?.format === 2) {
    const research = node('details', undefined, 'course-evidence');
    research.append(node('summary', `코스 구성 메모 · 네이버 블로그 글 ${p.course_search.posts?.length || 0}건`), courseSearchPanel(p.course_search, p));
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
