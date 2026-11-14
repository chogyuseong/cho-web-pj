/* 팝업 둘러보기 (1단계 1a). 장소 둘러보기 안의 [장소]·[팝업스토어] 전환으로 연다(헤더 탭을 늘리지 않음).
   출처 중심: 네이버 블로그 검색 글 하나가 항목 하나다. 제목·요약·링크는 받은 그대로 텍스트로만 넣고,
   데이트메이트가 읽은 기간·장소는 원문 인용과 나뉜 별도 칸에 "검색 요약에서 읽은 …"으로 적는다.
   서버 상태(/api/status)의 popups_enabled 가 true 일 때만 전환을 그린다. 늦게 온 응답은 generation 으로 버린다. */
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
    const box = node('div', undefined, 'popup-state popup-state-error');
    box.append(node('p', message), button('다시 찾기', () => this.search()));
    document.getElementById('popup-results').replaceChildren(box);
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
  card(post, data) {
    const card = node('article', undefined, 'popup-post');
    card.dataset.postId = post.id;
    const quote = node('div', undefined, 'popup-quote');
    const meta = ['네이버 블로그', post.blogger, post.posted_at ? this.day(post.posted_at) + ' 글' : null].filter(Boolean).join(' · ');
    const source = link('블로그 원문 보기 ↗', post.url);
    source.classList.add('popup-source-link');
    quote.append(node('p', meta, 'popup-meta'), node('h4', post.title || '(제목 없음)', 'popup-title'), node('p', post.description, 'popup-summary'), source);
    const reading = node('div', undefined, 'popup-reading');
    const facts = node('dl', undefined, 'popup-facts');
    facts.append(this.fact('기간', this.periodText(post.period, data), 'period'), this.fact('장소', this.placeText(post.place), 'place'));
    reading.append(node('p', '데이트메이트가 검색 요약에서 읽은 정보', 'popup-reading-title'), facts);
    card.append(quote, reading);
    return card;
  },
  list(title, posts, data) {
    const block = node('section', undefined, 'popup-list');
    block.append(node('h3', title));
    const items = node('div', undefined, 'popup-items');
    const render = rows => items.append(...rows.map(post => this.card(post, data)));
    render(posts.slice(0, this.firstPage));
    block.append(items);
    if (posts.length > this.firstPage) {
      const more = button(`글 더 보기 (${posts.length - this.firstPage}건)`, () => {
        more.remove();
        render(posts.slice(this.firstPage));
      });
      more.classList.add('popup-more');
      block.append(more);
    }
    return block;
  },
  notes(data) {
    const counts = data.counts || {},
      lines = [];
    if (counts.hidden_ended) lines.push(`${this.basisText(data)} 기준 종료로 확인된 글 ${counts.hidden_ended}건은 숨겼어요.`);
    if (counts.excluded_other_region) lines.push(`다른 시·도 장소로 읽힌 글 ${counts.excluded_other_region}건은 뺐어요.`);
    if (counts.location_unknown) lines.push(`위치를 확인하지 못한 글 ${counts.location_unknown}건은 뒤에 두었어요.`);
    return lines;
  },
  render(data) {
    const status = document.getElementById('popup-status'),
      results = document.getElementById('popup-results');
    results.replaceChildren();
    const posts = Array.isArray(data.posts) ? data.posts : [];
    if (data.status === 'key_missing' || data.status === 'unavailable') {
      status.textContent = data.status === 'key_missing' ? '팝업 글을 찾을 수 없어요.' : '팝업 글을 불러오지 못했어요.';
      const box = node('div', undefined, 'popup-state ' + (data.status === 'key_missing' ? 'popup-state-key' : 'popup-state-error'));
      box.append(node('p', data.message || '팝업 글을 불러오지 못했어요.'));
      if (data.status === 'unavailable') box.append(button('다시 찾기', () => this.search()));
      results.append(box);
      return;
    }
    const source = (data.sources || [])[0] || {};
    const scope = `${data.region} · ${this.basisText(data)} 기준 · ${data.attribution || '네이버 블로그 검색 결과'} 최신 ${source.returned ?? source.display ?? ''}건 중`;
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
