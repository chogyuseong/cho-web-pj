// 자동차로 도착하는 장소 근처 주차장(네이버 지역 검색). 일정·비용에는 넣지 않는다.
// 첫 주차장 패널이 화면에 보일 때 코스(plan id)마다 한 번만 요청하고, 일정 패널과 지도가 같은 응답을 쓴다.
const parkingState = new Map();
const PARKING_SOURCE_NOTE = '주차 시간·요금은 일정과 비용에 포함하지 않았어요. 출처: 네이버 지역 검색';

function parkingEntry(planId) {
  if (!parkingState.has(planId)) parkingState.set(planId, {
    request: null,
    data: null,
    listeners: new Set()
  });
  return parkingState.get(planId);
}

function parkingStops(plan) {
  if (plan?.conditions?.mode !== 'real') return [];
  return (plan.places || []).map((_, i) => i).filter(i => plan.legs?.[i] && legMode(plan, plan.legs[i]) === 'car');
}

function loadParking(plan, refresh = false) {
  const entry = parkingEntry(plan.id);
  if (refresh) entry.request = null;
  if (!entry.request) {
    entry.request = api('/plans/' + encodeURIComponent(plan.id) + '/parking').then(data => {
      entry.data = data;
      entry.listeners.forEach(listener => listener(data, null));
      return data;
    }).catch(error => {
      entry.request = null;
      entry.listeners.forEach(listener => listener(null, error));
      throw error;
    });
  }
  return entry.request;
}

// 요청을 시작하지 않고 결과만 기다린다(지도). 이미 받았으면 바로 부른다. 돌려준 함수로 구독을 끝낸다.
function onParkingLoaded(plan, listener) {
  const entry = parkingEntry(plan.id);
  entry.listeners.add(listener);
  if (entry.data) listener(entry.data, null);
  return () => entry.listeners.delete(listener);
}

function parkingSearchLink(place) {
  return link(`지도에서 '${place.name} 주차장' 찾기 ↗`, 'https://map.naver.com/p/search/' + encodeURIComponent(place.name + ' 주차장'));
}

function parkingLotItem(lot) {
  const item = node('li', undefined, 'parking-lot'),
    title = node('div', undefined, 'parking-lot-title');
  title.append(node('strong', lot.name));
  if (lot.public_by_name) title.append(node('span', '공영(이름 기준)', 'tag parking-public'));
  item.append(title,
    node('p', `직선 ${Number(lot.distance_m).toLocaleString()}m · 걸어서 약 ${lot.walk_minutes}분(추정)`, 'parking-distance'),
    node('p', lot.address || '주소는 지도에서 확인해 주세요.', 'parking-address'),
    node('p', '요금·운영시간·만차 여부 미확인', 'hint parking-unverified'),
    placeMapLink('네이버 지도에서 보기 ↗', lot));
  return item;
}

function parkingPanel(plan, index) {
  if (!parkingStops(plan).includes(index)) return document.createDocumentFragment();
  const place = plan.places[index],
    panel = node('section', undefined, 'parking-panel'),
    heading = `${index+1}번 · ${place.name} 근처 주차장`;
  panel.setAttribute('aria-label', heading);
  const body = node('div', undefined, 'parking-body');
  body.append(node('p', '근처 주차장을 찾고 있어요…', 'hint'));
  panel.append(node('h4', heading), body, node('p', PARKING_SOURCE_NOTE, 'hint parking-note'));
  const retry = () => loadParking(plan, true).catch(() => {});

  function show(data, error) {
    if (error) {
      const message = error.status === 429 ? '주차장 검색은 잠시 후 다시 시도해 주세요.' : '주차장 검색에 연결하지 못했어요.';
      body.replaceChildren(node('p', message, 'hint'), button('다시 찾기', retry, 'secondary parking-retry'));
      return;
    }
    const stop = (data.stops || []).find(s => s.index === index);
    if (!stop || data.status === 'not_car' || data.status === 'demo') {
      panel.remove();
      return;
    }
    if (stop.lots?.length) {
      const list = node('ul', undefined, 'parking-lots');
      stop.lots.forEach(lot => list.append(parkingLotItem(lot)));
      body.replaceChildren(list);
    } else if (stop.status === 'unavailable') {
      body.replaceChildren(node('p', '주차장 검색에 연결하지 못했어요.', 'hint'), button('다시 찾기', retry, 'secondary parking-retry'));
    } else if (stop.status === 'key_missing' || stop.status === 'permission_required' || data.status === 'key_missing') {
      body.replaceChildren(node('p', stop.message || data.message, 'hint'), parkingSearchLink(place));
    } else {
      body.replaceChildren(node('p', '이 장소 800m 안에서 주차장을 찾지 못했어요.', 'hint'), parkingSearchLink(place));
    }
  }
  // 이미 받은 응답은 바로 그린다(패널이 아직 문서에 붙기 전). 그 뒤 다시 그려져 떨어진 패널은 구독을 끝낸다.
  let attached = false;
  const stopListening = onParkingLoaded(plan, (data, error) => {
    if (attached && !panel.isConnected) {
      stopListening();
      return;
    }
    show(data, error);
  });
  attached = true;
  const start = () => loadParking(plan).catch(() => {});
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      if (entries.some(e => e.isIntersecting)) {
        observer.disconnect();
        start();
      }
    }, {
      rootMargin: '100px'
    });
    observer.observe(panel);
  } else start();
  return panel;
}

// 지도 정보창: 이름·주소·지도 링크만, 모두 텍스트 노드로.
function parkingMapInfo(lot) {
  const content = node('div', undefined, 'restaurant-map-info parking-map-info');
  content.append(node('strong', 'P · ' + lot.name), node('p', lot.address || ''), placeMapLink('네이버 지도에서 보기 ↗', lot));
  return content;
}

function parkingMapLots(data) {
  return (data?.stops || []).flatMap(stop => stop.lots || []).filter(lot => Number.isFinite(lot.lat) && Number.isFinite(lot.lon));
}

function parkingMapNote(note, lots) {
  note.hidden = !lots.length;
  note.textContent = lots.length ? `P: 주차장 ${lots.length}곳(일정 미포함)` : '';
}
