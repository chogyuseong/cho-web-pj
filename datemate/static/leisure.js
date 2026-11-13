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
    card.append(node('strong', place.name), node('p', leisureSportText(sport), 'leisure-sport-tag'), node('p', `${place.description||place.category} · 현재 장소에서 직선 ${leisureDistance(row.distance_m)}`, 'hint'), node('p', `교체 시 전체 소요 시간 ${row.delta.minutes>=0?'+':''}${row.delta.minutes}분 · ${costChangeText(row.delta.total_before, row.total)}`, 'hint'));
    const actions = node('div', undefined, 'actions');
    const select = button('이 레저로 교체', async () => {
      if (selected?.id !== plan.id) {
        toast('선택한 코스가 바뀌었어요. 현재 코스에서 다시 골라주세요.');
        return;
      }
      if (selecting) return;
      selecting = true;
      const controls = [...content.querySelectorAll('button')];
      controls.forEach(b => b.disabled = true);
      try {
        const updated = await api('/plans/' + plan.id + '/leisure-select', {
          index,
          locked: [...locks],
          replacement_id: place.id
        });
        if (commitPlanChange(plan.id, updated)) toast('선택한 레저로 교체하고 시간·비용·지도를 다시 계산했어요.');
      } catch (error) {
        toast(error.message);
      } finally {
        selecting = false;
        controls.forEach(b => b.disabled = false);
      }
    }, 'primary');
    select.disabled = plan.can_edit === false || locks.has(index);
    actions.append(select, placeMapLink('지도에서 확인 ↗', place));
    card.append(leisurePhotoPanel(place, plan.conditions.mode), actions);
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
        const message = diagnostics.search_status === 'permission_required' ? '네이버 지역 검색 권한을 확인하지 못했어요. API 사용 설정을 확인해 주세요.' : diagnostics.search_status === 'unavailable' ? '실제 지역 검색을 사용할 수 없어요. 네이버 검색 키와 연결 상태를 확인해 주세요.' : diagnostics.nearby_count ? '주변 레저 장소는 찾았지만 시간·예산·필수 조건 때문에 현재 일정에 넣을 수 없어요.' : '현재 일정에 넣을 수 있는 레저 후보를 찾지 못했어요. 다른 코스 위치에서도 확인해 보세요.';
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


function leisurePhotoPanel(place, photoMode) {
  const panel = node('section', undefined, 'leisure-photo-panel');
  panel.setAttribute('aria-label', place.name + ' 사진 최대 2장');
  if (place.demo || photoMode === 'demo') {
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
          await loadSafePhoto(slot.image, [photo], (selectedPhoto, url) => {
            if (!panel.isConnected || displayed.has(url)) return;
            displayed.add(url);
            slot.loaded = true;
            slot.image.alt = place.name + ' 사진 ' + (slot.index + 1);
            const original = link('', url);
            original.setAttribute('aria-label', place.name + ' 사진 ' + (slot.index + 1) + ' 크게 보기');
            original.append(slot.image);
            const credit = node('figcaption');
            if (['search_result', 'place_public'].includes(photo.kind)) {
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
          });
          if (slot.loaded) break;
        }
      }));
    }
    try {
      if (force) {
        for (const photo of lastPhotos)
          for (const url of photoCandidates(photo)) photoLoads.delete(url);
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
      if (!count) grid.remove();
      if (count < 2) panel.append(button('사진 다시 찾기', () => load(true), 'secondary leisure-photo-retry'), link('네이버에서 사진 보기 ↗', data.search_url || 'https://search.naver.com/search.naver?where=image&query=' + encodeURIComponent(placeSearchQuery(place))));
    } catch {
      panel.replaceChildren(node('p', '사진을 불러오지 못했어요.', 'hint'), button('사진 다시 찾기', () => load(true), 'secondary leisure-photo-retry'));
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
