/* 팝업 글 둘러보기와 코스 결과의 팝업 구역.
   2026-11-20(네이버 검색 API 특약 2.2: 가공 없이 독립적으로 노출, 순위·내용 수정 금지)부터 두 가지만 그린다.
   1) 네이버 블로그 검색 결과 블록(PopupView.block): 서버가 준 글을 받은 순서 그대로, 받은 건수 그대로, 제목·요약은 받은 글자 그대로
      텍스트로만 넣는다. 블록 안에는 네이버가 준 값(블로거·작성일·제목·요약·원문 링크)과 출처 표시만 둔다.
      글을 고르거나 나누거나 다시 줄 세우지 않고, 글에서 기간·장소를 읽어 적지 않는다. 사진도 없다.
   2) 팝업 거점 목록(PopupCourse.hubList)과 코스 지도의 팝업 표시(maps.js): 데이트메이트가 정해 둔 거점 사전(app/popup_hubs.py,
      좌표는 한국관광공사 자료)만으로 그린다. 검색된 글과 잇지 않는다(글 수·기간을 붙이지 않음). 출발지에서의 직선거리는 우리 계산이다.
   장소 둘러보기 안의 [장소]·[팝업스토어] 전환으로 연다(헤더 탭을 늘리지 않음). 코스 결과에서는 축제 구역 바로 뒤에 둔다.
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
  // 블록 밖에 적는 한 줄: 왜 기간·장소·사진이 없는지.
  about: '네이버 블로그 검색 결과를 받은 순서 그대로 보여 드려요. 글을 고르거나 다시 정렬하지 않아 팝업이 아닌 글이나 끝난 팝업 글이 섞일 수 있어요. 기간과 장소는 글 원문에서 확인해 주세요.',
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
    query.enterKeyHint = 'search';
    query.maxLength = 30;
    query.placeholder = '예: 성수, 캐릭터, 디저트';
    queryLabel.append(query);
    const searchButton = button('팝업 글 찾기', () => this.search(), 'primary');
    searchButton.id = 'popup-search';
    bar.append(regionLabel, queryLabel, searchButton);
    region.addEventListener('change', () => this.search());
    query.addEventListener('keydown', event => {
      // 한글 조합 중 Enter 는 글자 확정이라 검색하지 않는다.
      if (event.key === 'Enter' && !event.isComposing && event.keyCode !== 229) this.search();
    });
    const about = node('p', this.about, 'hint popup-about');
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
  // 작성일은 "2026.11.14" 꼴.
  day(value) {
    return String(value).replaceAll('-', '.');
  },
  source(data) {
    return (data.sources || [])[0] || {};
  },
  // "네이버 블로그 검색 ‘2026년 11월 서울 팝업스토어’ · 최신순 50건". 어떤 검색어의 결과인지 그대로 적는다.
  scopeText(data, count) {
    const source = this.source(data);
    return `네이버 블로그 검색 ‘${source.query || data.region + ' 팝업스토어'}’ · ${source.sort === 'date' ? '최신순 ' : ''}${count}건`;
  },
  // 같은 검색어의 네이버 블로그 검색 화면(블록의 원본 링크).
  searchUrl(data) {
    const query = this.source(data).query;
    return query ? 'https://search.naver.com/search.naver?' + new URLSearchParams({
      where: 'blog',
      query
    }) : null;
  },
  // 글 하나 = 항목 하나. 네이버가 준 값만 적는다: 블로거 이름 · 작성일, 제목, 요약, 원문 링크.
  card(post, titleTag = 'h4') {
    const card = node('article', undefined, 'popup-post');
    card.dataset.postId = post.id;
    const meta = [post.blogger, post.posted_at ? this.day(post.posted_at) : null].filter(Boolean).join(' · ');
    const source = link('블로그 원문 보기 ↗', post.url);
    source.classList.add('popup-source-link');
    if (meta) card.append(node('p', meta, 'popup-meta'));
    card.append(node(titleTag, post.title || '(제목 없음)', 'popup-title'), node('p', post.description, 'popup-summary'), source);
    return card;
  },
  // 네이버 검색결과 블록: 제목 줄(출처 표시) + 받은 순서 그대로의 글 + 「글 더 보기」. options: size(처음 보이는 수), heading·titleTag(제목 태그).
  // 「글 더 보기」는 뒤쪽 글을 접어 둔 것뿐이라 순서와 내용은 그대로다.
  block(data, options = {}) {
    const posts = Array.isArray(data.posts) ? data.posts : [],
      size = options.size || this.firstPage;
    // 블록 공통 부품(naver-attribution.js naverResultBlock): 머리글(건수 제목 + 출처 표시) + 본문(받은 글).
    const block = naverResultBlock('블로그 검색', this.searchUrl(data), {
      className: 'popup-list popup-naver-block',
      heading: node(options.heading || 'h3', `네이버 블로그 검색 결과 ${posts.length}건`)
    });
    const items = node('div', undefined, 'popup-items');
    const render = rows => items.append(...rows.map(post => this.card(post, options.titleTag)));
    render(posts.slice(0, size));
    block.body.append(items);
    if (posts.length > size) {
      const more = button(`글 더 보기 (${posts.length - size}건)`, () => {
        more.remove();
        render(posts.slice(size));
        // 키보드 사용자가 새로 열린 첫 글에서 이어 읽게 한다.
        items.children[size]?.querySelector('.popup-source-link')?.focus();
      });
      more.classList.add('popup-more');
      block.append(more);
    }
    return block;
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
  emptyBox(data, hint) {
    const box = node('div', undefined, 'popup-state popup-state-empty');
    box.append(node('p', data.message || '이 검색어로 검색된 글이 없어요.'));
    if (hint) box.append(node('p', hint, 'hint'));
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
    status.textContent = this.scopeText(data, posts.length);
    if (!posts.length) {
      results.append(this.emptyBox(data, '다른 시·도나 검색어로 찾아보세요.'));
      return;
    }
    results.append(this.block(data));
  }
};

/* 코스 결과의 팝업 구역. 축제 구역 바로 뒤에 둔다. 코스·지도와 따로 조회하고, 실패해도 코스·축제·지도·탭 동작에 영향이 없다.
   위: 네이버 블로그 검색 결과 블록(PopupView.block, 받은 순서 그대로). 아래: 팝업 거점 목록(우리 거점 사전, 글과 무관).
   거점은 출발지에서 가까운 순(직선거리, 같으면 거점 ID), 출발지 기준이 없으면 사전 순서. 코스 지도(maps.js)는 같은 배열(mapItems)에서 거점당 표시 하나를 그린다.
   거점은 '팝업이 자주 열리는 곳'일 뿐이고 지금 열리는지는 알 수 없다는 것을 목록 머리와 지도 설명에 적는다.
   주변 코스 버튼은 출발지(와 시·도)만 거점으로 바꾸고 방문일·시간대·예산·교통수단·취향은 조건 화면 값 그대로 다시 추천한다.
   festival 필드나 새 요청 필드를 싣지 않는다. 고른 거점과 되돌릴 출발지는 이 탭의 메모리에만 두고, 저장 코스를 다시 열면 되살리지 않는다.
   거점 좌표는 네이버 검색 결과가 아니라(관광공사 자료) 기기 보관 기한 표시(form-state.js 의 NaverDeviceRetention)를 붙이지 않는다.
   거리 계산·거리 문구는 축제 구역의 FestivalPanel.originOf·distance·distanceText 를 그대로 부른다(축제 파일은 고치지 않음). */
