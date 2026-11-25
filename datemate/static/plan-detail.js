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
// 마지막 장소 → 축제 행사장 한 줄과 [수단 바꾸기]. 이 구간은 plan.legs 밖이라 구간 번호 대신 요청의 festival 항목으로 바꾼다(app/leg_modes.festival_pair).
// 코스 중간에 둔 낮 축제(position 'middle', after=i)는 장소 i 칸 뒤에 같은 칸을 두고, 장소 i → 축제 행사장 줄(visit.leg)을 같이 적는다.
// 행사장 → 장소 i+1 구간은 plan.legs[i+1] 이라 그 장소 칸 앞의 보통 구간 줄(routeLine)로 그린다.
function festivalLegLine(plan, visit) {
  const middle = festivalMiddleAfter(plan),
    from = (middle === null ? plan.places.at(-1)?.name : plan.places[middle]?.name) || '마지막 장소',
    line = node('p', undefined, 'hint festival-visit-leg');
  line.append(node('span', `${from} → 축제 행사장 · ${legModeLabel(plan, visit.leg)}`));
  if (plan.can_edit === false || planHistoryExpired(plan)) return line;
  const id = 'transport-chooser-festival',
    toggle = button('수단 바꾸기', () => {
      const open = toggle.getAttribute('aria-expanded') === 'true';
      toggle.setAttribute('aria-expanded', String(!open));
      if (open) {
        document.getElementById(id)?.remove();
        return;
      }
      const chooser = transportChooser(`${from} → 축제 행사장 이동 수단`, legMode(plan, visit.leg), mode => ({
        festival: mode
      }), 'festival');
      chooser.id = id;
      line.after(chooser);
      chooser.querySelector('[aria-pressed="true"]')?.focus();
    }, 'secondary route-mode-toggle');
  toggle.setAttribute('aria-expanded', 'false');
  toggle.setAttribute('aria-controls', id);
  toggle.setAttribute('aria-label', `${from} → 축제 행사장 이동 수단 바꾸기`);
  toggle.dataset.transportToggle = 'festival';
  line.append(toggle);
  return line;
}

