/* Festivals for the submitted course conditions. Provider photos are KOGL Type1/Type3 (attribution, no alteration),
   so they are shown whole (never cropped or filtered) with a credit line, and dropped when missing or broken.
   Runs beside the course search and never blocks or fails it.
   Fees are the organizer's free text: shown as written, never parsed into course budgets or cost totals. */
const FestivalPanel = {
  generation: 0,
  firstPage: 6,
  detailLimit: 3,
  detailActive: 0,
  detailQueue: [],
  // 「이 축제 주변 코스 추천받기」로 고른 축제. 출발지가 그 축제가 아니게 되면 지운다.
  chosen: null,
  // 축제를 고르기 직전의 조건. 선택을 해제하면 이 조건으로 다시 추천한다.
  previous: null,
  // 코스 지도에 표시할, 좌표가 있는 방문일 축제.
  mapItems: [],
  // 공유 화면처럼 코스를 다시 추천할 수 없는 곳에서는 축제 선택 버튼을 그리지 않는다.
  readOnly: false,
  // 새로고침으로 검색을 이어받을 때 축제 구역을 다시 그리는 데 필요한 조건만 남긴다.
  // 출발지는 축제를 고른 경우(곧 축제 장소)에만 담는다.
  contextOf(conditions) {
    const festival = conditions.festival || null,
      origin = conditions.origin;
    return {
      mode: conditions.mode,
      region: conditions.region,
      visit_date: conditions.visit_date,
      festival,
      origin: festival && origin ? {
        name: origin.name,
        lat: origin.lat,
        lon: origin.lon
      } : null
    };
  },
  // 저장된 코스를 열거나 진행 중이던 검색을 이어받을 때. 그 코스가 고른 축제가 있으면 선택 상태로 되살린다.
  // 고르기 전 조건은 남아 있지 않으므로, 해제하면 조건 화면에서 다시 고르게 한다.
  restore(conditions) {
    const festival = conditions.festival,
      origin = conditions.origin;
    this.chosen = festival && origin && conditions.mode === 'real' ? {
      festival: {
        ...festival
      },
      originName: origin.name
    } : null;
    this.previous = null;
    this.load(conditions);
  },
  load(conditions) {
    const generation = ++this.generation;
    this.detailQueue = [];
    this.updateChosen(conditions);
    this.mapItems = [];
    this.refreshMaps();
    this.request(conditions, generation).catch(() => {
      if (generation === this.generation) this.status('축제 자료에 연결하지 못했어요. 코스 추천에는 영향이 없어요.');
    });
  },
  matches(conditions) {
    const chosen = this.chosen,
      origin = conditions.origin;
    return Boolean(chosen && conditions.mode === 'real' && origin && origin.name === chosen.originName &&
      Math.abs(origin.lat - chosen.festival.lat) < 1e-6 && Math.abs(origin.lon - chosen.festival.lon) < 1e-6);
  },
  // 추천 요청에 실어 보낼 축제 기준. 서버는 이 축제 위치를 탐색 중심으로 쓴다.
  anchorFor(conditions) {
    if (!this.matches(conditions)) return null;
    const festival = this.chosen.festival;
    return {
      id: String(festival.id).slice(0, 240),
      title: String(festival.title).slice(0, 200),
      lat: festival.lat,
      lon: festival.lon
    };
  },
  isChosen(festival) {
    return Boolean(this.chosen && this.chosen.festival.id === festival.id);
  },
  refreshMaps() {
    document.querySelectorAll('.plan-map').forEach(map => map.updateFestivals?.());
  },
  updateChosen(conditions) {
    if (!this.matches(conditions)) {
      this.chosen = null;
      this.previous = null;
    }
    const note = document.getElementById('festival-origin-note');
    if (!note) return;
    note.hidden = !this.chosen;
    note.replaceChildren();
    if (!this.chosen) return;
    note.append(node('strong', `‘${this.chosen.festival.title}’ 기준 코스`, 'festival-origin-title'),
      node('span', '축제 장소에서 출발해 주변 장소로 다시 추천했어요.'),
      button(this.previous ? '축제 선택 해제 · 원래 조건으로 다시 추천' : '축제 선택 해제 · 조건 다시 고르기', () => this.clearChoice()));
  },
  clearChoice() {
    const submit = document.getElementById('submit-plan');
    if (submit.disabled) {
      toast('코스를 찾는 중이에요. 끝난 뒤 다시 눌러 주세요.');
      return;
    }
    const previous = this.previous;
    this.chosen = null;
    this.previous = null;
    if (previous) {
      if (form.elements.mode.value !== previous.mode) {
        form.elements.mode.value = previous.mode;
        form.elements.mode.dispatchEvent(new Event('change', {
          bubbles: true
        }));
      }
      form.elements.region.value = previous.region;
      locationState.origin = previous.origin ? {
        ...previous.origin
      } : null;
      form.elements.origin_name.value = previous.originName;
      form.elements.visit_date.value = previous.visitDate;
    }
    if (!previous || !locationState.origin) {
      // 원래 출발지가 없던 경우(축제부터 고른 경우)나 이어받은 코스라 원래 조건을 모르는 경우는 조건 화면에서 다시 고르게 한다.
      this.updateChosen({});
      setTab(false);
      showPlannerPage(false);
      toast('축제 선택을 해제했어요. 데이트할 지역을 골라 다시 추천받아 주세요.');
      return;
    }
    form.requestSubmit();
  },
  photo(festival) {
    const url = String(festival.image_url || '');
    if (!url.startsWith('https://tong.visitkorea.or.kr/')) return null;
    const figure = node('figure', undefined, 'festival-photo');
    const frame = node('div', undefined, 'festival-photo-frame');
    const img = document.createElement('img');
    img.loading = 'lazy';
    img.decoding = 'async';
    img.referrerPolicy = 'no-referrer';
    img.alt = `${festival.title} 대표 사진`;
    img.addEventListener('error', () => figure.remove(), {
      once: true
    });
    img.src = url;
    frame.append(img);
    // 한국관광콘텐츠랩 저작권 정책이 정한 출처 표기 형식과, 직접 링크로 쓸 때 함께 제공해야 하는 정책 안내 링크.
    const credit = node('figcaption', '출처: ⓒ한국관광공사 · ', 'festival-photo-credit');
    credit.append(link('저작권 정책 ↗', 'https://api.visitkorea.or.kr/#/useServiceGuide/2'));
    figure.append(frame, credit);
    return figure;
  },
  status(text) {
    document.getElementById('festival-status').textContent = text;
  },
  hasPoint(festival) {
    return Number.isFinite(festival.lat) && Number.isFinite(festival.lon);
  },
  // 거리 기준이 되는 출발지. 사용자가 고른 실제 출발지만 쓴다(데모 출발점·공유 화면은 기준이 없다).
  originOf(conditions) {
    const origin = conditions.origin;
    return conditions.mode === 'real' && origin && this.hasPoint(origin) ? {
      lat: origin.lat,
      lon: origin.lon
    } : null;
  },
  // 두 좌표 사이의 직선거리(m). 실제 이동 거리와 다를 수 있다.
  distance(a, b) {
    const rad = Math.PI / 180,
      dLat = (b.lat - a.lat) * rad,
      dLon = (b.lon - a.lon) * rad;
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
    return 2 * 6371000 * Math.asin(Math.min(1, Math.sqrt(h)));
  },
  distanceText(meters) {
    if (meters < 950) return `약 ${Math.max(100, Math.round(meters / 100) * 100)}m`;
    const km = meters / 1000;
    return `약 ${km < 10 ? String(Math.round(km * 10) / 10) : Math.round(km)}km`;
  },
  // 좌표가 있는 축제는 출발지에서 가까운 순으로, 좌표가 없는 축제는 받은 순서 그대로 뒤에 둔다.
  byDistance(festivals, origin) {
    const located = festivals.filter(festival => this.hasPoint(festival)).map((festival, index) => ({
      festival,
      index,
      meters: this.distance(origin, festival)
    }));
    located.sort((a, b) => a.meters - b.meters || a.index - b.index);
    return [...located.map(item => item.festival), ...festivals.filter(festival => !this.hasPoint(festival))];
  },
  // 방문일이 축제 기간 밖이면 기간 안에서 오늘 이후 가장 가까운 날로 맞춘다. 이미 끝난 축제면 그대로 둔다.
  visitDayFor(festival, current) {
    const lower = festival.start > today() ? festival.start : today();
    if (lower > festival.end) return current;
    if (!current || current < lower) return lower;
    if (current > festival.end) return festival.end;
    return current;
  },
  planAround(festival) {
    const submit = document.getElementById('submit-plan');
    if (submit.disabled) {
      toast('코스를 찾는 중이에요. 끝난 뒤 다시 눌러 주세요.');
      return;
    }
    // 주변 장소 검색이 행사장 동네를 알 수 있게, 주소의 시·군·구(읍·면·동)를 ' · ' 앞에 둔다.
    const words = String(festival.address || '').replace(/[()]/g, ' ').split(/\s+/).slice(1);
    const area = [...words.filter(word => /^[가-힣]{1,8}(시|군|구)$/.test(word)).slice(0, 2),
      ...words.filter(word => /^[가-힣0-9]{1,8}(읍|면|동)$/.test(word)).slice(0, 1)
    ].join(' ');
    const originName = `${[festival.region, area].filter(Boolean).join(' ')} · ${String(festival.title).slice(0, 120)} 행사장 주변`;
    // 다른 축제로 바꿔 골라도 되돌릴 조건은 처음 축제를 고르기 전의 것이다.
    if (!this.previous) this.previous = {
      mode: form.elements.mode.value,
      region: form.elements.region.value,
      origin: locationState.origin ? {
        ...locationState.origin
      } : null,
      originName: form.elements.origin_name.value,
      visitDate: form.elements.visit_date.value
    };
    if (form.elements.mode.value !== 'real') {
      form.elements.mode.value = 'real';
      form.elements.mode.dispatchEvent(new Event('change', {
        bubbles: true
      }));
    }
    // 지역 change 이벤트를 보내지 않는다. 보내면 방금 넣은 출발지가 지워진다.
    form.elements.region.value = festival.region;
    locationState.origin = {
      name: originName,
      lat: festival.lat,
      lon: festival.lon
    };
    form.elements.origin_name.value = originName;
    form.elements.visit_date.value = this.visitDayFor(festival, form.elements.visit_date.value);
    this.chosen = {
      festival,
      originName
    };
    form.requestSubmit();
  },
  queueDetail(festival, fee, hours, generation) {
    if (!/^\d{1,12}$/.test(String(festival.id))) {
      fee.textContent = '이용요금 정보가 제공되지 않았어요';
      hours.hidden = true;
      return;
    }
    this.detailQueue.push({
      festival,
      fee,
      hours,
      generation
    });
    this.pumpDetails();
  },
  pumpDetails() {
    while (this.detailActive < this.detailLimit && this.detailQueue.length) {
      const job = this.detailQueue.shift();
      if (job.generation !== this.generation) continue;
      this.detailActive++;
      this.fetchDetail(job).finally(() => {
        this.detailActive--;
        this.pumpDetails();
      });
    }
  },
  async fetchDetail({
    festival,
    fee,
    hours,
    generation
  }) {
    let data = null;
    try {
      data = await api('/festivals/' + encodeURIComponent(festival.id) + '/detail', null, 'GET', {
        timeout: 30000
      });
    } catch {}
    // 조건이 바뀌어 다시 그려졌으면 옛 응답은 새 카드를 건드리지 않는다.
    if (generation !== this.generation || !fee.isConnected) return;
    if (!data || data.status !== 'available') {
      fee.textContent = '요금 정보를 불러오지 못했어요';
      hours.hidden = true;
      return;
    }
    fee.textContent = data.fee ? `이용요금: ${data.fee}` : '이용요금 정보가 제공되지 않았어요';
    hours.textContent = data.hours ? `운영 시간: ${data.hours}` : '';
    hours.hidden = !data.hours;
  },
  card(festival, generation, origin) {
    const card = node('article', undefined, 'festival-card');
    const chosen = this.chosen && this.chosen.festival.id === festival.id;
    if (chosen) {
      card.classList.add('festival-chosen');
      card.append(node('span', '선택한 축제', 'tag'));
    }
    const photo = this.photo(festival);
    if (photo) card.append(photo);
    const fee = node('p', '요금 확인 중…', 'hint festival-fee');
    const hours = node('p', '', 'hint festival-hours');
    hours.hidden = true;
    card.append(node('strong', festival.title),
      node('p', `${festival.start} ~ ${festival.end} · ${festival.region}`, 'hint'),
      node('p', festival.address, 'hint'));
    // 고른 축제는 곧 출발지라 거리를 적지 않는다. 좌표가 없으면 거리를 만들어 내지 않는다.
    if (origin && !chosen && this.hasPoint(festival)) card.append(node('p', `출발지에서 직선거리 ${this.distanceText(this.distance(origin, festival))}`, 'hint festival-distance'));
    card.append(fee, hours, link('한국관광공사에서 확인 ↗', festival.source_url));
    // 공유 화면에서는 보기만 하므로 축제 선택 버튼을 두지 않는다.
    if (!this.readOnly) {
      if (chosen) card.append(button('이 축제 선택 해제', () => this.clearChoice()));
      else if (this.hasPoint(festival)) card.append(button('이 축제 주변 코스 추천받기', () => this.planAround(festival)));
      else card.append(node('p', '위치 좌표가 없어 지도 표시와 주변 코스 추천을 할 수 없어요.', 'hint'));
    }
    this.queueDetail(festival, fee, hours, generation);
    return card;
  },
  async request(conditions, generation) {
    const section = document.getElementById('festival-section');
    const results = document.getElementById('festival-results');
    const more = document.getElementById('festival-more');
    const day = conditions.visit_date;
    const region = conditions.region || '서울';
    document.getElementById('festival-title').textContent = `${day || '방문일'} ${region}에서 열리는 축제·행사`;
    document.getElementById('festival-demo-note').hidden = conditions.mode !== 'demo';
    results.replaceChildren();
    more.hidden = true;
    more.onclick = null;
    section.hidden = false;
    // 코스 제목 옆 버튼으로 같은 지역의 축제 구역과 바로 이어 준다.
    const jump = document.getElementById('festival-jump');
    jump.textContent = `${region} 축제 보기 ↓`;
    jump.hidden = false;
    jump.onclick = () => {
      section.scrollIntoView({
        behavior: 'smooth',
        block: 'start'
      });
      const title = document.getElementById('festival-title');
      title.tabIndex = -1;
      title.focus({
        preventScroll: true
      });
    };
    if (!day) {
      this.status('방문 날짜를 정하면 그날 열리는 축제를 함께 보여드려요.');
      return;
    }
    this.status('방문일에 열리는 축제를 찾는 중…');
    const params = new URLSearchParams({
      start: day,
      end: day,
      region
    });
    const data = await api('/festivals?' + params, null, 'GET', {
      timeout: 90000
    });
    if (generation !== this.generation) return;
    if (data.status !== 'available') {
      this.status(data.status === 'key_missing' ? '축제 자료 키가 설정되지 않아 축제를 표시할 수 없어요. 코스 추천은 그대로 이용할 수 있어요.' : '축제 자료에 연결하지 못했어요. 코스 추천에는 영향이 없어요.');
      return;
    }
    let festivals = Array.isArray(data.festivals) ? data.festivals : [];
    // 시·도 전체 축제가 오므로, 출발지가 있으면 가까운 축제부터 보여 주고 요금·시간도 그 순서로 조회한다.
    const origin = this.originOf(conditions);
    if (origin) festivals = this.byDistance(festivals, origin);
    // 고른 축제는 맨 앞에 둔다. 방문일 목록에 없으면(날짜가 기간 끝으로 조정된 경우 등) 고른 정보를 그대로 앞에 붙인다.
    // 이어받은 코스의 축제는 저장된 이름·좌표뿐이라, 목록에서 찾은 자료로 바꾸고 못 찾으면 카드를 만들지 않는다.
    if (this.chosen) {
      const id = this.chosen.festival.id;
      const found = festivals.find(item => item.id === id);
      if (found && !this.chosen.festival.start) this.chosen.festival = found;
      const first = found || (this.chosen.festival.start ? this.chosen.festival : null);
      festivals = [...(first ? [first] : []), ...festivals.filter(item => item.id !== id)];
    }
    this.mapItems = festivals.filter(festival => this.hasPoint(festival));
    this.refreshMaps();
    if (!festivals.length) {
      this.status('');
      results.append(node('p', '방문일에 확인된 축제가 없어요.', 'hint'));
      return;
    }
    let text = `${festivals.length}건 · `;
    if (origin) {
      text += this.chosen ? '선택한 축제를 맨 위에 두고, 나머지는 축제 장소에서 가까운 순(직선거리)으로 보여드려요. ' : `${region} 전체 축제를 출발지에서 가까운 순(직선거리)으로 보여드려요. `;
      if (festivals.some(festival => !this.hasPoint(festival))) text += '위치 정보가 없는 축제는 맨 뒤에 있어요. ';
    }
    text += data.message || '';
    if (data.truncated) text += ' 조회 결과가 많아 일부만 표시합니다.';
    this.status(text);
    jump.textContent = `${region} 축제 ${festivals.length}건 보기 ↓`;
    const render = items => results.append(...items.map(festival => this.card(festival, generation, origin)));
    render(festivals.slice(0, this.firstPage));
    if (festivals.length > this.firstPage) {
      more.textContent = `축제 더 보기 (${festivals.length - this.firstPage}건)`;
      more.hidden = false;
      more.onclick = () => {
        more.hidden = true;
        more.onclick = null;
        render(festivals.slice(this.firstPage));
      };
    }
  }
};