const PopupCourse = {
  generation: 0,
  controller: null,
  // 코스 결과에서 처음 보이는 글 수와 거점 수. 나머지는 「더 보기」.
  firstPage: 6,
  firstHubs: 3,
  // 코스 지도에 그릴, 지금 세대의 거점({hub, meters}). 거점 목록과 같은 배열이다.
  mapItems: [],
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
    const hubs = node('div', undefined, 'popup-course-hubs');
    hubs.id = 'popup-course-hubs';
    section.append(heading, node('p', '코스에 넣지 않은 참고 자료예요. ' + PopupView.about, 'hint popup-course-about'), demo, status, results, hubs);
    festival.after(section);
  },
  ready() {
    return PopupView.enabled && Boolean(document.getElementById('popup-course'));
  },
  // 코스 제목 옆 '축제 보기' 옆에서 팝업 구역으로 바로 이어 준다(구역이 보일 때만).
  jump(text) {
    const jump = document.getElementById('popup-jump');
    if (!jump) return;
    if (!text) {
      jump.hidden = true;
      return;
    }
    jump.textContent = text;
    jump.hidden = false;
    jump.onclick = () => {
      const section = document.getElementById('popup-course');
      if (!section || section.hidden) return;
      section.scrollIntoView({
        block: 'start'
      });
      const title = document.getElementById('popup-course-title');
      title.tabIndex = -1;
      title.focus({
        preventScroll: true
      });
    };
  },
  // 저장된 코스를 열거나 진행 중이던 검색을 이어받을 때. 팝업 거점 선택은 되살리지 않는다.
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
    // 이전 조건의 지도 표시는 바로 지운다. 새 표시는 이 세대의 응답이 왔을 때만 그린다.
    this.setMapItems([]);
    this.request(conditions, generation);
  },
  setMapItems(items) {
    this.mapItems = items;
    document.querySelectorAll('.plan-map').forEach(map => map.updatePopups?.());
  },
  async request(conditions, generation) {
    const controller = new AbortController();
    this.controller = controller;
    const region = conditions.region || '서울',
      day = conditions.visit_date;
    const section = document.getElementById('popup-course'),
      status = document.getElementById('popup-course-status'),
      results = document.getElementById('popup-course-results');
    document.getElementById('popup-course-title').textContent = `${region} 팝업스토어 글`;
    document.getElementById('popup-course-demo').hidden = conditions.mode !== 'demo';
    section.hidden = false;
    this.jump(`${region} 팝업스토어 보기 ↓`);
    results.replaceChildren();
    document.getElementById('popup-course-hubs').replaceChildren();
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
      this.jump(null);
      return;
    }
    document.getElementById('popup-course-status').textContent = '팝업 글을 불러오지 못했어요. 코스 추천에는 영향이 없어요.';
    document.getElementById('popup-course-results').replaceChildren(PopupView.errorBox(error.message || '팝업 글을 불러오지 못했어요.', () => this.load(conditions)));
  },
  // 사용자가 고른 실제 출발지만 기준으로 쓴다(데모 출발점·이어받은 검색은 기준이 없다). 축제 구역과 같은 규칙.
  originOf(conditions) {
    return typeof FestivalPanel === 'undefined' ? null : FestivalPanel.originOf(conditions);
  },
  // 서버가 준 거점 사전(좌표 있는 것만)을 {hub, meters} 로. 출발지가 있으면 가까운 순(같으면 거점 ID), 없으면 사전 순서. 같은 입력이면 같은 결과다.
  hubItems(data, origin) {
    const hubs = (Array.isArray(data.hubs) ? data.hubs : []).filter(hub => hub && Number.isFinite(hub.lat) && Number.isFinite(hub.lon));
    const items = hubs.map(hub => ({
      hub,
      meters: origin ? FestivalPanel.distance(origin, hub) : null
    }));
    if (!origin) return items;
    return items.sort((a, b) => a.meters - b.meters || (a.hub.hub_id < b.hub.hub_id ? -1 : a.hub.hub_id > b.hub.hub_id ? 1 : 0));
  },
  // 건물은 축제와 같은 문구. 동네는 기준 장소의 좌표라 km 단위로만 적고 무엇을 기준으로 잰 것인지 붙인다.
  distanceText(meters, hub) {
    if (hub.kind === 'area') return `출발지에서 직선거리 ${meters < 1000 ? '1km 이내' : `약 ${Math.round(meters / 1000)}km`} · ${hub.anchor} 기준`;
    return `출발지에서 직선거리 ${FestivalPanel.distanceText(meters)}`;
  },
  label(hub) {
    return hub.kind === 'area' ? `${hub.name}(대략)` : hub.name;
  },
  isChosen(hub) {
    return Boolean(this.chosen && hub && this.chosen.hub.hub_id === hub.hub_id);
  },
  // 위치 줄. 건물 좌표는 행사장 층·입구가 아니고, 동네는 기준 장소의 좌표라 대략이다.
  levelText(hub) {
    return hub.kind === 'area' ? `동네 기준 장소 ${hub.anchor} · 대략 위치` : '건물 위치 · 행사장 층·입구는 현장에서 확인';
  },
  fact(label, text, kind) {
    const row = node('div', undefined, 'popup-fact popup-' + kind);
    row.append(node('dt', label), node('dd', text));
    return row;
  },
  // 네이버에서 '{거점} 팝업'을 직접 찾아보는 바깥 링크(검색 API 를 쓰지 않는다).
  searchLink(hub) {
    const query = `${hub.name.replace(/ 일대$/, '')} 팝업`;
    const a = link(`네이버에서 ‘${query}’ 찾아보기 ↗`, 'https://search.naver.com/search.naver?' + new URLSearchParams({
      query
    }));
    a.classList.add('popup-hub-search');
    return a;
  },
  hubAction(hub, chosen) {
    const row = node('div', undefined, 'popup-action');
    if (chosen) {
      row.classList.add('is-chosen');
      row.append(node('p', `지금 코스는 ‘${this.label(hub)}’ 주변에서 출발해요.`, 'popup-action-note'));
    } else row.append(button(hub.kind === 'area' ? '이 일대 주변 코스 추천받기' : '이 장소 주변 코스 추천받기', () => this.planAround(hub)));
    row.append(this.searchLink(hub));
    return row;
  },
  hubBlock(item, origin) {
    const hub = item.hub,
      chosen = this.isChosen(hub);
    const block = node('section', undefined, 'popup-hub' + (chosen ? ' popup-hub-chosen' : ''));
    block.dataset.hubId = hub.hub_id;
    const facts = node('dl', undefined, 'popup-facts');
    facts.append(this.fact('위치', this.levelText(hub), 'place'));
    // 고른 거점은 곧 출발지라 거리를 적지 않는다.
    if (origin && !chosen) facts.append(this.fact('거리', this.distanceText(item.meters, hub), 'distance'));
    block.append(node('h5', this.label(hub), 'popup-hub-name'), facts, this.hubAction(hub, chosen));
    return block;
  },
  hubList(items, data, origin) {
    const block = node('section', undefined, 'popup-list popup-hubs');
    const order = origin ? '출발지에서 가까운 순(직선거리)' : '출발지 기준이 없어 정해 둔 순서';
    const provider = data.hub_coordinates?.provider;
    block.append(node('h4', `팝업이 자주 열리는 곳 ${items.length}곳 · ${order}`),
      node('p', `데이트메이트가 정해 둔 목록이에요${provider ? `(위치: ${provider} 자료)` : ''}. 위 검색 글과는 관계없고, 지금 팝업이 열리는지는 알 수 없어요.`, 'hint popup-hubs-about'));
    const list = node('div', undefined, 'popup-hub-items');
    const render = rows => list.append(...rows.map(item => this.hubBlock(item, origin)));
    render(items.slice(0, this.firstHubs));
    block.append(list);
    const rest = items.length - this.firstHubs;
    if (rest > 0) {
      const more = button(`다른 장소 ${rest}곳 더 보기`, () => block.showAll(true), 'secondary popup-more popup-hubs-more');
      // 코스 지도 정보 칸에서 이 목록으로 올 때(revealHub)도 같은 펼치기를 쓴다(그때는 포커스를 거점 이름에 둠).
      block.showAll = focus => {
        if (!more.isConnected) return;
        more.remove();
        render(items.slice(this.firstHubs));
        if (focus) list.children[this.firstHubs]?.querySelector('button,a')?.focus();
      };
      block.append(more);
    }
    return block;
  },
  // 코스 지도 아래 정보 칸의 「목록에서 보기」. 지금 세대의 거점이고 구역에 거점 목록이 있을 때만 단추를 둔다.
  canReveal(hubId) {
    const section = document.getElementById('popup-course');
    return Boolean(section && !section.hidden && section.querySelector('.popup-hubs') && this.mapItems.some(item => item.hub.hub_id === hubId));
  },
  // 그 거점이 접혀 있으면 펼치고(「다른 장소 n곳 더 보기」), 거점으로 스크롤해 거점 이름에 포커스를 둔다.
  revealHub(hubId) {
    if (!this.canReveal(hubId)) return false;
    const list = document.querySelector('#popup-course .popup-hubs'),
      find = () => [...list.querySelectorAll('.popup-hub')].find(block => block.dataset.hubId === String(hubId));
    if (!find()) list.showAll?.(false);
    const block = find();
    if (!block) return false;
    const name = block.querySelector('.popup-hub-name');
    name.tabIndex = -1;
    block.scrollIntoView({
      block: 'start'
    });
    name.focus({
      preventScroll: true
    });
    return true;
  },
  render(data, conditions) {
    const status = document.getElementById('popup-course-status'),
      results = document.getElementById('popup-course-results'),
      hubs = document.getElementById('popup-course-hubs');
    results.replaceChildren();
    hubs.replaceChildren();
    // 거점 목록과 지도 표시는 검색 결과와 무관하다: 글이 없거나 검색을 못 써도 그린다.
    const origin = this.originOf(conditions),
      items = this.hubItems(data, origin);
    if (items.length) hubs.append(this.hubList(items, data, origin));
    this.setMapItems(items);
    if (data.status === 'key_missing' || data.status === 'unavailable') {
      status.textContent = (data.status === 'key_missing' ? '팝업 글을 찾을 수 없어요.' : '팝업 글을 불러오지 못했어요.') + ' 코스 추천에는 영향이 없어요.';
      results.append(PopupView.stateBox(data, () => this.load(conditions)));
      return;
    }
    const posts = Array.isArray(data.posts) ? data.posts : [];
    status.textContent = PopupView.scopeText(data, posts.length);
    if (!posts.length) {
      results.append(PopupView.emptyBox(data));
      return;
    }
    this.jump(`${conditions.region || '서울'} 팝업스토어 글 ${posts.length}건 보기 ↓`);
    results.append(PopupView.block(data, {
      size: this.firstPage,
      heading: 'h4',
      titleTag: 'h5'
    }));
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
    const area = this.chosen.hub.kind === 'area',
      fromDemo = this.previous && this.previous.mode === 'demo';
    note.append(node('strong', `‘${this.chosen.label}’ 주변 기준 코스`, 'popup-origin-title'),
      node('span', `팝업이 자주 열리는 ${area ? '동네의 기준 장소' : '장소'}를 출발지로 바꿔 다시 추천했어요. ${fromDemo ? '가상 장소 데모 대신 실제 장소로 찾았고, ' : ''}날짜·시간·예산·교통·취향은 그대로예요. 지금 팝업이 열리는지는 알 수 없으니 방문 전에 확인해 주세요.`),
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
  planAround(hub) {
    const submit = document.getElementById('submit-plan');
    if (submit.disabled) {
      toast('코스를 찾는 중이에요. 끝난 뒤 다시 눌러 주세요.');
      return;
    }
    const area = hub.kind === 'area',
      label = this.label(hub);
    // 기존 지역 검색이 동네를 알 수 있게 "시·도 시·군·구 (동네 기준 장소)"를 ' · ' 앞에 둔다(축제 버튼과 같은 형식).
    const head = [hub.region, hub.district, area ? hub.anchor : null].filter(Boolean).join(' ');
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
    form.elements.region.value = hub.region || form.elements.region.value;
    // 거점 좌표는 우리 거점 사전의 값(관광공사 자료)이라 네이버 검색 결과의 기기 보관 표시를 붙이지 않는다.
    locationState.origin = {
      name: originName,
      lat: hub.lat,
      lon: hub.lon
    };
    form.elements.origin_name.value = originName;
    this.chosen = {
      hub: {
        ...hub
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
