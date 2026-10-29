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
  async function load() {
    if (panel.getAttribute('aria-busy') === 'true') return;
    content.replaceChildren(node('p', '코스 주변의 클라이밍·볼링 등 스포츠 장소를 찾고 있어요…', 'hint'));
    panel.setAttribute('aria-busy', 'true');
    try {
      const data = await api('/plans/' + plan.id + '/leisure-options', {
        index,
        locked: [...locks]
      });
      if (!panel.isConnected || selected?.id !== plan.id) return;
      content.replaceChildren(node('p', data.message, 'hint'));
      for (const row of data.options) {
        const place = row.place,
          card = node('article', undefined, 'leisure-result-card');
        card.append(node('strong', place.name), node('p', `${place.description||place.category} · 현재 장소에서 직선 ${row.distance_m}m`, 'hint'), node('p', `교체 시 전체 소요 시간 ${row.delta.minutes>=0?'+':''}${row.delta.minutes}분 · 비용 변화 ${range(row.delta.cost)}`, 'hint'));
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
        actions.append(select, link('지도에서 확인 ↗', 'https://map.naver.com/p/search/' + encodeURIComponent(placeSearchQuery(place))));
        card.append(actions);
        content.append(card);
      }
      if (!data.options.length) {
        const diagnostics = data.diagnostics || {};
        const message = diagnostics.search_status === 'permission_required' ? '네이버 지역 검색 권한을 확인하지 못했어요. API 사용 설정을 확인해 주세요.' : diagnostics.search_status === 'unavailable' ? '실제 지역 검색을 사용할 수 없어요. 네이버 검색 키와 연결 상태를 확인해 주세요.' : diagnostics.nearby_count ? '주변 스포츠 장소는 찾았지만 시간·예산·필수 조건 때문에 현재 일정에 넣을 수 없어요.' : '반경 1.5km에서 현재 일정에 넣을 수 있는 스포츠 후보를 찾지 못했어요. 다른 코스 위치에서도 확인해 보세요.';
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
