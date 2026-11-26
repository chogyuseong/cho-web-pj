const LEISURE_SETTINGS = [
  ['indoor', '실내 레저'],
  ['outdoor', '실외 레저']
];

function leisureDistance(meters) {
  return meters >= 1000 ? (Math.round(meters / 100) / 10) + 'km' : meters + 'm';
}

function leisureSport(row) {
  return row.sport || {
    label: row.place.category || '레저',
    setting: 'indoor',
    varies: false
  };
}

function leisureSportText(sport) {
  return sport.label + ' · ' + (sport.setting === 'outdoor' ? '실외' : '실내') + (sport.varies ? ' (시설에 따라 다름)' : '');
}

// 종목 그림(2026-11-24 사용자 요청 — 레저 카드를 사진 있는 형식으로).
// 왜: 상가정보 레저(당구장·볼링장·탁구장 등)에는 등록 사진도 관광공사 사진도 없고, 네이버 검색 사진은 쓰지 않는다(특약 1.2, app/media.py).
//     그래서 실제 사진이 0장이면 카드 맨 위에 종목 묶음(app/sports.py 의 Sport.group)의 그림을 두고 '이 가게 사진 아님'을 적는다.
// 그림: 48×48 선 그림, 색은 CSS(.leisure-sport-art — results.css)가 currentColor 로 정한다. 묶음 이름이 바뀌거나 새 묶음이 생기면
//     여기에 한 줄 더한다(없으면 LEISURE_ART_DEFAULT). 서버가 group 을 주지 않는 옛 응답도 기본 그림으로 그린다.
const LEISURE_ART_DEFAULT = '<circle cx="24" cy="24" r="14"/><path d="M24 14v20M14 24h20"/>';
const LEISURE_ART = {
  // 볼링 핀과 공
  '실내 게임': '<path d="M17 8c-3 0-4 4-3 8s-3 6-3 12c0 7 3 12 6 12s6-5 6-12c0-6-4-8-3-12s0-8-3-8z"/><circle cx="34" cy="32" r="8"/><circle cx="32" cy="29" r="1"/><circle cx="36" cy="29" r="1"/>',
  // 라켓과 셔틀콕
  '실내 코트': '<ellipse cx="19" cy="19" rx="9" ry="11" transform="rotate(-35 19 19)"/><path d="M25 27l10 12M14 14l10 10M12 21l8-8"/><path d="M36 9l4 6-3 2-4-6zM37 16l-1 4"/>',
  // 화면과 공
  '스크린': '<rect x="6" y="9" width="36" height="24" rx="2"/><path d="M18 40h12M24 33v7"/><circle cx="30" cy="21" r="4"/><path d="M12 27l8-6"/>',
  // 클라이밍 벽의 홀드
  '실내 활동': '<path d="M8 42L16 6h24v36z"/><circle cx="22" cy="14" r="2.5"/><circle cx="30" cy="22" r="2.5"/><circle cx="20" cy="28" r="2.5"/><circle cx="31" cy="35" r="2.5"/>',
  // 스케이트
  '빙상·롤러': '<path d="M12 12h10v12l12 4c3 1 4 3 4 6H12z"/><path d="M8 40h34M16 34v6M34 34v6"/>',
  // 물결과 헤엄치는 사람
  '물놀이': '<circle cx="30" cy="14" r="4"/><path d="M12 26l8-6 10 4 8-2"/><path d="M6 34c4-3 8-3 12 0s8 3 12 0 8-3 12 0M6 41c4-3 8-3 12 0s8 3 12 0 8-3 12 0"/>',
  // 산과 해
  '육상 레저': '<path d="M4 40l14-22 8 11 6-8 12 19z"/><circle cx="36" cy="11" r="4"/>',
  // 물 위의 배
  '수상 레저': '<path d="M24 8v22M24 10l12 18H24"/><path d="M10 31h28l-5 6H15z"/><path d="M6 42c4-3 8-3 12 0s8 3 12 0 8-3 12 0"/>',
  // 라켓과 공, 바닥 선
  '야외 코트': '<ellipse cx="18" cy="18" rx="9" ry="11" transform="rotate(-35 18 18)"/><path d="M24 26l9 11"/><circle cx="36" cy="12" r="4"/><path d="M4 42h40"/>',
  // 눈 결정
  '겨울 레저': '<path d="M24 6v36M8 15l32 18M8 33l32-18M20 9l4 4 4-4M20 39l4-4 4 4"/>',
  // 패러글라이더
  '하늘 레저': '<path d="M6 20C10 10 38 10 42 20"/><path d="M6 20l18 16 18-16M15 14l9 22 9-22"/><circle cx="24" cy="39" r="2"/>'
};

