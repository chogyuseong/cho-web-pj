'use strict';
const $ = s => document.querySelector(s),
  form = $('#conditions');
let statusData, plans = [],
  selected = null,
  locks = new Set(),
  mode = 'real';

function showPlannerPage(results, navigate = true) {
  document.body.classList.toggle('show-date-plan', results);
  document.querySelector('.results-area').hidden = !results;
  document.querySelector('.conditions.panel').hidden = results;
  if (navigate) {
    location.hash = results ? 'date-plan' : 'planner-section';
  }
  requestAnimationFrame(() => {
    const heading = document.querySelector(results ? '.results-area .section-heading h2' : '.conditions .section-heading h2');
    heading.tabIndex = -1;
    heading.focus({
      preventScroll: true
    });
    document.getElementById('planner-section').scrollIntoView({
      block: 'start'
    });
  });
}
window.addEventListener('hashchange', () => {
  if (location.hash === '#explore-section') {
    setTab(true);
    search().catch(e => toast(e.message));
  } else if (location.hash === '#date-plan') {
    setTab(false);
    showPlannerPage(true, false);
  } else if (['#curation', '#inspiration'].includes(location.hash)) {
    navigateHomeSection(location.hash, false);
  } else if (location.hash === '#planner-section' || !location.hash) {
    setTab(false);
    showPlannerPage(false, false);
  }
});
const won = n => n == null ? '미확인' : Number(n).toLocaleString('ko-KR') + '원';
const range = v => v == null ? '미확인' : v[0] === v[1] ? won(v[0]) : won(v[0]) + ' ~ ' + won(v[1]);
const node = (tag, text, cls) => {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (cls) n.className = cls;
  return n;
};

function button(text, action, cls = 'secondary') {
  const b = node('button', text, cls);
  b.type = 'button';
  b.addEventListener('click', () => Promise.resolve().then(action).catch(error => toast(error.message)));
  return b;
}

function searchQueryAddressOnly(value) {
  const text = String(value || '').normalize('NFKC').replace(/\s+/g, ' ').trim().replace(/((?:대로|로))\s+(\d+(?:번)?길)/g, '$1$2');
  const road = text.match(/[가-힣A-Za-z0-9·.]+(?:대로|로|길)\s*\d+(?:-\d+)?/);
  return road ? text.slice(0, road.index + road[0].length).trim() : text;
}

function placeSearchQuery(place) {
  return searchQueryAddressOnly(place.name + ' ' + (place.address || ''));
}

function normalizeLink(raw) {
  if (typeof raw !== 'string' || !raw.trim()) return null;
  let value = raw.trim().replace(/&amp;/gi, '&');
  if (/^www\./i.test(value)) value = 'https://' + value;
  try {
    const u = new URL(value, location.origin);
    if (u.username || u.password) return null;
    if (u.protocol === 'nmap:') return 'https://map.naver.com/p/search/' + encodeURIComponent(u.searchParams.get('dname') || '서울');
    if (!['http:', 'https:'].includes(u.protocol)) return null;
    if (u.origin === location.origin && /^\/api\/plans\/[a-zA-Z0-9_-]+$/.test(u.pathname)) return '/?plan=' + encodeURIComponent(u.pathname.split('/').at(-1));
    if (['blog.naver.com', 'm.blog.naver.com'].includes(u.hostname) && /PostView\.naver$/i.test(u.pathname)) {
      const blog = u.searchParams.get('blogId'),
        post = u.searchParams.get('logNo');
      if (blog && /^\d+$/.test(post || '')) return 'https://blog.naver.com/' + encodeURIComponent(blog) + '/' + post;
    }
    if (u.hostname === 'map.naver.com' && u.pathname.startsWith('/p/search/')) {
      const query = decodeURIComponent(u.pathname.slice('/p/search/'.length));
      u.pathname = '/p/search/' + encodeURIComponent(searchQueryAddressOnly(query));
    }
    if (['search.naver.com', 'm.search.naver.com'].includes(u.hostname) && u.searchParams.has('query')) u.searchParams.set('query', searchQueryAddressOnly(u.searchParams.get('query')));
    return u.href;
  } catch {
    return null;
  }
}

