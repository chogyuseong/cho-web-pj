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
  const lats = points.map(x => x.lat),
    lons = points.map(x => x.lon),
    minLat = Math.min(...lats),
    minLon = Math.min(...lons),
    dy = Math.max(.002, Math.max(...lats) - minLat),
    dx = Math.max(.002, Math.max(...lons) - minLon);
  const coords = points.map(x => [60 + (x.lon - minLon) / dx * 480, 180 - (x.lat - minLat) / dy * 130]);
  const path = document.createElementNS(ns, 'polyline');
  path.setAttribute('points', coords.map(x => x.join(',')).join(' '));
  path.setAttribute('fill', 'none');
  path.setAttribute('stroke', '#91a27b');
  path.setAttribute('stroke-width', '3');
  path.setAttribute('stroke-dasharray', '7 6');
  svg.append(path);
  coords.forEach(([x, y], i) => {
    const circle = document.createElementNS(ns, 'circle');
    circle.setAttribute('cx', x);
    circle.setAttribute('cy', y);
    circle.setAttribute('r', 17);
    circle.setAttribute('fill', i === 0 ? '#e4774b' : '#294d3d');
    const t = document.createElementNS(ns, 'text');
    t.setAttribute('x', x);
    t.setAttribute('y', y + 5);
    t.setAttribute('text-anchor', 'middle');
    t.setAttribute('fill', 'white');
    t.setAttribute('font-size', '12');
    t.textContent = i === 0 ? '출발' : i > p.places.length ? '귀가' : String(i);
    svg.append(circle, t);
  });
  wrap.append(svg, node('div', '좌표 개략도 · 직선 연결 · 실제 지도/경로 아님', 'map-caption'));
  return wrap;
}
let dialogGeneration = 0;

function openDialog(title) {
  dialogGeneration++;
  const root = $('#dialog-content');
  root.replaceChildren(node('h2', title));
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
  root.append(node('p', '앞뒤 이동과 전체 시간·비용을 다시 확인하고 있어요.', 'hint'));
  const result = await api('/plans/' + planId + '/alternatives', {
    index,
    locked: [...locks]
  });
  if (generation !== dialogGeneration || !$('#dialog').open || selected?.id !== planId) return;
  if (!result.alternatives.length) root.append(node('p', '현재 조건을 충족하는 대체 장소가 없습니다. 시간·예산·테마 조건을 직접 수정해 주세요.', 'warning'));
  let replacing = false;
  for (const option of result.alternatives) {
    const card = node('article', undefined, 'plan-card');
    if (option.replacement_evidence) {
      const info = option.replacement_evidence;
      card.append(node('p', `기존 장소에서 약 ${info.distance_m}m · 운영 정보 ${info.coverage.confirmed.length}/4항목 확인`, 'hint'), node('p', info.scope, 'hint'));
    }
    card.append(node('h3', option.places[index].name), node('p', `전체 ${range(option.total)} · 시간 변화 ${option.delta.minutes}분 · 비용 변화 ${option.delta.cost.map(won).join(' ~ ')}`, 'hint'), button('이 장소로 교체', async () => {
      if (selected?.id !== planId || generation !== dialogGeneration) {
        toast('선택한 코스가 바뀌었어요. 현재 코스에서 다시 골라주세요.');
        return;
      }
      if (replacing || !reason.querySelector('select').reportValidity()) return;
      replacing = true;
      const controls = [...root.querySelectorAll('button,select')];
      controls.forEach(control => control.disabled = true);
      try {
        const updated = await api('/plans/' + planId + '/replace', {
          index,
          locked: [...locks],
          replacement_id: option.places[index].id
        });
        const displayed = commitPlanChange(planId, updated);
        api('/plans/' + planId + '/feedback', {
          kind: 'replace_reason',
          place_id: oldPlaceId,
          reason: reason.querySelector('select').value
        }).catch(() => toast('일정은 변경됐지만 변경 이유 저장에 실패했어요.'));
        if (generation === dialogGeneration) $('#dialog').close();
        if (!displayed) return;
      } finally {
        replacing = false;
        controls.forEach(control => control.disabled = false);
      }
    }));
    root.append(card);
  }
}
async function showPlace(id, placeMode) {
  const root = openDialog('장소 정보를 불러오고 있어요'),
    generation = dialogGeneration;
  const p = await api('/places/' + encodeURIComponent(id) + '?mode=' + placeMode);
  if (generation !== dialogGeneration || !$('#dialog').open) return;
  root.replaceChildren(node('span', p.demo ? '가상 장소 · 시연용' : '실제 장소 메타데이터 · 운영정보 확인 필요', 'tag'), node('h2', p.name), node('p', p.description || '확인된 설명이 없습니다.'));
  const facts = node('dl', undefined, 'facts');
  for (const [key, value] of [
      ['분류', p.category],
      ['주소', p.address || '미확인'],
      ['가격', range(p.price)],
      ['운영시간', p.hours ? p.hours.map(n => `${Math.floor(n/60)}:${String(n%60).padStart(2,'0')}`).join(' ~ ') : '미확인'],
      ['휴무', p.closed_days === null ? '미확인' : p.closed_days.length ? p.closed_days.map(n => ['월', '화', '수', '목', '금', '토', '일'][n]).join(', ') + '요일' : '없음 (데모 가정)'],
      ['체류 시간', p.stay ? `${p.stay}분 / ${p.stay_basis}` : '미확인'],
      ['예약', p.reservation === null ? '미확인' : p.reservation ? '필요' : '불필요'],
      ['확인 시점', p.checked_at],
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
  links.append(link('구글 사진 더보기', 'https://www.google.com/search?tbm=isch&q=' + q), link('구글 영상 더보기', 'https://www.google.com/search?tbm=vid&q=' + q), link('네이버 지도', 'https://map.naver.com/p/search/' + q));
  root.append(links, node('h3', '근거를 보며 질문하기'), chatWidget('place', id, placeMode));
}