function festivalVisitBlock(plan, visit) {
  const last = visit.position === 'last',
    middle = festivalMiddleAfter(plan),
    goes = last || middle !== null;
  const block = node('section', undefined, 'festival-visit' + (middle !== null ? ' middle' : ''));
  block.setAttribute('aria-label', last ? '운영 시간에 맞춰 코스 끝에 둔 축제 방문' : middle !== null ? '운영 시간에 맞춰 코스 중간에 둔 축제 방문' : '운영 시간에 맞춰 고정한 축제 방문');
  if (goes && visit.leg && Number.isFinite(visit.leg.minutes)) block.append(festivalLegLine(plan, visit));
  const wait = visit.wait ? ` · ${goes ? '행사장에 닿은 뒤 ' : ''}시작까지 ${visit.wait}분 기다림` : '';
  // 「+ 내 코스에 추가」로 넣은 축제(행사장 ≠ 출발지, maps.js festivalVenueApart)는 행사장으로 '돌아오지' 않고 간다.
  const after = last ? `마지막 장소를 둘러본 뒤 행사장으로 ${festivalVenueApart(plan) ? '가서' : '돌아와'} 축제로 하루를 마무리해요.` : middle !== null ? `${middle + 1}번째 장소(${plan.places[middle].name}) 다음에 행사장에 들러 축제를 보고, 끝나면 행사장에서 다음 장소로 이동해요.` : '축제가 끝나면 행사장에서 아래 첫 장소로 이동해요.';
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
  // 축제 카드의 「+ 내 코스에 추가」는 지금 고른 코스에 넣는다. 코스가 바뀔 때마다(탭·확정·되돌리기) 단추 상태를 맞춘다(festivals.js).
  if (typeof FestivalPanel !== 'undefined') FestivalPanel.syncAdd();
  extras?.replaceChildren();
  if (!selected) {
    renderPlanMapCard();
    return;
  }
  const p = selected,
    box = node('section', undefined, 'detail panel');
  // 2026-11-25 상세 결과 시안에는 이 제목이 없다(위 조건 칩 줄이 날짜·시간·인원을 보여 줌). 화면 읽기·구역 표시줄(section-indicator.js)이
  // 이 h2 로 구역을 알기 때문에 지우지 않고 눈에만 숨긴다. 다시 보이게 하려면 'visually-hidden' 을 뺀다.
  const head = node('div', undefined, 'detail-header visually-hidden');
  head.append(node('h2', '우리 하루, 자세히 보기'), node('p', `${p.conditions.visit_date} · ${p.conditions.start} ~ ${p.finish} · ${p.conditions.people}명`, 'hint'));
  box.append(head);
  if (p.delta) box.append(node('p', `${p.change_reason} 시간 ${p.delta.minutes>=0?'+':''}${p.delta.minutes}분 · ${costChangeText(totalBefore(p), p.total)}`, 'warning'));
  // 수단·장소를 바꾼 탓에 축제 방문이 새로 들어가거나 빠지거나 자리가 바뀌었으면 서버가 적어 준 한 줄(app/festival_time.change_note).
  // 문구는 서버에서만 만든다 — 여기서는 그대로 적는다. 달라진 게 없으면 키가 없다.
  if (p.festival_change) box.append(node('p', p.festival_change, 'warning festival-change-note'));
  if (p.conditions.mode === 'demo') box.append(node('p', '모든 장소와 운영·가격 조건은 가상입니다. 이동선은 직선거리로 만든 개략도이며 실제 경로가 아닙니다.', 'warning'));
  if (p.conditions.mode === 'real' && p.conditions.allow_estimates) box.append(estimatedPlanNotice());
  // 보관 기한(21일)이 지나 좌표까지 지운 네이버 검색 장소가 있으면 다시 계산하는 기능(바꾸기·주변 찾기)을 그리지 않는다.
  const expired = planHistoryExpired(p);
  if (expired) box.append(planHistoryExpiredNote());
  if (p.parent && p.can_edit !== false) {
    const undo = node('div', undefined, 'actions undo-actions');
    // 지각 복구(delay-check.js)로 만든 코스는 그 기록(delay_recovery)이 있다. 그 뒤 수단·장소를 바꾸면 기록이 kept 표시와 함께 이어진다
    // (app/delay_check.kept_record — 'transport' 또는 'place', 80차에 저장된 true 는 'transport'; moved_record — 식사 추가 'meal'·합의 코스 'agreement').
    // 그런 코스의 되돌리기는 지각 반영이 아니라 그 변경을 되돌린다('meal'·'agreement' 는 지연 기록이 없는 식사·합의 코스와 같은 '교체 되돌리기').
    const kept = p.delay_recovery?.kept;
    // 수단 바꾸기로 만든 코스는 저장된 표시(change_kind='transport', app/plan_changes.save_change)로 알아본다. 예전에는 응답에만 있는
    // transport_change 를 봐서 고정 토글·새로고침 뒤 '교체 되돌리기'로 바뀌었다(2026-11-24 점검 F6). 이 표시가 생기기 전에 저장한 코스는 예전처럼 '교체 되돌리기'다.
    const transportMade = p.change_kind === 'transport';
    // 되돌리기도 코스 변경 잠금을 같이 쓴다(plan-actions.js runPlanChange, 2026-11-24 점검 F3): 다른 변경을 기다리는 동안에는 보내지 않고 알린다.
    const undoButton = button(transportMade || kept === true || kept === 'transport' ? '수단 변경 되돌리기' : p.delay_recovery && !kept ? '지각 반영 되돌리기' : '교체 되돌리기', () => runPlanChange(async () => {
      undoButton.disabled = true;
      try {
        const restored = await api('/plans/' + p.id + '/undo', {});
        if (commitNewPlan(p.id, restored, '되돌렸어요')) restoreUndoLocks(p, restored);
      } finally {
        undoButton.disabled = false;
      }
    }));
    undo.append(undoButton);
    box.append(undo);
  }
  // 2026-11-25 시안: 일정 위에는 경고·되돌리기와 '늦어지면?' 줄만 둔다. 아래 도구들(한 번에 수단 바꾸기, 네이버 지도 목록, 계산 방식,
  // 대중교통 메모, 지각 확인, 순서 제안, 당일 도구)은 일정 아래 접힌 '더 할 수 있는 것'(planMoreFold)의 맨 앞으로 옮겼다. 지우지 않았다.
  // 모두 #plan-detail 안에 남아 있어야 한다(delay-check.js 가 '#plan-detail .delay-check' 로 상자를 찾음).
  const tools = node('div', undefined, 'plan-more-tools');
  tools.append(transportOverview(p));
  const links = node('div', undefined, 'map-link-list');
  links.append(node('span', '네이버 지도에서 찾기', 'map-link-label'));
  // 이름·주소를 지운 장소(보관 기간 지남)는 지도에서 찾을 말이 없어 빼고, 번호는 일정 순서 그대로 둔다.
  p.places.forEach((place, i) => {
    if (!place.naver_expired) links.append(placeMapLink(`${i+1}. ${place.name}`, place));
  });
  tools.append(links);
  // 구간마다 같은 설명(예: '직선거리 × 1.35 기반 이동 추정 · 실제 길찾기 미반영')이면 여기서 한 번만 적는다(routeLine 은 생략).
  // 기본은 접어 둔다(2026-11-24 사용자 요청 — 늘 보일 필요는 없고, 궁금한 사람만 눌러 본다). 모양은 '출처'·'사진 정보' 접기와 같다
  // (results.css 의 .detail :is(.stop-source,.photo-meta,.route-source-note)). 다시 늘 보이게 하려면 예전처럼
  // node('p', '이동 시간: ' + legSource, 'hint route-source-note') 한 줄로 되돌리고 그 CSS 목록에서 .route-source-note 를 뺀다.
  const legSource = sharedLegSource(p);
  if (legSource) {
    const fold = node('details', undefined, 'route-source-note');
    fold.append(node('summary', '이동 시간 계산 방식'), node('p', legSource, 'hint'));
    tools.append(fold);
  }
  // 대중교통 구간이 있으면 지하철·버스 구분 없는 추정이라는 것과 가정값을 일정 위에 한 번 적는다(plan-evidence.js transitBasisNote).
  const transitNote = transitBasisNote(p);
  if (transitNote) tools.append(transitNote);
  // 지금 늦으면 어디서 처음 문제가 생기는지(읽기 전용, delay-check.js). 저장된 코스(id)가 있을 때만.
  if (p.id && typeof delayCheckPanel === 'function') tools.append(delayCheckPanel(p));
  // 같은 장소를 다른 순서로 돌면 이동이 줄어드는지(order-suggestion.js). 바꿀 수 없는 코스·장소 한 곳짜리는 상자가 없다(null).
  const orderPanel = typeof orderSuggestionPanel === 'function' ? orderSuggestionPanel(p) : null;
  if (orderPanel) tools.append(orderPanel);
  // 약속 당일 도구(day-of.js): 마지막 출발 시각, 한 곳씩 크게 보기, 현장용 일정 복사. 서버에 묻지 않는다.
  if (typeof dayOfTools === 'function') tools.append(dayOfTools(p));
  // '+30분 늦어지면?' 토글(delay-check.js delaySimBar): 일정 바로 위. 켜면 장소 칸에 밀린 시각·주의 배지를 겹친다(아래 delaySimRefresh).
  if (p.id && typeof delaySimBar === 'function') box.append(delaySimBar(p));
  // 운영 시간에 맞춰 맨 앞에 고정한 축제 방문(app/festival_time.py). 첫 구간 줄(행사장 → 첫 장소) 바로 앞에 둔다.
  const middle = festivalMiddleAfter(p);
  if (p.festival_visit && p.festival_visit.position !== 'last' && middle === null) box.append(festivalVisitBlock(p, p.festival_visit));
  p.places.forEach((place, i) => {
    // 코스 중간에 둔 축제: 앞 장소 칸(과 주차·식사 칸) 뒤, 행사장 → 다음 장소 구간 줄 앞.
    if (middle !== null && i === middle + 1) box.append(festivalVisitBlock(p, p.festival_visit));
    box.append(routeLine(p, i, `${p.legs[i].origin} → ${place.name}`));
    // 2026-11-25 상세 결과 시안(Downloads screencapture-gemini-…-09_51_31·09_51_44.png)의 장소 카드. 카드 하나(.timeline-card) 안에
    //   ① 위 줄(.stop-head): 번호 동그라미 · 빨간 시각 '도착 – 떠남' · (머무는 분) · 오른쪽 태그(분류·실내/실외·예약 권장)
    //   ② 아이콘 타일(.stop-kind) | 이름(h4) · 주소 · 한 줄 요약 | 오른쪽 가격(.stop-price)  ← redesign.css 10) 의 grid 로 배치
    //   ③ 사진 · 접힌 '방문 팁 & 블로그 요약'(추천 이유·확인, 후기에서 읽은 정보, 정보 출처, 메뉴, 블로그) · 단추 줄
    // 예전에는 시각·번호가 카드 왼쪽 세로줄(.timeline-stamp 가 .stop 의 첫 칸)에 있었다. 지금은 그 도장을 카드 안 위 줄로 옮겼다.
    // 꼭 남길 것: .timeline-card>h4(지도·대화상자·지각 표시가 찾음, maps.js focusPlanStop·place-dialog.js·delay-check.js)와
    // .timeline-stamp(지각 미리 보기가 밀린 시각을 붙임, delay-check.js delaySimRefresh). 둘 다 이름·위치(카드 안)를 바꾸면 그 파일도 고친다.
    const stop = node('article', undefined, 'stop');
    const body = node('div', undefined, 'timeline-card');
    const head = node('div', undefined, 'stop-head');
    const stamp = node('div', undefined, 'timeline-stamp');
    const stay = p.timeline[i]?.stay;
    stamp.append(node('strong', p.timeline[i].arrival), node('small', '– ' + p.timeline[i].departure));
    if (Number.isFinite(stay)) stamp.append(node('span', `(${stay}분)`, 'stamp-stay'));
    head.append(node('span', String(i + 1), 'stop-number'), stamp);
    // 태그는 장소 자료 그대로(없으면 안 단다): 분류, 실내·실외, 예약 권장.
    const tags = node('div', undefined, 'stop-tags');
    tags.append(node('span', placeKind(place), 'stop-tag step-category'));
    if (place.setting === 'indoor' || place.setting === 'outdoor') tags.append(node('span', place.setting === 'indoor' ? '실내' : '실외', 'stop-tag is-' + place.setting));
    if (place.reservation === true) tags.append(node('span', '예약 권장', 'stop-tag is-reserve'));
    head.append(tags);
    body.append(head, stopKindIcon(place), node('h4', place.name));
    if (place.address) body.append(node('p', place.address, 'stop-address'));
    // 네이버 지역 검색으로 찾은 장소: '네이버 검색결과' 표시와 원본 링크(특약 2.1·2.2). 21일이 지나 지운 장소는 안내만.
    if (place.naver_expired) body.append(naverExpiredNote());
    else if (isNaverResult(place)) body.append(naverAttribution('지역 검색', place.place_source || place.source));
    // 예전 한 줄 요약(.stop-meta: 분류 · 비용 · 머무는 시간)은 나눠 옮겼다 — 분류는 위 태그, 머무는 시간은 위 줄 '(N분)', 비용은 오른쪽 가격.
    // 남은 것은 '새로운 곳' 표시뿐이라 그때만 이 줄을 단다.
    // 한 곳만 새로운 곳으로(app/fresh_place.py): 최근 코스에 드물던 종류로 넣은 장소.
    if (p.fresh_place?.index === i) {
      const meta = node('p', undefined, 'stop-meta');
      meta.append(node('span', `새로운 곳 · ${p.fresh_place.label}`, 'fresh-place-tag'));
      body.append(meta);
    }
    // 오른쪽 가격: 일행 전체 금액(비용표와 같은 값). 무료(0원)면 '무료'.
    const cost = p.costs.find(c => c.name === place.name);
    if (cost) {
      const free = Array.isArray(cost.amount) ? cost.amount.every(v => !v) : !cost.amount;
      const price = node('p', undefined, 'stop-price');
      price.append(node('span', `${p.conditions.people}인`, 'stop-price-people'), node('span', free ? '무료' : range(cost.amount), 'stop-cost'));
      body.append(price);
    }
    // 후기에서 읽은 영업시간·가격(review-facts.js)은 짧고 방문 판단에 바로 쓰여 접기 밖에 둔다(화면에 올 때 불러온다).
    body.append(reviewFactsLine(place, p.conditions.mode));
    // 접힌 '방문 팁 & 블로그 요약': 카드에 늘 보이던 긴 내용을 모은다. 안의 순서는 예전 카드 순서 그대로.
    const tips = node('details', undefined, 'stop-tips');
    tips.append(node('summary', '방문 팁 & 블로그 요약'));
    const tipsBody = node('div', undefined, 'stop-tips-body');
    tips.append(tipsBody);
    if (p.reasons[i]) {
      const source = node('details', undefined, 'stop-source');
      source.append(node('summary', '정보 출처'), linkedText('p', p.reasons[i], 'hint'));
      tipsBody.append(source);
    }
    const buttons = node('div', undefined, 'actions');
    buttons.append(button(locks.has(i) ? '● 고정됨' : '○ 장소 고정', () => togglePlanLock(p, i)), button('↻ 다른 장소로 바꾸기', () => showAlternatives(i)), button('장소 정보 · 질문', () => showPlace(place.id, p.conditions.mode)));
    // 실제 장소는 「네이버 지도 보기」(오늘 영업시간·최근 리뷰 확인용, 2026-11-24 UX P1). 예전 「도착지 지도·길찾기 확인」은 앱 전용 주소(nmap://)라
    // 컴퓨터에서는 열리지 않았다. 길찾기는 구간 줄의 「길찾기 ▾」(plan-actions.js routeLine)에 있다. 체험 코스(가상 장소)는 지도에 없는 곳이라 달지 않는다.
    if (p.conditions.mode !== 'demo' && typeof placeMapLink === 'function') {
      const map = placeMapLink('네이버 지도 보기 ↗', place);
      map.classList.add('stop-map-link');
      buttons.append(map);
      // 카카오맵 길찾기(2026-11-25 HTML 시안): 앞 장소(또는 출발지)에서 이 장소까지. 구간 줄의 「길찾기 ▾」와 같은 주소(plan-actions.js kakaoDirectionsUrl).
      const kakao = typeof kakaoDirectionsUrl === 'function' ? kakaoDirectionsUrl(p, p.legs[i]) : null;
      if (kakao) {
        const anchor = link('카카오맵 길찾기 ↗', kakao);
        anchor.classList.add('stop-kakao-link');
        anchor.setAttribute('aria-label', `${i + 1}번 ${place.name}까지 카카오맵 길찾기 (새 탭)`);
        buttons.append(anchor);
      }
    }
    // 일정 카드 → 코스 지도(maps.js focusPlanMapStop, 리디자인 3단계): 지도의 이 장소 표시를 강조하고 지도를 그 위치로 옮긴다.
    // 지도 표시 → 일정 카드(focusPlanStop)의 반대 방향. 좌표가 없는 장소(보관 기간이 지나 지움)는 지도에 없어 달지 않는다.
    if (Number.isFinite(place.lat) && Number.isFinite(place.lon) && typeof focusPlanMapStop === 'function') {
      const show = button('코스 지도에서 보기', () => focusPlanMapStop(i), 'secondary stop-map-focus');
      show.setAttribute('aria-label', `${i + 1}번 ${place.name} 코스 지도에서 보기`);
      buttons.append(show);
    }
    // 추천 이유·정보 확인은 '방문 팁' 접기의 맨 앞(사진·단추는 접기 밖).
    tipsBody.prepend(placeEvidencePanel(p, i));
    if (p.can_edit === false) {
      buttons.children[0].disabled = true;
      buttons.children[1].disabled = true;
    }
    // 보관 기간이 지난 장소가 있는 코스는 장소를 바꿀 수 없다(서버가 409, 위 planHistoryExpiredNote).
    if (expired) buttons.children[1].disabled = true;
    // 보관 기간이 지난 네이버 검색 장소는 장소 정보(사진·블로그·메뉴)를 다시 찾지 않는다(이름·주소가 지워짐).
    if (place.naver_expired) {
      body.append(tips, buttons);
      stop.append(body);
      box.append(stop);
      return;
    }
    if (p.conditions.mode === 'real' && hasPlaceMenu(place)) tipsBody.append(restaurantMenuPanel(place));
    tipsBody.append(placeBlogPanel(place, p.conditions.mode));
    // 사진은 시안에 없지만 실제 장소에서는 고르는 데 중요해 접기 밖에 둔다(체험 코스는 '가상 장소 · 사진 없음' 한 줄).
    body.append(placePhotoPanel(place, p.conditions.mode, false, true), tips, buttons);
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
  // 코스 비교 표(2026-11-25 시안 'COMPARISON MATRIX'): 예전에는 코스 카드 바로 아래(plan-results.js)였는데 시안대로 일정 뒤로 옮겼다.
  if (plans.length && typeof optionComparison === 'function') box.append(planComparison());
  // 할 일 순서(action-card.js): 확인할 것을 시점 순서로 모은 체크리스트(시안 '출발 전 체크리스트').
  box.append(actionCard(p));
  // 시안에 없는 기능은 지우지 않고 접힌 '더 할 수 있는 것' 하나에 모은다(2026-11-25 사용자 결정). 순서: 위에서 옮긴 도구들 →
  // 네 가지 확인 → 비용표·합계 → 결정·공유. 펼침 여부는 브라우저에 기억한다(PLAN_MORE_KEY).
  const fold = planMoreFold(PLAN_MORE_KEY, '더 할 수 있는 것', '수단·순서 바꾸기, 당일 도구, 비용표, 결정·공유'),
    foldBody = fold.lastElementChild;
  foldBody.append(tools, executionSummary(p), node('h3', '비용은 투명하게'));
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
  foldBody.append(costs);
  // 합계의 성격을 표 바로 아래에 한 줄로 밝힌다(실제 장소 코스만). 블로그 글의 금액은 읽지 않으므로 등록 단가가 없는 곳은 가정 범위나 미확인이다.
  const basisNote = costBasisNote(p);
  if (basisNote) foldBody.append(basisNote);
  for (const [label, value] of [
      ['확인된 비용', range(p.confirmed)],
      ['추정 비용', range(p.estimated)],
      budgetUnlimited(p) ? ['예산', '예산 무관 · 예산과 비교하지 않아요'] : ['예산 대비 차액 (미확인 비용 제외)', range(p.remaining)]
    ]) {
    const row = node('div', undefined, 'total-row');
    row.append(node('span', label), node('span', value));
    foldBody.append(row);
  }
  // 합계에 무엇이 들어갔고 무엇이 빠졌는지(개선안 22). 가정 가격은 합계에 '들어간' 추정이고, 미확인은 합계에서 '빠진' 항목이다.
  const assumed = p.costs.filter(c => c.price_kind === 'planning_assumption');
  if (assumed.length) foldBody.append(node('p', '합계에 들어간 가정 가격(실제 단가 아님): ' + assumed.map(c => `${c.name} ${range(c.amount)}`).join(', '), 'hint cost-assumed'));
  if (p.unknown.length) foldBody.append(node('p', '합계에서 빠진 항목(추가 확인 필요): ' + p.unknown.join(', ') + ' · 0원으로 처리하지 않았습니다.', 'warning'));
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
  // 공유 두 가지를 앞에(2026-11-24 UX P1): 카톡용 일정 글 복사(공유 링크 포함), 공유 링크만 복사. 그 뒤 이미지 카드·취소·인쇄.
  actions.append(button('카톡용 일정 복사', () => copyKakaoItinerary(p), 'primary kakao-copy'), button('공유 링크 복사', () => copyPlanShare(p)), button('코스 카드 저장', () => showShareCard(p)), button('공유 취소', () => revokePlanShares(p)), printButton);
  // 공유 링크 현황(개선안 31·32): 이 코스와 바뀌기 전 코스의 열린 링크, 만료 시각. 상자가 문서에 붙은 뒤 채운다.
  const shareStatus = node('p', undefined, 'hint share-status');
  shareStatus.dataset.plan = p.id || '';
  shareStatus.setAttribute('aria-live', 'polite');
  share.append(decisionPanel(p), node('h3', '코스 저장·공유'), actions, shareStatus);
  // 아이폰·아이패드: 그래도 인쇄 창이 뜨지 않는 경우가 있어 Safari 공유 시트의 프린트 경로를 함께 알린다(인쇄 때는 숨김).
  if (/iP(hone|ad|od)/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)) {
    share.append(node('p', '아이폰에서 인쇄 창이 뜨지 않으면 Safari의 공유(□↑) → 프린트에서 인쇄하거나 PDF로 저장할 수 있어요.', 'hint ios-print-hint'));
  }
  foldBody.append(share);
  box.append(fold);
  if (p.id) queueMicrotask(() => refreshShareStatus(p));
  root.append(box);
  // 지연 토글이 켜져 있으면 새로 그린 장소 칸에 다시 겹친다(코스가 바뀌었으면 새 코스로 다시 계산).
  if (typeof delaySimRefresh === 'function') delaySimRefresh(p);
  renderPlanMapCard();
  // 부가 정보: 축제 구역 뒤 #plan-extras
  const more = node('section', undefined, 'detail panel plan-extras-panel');
  more.setAttribute('aria-label', '더 둘러보기');
  // 레저·블로그 메모·질문·후기도 접힌 칸 하나에(펼침 기억 PLAN_EXTRAS_KEY). 축제 구역 뒤에 온다.
  const extrasFold = planMoreFold(PLAN_EXTRAS_KEY, '더 둘러보기 · 질문 · 후기', '주변 레저, 코스 메모, 이 일정에 물어보기, 이용 후기'),
    extrasBody = extrasFold.lastElementChild;
  more.append(extrasFold);
  extrasBody.append(leisureCoursePanel(p));
  // 네이버 블로그 글은 받은 그대로의 독립 블록으로만 보여 준다(course-search.js). 예전 형식(우리가 고른 5건, format 없음)은 그리지 않는다.
  if (p.course_search?.format === 2) {
    const research = node('details', undefined, 'course-evidence');
    research.append(node('summary', `코스 구성 메모 · 네이버 블로그 글 ${p.course_search.posts?.length || 0}건`), courseSearchPanel(p.course_search, p));
    extrasBody.append(research);
  }
  extrasBody.append(node('p', '외부 장소 평점: 확보한 평가 자료가 없습니다. 아래 자체 후기와 별도입니다.', 'hint'));
  extrasBody.append(node('h3', '이 일정에 대해 물어보세요'), chatWidget('plan', p.id, p.conditions.mode));
  const reviews = node('div');
  extrasBody.append(reviews);
  extrasBody.append(experiencePanel(p));
  (extras || root).append(more);
  loadReviews(reviews, p).catch(e => reviews.append(node('p', e.message, 'warning')));
}

// 접힌 칸의 펼침 기억(2026-11-25). 한 번 펼치면 이 브라우저에서는 다음 코스에도 펼쳐 둔다. 저장이 막힌 브라우저는 늘 접힌 채로 시작한다.
// 테스트는 tests/conftest.py 가 두 키를 'open' 으로 미리 넣어 예전처럼 펼친 화면에서 시험한다(기본 접힘은 test_plan_more_ui.py).
// 키 이름을 바꾸면 conftest.py 의 PLAN_FOLDS_OPEN 도 같이 고친다.
const PLAN_MORE_KEY = 'datemate:plan-more',
  PLAN_EXTRAS_KEY = 'datemate:plan-extras-more';

function planMoreFold(key, title, hint) {
  const fold = node('details', undefined, 'plan-more');
  fold.dataset.key = key;
  const summary = node('summary', undefined);
  summary.append(node('span', title, 'plan-more-title'), node('span', hint, 'plan-more-hint'));
  fold.append(summary, node('div', undefined, 'plan-more-body'));
  try {
    fold.open = localStorage.getItem(key) === 'open';
  } catch {}
  fold.addEventListener('toggle', () => {
    // 인쇄 때 잠깐 연 것(아래 beforeprint)은 기억하지 않는다. 열 때와 닫을 때 한 번씩 이 표시를 보고 지나간다.
    if (fold.dataset.printOpen) {
      if (!fold.open) delete fold.dataset.printOpen;
      return;
    }
    try {
      localStorage.setItem(key, fold.open ? 'open' : 'closed');
    } catch {}
  });
  return fold;
}

// 인쇄 / PDF: 비용표·합계·네 가지 확인은 '더 할 수 있는 것' 안에 있어 접혀 있으면 종이에 빠진다. 인쇄하는 동안만 펼쳤다가 끝나면 되돌린다.
// (접힌 칸 제목과 그 안의 조작 구역은 인쇄 CSS 가 숨긴다 — redesign.css 11) 의 @media print.)
addEventListener('beforeprint', () => {
  document.querySelectorAll('#plan-detail .plan-more:not([open])').forEach(fold => {
    fold.dataset.printOpen = '1';
    fold.open = true;
  });
});
addEventListener('afterprint', () => {
  document.querySelectorAll('#plan-detail .plan-more[data-print-open]').forEach(fold => {
    fold.open = false;
  });
});

// 코스 비교 표(예전 plan-results.js renderResults 4번). 다시 그려도 사용자가 펼치거나 접은 상태를 이어 간다(처음에는 데스크톱 펼침·휴대폰 접힘).
let comparisonOpen = null;

function planComparison() {
  const compare = node('details', undefined, 'comparison-details');
  compare.append(node('summary', `코스 ${plans.length}개 비용·이동 시간 비교 표`), optionComparison(plans));
  compare.open = comparisonOpen ?? !RESULTS_MOBILE.matches;
  compare.addEventListener('toggle', () => {
    comparisonOpen = compare.open;
  });
  return compare;
}

function replaceInList(oldId, p) {
  const i = plans.findIndex(x => x.id === oldId);
  if (i < 0) return false;
  plans[i] = p;
  return true;
}

/* 장소 칸 번호 아래 종류 그림(2026-11-25 HTML 시안의 둥근 네모 그림). 장식이라 화면 읽기에서는 숨긴다(종류는 stop-meta 글자로 읽는다).
   분류는 서버 분류(app/models.py THEMES)와 식사(category '음식점'·is_meal). 모르는 분류는 동그라미. 색은 redesign.css 10) [data-kind]. */
const STOP_KIND_ICONS = {
  cafe: '<path d="M17 8h1a4 4 0 1 1 0 8h-1"/><path d="M3 8h14v9a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4Z"/><path d="M6 2v2M10 2v2M14 2v2"/>',
  meal: '<path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2"/><path d="M7 2v20"/><path d="M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7"/>',
  art: '<rect width="18" height="18" x="3" y="3" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3-3a2 2 0 0 0-2.8 0L6 21"/>',
  walk: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
  make: '<path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/>',
  play: '<circle cx="12" cy="12" r="9"/><path d="M10 8l6 4-6 4z"/>',
  rest: '<path d="M4 18v-6a8 8 0 0 1 16 0v6"/><path d="M4 18h16"/>',
  other: '<circle cx="12" cy="12" r="9"/>'
};

function stopKindKey(place) {
  const c = String(place?.category || '');
  if (place?.is_meal || /음식|식당|맛집/.test(c)) return 'meal';
  return {
    '카페·미식': 'cafe',
    '문화·예술': 'art',
    '산책·풍경': 'walk',
    '체험·제작': 'make',
    '오락·놀이': 'play',
    '레저·활동': 'play',
    '휴식·힐링': 'rest'
  } [c] || 'other';
}

function stopKindIcon(place) {
  const key = stopKindKey(place),
    box = node('span', undefined, 'stop-kind');
  box.dataset.kind = key;
  box.setAttribute('aria-hidden', 'true');
  box.innerHTML = `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${STOP_KIND_ICONS[key]}</svg>`;
  return box;
}