function link(text, url) {
  const href = normalizeLink(url);
  if (!href) return node('span', text || '출처 주소 없음');
  const a = node('a', text);
  a.href = href;
  a.target = '_blank';
  a.rel = 'noopener noreferrer';
  return a;
}

function sourceLinks(text, url, query) {
  const wrap = node('span', undefined, 'source-link-options');
  wrap.append(link(text, url));
  if (query) {
    const fallback = link('원문이 안 열리면 검색 ↗', 'https://search.naver.com/search.naver?query=' + encodeURIComponent(query));
    fallback.className = 'source-search-fallback';
    wrap.append(fallback);
  }
  return wrap;
}

function linkedText(tag, text, cls) {
  const root = node(tag, undefined, cls),
    value = String(text || '');
  const pattern = /https?:\/\/[^\s<>"'`]+/gi;
  let offset = 0;
  for (const match of value.matchAll(pattern)) {
    let url = match[0].replace(/[.,;!]+$/, '');
    for (const [open, close] of [
        ['(', ')'],
        ['[', ']'],
        ['{', '}']
      ]) {
      while (url.endsWith(close) && url.split(close).length > url.split(open).length) url = url.slice(0, -1);
    }
    root.append(document.createTextNode(value.slice(offset, match.index)), sourceLinks(url, url, url));
    offset = match.index + url.length;
  }
  root.append(document.createTextNode(value.slice(offset)));
  return root;
}

function toast(text) {
  $('#toast').textContent = text;
  $('#toast').style.display = 'block';
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => $('#toast').style.display = 'none', 6500);
}

function today() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}
form.elements.visit_date.value = today();