function leisureSportArt(sport) {
  const figure = node('figure', undefined, 'leisure-sport-art');
  figure.dataset.setting = sport.setting === 'outdoor' ? 'outdoor' : 'indoor';
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 48 48');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  // 고정 문자열(LEISURE_ART)만 SVG 로 읽는다(innerHTML 을 쓰지 않는 저장소 관례). 서버 값은 묶음 이름을 고르는 데만 쓴다.
  const shapes = new DOMParser().parseFromString('<svg xmlns="http://www.w3.org/2000/svg">' + (LEISURE_ART[sport.group] || LEISURE_ART_DEFAULT) + '</svg>', 'image/svg+xml');
  svg.append(...[...shapes.documentElement.childNodes].map(child => document.importNode(child, true)));
  const caption = node('figcaption');
  caption.append(node('strong', sport.label), node('span', '종목 예시 그림 · 이 가게 사진 아님'));
  figure.append(svg, caption);
  return figure;
}

function leisureSuggestionPanel(plan, index) {
  const panel = node('details', undefined, 'leisure-results');
  panel.append(node('summary', `${index+1}. ${plan.places[index].name} 주변 레저`));
  if (locks.has(index) || Object.hasOwn(plan.conditions.locked || {}, index)) {
    panel.append(node('p', '고정한 장소예요. 아래 일정에서 고정을 해제하면 주변 레저를 선택할 수 있어요.', 'hint'));
    return panel;
  }
  const content = node('div');
  panel.append(content);
  let loaded = false,
    selecting = false;

  function leisureCard(row) {
    const place = row.place,
      sport = leisureSport(row),
      card = node('article', undefined, 'leisure-result-card');
    card.dataset.sport = sport.label;
    // 사진 칸을 카드 맨 위에 둔다(2026-11-24 — 사진 있는 형식). 실제 사진이 없으면 그 칸이 종목 그림을 보여 준다(leisureSportArt).
    card.append(leisurePhotoPanel(place, plan.conditions.mode, sport));
    card.append(node('strong', place.name), node('p', leisureSportText(sport), 'leisure-sport-tag'), node('p', `${place.description||place.category} · 현재 장소에서 직선 ${leisureDistance(row.distance_m)}`, 'hint'), node('p', `교체 시 전체 소요 시간 ${row.delta.minutes>=0?'+':''}${row.delta.minutes}분 · ${costChangeText(row.delta.total_before, row.total)}`, 'hint'));
    // 이 레저로 바꾸면 축제 방문이 달라지는 후보는 고르기 전에 알린다(app/festival_time.change_note).
    if (row.festival_change) card.append(node('p', row.festival_change, 'warning festival-change-note'));
    const actions = node('div', undefined, 'actions');
    const select = button('이 레저로 교체', async () => {
      if (selected?.id !== plan.id) {
        toast('선택한 코스가 바뀌었어요. 현재 코스에서 다시 골라주세요.');
        return;
      }
      if (selecting) return;
      // 코스 변경 잠금은 다른 변경·되돌리기와 같이 쓴다(plan-actions.js runPlanChange). 못 연 새 코스는 commitNewPlan 이 알린다.
      await runPlanChange(async () => {
        selecting = true;
        const controls = [...content.querySelectorAll('button')];
        controls.forEach(b => b.disabled = true);
        try {
          const updated = await api('/plans/' + plan.id + '/leisure-select', {
            index,
            locked: [...locks],
            replacement_id: place.id
          });
          if (commitNewPlan(plan.id, updated)) toast('선택한 레저로 교체하고 시간·비용·지도를 다시 계산했어요.');
        } catch (error) {
          toast(error.message);
        } finally {
          selecting = false;
          controls.forEach(b => b.disabled = false);
        }
      });
    }, 'primary');
    select.disabled = plan.can_edit === false || locks.has(index);
    actions.append(select, placeMapLink('지도에서 확인 ↗', place));
    // 레저 후보는 공공 자료(한국관광공사·소상공인 상가정보)에서 찾는다(app/leisure.py). 출처 한 줄을 둔다.
    if (isPublicDataPlace(place)) card.append(publicDataSource(place));
    card.append(actions);
    return card;
  }

  function leisureFilter(options, sections) {
    const labels = [...new Set(options.map(row => leisureSport(row).label))];
    const group = node('div', undefined, 'leisure-filter');
    group.setAttribute('role', 'group');
    group.setAttribute('aria-label', '종목으로 후보 좁히기');
    const chips = [];

    function apply(label) {
      chips.forEach(chip => chip.setAttribute('aria-pressed', String(chip.dataset.sport === label)));
      for (const section of sections) {
        const cards = [...section.querySelectorAll('.leisure-result-card')];
        cards.forEach(card => card.hidden = label !== '' && card.dataset.sport !== label);
        const empty = section.querySelector('.leisure-filter-empty');
        if (empty) empty.hidden = !cards.length || cards.some(card => !card.hidden);
      }
    }
    for (const label of ['', ...labels]) {
      const count = label ? options.filter(row => leisureSport(row).label === label).length : options.length;
      const chip = button(`${label||'전체'} ${count}`, () => apply(label), 'secondary');
      chip.dataset.sport = label;
      chip.setAttribute('aria-pressed', String(label === ''));
      chips.push(chip);
      group.append(chip);
    }
    return group;
  }

  async function load() {
    if (panel.getAttribute('aria-busy') === 'true') return;
    content.replaceChildren(node('p', '코스 주변의 실내·실외 레저 장소를 찾고 있어요…', 'hint'));
    panel.setAttribute('aria-busy', 'true');
    try {
      const data = await api('/plans/' + plan.id + '/leisure-options', {
        index,
        locked: [...locks]
      });
      if (!panel.isConnected || selected?.id !== plan.id) return;
      content.replaceChildren(node('p', data.message, 'hint'));
      const sections = LEISURE_SETTINGS.map(([setting, title]) => {
        const rows = data.options.filter(row => leisureSport(row).setting === setting),
          section = node('section', undefined, 'leisure-setting');
        section.dataset.setting = setting;
        section.setAttribute('aria-label', title);
        section.append(node('h4', `${title} ${rows.length}곳`));
        if (setting === 'outdoor') section.append(node('p', '날씨와 계절에 따라 운영이 달라요. 방문 전 확인해 주세요.', 'hint leisure-outdoor-note'));
        if (!rows.length) section.append(node('p', '주변에서 찾지 못했어요.', 'hint'));
        else {
          const empty = node('p', '선택한 종목은 이 구분에 없어요.', 'hint leisure-filter-empty');
          empty.hidden = true;
          section.append(empty, ...rows.map(leisureCard));
        }
        const rejected = (data.diagnostics?.rejected_by_setting || {})[setting];
        if (rejected?.count) {
          const reasons = Object.entries(rejected.reasons || {}).map(([reason, count]) => `${reason} ${count}곳`).join(' · ');
          section.append(node('p', `${title} ${rejected.count}곳은 현재 일정 조건 때문에 제외했어요${reasons?' ('+reasons+')':''}. 이동 시간이나 예산을 늘리면 더 볼 수 있어요.`, 'hint leisure-rejected'));
        }
        return section;
      });
      if (new Set(data.options.map(row => leisureSport(row).label)).size > 1) content.append(leisureFilter(data.options, sections));
      content.append(...sections);
      if (!data.options.length) {
        const diagnostics = data.diagnostics || {};
        const message = diagnostics.search_status === 'unavailable' ? '공공 자료(한국관광공사·소상공인 상가정보)를 불러오지 못했어요. 잠시 후 다시 확인해 주세요.' : diagnostics.nearby_count ? '주변 레저 장소는 찾았지만 시간·예산·필수 조건 때문에 현재 일정에 넣을 수 없어요.' : '현재 일정에 넣을 수 있는 레저 후보를 찾지 못했어요. 다른 코스 위치에서도 확인해 보세요.';
        content.append(node('p', message, 'hint'));
        for (const reason of Object.keys(diagnostics.rejected || {})) content.append(node('p', '제외 사유: ' + reason, 'hint'));
      }
      content.append(button('주변 레저 다시 찾기', load, 'secondary'));
      loaded = true;
    } catch (error) {
      content.replaceChildren(node('p', error.message, 'warning'), button('다시 찾기', load, 'secondary'));
    } finally {
      panel.setAttribute('aria-busy', 'false');
    }
  }
  panel.addEventListener('toggle', () => {
    if (panel.open && !loaded && panel.getAttribute('aria-busy') !== 'true') load();
  });
  return panel;
}

