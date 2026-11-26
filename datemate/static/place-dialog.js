'use strict';
// Place dialog rendering; initialized by app.js after shared UI helpers exist.
function drawMap(p) {
  const wrap = node('div', undefined, 'map');
  const ns = 'http://www.w3.org/2000/svg',
    svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 600 230');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', '장소 좌표 개략도. 실제 도로 경로 아님');
  const points = [p.conditions.origin, ...p.places, ...(p.conditions.return_home ? [p.conditions.home] : [])];
  // 보관 기간(21일)이 지나 좌표를 지운 장소(lat·lon 이 null)는 개략도에서 빼고, 그 장소에 닿는 구간 선도 그리지 않는다.
  const located = x => Number.isFinite(x?.lat) && Number.isFinite(x?.lon);
  // 출발지가 아닌 행사장을 들르는 코스(「+ 내 코스에 추가」, maps.js festivalVenueApart)는 행사장도 범위에 넣고 '축제' 점을 찍는다.
  const venue = p.festival_visit && festivalVenueApart(p) ? festivalVenuePoint(p) : null;
  const known = [...points, ...(venue ? [venue] : [])].filter(located);
  const lats = known.map(x => x.lat),
    lons = known.map(x => x.lon),
    minLat = Math.min(...lats),
    minLon = Math.min(...lons),
    dy = Math.max(.002, Math.max(...lats) - minLat),
    dx = Math.max(.002, Math.max(...lons) - minLon);
  const coords = points.map(x => located(x) ? [60 + (x.lon - minLon) / dx * 480, 180 - (x.lat - minLat) / dy * 130] : null);
  // 구간마다 수단에 맞는 점선(도보 짧은 점선, 그 밖 긴 점선)으로 잇는다. 개략도라 실제 도로는 그리지 않는다.
  // 구간 목록은 지도와 같다(maps.js planSegments — 저녁 축제면 행사장을 거쳐 귀가).
  const at = x => located(x) ? [60 + (x.lon - minLon) / dx * 480, 180 - (x.lat - minLat) / dy * 130] : null;
  planSegments(p).forEach(({
    from,
    to,
    leg
  }) => {
    const start = at(from),
      end = at(to);
    if (!start || !end) return;
    const path = document.createElementNS(ns, 'polyline');
    path.setAttribute('points', [start, end].map(x => x.join(',')).join(' '));
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', '#b5245e');
    path.setAttribute('stroke-width', '3');
    path.setAttribute('stroke-dasharray', LINE_DASH.svg[legLineStyle(p, leg) === 'short' ? 'short' : 'long']);
    svg.append(path);
  });
  coords.forEach((at, i) => {
    if (!at) return;
    const [x, y] = at;
    const circle = document.createElementNS(ns, 'circle');
    circle.setAttribute('cx', x);
    circle.setAttribute('cy', y);
    circle.setAttribute('r', 17);
    circle.setAttribute('fill', i === 0 ? '#1f2328' : '#b5245e');
    const t = document.createElementNS(ns, 'text');
    t.setAttribute('x', x);
    t.setAttribute('y', y + 5);
    t.setAttribute('text-anchor', 'middle');
    t.setAttribute('fill', 'white');
    t.setAttribute('font-size', '12');
    t.textContent = i === 0 ? '출발' : i > p.places.length ? '귀가' : String(i);
    svg.append(circle, t);
  });
  if (venue) {
    const [x, y] = at(venue);
    const circle = document.createElementNS(ns, 'circle');
    circle.setAttribute('cx', x);
    circle.setAttribute('cy', y);
    circle.setAttribute('r', 17);
    circle.setAttribute('fill', '#8a5a00');
    const t = document.createElementNS(ns, 'text');
    t.setAttribute('x', x);
    t.setAttribute('y', y + 5);
    t.setAttribute('text-anchor', 'middle');
    t.setAttribute('fill', 'white');
    t.setAttribute('font-size', '12');
    t.textContent = '축제';
    svg.append(circle, t);
  }
  wrap.append(svg, node('div', '좌표 개략도 · 직선 연결 · 실제 지도/경로 아님', 'map-caption'));
  return wrap;
}
let dialogGeneration = 0;
// 대화상자를 연 단추와 그 단추가 있던 장소 카드 순번. 닫을 때 브라우저는 연 단추로 포커스를 돌려주지만,
// 장소 교체·제보처럼 결과를 다시 그리면 그 단추가 사라져 포커스가 페이지 맨 위(body)로 떨어진다.
let dialogReturn = null;

function openDialog(title) {
  dialogGeneration++;
  if (!$('#dialog').open) {
    const opener = document.activeElement;
    const stop = opener?.closest?.('#plan-detail .stop');
    dialogReturn = {
      opener,
      stop: stop ? [...document.querySelectorAll('#plan-detail .stop')].indexOf(stop) : -1
    };
  }
  const root = $('#dialog-content');
  const heading = node('h2', title);
  heading.id = 'dialog-title';
  root.replaceChildren(heading);
  if (!$('#dialog').open) $('#dialog').showModal();
  return root;
}

