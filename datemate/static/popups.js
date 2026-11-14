/* 팝업 둘러보기 (1단계 1a)와 코스 결과의 팝업 글 구역 (1b).
   1a: 장소 둘러보기 안의 [장소]·[팝업스토어] 전환으로 연다(헤더 탭을 늘리지 않음).
   1b: 코스 결과의 축제 구역 바로 뒤에 같은 지역·방문일의 팝업 글을 보이고(PopupCourse), 거점 기준 주변 코스 버튼을 둔다.
   출처 중심: 네이버 블로그 검색 글 하나가 항목 하나다. 제목·요약·링크는 받은 그대로 텍스트로만 넣고,
   데이트메이트가 읽은 기간·장소·거리는 원문 인용과 나뉜 별도 칸에 "검색 요약에서 읽은 …"으로 적는다.
   두 화면이 같은 항목 구성(PopupView.card·list·periodText·placeText·notes)을 쓴다.
   서버 상태(/api/status)의 popups_enabled 가 true 일 때만 전환과 구역을 그린다. 늦게 온 응답은 generation 으로 버린다. */
const PopupView = {
  generation: 0,
  controller: null,
  enabled: false,
  active: false,
  searched: false,
  firstPage: 10,
  regions: ['서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종', '경기', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주'],
  placesHeading: '',
  mount(enabled) {
    this.enabled = enabled === true;
    if (this.enabled) PopupCourse.mount();
    const section = document.getElementById('explore-section'),
      places = document.getElementById('explore-places');
    if (!this.enabled || !section || !places || document.getElementById('explore-switch')) return;
    const heading = section.querySelector('.section-heading h2');
    this.placesHeading = heading.textContent;
    const switcher = node('div', undefined, 'explore-switch');
    switcher.id = 'explore-switch';
    switcher.setAttribute('role', 'group');
    switcher.setAttribute('aria-label', '둘러볼 대상');
    const placeButton = button('장소', () => this.show(false), 'explore-switch-button'),
      popupButton = button('팝업스토어', () => this.show(true), 'explore-switch-button');
    placeButton.id = 'explore-switch-places';
    popupButton.id = 'explore-switch-popups';
    placeButton.setAttribute('aria-pressed', 'true');
    popupButton.setAttribute('aria-pressed', 'false');
    switcher.append(placeButton, popupButton);
    places.before(switcher);
    places.after(this.panel());
    document.getElementById('nav-explore').addEventListener('click', () => this.show(false));
    window.addEventListener('hashchange', () => {
      if (location.hash === '#explore-section') this.show(false);
    });
  },
  panel() {
    const root = node('div', undefined, 'popup-browse');
    root.id = 'popup-browse';
    root.hidden = true;
    const bar = node('div', undefined, 'panel searchbar popup-searchbar');
    const regionLabel = node('label', '시·도'),
      region = node('select');
    region.id = 'popup-region';
    for (const name of this.regions) {
      const option = node('option', name);
      option.value = name;
      region.append(option);
    }
    regionLabel.append(region);
    const queryLabel = node('label', '검색어 (선택)', 'grow'),
      query = node('input');
    query.id = 'popup-query';
    query.type = 'search';
    query.maxLength = 30;
    query.placeholder = '예: 성수, 캐릭터, 디저트';
    queryLabel.append(query);
    const searchButton = button('팝업 글 찾기', () => this.search(), 'primary');
    searchButton.id = 'popup-search';
    bar.append(regionLabel, queryLabel, searchButton);
    region.addEventListener('change', () => this.search());
    query.addEventListener('keydown', event => {
      if (event.key === 'Enter') this.search();
    });
    const about = node('p', '네이버 블로그 검색 결과를 글마다 그대로 보여 드려요. 기간·장소는 검색 요약에서 읽은 것이라 실제 운영과 다를 수 있어요. 방문 전 원문을 확인해 주세요.', 'hint popup-about');
    const status = node('p', '', 'popup-status');
    status.id = 'popup-status';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    const results = node('div', undefined, 'popup-results');
    results.id = 'popup-results';
    root.append(bar, about, status, results);
    return root;
  },
  show(popup) {
    if (!this.enabled) return;
    this.active = popup;
    document.getElementById('explore-places').hidden = popup;
    document.getElementById('popup-browse').hidden = !popup;
    document.getElementById('explore-switch-places').setAttribute('aria-pressed', String(!popup));
    document.getElementById('explore-switch-popups').setAttribute('aria-pressed', String(popup));
    document.querySelector('#explore-section .section-heading h2').textContent = popup ? '팝업스토어 둘러보기' : this.placesHeading;
    if (popup && !this.searched) {
      // 처음 열 때는 장소 둘러보기에서 고른 시·도로 시작한다.
      const from = document.getElementById('explore-region')?.value;
      if (this.regions.includes(from)) document.getElementById('popup-region').value = from;
      this.search();
    }
  },
  // 찾는 중에도 검색 버튼은 막지 않는다. 새로 찾으면 앞선 요청은 취소하고, 늦게 와도 generation 으로 버린다.
  setBusy(busy) {
    document.getElementById('popup-results').setAttribute('aria-busy', String(busy));
  },
  async search() {
    this.searched = true;
    const generation = ++this.generation;
    if (this.controller) this.controller.abort();
    const controller = new AbortController();
    this.controller = controller;
    const region = document.getElementById('popup-region').value,
      q = document.getElementById('popup-query').value.trim();
    document.getElementById('popup-status').textContent = `${region}의 팝업 글을 찾고 있어요.`;
    document.getElementById('popup-results').replaceChildren();
    this.setBusy(true);
    try {
      const params = new URLSearchParams({
        region,
        q
      });
      const data = await api('/popups?' + params, null, 'GET', {
        timeout: 20000,
        signal: controller.signal
      });
      if (generation !== this.generation) return;
      this.render(data);
    } catch (error) {
      if (generation !== this.generation) return;
      this.failed(error.message || '팝업 글을 불러오지 못했어요.');
    } finally {
      if (generation === this.generation) this.setBusy(false);
    }
  },
  failed(message) {
    document.getElementById('popup-status').textContent = '팝업 글을 불러오지 못했어요.';
    document.getElementById('popup-results').replaceChildren(this.errorBox(message, () => this.search()));
  },
  // 날짜는 "2026.11.14" 꼴. 연도까지 확인된 날짜에만 쓴다.
  day(value) {
    return String(value).replaceAll('-', '.');
  },
  basisText(data) {
    return data.basis === 'today' ? `오늘(${this.day(data.visit_date)})` : `방문일(${this.day(data.visit_date)})`;
  },
  periodText(period, data) {
    const basis = data.basis === 'today' ? '오늘' : '방문일';
    if (period.level === 'confirmed') {
      if (period.start && period.end) {
        const state = period.status === 'ongoing' ? `${basis} 기준 진행 중` : period.status === 'upcoming' ? `${basis} 기준 오픈 예정` : '기간 미확인';
        return {
          known: period.status !== 'unknown',
          text: `${this.day(period.start)} ~ ${this.day(period.end)} · ${state} · 원문 확인`
        };
      }
      if (period.start) return {
        known: period.status === 'upcoming',
        text: period.status === 'upcoming' ? `시작일 ${this.day(period.start)}만 읽었어요 · ${basis} 기준 오픈 예정` : `기간 미확인 · 시작일 ${this.day(period.start)}만 읽었어요`
      };
      return {
        known: false,
        text: `기간 미확인 · 종료일 ${this.day(period.end)}만 읽었어요`
      };
    }
    if (period.level === 'month_day') return {
      known: false,
      text: `기간 미확인 · 검색 요약에 적힌 날짜: ${period.evidence[0]}`
    };
    if (period.level === 'conflict') return {
      known: false,
      text: `기간 미확인 · 요약에 기간이 여럿 적혀 있어요: ${period.evidence.join(' / ')}`
    };
    return {
      known: false,
      text: '기간 미확인 · 요약에서 기간을 찾지 못했어요'
    };
  },
  placeText(place) {
    if (!place.hub_id) return {
      known: false,
      text: place.reason === 'multiple' ? '위치 미확인 · 요약에 장소가 여러 곳 적혀 있어요' : '위치 미확인 · 요약에서 장소를 찾지 못했어요'
    };
    const name = place.kind === 'area' ? `${place.name}(대략)` : place.name;
    if (place.level === 'building') return {
      known: true,
      text: `${name} · 건물 위치 확인(행사장 층·입구는 원문 확인)`
    };
    if (place.level === 'area_anchor') return {
      known: true,
      text: `${name} · 동네 기준점 ${place.anchor}`
    };
    return {
      known: false,
      text: `${name} · 위치 미확인(지도 위치를 확정하지 못했어요)`
    };
  },
  fact(label, value, kind) {
    const row = node('div', undefined, `popup-fact popup-${kind}` + (value.known ? '' : ' is-unconfirmed'));
    row.append(node('dt', label), node('dd', value.text));
    return row;
  },
  // 글 하나 = 항목 하나. extra.facts 는 읽은 정보 칸에 더할 줄(코스 구역의 거리 등), extra.action 은 항목 맨 아래 행동 줄.
  card(post, data, extra = {}) {
    const card = node('article', undefined, 'popup-post');
    card.dataset.postId = post.id;
    const quote = node('div', undefined, 'popup-quote');
    const meta = ['네이버 블로그', post.blogger, post.posted_at ? this.day(post.posted_at) + ' 글' : null].filter(Boolean).join(' · ');
    const source = link('블로그 원문 보기 ↗', post.url);
    source.classList.add('popup-source-link');
    quote.append(node('p', meta, 'popup-meta'), node('h4', post.title || '(제목 없음)', 'popup-title'), node('p', post.description, 'popup-summary'), source);
    const reading = node('div', undefined, 'popup-reading');
    const facts = node('dl', undefined, 'popup-facts');
    facts.append(this.fact('기간', this.periodText(post.period, data), 'period'), this.fact('장소', this.placeText(post.place), 'place'), ...(extra.facts || []));
    reading.append(node('p', '데이트메이트가 검색 요약에서 읽은 정보', 'popup-reading-title'), facts);
    card.append(quote, reading);
    if (extra.action) card.append(extra.action);
    return card;
  },
  // 처음 size 건 + "글 더 보기". options: size, heading(제목 태그), cardOf(항목 만들기).
  list(title, posts, data, options = {}) {
    const size = options.size || this.firstPage,
      cardOf = options.cardOf || (post => this.card(post, data));
    const block = node('section', undefined, 'popup-list');
    if (title) block.append(node(options.heading || 'h3', title));
    const items = node('div', undefined, 'popup-items');
    const render = rows => items.append(...rows.map(cardOf));
    render(posts.slice(0, size));
    block.append(items);
    if (posts.length > size) {
      const more = button(`글 더 보기 (${posts.length - size}건)`, () => {
        more.remove();
        render(posts.slice(size));
      });
      more.classList.add('popup-more');
      block.append(more);
    }
    return block;
  },
  notes(data, withUnknown = true) {
    const counts = data.counts || {},
      lines = [];
    if (counts.hidden_ended) lines.push(`${this.basisText(data)} 기준 종료로 확인된 글 ${counts.hidden_ended}건은 숨겼어요.`);
    if (counts.excluded_other_region) lines.push(`다른 시·도 장소로 읽힌 글 ${counts.excluded_other_region}건은 뺐어요.`);
    if (withUnknown && counts.location_unknown) lines.push(`위치를 확인하지 못한 글 ${counts.location_unknown}건은 뒤에 두었어요.`);
    return lines;
  },
  // "서울 · 오늘(2026.11.14) 기준 · 네이버 블로그 검색 결과 최신 50건 중"
  scopeText(data) {
    const source = (data.sources || [])[0] || {};
    return `${data.region} · ${this.basisText(data)} 기준 · ${data.attribution || '네이버 블로그 검색 결과'} 최신 ${source.returned ?? source.display ?? ''}건 중`;
  },
  // 서버 상태가 검색원을 쓰지 못한 경우(키 없음·연결 실패)의 상자. retry 가 있으면 연결 실패에만 "다시 찾기"를 둔다.
  stateBox(data, retry) {
    const box = node('div', undefined, 'popup-state ' + (data.status === 'key_missing' ? 'popup-state-key' : 'popup-state-error'));
    box.append(node('p', data.message || '팝업 글을 불러오지 못했어요.'));
    if (data.status === 'unavailable' && retry) box.append(button('다시 찾기', retry));
    return box;
  },
  errorBox(message, retry) {
    const box = node('div', undefined, 'popup-state popup-state-error');
    box.append(node('p', message), button('다시 찾기', retry));
    return box;
  },
  render(data) {
    const status = document.getElementById('popup-status'),
      results = document.getElementById('popup-results');
    results.replaceChildren();
    const posts = Array.isArray(data.posts) ? data.posts : [];
    if (data.status === 'key_missing' || data.status === 'unavailable') {
      status.textContent = data.status === 'key_missing' ? '팝업 글을 찾을 수 없어요.' : '팝업 글을 불러오지 못했어요.';
      results.append(this.stateBox(data, () => this.search()));
      return;
    }
    const scope = this.scopeText(data);
    if (data.status === 'empty' || !posts.length) {
      status.textContent = `${scope} 보여 드릴 팝업 글이 없어요.`;
      const box = node('div', undefined, 'popup-state popup-state-empty');
      box.append(node('p', data.message || '검색된 글 중에 보여 드릴 팝업 글이 없어요.'), ...this.notes(data).map(line => node('p', line, 'hint')), node('p', '다른 시·도나 검색어로 찾아보세요.', 'hint'));
      results.append(box);
      return;
    }
    status.textContent = `${scope} 팝업 글 ${posts.length}건`;
    if (data.status === 'partial') results.append(node('p', data.message || '일부 장소의 위치를 확인하지 못해 위치 미확인으로 표시했어요.', 'popup-state popup-state-partial'));
    for (const line of this.notes(data)) results.append(node('p', line, 'hint popup-note'));
    const general = posts.filter(post => !post.roundup),
      roundups = posts.filter(post => post.roundup);
    if (general.length) results.append(this.list(`검색된 팝업 글 ${general.length}건`, general, data));
    if (roundups.length) results.append(this.list(`여러 팝업을 모아 소개한 글 ${roundups.length}건`, roundups, data));
    results.append(node('p', `출처: ${data.attribution || '네이버 블로그 검색 결과'} · 순위나 인기순이 아니에요.`, 'hint popup-attribution'));
  }
};

/* 코스 결과의 팝업 글 구역 (1b). 축제 구역 바로 뒤에 둔다. 코스·지도와 따로 조회하고, 실패해도 코스·축제·지도·탭 동작에 영향이 없다.
   기본 목록은 위치가 확인된 글(건물·동네 기준점)만, 출발지에서 가까운 순(직선거리, 같으면 글 ID). 위치 미확인 글은 접어 두고 거리를 만들지 않는다.
   주변 코스 버튼은 출발지(와 시·도)만 거점으로 바꾸고 방문일·시간대·예산·교통수단·취향은 조건 화면 값 그대로 다시 추천한다.
   festival 필드나 새 요청 필드를 싣지 않는다. 고른 거점과 되돌릴 출발지는 이 탭의 메모리에만 두고, 저장 코스를 다시 열면 되살리지 않는다.
   거리 계산·거리 문구는 축제 구역의 FestivalPanel.originOf·distance·distanceText 를 그대로 부른다(축제 파일은 고치지 않음). */
const PopupCourse = {
  generation: 0,
  controller: null,
  firstPage: 6,
  // 「이 장소 주변 코스 추천받기」로 고른 거점({hub, label, originName}). 출발지가 그 거점이 아니게 되면 지운다.
  chosen: null,
  // 처음 거점을 고르기 직전의 출발지. 그때 축제를 고른 상태였으면 축제를 고르기 전 출발지. 모르면 null.
  previous: null,
  mount() {
    if (document.getElementById('popup-course')) return;
    const festival = document.getElementById('festival-section'),
      festivalNote = document.getElementById('festival-origin-note');
    if (!festival || !festivalNote) return;
    const note = node('div', undefined, 'popup-origin-note');
    note.id = 'popup-origin-note';
    note.setAttribute('role', 'status');
    note.hidden = true;
    festivalNote.after(note);
    const section = node('section', undefined, 'popup-course');
    section.id = 'popup-course';
    section.hidden = true;
    section.setAttribute('aria-labelledby', 'popup-course-title');
    const heading = node('div', undefined, 'section-heading');
    const title = node('h3', '팝업스토어 글');
    title.id = 'popup-course-title';
    heading.append(title);
    const demo = node('p', '코스는 서울 가상 장소 데모지만, 아래 글은 실제 네이버 블로그 검색 결과예요. 데모 출발점은 실제 위치가 아니라 거리를 적지 않고, 주변 코스 버튼을 누르면 실제 장소로 바꿔 추천해요.', 'hint popup-course-demo');
    demo.id = 'popup-course-demo';
    demo.hidden = true;
    const status = node('p', '', 'popup-status');
    status.id = 'popup-course-status';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    const results = node('div', undefined, 'popup-results');
    results.id = 'popup-course-results';
    section.append(heading,
      node('p', '네이버 블로그 검색 결과예요. 기간과 장소는 원문에서 확인해 주세요.', 'hint popup-course-about'),
      node('p', '코스에 넣지 않은 주변 후보예요. 주변 코스 버튼은 출발지만 그 장소로 바꾸고 날짜·시간·예산·교통·취향은 그대로 다시 추천해요.', 'hint popup-course-about'),
      demo, status, results);
    festival.after(section);
  },
  ready() {
    return PopupView.enabled && Boolean(document.getElementById('popup-course'));
  },
  // 저장된 코스를 열거나 진행 중이던 검색을 이어받을 때. 팝업 거점 선택은 되살리지 않는다(0단계 보고 8절).
  restore(conditions) {
    this.chosen = null;
    this.previous = null;
    this.load(conditions);
  },
  load(conditions) {
    if (!this.ready()) return;
    const generation = ++this.generation;
    if (this.controller) this.controller.abort();
    this.controller = null;
    this.updateChosen(conditions);
    this.request(conditions, generation);
  },
  async request(conditions, generation) {
    const controller = new AbortController();
    this.controller = controller;
    const region = conditions.region || '서울',
      day = conditions.visit_date;
    const section = document.getElementById('popup-course'),
      status = document.getElementById('popup-course-status'),
      results = document.getElementById('popup-course-results');
    document.getElementById('popup-course-title').textContent = `${region}에서 찾은 팝업스토어 글`;
    document.getElementById('popup-course-demo').hidden = conditions.mode !== 'demo';
    section.hidden = false;
    results.replaceChildren();
    results.setAttribute('aria-busy', 'true');
    status.textContent = `${region}의 팝업 글을 찾고 있어요.`;
    try {
      const params = new URLSearchParams({
        region
      });
      if (day) params.set('visit_date', day);
      const data = await api('/popups?' + params, null, 'GET', {
        timeout: 20000,
        signal: controller.signal
      });
      if (generation !== this.generation) return;
      this.render(data, conditions);
    } catch (error) {
      if (generation !== this.generation) return;
      this.failed(error, conditions);
    } finally {
      if (generation === this.generation) {
        results.setAttribute('aria-busy', 'false');
        this.controller = null;
      }
    }
  },
  failed(error, conditions) {
    // 페이지를 연 뒤 스위치가 꺼졌으면(404) 구역을 내린다.
    if (error.status === 404) {
      document.getElementById('popup-course').hidden = true;
      return;
    }
    document.getElementById('popup-course-status').textContent = '팝업 글을 불러오지 못했어요. 코스 추천에는 영향이 없어요.';
    document.getElementById('popup-course-results').replaceChildren(PopupView.errorBox(error.message || '팝업 글을 불러오지 못했어요.', () => this.load(conditions)));
  },
  located(place) {
    return Boolean(place && (place.level === 'building' || place.level === 'area_anchor') && Number.isFinite(place.lat) && Number.isFinite(place.lon));
  },
  // 사용자가 고른 실제 출발지만 기준으로 쓴다(데모 출발점·이어받은 검색은 기준이 없다). 축제 구역과 같은 규칙.
  originOf(conditions) {
    return typeof FestivalPanel === 'undefined' ? null : FestivalPanel.originOf(conditions);
  },
  // 출발지가 있으면 가까운 순, 같은 거리(같은 거점)는 글 ID 순. 없으면 받은 순서 그대로.
  byDistance(posts, origin) {
    if (!origin) return posts;
    return posts.map(post => ({
      post,
      meters: FestivalPanel.distance(origin, post.place)
    })).sort((a, b) => a.meters - b.meters || (a.post.id < b.post.id ? -1 : a.post.id > b.post.id ? 1 : 0)).map(item => item.post);
  },
  // 건물은 축제와 같은 문구. 동네 기준점은 기준점이 대략이라 km 단위로만 적고 무엇을 기준으로 잰 것인지 붙인다.
  distanceText(origin, place) {
    const meters = FestivalPanel.distance(origin, place);
    if (place.level === 'area_anchor') return `출발지에서 직선거리 ${meters < 1000 ? '1km 이내' : `약 ${Math.round(meters / 1000)}km`} · ${place.name} 기준`;
    return `출발지에서 직선거리 ${FestivalPanel.distanceText(meters)}`;
  },
  label(place) {
    return place.level === 'area_anchor' ? `${place.name}(대략)` : place.name;
  },
  isChosen(place) {
    return Boolean(this.chosen && place && this.chosen.hub.hub_id === place.hub_id);
  },
  // 방문일 기준 상태가 확인되지 않았거나 아직 열리지 않았으면 버튼 바로 옆에 글자로 적는다.
  stateNote(period, data) {
    const basis = data.basis === 'today' ? '오늘' : '방문일';
    if (period.status === 'upcoming') return `${basis} 기준 오픈 예정이에요. 방문일에 열리는지 원문에서 확인해 주세요.`;
    if (period.status !== 'ongoing') return '기간 미확인 · 방문일에 열리는지 원문에서 확인해 주세요.';
    return '';
  },
  action(post, data, chosen) {
    const row = node('div', undefined, 'popup-action'),
      place = post.place;
    if (!this.located(place)) {
      row.append(node('p', '위치를 확인하지 못해 주변 코스 추천을 할 수 없어요.', 'popup-action-note'));
      return row;
    }
    if (chosen) {
      row.classList.add('is-chosen');
      row.append(node('p', `지금 코스는 ‘${this.label(place)}’ 주변에서 출발해요.`, 'popup-action-note'));
      return row;
    }
    const go = button(place.level === 'area_anchor' ? '이 일대 주변 코스 추천받기' : '이 장소 주변 코스 추천받기', () => this.planAround(place));
    row.append(go);
    const state = this.stateNote(post.period, data);
    if (state) {
      const note = node('p', state, 'popup-action-note');
      note.id = 'popup-action-' + post.id.replace(/[^a-zA-Z0-9_-]/g, '-');
      go.setAttribute('aria-describedby', note.id);
      row.append(note);
    }
    return row;
  },
  card(post, data, origin) {
    const place = post.place,
      chosen = this.located(place) && this.isChosen(place),
      facts = [];
    // 고른 거점은 곧 출발지라 거리를 적지 않는다. 위치 미확인 글은 거리를 만들지 않는다.
    if (origin && this.located(place) && !chosen) facts.push(PopupView.fact('거리', {
      known: true,
      text: this.distanceText(origin, place)
    }, 'distance'));
    if (post.roundup) facts.push(PopupView.fact('종류', {
      known: true,
      text: '여러 팝업을 모아 소개한 글'
    }, 'kind'));
    const card = PopupView.card(post, data, {
      facts,
      action: this.action(post, data, chosen)
    });
    if (chosen) card.classList.add('popup-post-chosen');
    return card;
  },
  unknownBlock(posts, data) {
    const wrap = node('div', undefined, 'popup-unknown'),
      panel = node('div', undefined, 'popup-unknown-list');
    panel.id = 'popup-course-unknown';
    panel.hidden = true;
    const label = open => `위치를 확인하지 못한 글 ${posts.length}건 ${open ? '접기' : '보기'}`;
    const toggle = button(label(false), () => {
      const open = panel.hidden;
      panel.hidden = !open;
      toggle.textContent = label(open);
      toggle.setAttribute('aria-expanded', String(open));
      if (open && !panel.childElementCount) {
        panel.append(node('p', '장소를 확인하지 못해 거리를 적지 않았고, 주변 코스 추천도 할 수 없어요.', 'hint popup-note'),
          PopupView.list(null, posts, data, {
            size: this.firstPage,
            cardOf: post => this.card(post, data, null)
          }));
      }
    }, 'secondary popup-unknown-toggle');
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-controls', panel.id);
    wrap.append(toggle, panel);
    return wrap;
  },
  render(data, conditions) {
    const status = document.getElementById('popup-course-status'),
      results = document.getElementById('popup-course-results');
    results.replaceChildren();
    if (data.status === 'key_missing' || data.status === 'unavailable') {
      status.textContent = (data.status === 'key_missing' ? '팝업 글을 찾을 수 없어요.' : '팝업 글을 불러오지 못했어요.') + ' 코스 추천에는 영향이 없어요.';
      results.append(PopupView.stateBox(data, () => this.load(conditions)));
      return;
    }
    const posts = Array.isArray(data.posts) ? data.posts : [];
    const origin = this.originOf(conditions);
    const located = this.byDistance(posts.filter(post => this.located(post.place)), origin),
      unknown = posts.filter(post => !this.located(post.place));
    const scope = PopupView.scopeText(data),
      notes = PopupView.notes(data, false);
    if (data.status === 'empty' || !posts.length) {
      status.textContent = `${scope} 보여 드릴 팝업 글이 없어요.`;
      const box = node('div', undefined, 'popup-state popup-state-empty');
      box.append(node('p', data.message || '검색된 글 중에 보여 드릴 팝업 글이 없어요.'), ...notes.map(line => node('p', line, 'hint')));
      results.append(box);
      return;
    }
    status.textContent = `${scope} 팝업 글 ${posts.length}건 · 위치를 확인한 글 ${located.length}건`;
    if (data.status === 'partial') results.append(node('p', data.message || '일부 장소의 위치를 확인하지 못해 위치 미확인으로 표시했어요.', 'popup-state popup-state-partial'));
    for (const line of notes) results.append(node('p', line, 'hint popup-note'));
    if (located.length) {
      const order = origin ? '출발지에서 가까운 순(직선거리)' : '출발지 기준이 없어 받은 순서';
      results.append(PopupView.list(`위치를 확인한 글 ${located.length}건 · ${order}`, located, data, {
        size: this.firstPage,
        heading: 'h4',
        cardOf: post => this.card(post, data, origin)
      }));
    } else {
      const box = node('div', undefined, 'popup-state popup-state-empty popup-state-unlocated');
      box.append(node('p', '위치를 확인한 글이 없어 거리순으로 보여 드릴 글이 없어요.'));
      results.append(box);
    }
    if (unknown.length) results.append(this.unknownBlock(unknown, data));
    results.append(node('p', `출처: ${data.attribution || '네이버 블로그 검색 결과'} · 순위나 인기순이 아니에요.`, 'hint popup-attribution'));
  },
  matches(conditions) {
    const chosen = this.chosen,
      origin = conditions.origin;
    return Boolean(chosen && conditions.mode === 'real' && origin && origin.name === chosen.originName &&
      Math.abs(origin.lat - chosen.hub.lat) < 1e-6 && Math.abs(origin.lon - chosen.hub.lon) < 1e-6);
  },
  updateChosen(conditions) {
    if (!this.matches(conditions)) {
      this.chosen = null;
      this.previous = null;
    }
    const note = document.getElementById('popup-origin-note');
    if (!note) return;
    note.hidden = !this.chosen;
    note.replaceChildren();
    if (!this.chosen) return;
    const area = this.chosen.hub.level === 'area_anchor',
      fromDemo = this.previous && this.previous.mode === 'demo';
    note.append(node('strong', `‘${this.chosen.label}’ 주변 기준 코스`, 'popup-origin-title'),
      node('span', `팝업 글에서 읽은 ${area ? '동네 기준점' : '장소'}을 출발지로 바꿔 다시 추천했어요. ${fromDemo ? '가상 장소 데모 대신 실제 장소로 찾았고, ' : ''}날짜·시간·예산·교통·취향은 그대로예요. 팝업 운영 여부는 원문에서 확인해 주세요.`),
      button(this.previous ? '원래 출발지로 다시 추천' : '팝업 기준 해제 · 조건 다시 고르기', () => this.clearChoice()));
  },
  // 되돌릴 출발지. 지금 출발지가 고른 축제 장소이면 축제를 고르기 전 출발지를 쓴다(축제 쪽이 기억하는 값).
  snapshot() {
    const current = {
      mode: form.elements.mode.value,
      origin: locationState.origin
    };
    let source = {
      mode: current.mode,
      region: form.elements.region.value,
      origin: locationState.origin,
      originName: form.elements.origin_name.value
    };
    if (typeof FestivalPanel !== 'undefined' && FestivalPanel.matches(current)) source = FestivalPanel.previous;
    return source ? {
      mode: source.mode,
      region: source.region,
      origin: source.origin ? {
        ...source.origin
      } : null,
      originName: source.originName
    } : null;
  },
  planAround(place) {
    const submit = document.getElementById('submit-plan');
    if (submit.disabled) {
      toast('코스를 찾는 중이에요. 끝난 뒤 다시 눌러 주세요.');
      return;
    }
    const area = place.level === 'area_anchor',
      label = this.label(place);
    // 기존 지역 검색이 동네를 알 수 있게 "시·도 시·군·구 (동네 기준점)"을 ' · ' 앞에 둔다(축제 버튼과 같은 형식).
    const head = [place.region, place.district, area ? place.anchor : null].filter(Boolean).join(' ');
    const originName = `${head} · ${label} 주변`.slice(0, 200);
    // 다른 거점으로 바꿔 골라도 되돌릴 출발지는 처음 거점을 고르기 전의 것이다.
    if (!this.chosen) this.previous = this.snapshot();
    if (form.elements.mode.value !== 'real') {
      form.elements.mode.value = 'real';
      form.elements.mode.dispatchEvent(new Event('change', {
        bubbles: true
      }));
    }
    // 지역 change 이벤트를 보내지 않는다. 보내면 방금 넣은 출발지가 지워진다. 방문일·시간·예산·교통·취향은 건드리지 않는다.
    form.elements.region.value = place.region || form.elements.region.value;
    locationState.origin = {
      name: originName,
      lat: place.lat,
      lon: place.lon
    };
    form.elements.origin_name.value = originName;
    this.chosen = {
      hub: {
        ...place
      },
      label,
      originName
    };
    form.requestSubmit();
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
    if (previous && previous.origin) {
      if (form.elements.mode.value !== previous.mode) {
        form.elements.mode.value = previous.mode;
        form.elements.mode.dispatchEvent(new Event('change', {
          bubbles: true
        }));
      }
      form.elements.region.value = previous.region;
      locationState.origin = {
        ...previous.origin
      };
      form.elements.origin_name.value = previous.originName;
      form.requestSubmit();
      return;
    }
    // 원래 출발지를 모르면(이어받은 코스에서 고른 경우 등) 조건 화면에서 다시 고르게 한다.
    this.updateChosen({});
    setTab(false);
    showPlannerPage(false);
    toast('팝업 기준을 해제했어요. 데이트할 지역을 골라 다시 추천받아 주세요.');
  }
};