function values() {
  const f = new FormData(form),
    number = k => Number(f.get(k));
  const data = {
    course_query: f.get('course_query') || '',
    mode: f.get('mode'),
    allow_price_estimates: f.has('allow_price_estimates'),
    allow_estimates: f.has('allow_estimates'),
    stay_minutes: number('stay_minutes'),
    region: f.get('region'),
    origin: selectedLocation('origin'),
    visit_date: f.get('visit_date'),
    start: f.get('start'),
    end: f.get('end'),
    people: number('people'),
    budget: number('budget'),
    transport: f.get('transport'),
    count: number('count'),
    themes: f.getAll('themes'),
    date_category: f.get('date_category') || '',
    date_subcategory: f.get('date_subcategory') || '',
    theme_mode: f.get('theme_mode'),
    setting: f.get('setting'),
    avoid: f.get('avoid').split(',').map(x => x.trim()).filter(Boolean),
    reservation: f.has('reservation'),
    max_leg: number('max_leg'),
    max_walk: f.get('max_walk') === '' ? null : number('max_walk'),
    return_home: f.has('return_home'),
    home: null,
    mbti: f.get('mbti').toUpperCase(),
    use_mbti: f.has('use_mbti'),
    request: f.get('request'),
    locked: {}
  };
  data.include_meal = f.has('include_meal');
  data.transition_buffer_minutes = Number(f.get('transition_buffer_minutes') || 0);
  data.neighborhood_radius_km = Number(f.get('neighborhood_radius_km') || 2.5);
  updateExperienceValues(data, f);
  if (data.return_home) data.home = selectedLocation('home');
  if (selected && selected.conditions.mode === data.mode)
    for (const i of locks) data.locked[i] = selected.places[i].id;
  return data;
}
async function init() {
  try {
    statusData = await api('/status');
    $('#status').textContent = `서울 전용 · 가상 장소 ${statusData.counts.demo.places}건 · 실제 장소 메타데이터 ${statusData.counts.real.places}건 / 색인 ${statusData.counts.real.indexed}건 · ${statusData.llm} · ${statusData.embedding==='demo'?'문자 해시 임베딩 데모 (의미 검색 아님)':'의미 임베딩 설정'} · 실제 운영정보 확인 필요`;
    for (const theme of statusData.themes) {
      const l = node('label'),
        i = node('input');
      i.type = 'checkbox';
      i.name = 'themes';
      i.value = theme;
      l.append(i, node('span', theme));
      $('#themes').append(l);
    }
    form.elements.region.value = statusData.region;
    mountDateCategories(statusData.date_categories);
    const id = new URLSearchParams(location.search).get('plan');
    if (id) {
      selected = await api('/plans/' + encodeURIComponent(id));
      mode = selected.conditions.mode;
      locks = new Set(Object.keys(selected.conditions.locked || {}).map(Number));
      form.elements.count.value = selected.conditions.count;
      plans = [selected];
      renderResults();
      renderDetail();
      showPlannerPage(true);
    }
    if (location.hash === '#explore-section') {
      setTab(true);
      await search();
    } else if (['#curation', '#inspiration'].includes(location.hash)) {
      navigateHomeSection(location.hash, false);
    } else await resumePlanSearch();
  } catch (e) {
    $('#status').textContent = e.message;
  }
}
let parsedRequest = '';
async function applyRequest() {
  const text = form.elements.request.value.trim();
  const people = Number(form.elements.people.value);
  const signature = JSON.stringify([text, people, FormState.edited.has('people')]);
  if (!text || signature === parsedRequest) return;
  const result = await api('/conditions/parse', {
    text,
    people,
    explicit_people: FormState.edited.has('people')
  });
  for (const [key, value] of Object.entries(result.patch)) {
    if (FormState.edited.has(key)) continue;
    if (key === 'themes') {
      if (!FormState.edited.has('date_subcategory')) setDateClassification('콘셉트별', '');
      document.querySelectorAll('[name=themes]').forEach(c => c.checked = value.includes(c.value));
    } else if (form.elements[key]) {
      if (form.elements[key].type === 'checkbox') form.elements[key].checked = Boolean(value);
      else form.elements[key].value = value;
    }
  }
  $('#parse-notice').textContent = result.warnings.join(' ') + ' 직접 수정한 조건은 유지해요.';
  parsedRequest = JSON.stringify([text, Number(form.elements.people.value), FormState.edited.has('people')]);
}
$('#parse').onclick = () => applyRequest().then(() => toast('해석된 조건을 폼에서 확인하고 수정해 주세요.')).catch(e => toast(e.message));