async function showAlternatives(index) {
  if (locks.has(index)) {
    toast('고정한 장소는 먼저 고정을 해제하세요.');
    return;
  }
  const root = openDialog('조금 다른 장소로 바꿔볼까요?');
  const generation = dialogGeneration;
  const planId = selected.id;
  const oldPlaceId = selected.places[index].id;
  const reason = experienceSelect('어떤 점을 바꾸고 싶나요?', 'replacement_reason', [
    ['', '변경 이유 선택'],
    ['budget', '비싸요'],
    ['distance', '멀어요'],
    ['taste', '취향이 아니에요'],
    ['visited', '이미 가봤어요']
  ]);
  reason.querySelector('select').required = true;
  root.append(reason);
  // 후보 조회는 실패할 수 있다(서버 깨우는 중·429·네트워크). 예전에는 '다시 확인하고 있어요'가 그대로 남고 재시도 단추가 없었다(점검 F10).
  // 실패하면 그 한 줄을 까닭 + 「다시 불러오기」로 바꾼다. 다시 불러와도 고른 변경 이유(reason)는 그대로 둔다 — 대화상자를 새로 열지 않는다.
  // 늦게 온 응답은 예전처럼 버린다(다른 대화상자·다른 코스로 바뀌었으면 generation·planId 가 다르다).
  const status = node('p', '앞뒤 이동과 전체 시간·비용을 다시 확인하고 있어요.', 'hint alternatives-status');
  root.append(status);
  let result;
  while (!result) {
    try {
      result = await api('/plans/' + planId + '/alternatives', {
        index,
        locked: [...locks]
      });
    } catch (error) {
      if (generation !== dialogGeneration || !$('#dialog').open || selected?.id !== planId) return;
      const retry = new Promise(resolve => {
        status.replaceChildren(
          node('span', (error?.message || '대신 갈 곳을 불러오지 못했어요.') + ' '),
          button('다시 불러오기', resolve)
        );
      });
      status.className = 'warning alternatives-status';
      await retry;
      if (generation !== dialogGeneration || !$('#dialog').open || selected?.id !== planId) return;
      status.className = 'hint alternatives-status';
      status.replaceChildren('앞뒤 이동과 전체 시간·비용을 다시 확인하고 있어요.');
    }
  }
  if (generation !== dialogGeneration || !$('#dialog').open || selected?.id !== planId) return;
  status.textContent = '앞뒤 이동과 전체 시간·비용을 다시 계산한 후보예요.';
  if (!result.alternatives.length) root.append(node('p', '현재 조건을 충족하는 대체 장소가 없습니다. 시간·예산·테마 조건을 직접 수정해 주세요.', 'warning'));
  let replacing = false;
  for (const option of result.alternatives) {
    const card = node('article', undefined, 'plan-card');
    if (option.replacement_evidence) {
      const info = option.replacement_evidence;
      card.append(node('p', `기존 장소에서 약 ${info.distance_m}m · 운영 정보 ${info.coverage.confirmed.length}/4항목 확인`, 'hint'), node('p', info.scope, 'hint'));
    }
    card.append(node('h3', option.places[index].name), node('p', `시간 변화 ${option.delta.minutes}분 · ${costChangeText(option.delta.total_before, option.total)}`, 'hint'), button('이 장소로 교체', async () => {
      if (selected?.id !== planId || generation !== dialogGeneration) {
        toast('선택한 코스가 바뀌었어요. 현재 코스에서 다시 골라주세요.');
        return;
      }
      if (replacing || !reason.querySelector('select').reportValidity()) return;
      // 코스 변경 잠금은 다른 변경·되돌리기와 같이 쓴다(plan-actions.js runPlanChange). 못 연 새 코스는 commitNewPlan 이 알린다.
      await runPlanChange(async () => {
        replacing = true;
        const controls = [...root.querySelectorAll('button,select')];
        controls.forEach(control => control.disabled = true);
        try {
          const updated = await api('/plans/' + planId + '/replace', {
            index,
            locked: [...locks],
            replacement_id: option.places[index].id
          });
          // 못 연 새 코스의 토스트는 열린 대화상자 안에 뜨고, 닫히면 바깥으로 옮겨진다(app.js toast).
          commitNewPlan(planId, updated, "장소를 바꿨어요");
          api('/plans/' + planId + '/feedback', {
            kind: 'replace_reason',
            place_id: oldPlaceId,
            reason: reason.querySelector('select').value
          }).catch(() => toast('일정은 변경됐지만 변경 이유 저장에 실패했어요.'));
          if (generation === dialogGeneration) $('#dialog').close();
        } finally {
          replacing = false;
          controls.forEach(control => control.disabled = false);
        }
      });
    }));
    // 이 장소로 바꾸면 축제 방문이 달라지는 후보는 고르기 전에 알린다(app/festival_time.change_note — 문구는 서버가 만든다).
    // [이 장소로 교체] 단추(방금 붙인 마지막 요소) 바로 앞에 둔다. 달라지는 게 없으면 키가 없어 아무것도 그리지 않는다.
    if (option.festival_change) card.lastElementChild.before(node('p', option.festival_change, 'warning festival-change-note'));
    root.append(card);
  }
}
async function showPlace(id, placeMode) {
  const root = openDialog('장소 정보를 불러오고 있어요'),
    generation = dialogGeneration;
  const p = await api('/places/' + encodeURIComponent(id) + '?mode=' + placeMode);
  if (generation !== dialogGeneration || !$('#dialog').open) return;
  root.replaceChildren(node('span', p.demo ? '가상 장소 · 시연용' : '실제 장소 메타데이터 · 운영정보 확인 필요', 'tag'), node('h2', p.name), node('p', p.description || '확인된 설명이 없습니다.'));
  // 네이버 검색으로 찾은 장소: '네이버 검색결과' 표시와 원본 링크(특약 1.1·1.2).
  if (isNaverResult(p)) root.append(naverAttribution('지역 검색', p.place_source || p.source));
  const facts = node('dl', undefined, 'facts');
  for (const [key, value] of [
      ['분류', p.category],
      ['주소', p.address || '미확인'],
      ['가격', range(p.price)],
      ['운영시간', p.hours ? p.hours.map(n => `${Math.floor(n/60)}:${String(n%60).padStart(2,'0')}`).join(' ~ ') : '미확인'],
      ['휴무', p.closed_days === null ? '미확인' : p.closed_days.length ? p.closed_days.map(n => ['월', '화', '수', '목', '금', '토', '일'][n]).join(', ') + '요일' : '없음 (데모 가정)'],
      ['체류 시간', p.stay ? `${p.stay}분 / ${p.stay_basis}` : '미확인'],
      ['예약', p.reservation === null ? '미확인' : p.reservation ? '필요' : '불필요'],
      // 서버 원문(UTC ISO)이 아니라 한국 시각으로(app.js koreaTimeText, 2026-11-25 운영 QA-09).
      ['확인 시점', koreaTimeText(p.checked_at) || '미확인'],
      ['자료 유형', p.source_type],
      ['외부 평점', p.rating ? JSON.stringify(p.rating) : '확보한 자료 없음'],
      ['권리', p.license]
    ]) facts.append(node('dt', key), node('dd', value));
  root.append(operatingFactsNotice(p), facts, link('메타데이터 원문', p.source), node('h3', '사진 · 영상'));
  if (!p.demo && statusData?.map_js_key) {
    const map = node('div', 'NAVER Maps', 'map');
    root.append(map);
    officialPlaceMap(map, p, statusData.map_js_key);
  }
  const photos = (p.photos || []).filter(x => x.license && x.source && x.url).slice(0, 5),
    videos = (p.videos || []).filter(x => x.source).slice(0, 3);
  const gallery = node('div', undefined, 'media-grid');
  photos.forEach(photo => {
    const figure = node('figure'),
      img = node('img');
    loadSafePhoto(img, [{
      ...photo,
      image_url: photo.url,
      title: photo.title || p.name
    }], null, () => img.replaceWith(node('p', '사진을 표시할 수 없어요. 사진 원문을 확인해 주세요.', 'hint')));
    img.alt = p.name;
    img.loading = 'lazy';
    figure.append(img, link('사진 출처 · ' + photo.license, photo.source));
    gallery.append(figure);
  });
  root.append(gallery, placePhotoPanel(p, placeMode, true), placeBlogPanel(p, placeMode));
  if (!videos.length) root.append(node('p', '확보한 영상이 없습니다. 영상 내용은 분석하지 않았습니다.', 'hint'));
  videos.forEach(v => root.append(link(v.title || '영상 원문', v.source)));
  const links = node('div', undefined, 'actions'),
    q = encodeURIComponent(p.name + ' ' + p.region);
  links.append(link('구글 사진 더보기', 'https://www.google.com/search?tbm=isch&q=' + q), link('구글 영상 더보기', 'https://www.google.com/search?tbm=vid&q=' + q), placeMapLink('네이버 지도', p));
  root.append(links, node('h3', '근거를 보며 질문하기'), chatWidget('place', id, placeMode));
}

// 닫힌 뒤 포커스가 갈 곳을 잃었으면(연 단추가 다시 그려져 사라짐) 같은 순번 장소의 제목, 없으면 상세 제목으로 옮긴다.
// 이 파일은 app.js($ 정의)보다 먼저 읽히므로 맨 위 수준에서는 getElementById 를 쓴다.
document.getElementById('dialog').addEventListener('close', () => {
  const back = dialogReturn;
  dialogReturn = null;
  setTimeout(() => {
    const active = document.activeElement;
    if (active && active !== document.body) return;
    if (back?.opener?.isConnected && back.opener !== document.body) return back.opener.focus({
      preventScroll: true
    });
    const stops = document.querySelectorAll('#plan-detail .stop');
    const target = (back && back.stop >= 0 && stops[back.stop]?.querySelector('h4')) || document.querySelector('#plan-detail h2, #plan-detail h3');
    if (!target) return;
    if (!target.hasAttribute('tabindex')) target.tabIndex = -1;
    target.focus({
      preventScroll: true
    });
  }, 0);
});