function leisureCoursePanel(plan) {
  const section = node('section', undefined, 'leisure-course-panel');
  section.setAttribute('aria-label', '이 동선에서 즐길 레저 골라보기');
  section.append(node('h3', '이 동선에서 즐길 레저 골라보기'), node('p', '주변 레저를 찾을 코스 위치를 펼쳐주세요. 선택하면 그 순서의 방문지만 교체해요.', 'hint'));
  plan.places.forEach((place, index) => section.append(leisureSuggestionPanel(plan, index)));
  return section;
}


// sport: 실제 사진이 0장일 때 대신 보여 줄 종목(leisureSportArt). 없으면 그림 없이 예전처럼 안내만.
function leisurePhotoPanel(place, photoMode, sport) {
  const panel = node('section', undefined, 'leisure-photo-panel');
  panel.setAttribute('aria-label', place.name + ' 사진 최대 2장');
  if (place.demo || photoMode === 'demo') {
    if (sport) panel.append(leisureSportArt(sport));
    panel.append(node('p', '가상 장소 · 실제 사진을 붙이지 않습니다.', 'hint'));
    return panel;
  }
  const status = node('p', '장소 사진 2장을 찾고 있어요…', 'hint');
  status.setAttribute('role', 'status');
  panel.append(status);
  let busy = false,
    lastPhotos = [];
  async function load(force = false) {
    if (busy || !panel.isConnected) return;
    busy = true;
    panel.setAttribute('aria-busy', 'true');
    panel.replaceChildren(status);
    status.textContent = '장소 사진 2장을 찾고 있어요…';
    const grid = node('div', undefined, 'leisure-photo-grid');
    panel.append(grid);
    const slots = Array.from({
      length: 2
    }, (_, index) => {
      const figure = node('figure'),
        image = node('img');
      image.width = 480;
      image.height = 320;
      image.decoding = 'async';
      const placeholder = node('p', (index + 1) + '번째 사진 확인 중…', 'leisure-photo-empty');
      figure.append(placeholder);
      grid.append(figure);
      return {
        figure,
        image,
        index,
        loaded: false
      };
    });
    const seen = new Set(),
      displayed = new Set();
    let deadline = 0;
    async function fill(photos) {
      lastPhotos.push(...photos);
      const queue = photos.filter(photo => {
        const key = photoCandidates(photo)[0];
        if (!key || seen.has(key)) return false;
        seen.add(key);
        return true;
      }).slice(0, 8);
      await Promise.all(slots.filter(slot => !slot.loaded).map(async slot => {
        while (queue.length && panel.isConnected && Date.now() < deadline) {
          const photo = queue.shift();
          // 격자에는 서버가 줄인 사진(thumb_url, /photo-thumb 폭 960 WebP)을 먼저 쓰고, 안 되면 원본(loadSafePhoto thumb 옵션, 2026-11-18).
          // 눌러서 여는 '크게 보기' 링크는 늘 원본이다. url 이 줄인 사진이면 그 사진의 첫 원본 후보로 바꿔 건다(같은 사진 거르기도 원본 기준).
          await loadSafePhoto(slot.image, [photo], (selectedPhoto, url) => {
            const full = url === selectedPhoto.thumb_url ? photoCandidates(selectedPhoto)[0] || url : url;
            if (!panel.isConnected || displayed.has(full)) return;
            displayed.add(full);
            slot.loaded = true;
            slot.image.alt = place.name + ' 사진 ' + (slot.index + 1);
            const original = link('', full);
            original.setAttribute('aria-label', place.name + ' 사진 ' + (slot.index + 1) + ' 크게 보기');
            original.append(slot.image);
            const credit = node('figcaption');
            if (NAVER_PHOTO_KINDS.includes(photo.kind)) {
              credit.append(link(photoLabel(photo, '사진 출처') + ' ↗', photo.source));
            } else {
              credit.append(node('span', (photo.author || '') + ' · '), link(photo.license || '이용 조건', photo.license_url), node('span', ' · '), link(photoLabel(photo, '사진 출처') + ' ↗', photo.source));
            }
            slot.figure.replaceChildren(original, credit);
          }, () => {
            slot.loaded = false;
            slot.figure.replaceChildren(node('p', '이 사진을 표시할 수 없어요.', 'leisure-photo-empty'));
            if (!busy && panel.isConnected) {
              status.textContent = '일부 사진을 표시하지 못했어요. 다시 찾기를 눌러 주세요.';
              if (!panel.querySelector('.leisure-photo-retry')) panel.append(button('사진 다시 찾기', () => load(true), 'secondary leisure-photo-retry'));
            }
          }, {
            thumb: true
          });
          if (slot.loaded) break;
        }
      }));
    }
    try {
      if (force) {
        for (const photo of lastPhotos)
          for (const url of [photo.thumb_url, ...photoCandidates(photo)]) photoLoads.delete(url);
      }
      lastPhotos = [];
      let data;
      try {
        data = await fetchPlacePhotos(place, photoMode, force);
      } catch {
        data = {
          photos: [],
          message: '업체 사진 조회에 실패해 리뷰 사진을 확인했어요.'
        };
      }
      if (!panel.isConnected) return;
      deadline = Date.now() + 20000;
      await fill(data.photos || []);
      if (slots.some(slot => !slot.loaded) && panel.isConnected) {
        status.textContent = '업체 사진이 부족해 리뷰 사진을 찾고 있어요…';
        try {
          const fallback = await api('/places/' + encodeURIComponent(place.id) + '/media?mode=' + photoMode + '&fallback=reviews', null, 'GET', {
            timeout: 60000
          });
          if (panel.isConnected) await fill(fallback.photos || []);
        } catch {}
      }
      if (!panel.isConnected) return;
      const count = slots.filter(slot => slot.loaded).length;
      status.textContent = count ? '장소 사진 ' + count + '장 · 누르면 크게 볼 수 있어요.' : (data.message || '현재 표시할 수 있는 장소 사진을 찾지 못했어요.');
      for (const slot of slots.filter(slot => !slot.loaded)) {
        slot.figure.remove();
      }
      if (!count) {
        grid.remove();
        // 사진이 하나도 없으면 안내 글 앞에 종목 그림(다시 찾기로 사진이 오면 load 가 panel 을 비우며 그림도 지운다).
        // 그림 설명이 '이 가게 사진 아님'을 말하므로 서버의 긴 까닭 문장은 숨기고 '네이버 지도에서 사진 보기 ↗'만 남긴다(화면 읽기 프로그램에도 숨김).
        if (sport) {
          status.before(leisureSportArt(sport));
          status.hidden = true;
        }
      }
      // 서버가 '다시 불러와도 같다'고 알린 경우(photo_retry===false: 자료에 사진이 없다고 확정)에는 다시 찾기 단추를 두지 않는다(place-photos.js 와 같은 규칙).
      if (count < 2) panel.append(...(data.photo_retry === false ? [] : [button('사진 다시 찾기', () => load(true), 'secondary leisure-photo-retry')]), data.map_url ? photoMapLink(place) : link('네이버에서 사진 보기 ↗', data.search_url || 'https://search.naver.com/search.naver?where=image&query=' + encodeURIComponent(placeSearchQuery(place))));
    } catch {
      panel.replaceChildren(...(sport ? [leisureSportArt(sport)] : []), node('p', '사진을 불러오지 못했어요.', 'hint'), button('사진 다시 찾기', () => load(true), 'secondary leisure-photo-retry'));
    } finally {
      busy = false;
      panel.setAttribute('aria-busy', 'false');
    }
  }
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) {
        observer.disconnect();
        load();
      }
    }, {
      rootMargin: '150px'
    });
    observer.observe(panel);
  } else requestAnimationFrame(() => load());
  return panel;
}