function beginPlanSearch() {
  plans = [];
  selected = null;
  locks.clear();
  const detail = $('#plan-detail');
  detail.replaceChildren();
  $('#results').replaceChildren(detail);
  renderPlanMapCard();
  $('#results').setAttribute('aria-busy', 'true');
  $('#result-count').textContent = '새 코스를 찾고 있어요';
  const progress = $('#progress');
  progress.classList.add('is-searching');
  const icon = node('span', undefined, 'search-spinner');
  icon.setAttribute('aria-hidden', 'true');
  const copy = node('div', undefined, 'search-progress-copy');
  copy.append(node('strong', '우리에게 맞는 코스를 찾고 있어요'), node('p', '조건 확인 → 코스 탐색 → 실시간 단가 검색·비용 계산 중…'), node('small', '검색을 진행 중이에요. 결과가 준비되면 여기에 보여드릴게요.'));
  progress.replaceChildren(icon, copy, button('검색 취소', async () => {
    await PlanSearch.cancel();
    showPlannerPage(false);
  }));
}
form.addEventListener('submit', async e => {
  e.preventDefault();
  const submit = $('#submit-plan');
  if (submit.disabled) return;
  try {
    submit.disabled = true;
    await applyRequest();
    if (!form.reportValidity()) return;
    const data = values();
    data.explicit_fields = [...FormState.edited];
    await PlanningStudy.prepare(data);
    mode = data.mode;
    beginPlanSearch();
    setTab(false);
    showPlannerPage(true);
    $('#progress').append(node('p', '적용 조건: ' + FormState.summary(data), 'applied-conditions'));
    const result = await createPlanWithProgress(data);
    plans = result.plans;
    selected = plans[0] || null;
    renderResults(result);
    renderDetail();
    $('#progress').textContent = plans.length ? `추천 완료 · ${plans.length}개의 일정` : (result.reasons?.[0] || '추천 조건을 확인해 주세요.');
    if (window.innerWidth < 720) $('#results').scrollIntoView({
      behavior: 'smooth'
    });
  } catch (error) {
    toast(error.message);
    showSearchFailure(error);
  } finally {
    submit.disabled = false;
    $('#progress').classList.remove('is-searching');
    $('#results').setAttribute('aria-busy', 'false');
  }
});
form.elements.mode.addEventListener('change', () => {
  selected = null;
  locks.clear();
  plans = [];
  mode = form.elements.mode.value;
  clearLocationsForMode();
  $('#mode-badge').textContent = mode === 'demo' ? 'DEMO SPACE' : 'REAL DATA';
  renderResults();
  renderDetail();
});


$('#close-dialog').onclick = () => $('#dialog').close();
$('#dialog').addEventListener('click', e => {
  if (e.target === $('#dialog')) $('#dialog').close();
});

function setTab(explore) {
  document.body.classList.toggle('show-explore', explore);
  document.body.classList.remove('show-date-plan');
  if (!explore) showPlannerPage(false, false);
  $('#planner-section').hidden = explore;
  $('#explore-section').hidden = !explore;
  $('#nav-plan').classList.toggle('active', !explore);
  $('#nav-explore').classList.toggle('active', explore);
  if (explore) {
    if (location.hash !== '#explore-section') history.pushState(null, '', '#explore-section');
    requestAnimationFrame(() => {
      const section = $('#explore-section'),
        heading = section.querySelector('h2');
      heading.tabIndex = -1;
      heading.focus({
        preventScroll: true
      });
      section.scrollIntoView({
        block: 'start',
        behavior: 'auto'
      });
    });
  }
}
$('#nav-explore').onclick = () => {
  setTab(true);
  search().catch(e => toast(e.message));
};
async function search() {
  return ExploreView.search();
}
$('#search-button').onclick = () => search().catch(e => toast(e.message));
$('#search').addEventListener('keydown', e => {
  if (e.key === 'Enter') search().catch(e => toast(e.message));
});
mountLocationFields();
mountPriceControls();
init();

$('#edit-conditions').onclick = () => {
  setTab(false);
  showPlannerPage(false);
};


// Reveal the destination screen before scrolling, including repeated anchor clicks.
function navigateHomeSection(hash, updateHistory = true) {
  if (!['#planner-section', '#curation', '#inspiration'].includes(hash)) return;
  setTab(false);
  if (updateHistory && location.hash !== hash) history.pushState(null, '', hash);
  requestAnimationFrame(() => {
    const section = document.querySelector(hash);
    if (!section) return;
    const heading = section.querySelector('h2') || section;
    heading.tabIndex = -1;
    heading.focus({
      preventScroll: true
    });
    section.scrollIntoView({
      block: 'start',
      behavior: 'instant'
    });
  });
}
document.addEventListener('click', event => {
  const anchor = event.target.closest('a[href]');
  if (!anchor || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
  const hash = anchor.getAttribute('href');
  if (['#planner-section', '#curation', '#inspiration'].includes(hash)) {
    event.preventDefault();
    navigateHomeSection(hash);
  }
});
$('#nav-plan').onclick = () => navigateHomeSection('#planner-section');
