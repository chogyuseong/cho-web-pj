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
  } else if (location.hash === '#curation') {
    navigateHomeSection(location.hash, false);
  } else if (location.hash === '#planner-section' || !location.hash) {
    setTab(false);
    showPlannerPage(false, false);
  }
});
const won = n => n == null ? '미확인' : Number(n).toLocaleString('ko-KR') + '원';
const range = v => v == null ? '미확인' : v[0] === v[1] ? won(v[0]) : won(v[0]) + ' ~ ' + won(v[1]);
// 바꾸기 전·후의 예상 비용 범위를 나란히 보여 준다. 범위끼리의 차이(음수~양수)는 내지 않는다.
function costChangeText(before, after) {
  const known = v => Array.isArray(v) && v.length === 2 && v.every(n => n != null);
  if (!known(before) || !known(after)) return '예상 비용 ' + range(after);
  const low = after[0] - before[0],
    high = after[1] - before[1];
  if (!low && !high) return '비용은 그대로예요 · 예상 비용 ' + range(after);
  const text = `예상 비용 ${range(before)} → ${range(after)}`;
  return low === high ? `${text} · 약 ${won(Math.abs(low))} ${low > 0 ? '늘어요' : '줄어요'}` : text;
}
// 바꾸기 전 범위. 예전에 저장한 코스는 total_before 가 없어 cost(범위끼리의 차이: [후 최소−전 최대, 후 최대−전 최소])에서 되짚는다.
function totalBefore(plan) {
  const delta = plan.delta || {};
  if (Array.isArray(delta.total_before)) return delta.total_before;
  if (plan.parent && Array.isArray(delta.cost) && Array.isArray(plan.total)) return [plan.total[1] - delta.cost[1], plan.total[0] - delta.cost[0]];
  return null;
}
// 예산 무관으로 만든 코스. 서버가 이 필드를 싣지 않은 예전 코스는 기존처럼 예산과 비교해 보여 준다.
const budgetUnlimited = plan => plan?.conditions?.budget_unlimited === true;
// 장소 종류 이름. 식당(meal)은 '식사', 그 밖의 카페·미식은 '카페'로 나눠 부른다(코스 카드의 구성 이름과 같은 기준, 서버 option_diversity.place_group).
function placeKind(place) {
  if (place.meal || String(place.id || '').startsWith('food:')) return '식사';
  return place.category === '카페·미식' ? '카페' : place.category;
}
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

function cleanPlaceText(value) {
  return String(value || '').normalize('NFKC').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
}

function streetAddressText(value) {
  const text = cleanPlaceText(value).replace(/((?:대로|로))\s+(\d+(?:번)?길)/g, '$1$2');
  const road = text.match(/[가-힣A-Za-z0-9·.]+(?:대로|로|길)\s*\d+(?:-\d+)?(?=\s|$|[,(])/);
  if (road) return text.slice(0, road.index + road[0].length).trim();
  const lot = text.match(/(?:동|가|리)\s+(?:산\s*)?\d+(?:-\d+)?(?=\s|$|[,(])/);
  if (lot) return text.slice(0, lot.index + lot[0].length).trim();
  const district = text.match(/(?:서울특별시|서울시|서울)\s+[가-힣]+구/);
  return district ? district[0] : '';
}

function addressStart(text) {
  const city = text.match(/(?:^|\s)(?:서울특별시|서울시|서울)\s+/);
  if (city) return city.index + (text[city.index] === ' ' ? 1 : 0);
  const district = text.match(/(?:^|\s)[가-힣]+구\s+/);
  return district ? district.index + (text[district.index] === ' ' ? 1 : 0) : -1;
}

function searchQueryAddressOnly(value) {
  const text = cleanPlaceText(value),
    start = addressStart(text);
  if (start < 0) return text;
  const address = streetAddressText(text.slice(start));
  return address && /\d/.test(address) ? [text.slice(0, start).trim(), address].filter(Boolean).join(' ') : text;
}

function placeSearchQuery(place) {
  return [cleanPlaceText(place.name), streetAddressText(place.address)].filter(Boolean).join(' ');
}

// app/regions.py 의 REGIONS 와 같은 시·도 별칭 표
const REGION_ALIASES = Object.fromEntries(Object.entries({
  서울: ['서울시', '서울특별시'],
  부산: ['부산시', '부산광역시'],
  대구: ['대구시', '대구광역시'],
  인천: ['인천시', '인천광역시'],
  광주: ['광주시', '광주광역시'],
  대전: ['대전시', '대전광역시'],
  울산: ['울산시', '울산광역시'],
  세종: ['세종시', '세종특별자치시'],
  경기: ['경기도'],
  강원: ['강원도', '강원특별자치도'],
  충북: ['충청북도'],
  충남: ['충청남도'],
  전북: ['전라북도', '전북특별자치도'],
  전남: ['전라남도'],
  경북: ['경상북도'],
  경남: ['경상남도'],
  제주: ['제주도', '제주특별자치도'],
}).flatMap(([region, names]) => [region, ...names].map(alias => [alias, region])));

function regionFromAddress(address) {
  return REGION_ALIASES[String(address || '').trim().split(' ')[0]] || null;
}

function placeMapQuery(place) {
  const name = cleanPlaceText(place.name),
    address = cleanPlaceText(place.address);
  const district = address.match(/(?:^|\s)([가-힣]+구)(?=\s|$)/);
  // 지역 정보가 전혀 없는 장소는 기존 서울 수집 자료뿐이므로 서울로 본다.
  const region = REGION_ALIASES[place.region] || regionFromAddress(address) || '서울';
  return [region, district?.[1], name].filter(Boolean).join(' ');
}

const verifiedMapTargets = new Map();

function placeMapUrl(place) {
  const id = place.naver_place_id_verified === true ? String(place.naver_place_id || '') : '';
  if (/^\d+$/.test(id)) return 'https://map.naver.com/p/entry/place/' + id;
  return verifiedMapTargets.get(place.id) || 'https://map.naver.com/p/search/' + encodeURIComponent(placeMapQuery(place));
}

function placeMapLink(label, place) {
  const anchor = link(label, placeMapUrl(place));
  anchor.dataset.mapPlaceId = place.id;
  anchor.title = placeMapQuery(place) + ' · 새 탭에서 지도 열기';
  return anchor;
}

function rememberVerifiedMapTarget(place, data) {
  if (data.place_id && data.place_id !== place.id) return;
  // 공공 자료(상가정보·인허가)로 본 같은 업체 판정(app/place_identity.py)을 '위치' 줄에 넘긴다. 지도 링크는 그대로(업체 번호가 없음).
  if (data.identity && typeof markIdentity === 'function') markIdentity(place, data.identity);
  // 한국관광공사 영업 안내가 있으면 '영업 정보' 줄에 덧붙인다(plan-evidence.js markTourHours).
  if (data.tour_hours && typeof markTourHours === 'function') markTourHours(place.id, data.tour_hours);
  const id = String(data.naver_place_id || '');
  if (data.naver_place_id_verified !== true || !/^\d+$/.test(id)) return;
  const url = 'https://map.naver.com/p/entry/place/' + id;
  verifiedMapTargets.set(place.id, url);
  for (const anchor of document.querySelectorAll('a[data-map-place-id]')) {
    if (anchor.dataset.mapPlaceId === place.id) anchor.href = url;
  }
}

function normalizeMapQuery(value) {
  const text = cleanPlaceText(value),
    start = addressStart(text);
  if (start > 0) return placeMapQuery({
    name: text.slice(0, start).trim(),
    address: text.slice(start)
  });
  return text;
}

function normalizeLink(raw) {
  if (typeof raw !== 'string' || !raw.trim()) return null;
  let value = raw.trim().replace(/&amp;/gi, '&');
  if (/^www\./i.test(value)) value = 'https://' + value;
  try {
    const u = new URL(value, location.origin);
    if (u.username || u.password) return null;
    if (u.protocol === 'nmap:') return 'https://map.naver.com/p/search/' + encodeURIComponent(normalizeMapQuery(u.searchParams.get('dname') || '서울'));
    if (!['http:', 'https:'].includes(u.protocol)) return null;
    if (u.origin === location.origin && /^\/api\/plans\/[a-zA-Z0-9_-]+$/.test(u.pathname)) return '/?plan=' + encodeURIComponent(u.pathname.split('/').at(-1));
    if (['blog.naver.com', 'm.blog.naver.com'].includes(u.hostname) && /PostView\.naver$/i.test(u.pathname)) {
      const blog = u.searchParams.get('blogId'),
        post = u.searchParams.get('logNo');
      if (blog && /^\d+$/.test(post || '')) return 'https://blog.naver.com/' + encodeURIComponent(blog) + '/' + post;
    }
    if (u.hostname === 'map.naver.com' && u.pathname.startsWith('/p/search/')) {
      const query = decodeURIComponent(u.pathname.slice('/p/search/'.length));
      u.pathname = '/p/search/' + encodeURIComponent(normalizeMapQuery(query));
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

// 주소 문자열 대신 목적이 드러나는 이름으로 링크를 보여준다. 인쇄할 때는 CSS가 주소를 덧붙인다.
function sourceLinkLabel(url) {
  let host = '';
  try {
    host = new URL(normalizeLink(url) || '').hostname.replace(/^(?:www|m)\./, '');
  } catch {}
  if (host === 'map.naver.com') return '네이버 지도에서 보기 ↗';
  if (host === 'blog.naver.com' || host.endsWith('.tistory.com') || host === 'brunch.co.kr') return '블로그 글 보기 ↗';
  if (host === 'search.naver.com') return '네이버 검색 결과 보기 ↗';
  if (host.endsWith('visitkorea.or.kr')) return '한국관광공사 자료 보기 ↗';
  if (host.endsWith('wikipedia.org')) return '위키백과 보기 ↗';
  return '출처 보기 ↗';
}

function namedSourceLinks(url, query, prefix = '') {
  const wrap = sourceLinks(prefix + sourceLinkLabel(url), url, query);
  const anchor = wrap.querySelector('a');
  if (anchor) {
    anchor.classList.add('source-url-link');
    anchor.title = anchor.href;
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
    root.append(document.createTextNode(value.slice(offset, match.index)), namedSourceLinks(url, url));
    offset = match.index + url.length;
  }
  root.append(document.createTextNode(value.slice(offset)));
  return root;
}

function toast(text) {
  const el = $('#toast');
  // showModal() 로 연 대화상자는 최상위 층이고 바깥은 비활성(inert)이라 body 의 토스트가 그 뒤에 가려지고 읽히지도 않는다.
  // 열린 모달이 있으면 토스트를 그 안으로 옮기고, 대화상자가 닫히면 body 로 되돌린다.
  let host = document.body;
  for (const dialog of document.querySelectorAll('dialog[open]')) {
    try {
      if (dialog.matches(':modal')) host = dialog;
    } catch {}
  }
  if (el.parentElement !== host) {
    host.append(el);
    if (host !== document.body) host.addEventListener('close', () => document.body.append(el), {
      once: true
    });
  }
  el.textContent = text;
  $('#toast').style.display = 'block';
  // 읽을 시간: 글 길이에 맞춰 6.5~15초(한 글자 약 0.15초). 마우스를 올리거나 포커스가 있는 동안은 닫지 않는다(WCAG 2.2.1, 2026-11-17).
  toast.wait = Math.min(15000, Math.max(6500, String(text).length * 150));
  toast.schedule();
}
toast.schedule = function(wait = toast.wait || 6500) {
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => {
    const el = $('#toast');
    if (el.matches(':hover') || el.contains(document.activeElement)) return toast.schedule(2000);
    el.style.display = 'none';
  }, wait);
};

function today() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}
form.elements.visit_date.value = today();
// 방문 날짜 칸의 가장 이른 날 = 오늘(한국 날짜, 2026-11-25 운영 QA-12). 서버의 지난 날짜 검사(app/service_time.past_visit_message)와 같은
// 시계를 쓰도록 /api/status 의 today 를 받는다(브라우저 시간대와 무관). 지금 값이 그보다 이르면(한국보다 늦은 시간대) 그날로 맞춘다.
function applyVisitDateMin(day) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(day || ''))) return;
  const input = form.elements.visit_date;
  input.min = day;
  if (input.value && input.value < day) input.value = day;
}
// 서버가 준 시각 글(ISO, 대개 UTC)을 한국 시각 'YYYY-MM-DD HH:MM' 으로(2026-11-25 운영 QA-09). 날짜만 있거나 읽을 수 없는 글은 그대로 둔다.
const KOREA_TIME = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Seoul',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23'
});

function koreaTimeText(value) {
  const text = String(value ?? '').trim();
  if (!/^\d{4}-\d{2}-\d{2}T/.test(text)) return text;
  const at = new Date(text);
  if (Number.isNaN(at.getTime())) return text;
  const part = Object.fromEntries(KOREA_TIME.formatToParts(at).map(p => [p.type, p.value]));
  return `${part.year}-${part.month}-${part.day} ${part.hour}:${part.minute}`;
}

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
    // 예산 무관이면 서버가 budget 숫자를 쓰지 않는다.
    budget_unlimited: f.has('budget_unlimited'),
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
  // ‘이렇게 이해했어요’에서 뺀 조건. 서버가 같은 글을 다시 해석할 때도 빼고 쓴다.
  const ignored = typeof RequestUnderstanding === 'undefined' || !String(data.request || '').trim() ? [] : RequestUnderstanding.requestIgnore();
  if (ignored.length) data.request_ignore = ignored;
  data.include_meal = f.has('include_meal');
  data.transition_buffer_minutes = Number(f.get('transition_buffer_minutes') || 0);
  data.neighborhood_radius_km = Number(f.get('neighborhood_radius_km') || 2.5);
  updateExperienceValues(data, f);
  if (data.return_home) data.home = selectedLocation('home');
  // 결과 화면에서 고른 축제가 지금 출발지라면 축제 기준 코스로 요청한다.
  data.festival = FestivalPanel.anchorFor(data);
  if (selected && selected.conditions.mode === data.mode)
    for (const i of locks) data.locked[i] = selected.places[i].id;
  // 둘러보기에서 「이 장소 포함해서 코스 짜기」로 고른 장소(explore.js includePlace, 2026-11-24 UX P2)를 비어 있는 첫 자리에 고정한다.
  // 서버는 고정한 장소가 후보에 없으면 둘러보기 보관분에서 찾아 넣는다(app/quality.py pool). 체험 코스(가상 장소)에는 넣지 않는다.
  if (typeof includedPlace !== 'undefined' && includedPlace && data.mode === 'real' && !Object.values(data.locked).includes(includedPlace.id)) {
    let slot = 0;
    while (slot in data.locked) slot += 1;
    if (slot < data.count) data.locked[slot] = includedPlace.id;
  }
  return data;
}
async function init() {
  try {
    // 잠든 서버가 켜지는 동안에는 다시 물으며 안내를 보여 준다(server-wake.js).
    statusData = await ServerWake.load(timeout => api('/status', null, 'GET', {
      timeout
    }));
    // 정상일 때는 서비스 상태를 보여 주지 않는다(2026-11-24 UX P0 — 예전에는 장소 수·색인·키 상태 같은 내부 정보를 적었다).
    // 공공 장소 자료 키가 없을 때만 친절한 폴백 배너를 띄운다(서버 public_places_available, app/main.py _status). 장애는 아래 catch.
    if (statusData.public_places_available === false) showServiceNotice('현재 실시간 장소 검색을 점검 중이에요. 지금은 서울 체험 코스로 먼저 둘러보실 수 있어요.', true);
    // ?demo=1 로 들어오면 서울 체험 코스(가상 장소)로 시작한다. 일반 첫 화면에는 데모 선택지를 보여 주지 않는다.
    if (new URLSearchParams(location.search).get('demo') === '1') useTourMode();
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
    applyVisitDateMin(statusData.today);
    mountDateCategories(statusData.date_categories);
    // 팝업 둘러보기 전환은 서버 스위치(DATEMATE_POPUPS_ENABLED)가 켜져 있을 때만 그린다.
    if (typeof PopupView !== 'undefined') PopupView.mount(statusData.popups_enabled === true);
    const id = new URLSearchParams(location.search).get('plan');
    if (id) {
      selected = await api('/plans/' + encodeURIComponent(id));
      mode = selected.conditions.mode;
      locks = new Set(Object.keys(selected.conditions.locked || {}).map(Number));
      form.elements.count.value = selected.conditions.count;
      plans = [selected];
      renderResults();
      renderDetail();
      // 저장된 코스를 링크로 열 때도 그 코스의 지역·방문일 축제를 함께 보여 준다.
      try {
        FestivalPanel.restore(selected.conditions);
      } catch {}
      // 팝업 글 구역도 같은 지역·방문일로 따로 조회한다(팝업 거점 선택은 되살리지 않음).
      try {
        if (typeof PopupCourse !== 'undefined') PopupCourse.restore(selected.conditions);
      } catch {}
      showPlannerPage(true);
    }
    if (location.hash === '#explore-section') {
      setTab(true);
      await search();
    } else if (location.hash === '#curation') {
      navigateHomeSection(location.hash, false);
    } else await resumePlanSearch();
  } catch (e) {
    // 장애일 때만 보이는 배너. 서버가 준 사용자용 문장(예: '요청이 많아요…')을 그대로 쓴다.
    showServiceNotice(e.message || '지금 서비스에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.', false);
  }
}

// 첫 화면 맨 위의 서비스 안내 배너(#status, index.html). 정상일 때는 숨어 있다. tour 면 '서울 체험 코스 둘러보기' 단추를 단다.
function showServiceNotice(text, tour) {
  const box = $('#status');
  box.replaceChildren(node('span', text));
  if (tour) box.append(' ', button('서울 체험 코스 둘러보기', () => useTourMode(), 'secondary'));
  box.hidden = false;
}

// 서울 체험 코스(가상 장소, mode=demo)로 바꾼다. ?demo=1, 폴백 배너 단추, 결과가 비었을 때 단추가 부른다.
// 첫 화면에서는 이 선택지를 숨긴다(코스 종류 select 는 숨은 설정 영역에 있다, simple-form.js).
function useTourMode() {
  if (form.elements.mode.value === 'demo') return;
  form.elements.mode.value = 'demo';
  form.elements.mode.dispatchEvent(new Event('change'));
}
let parsedRequest = '';
let pendingRequest = null;
// 자유 입력 해석이 폼에 넣은 값: 이름 → {before, after}. 해석에서 그 조건이 빠지면(칩으로 빼거나 글을 고침)
// 사용자가 그사이 직접 바꾸지 않았을 때만 넣기 전 값으로 되돌린다.
const requestApplied = new Map();
// 해석이 '피할 활동'에 더한 낱말. 직접 적은 낱말은 건드리지 않는다.
const requestAvoid = new Set();
const requestUnderstanding = () => typeof RequestUnderstanding === 'undefined' ? null : RequestUnderstanding;

function requestFieldValue(key) {
  if (key === 'themes') return [...document.querySelectorAll('[name=themes]:checked')].map(c => c.value).join('|');
  if (key === 'date') return form.elements.date_category.value + '|' + (form.elements.date_subcategory?.value || '');
  const input = form.elements[key];
  if (!input) return null;
  return input.type === 'checkbox' ? String(input.checked) : String(input.value);
}

function setRequestField(key, value) {
  if (key === 'themes') {
    const chosen = value ? value.split('|') : [];
    document.querySelectorAll('[name=themes]').forEach(c => c.checked = chosen.includes(c.value));
  } else if (key === 'date') {
    const [category, subcategory] = value.split('|');
    setDateClassification(category, subcategory);
  } else if (form.elements[key].type === 'checkbox') form.elements[key].checked = value === 'true';
  else form.elements[key].value = value;
}

function requestEdited(key) {
  if (key === 'date') return ['date_category', 'date_subcategory', 'themes'].some(name => FormState.edited.has(name));
  return FormState.edited.has(key);
}

function applyRequestPatch(patch) {
  const wanted = new Map();
  for (const [key, value] of Object.entries(patch)) {
    if (key === 'avoid' || key === 'date_category') continue;
    if (key === 'date_subcategory') {
      if (!requestEdited('date')) wanted.set('date', patch.date_category + '|' + value);
      continue;
    }
    if (FormState.edited.has(key) || requestFieldValue(key) === null) continue;
    if (key === 'themes') {
      if (!FormState.edited.has('date_subcategory') && !wanted.has('date')) wanted.set('date', '콘셉트별|');
      wanted.set('themes', value.join('|'));
    } else wanted.set(key, form.elements[key].type === 'checkbox' ? String(Boolean(value)) : String(value));
  }
  for (const [key, record] of [...requestApplied]) {
    if (wanted.has(key)) continue;
    if (!requestEdited(key) && requestFieldValue(key) === record.after) setRequestField(key, record.before);
    requestApplied.delete(key);
  }
  for (const [key, value] of wanted) {
    const before = requestApplied.get(key)?.before ?? requestFieldValue(key);
    setRequestField(key, value);
    requestApplied.set(key, {
      before,
      after: requestFieldValue(key)
    });
  }
  // 글에서 찾은 제외 단어는 직접 적은 '피할 활동'에 더한다. 해석에서 빠진 낱말은 해석이 더한 것만 뺀다.
  const words = patch.avoid || [];
  const typed = form.elements.avoid.value.split(',').map(x => x.trim()).filter(Boolean);
  const current = typed.filter(word => !requestAvoid.has(word) || words.includes(word));
  for (const word of [...requestAvoid])
    if (!words.includes(word)) requestAvoid.delete(word);
  for (const word of words)
    if (!current.includes(word)) {
      current.push(word);
      requestAvoid.add(word);
    }
  if (current.length !== typed.length || current.some((word, i) => word !== typed[i])) form.elements.avoid.value = current.slice(0, 30).join(', ');
}
async function applyRequest() {
  const text = form.elements.request.value.trim();
  const people = Number(form.elements.people.value);
  const view = requestUnderstanding();
  const ignore = view ? view.requestIgnore().sort() : [];
  const signature = JSON.stringify([text, people, FormState.edited.has('people'), ignore]);
  if (signature === parsedRequest) return;
  if (pendingRequest?.signature === signature) return pendingRequest.promise;
  if (!text) {
    applyRequest.turn++;
    applyRequestPatch({});
    view?.clear();
    parsedRequest = signature;
    return;
  }
  const turn = ++applyRequest.turn;
  const promise = (async () => {
    const result = await api('/conditions/parse', {
      text,
      people,
      explicit_people: FormState.edited.has('people'),
      ignore
    });
    // 늦게 도착한 예전 글의 해석은 버린다(칸을 벗어날 때와 칩을 누를 때 두 번 부를 수 있다).
    if (turn !== applyRequest.turn) return;
    applyRequestPatch(result.patch);
    if (view) {
      view.prune(result);
      view.render(result);
    }
    $('#parse-notice').textContent = result.warnings.join(' ') + ' 직접 수정한 조건은 유지해요.';
    parsedRequest = JSON.stringify([text, Number(form.elements.people.value), FormState.edited.has('people'), view ? view.requestIgnore().sort() : []]);
  })();
  pendingRequest = {
    signature,
    promise
  };
  try {
    await promise;
  } finally {
    if (pendingRequest?.promise === promise) pendingRequest = null;
  }
}
applyRequest.turn = 0;
$('#parse').onclick = () => applyRequest().then(() => toast('해석된 조건을 폼에서 확인하고 수정해 주세요.')).catch(e => toast(e.message));
// 글을 다 쓰고 칸을 벗어나면 바로 해석해 ‘이렇게 이해했어요’를 보여 준다(입력 중에는 부르지 않는다).
form.elements.request.addEventListener('change', () => applyRequest().catch(e => toast(e.message)));

function beginPlanSearch() {
  plans = [];
  selected = null;
  locks.clear();
  const detail = $('#plan-detail');
  detail.replaceChildren();
  $('#results').replaceChildren(detail);
  $('#plan-extras')?.replaceChildren();
  renderPlanMapCard();
  $('#results').setAttribute('aria-busy', 'true');
  $('#result-count').textContent = '새 코스를 찾고 있어요';
  const progress = $('#progress');
  progress.classList.add('is-searching');
  const icon = node('span', undefined, 'search-spinner');
  icon.setAttribute('aria-hidden', 'true');
  const copy = node('div', undefined, 'search-progress-copy');
  copy.append(node('strong', '우리에게 맞는 코스를 찾고 있어요'), node('p', '조건 확인 → 코스 탐색 → 비용 계산 중…'), node('small', '검색을 진행 중이에요. 결과가 준비되면 여기에 보여드릴게요.'));
  // 실패 안내의 단추(이어보기·다시 검색)를 연달아 탭하면 두 번째 탭이 같은 자리에 새로 나타난 이 단추를 눌러
  // 방금 시작한 검색을 취소했다(2026-11-19 확인). 나타난 뒤 0.6초 안의 누름은 무시한다.
  const shownAt = performance.now();
  progress.replaceChildren(icon, copy, button('검색 취소', async () => {
    if (performance.now() - shownAt < 600) return;
    await PlanSearch.cancel();
    showPlannerPage(false);
    toast('검색을 취소했어요.');
  }));
}
// 종료 시간이 시작 시간과 같거나 이르면 보내기 전에 막는다. 서버도 같은 규칙으로 거부한다(app/models.py Conditions.valid).
// 2026-11-25 운영 QA-01: 전에는 그대로 보내 422 를 받았다. 종료 칸 바로 아래에 안내를 두고 aria-invalid 로 표시하며,
// 시작·종료를 고치면 다시 확인해 안내를 지운다.
const TIME_RANGE_TEXT = '종료 시간은 시작 시간보다 늦게 골라 주세요.';

function timeRangeInvalid() {
  const {
    start,
    end
  } = form.elements;
  let note = document.getElementById('end-time-error');
  // type=time 값은 'HH:MM' 이라 글자 비교가 곧 시각 비교다.
  const bad = Boolean(start.value && end.value && end.value <= start.value);
  if (!bad) {
    note?.remove();
    end.removeAttribute('aria-invalid');
    if (end.getAttribute('aria-describedby') === 'end-time-error') end.removeAttribute('aria-describedby');
    return false;
  }
  if (!note) {
    note = node('span', TIME_RANGE_TEXT, 'warning field-error');
    note.id = 'end-time-error';
    end.after(note);
  }
  end.setAttribute('aria-invalid', 'true');
  end.setAttribute('aria-describedby', note.id);
  return true;
}
for (const name of ['start', 'end'])
  for (const type of ['input', 'change']) form.elements[name].addEventListener(type, () => {
    if (form.elements.end.hasAttribute('aria-invalid')) timeRangeInvalid();
  });
form.addEventListener('submit', async e => {
  e.preventDefault();
  const submit = $('#submit-plan');
  if (submit.disabled) return;
  try {
    submit.disabled = true;
    // 서버가 아직 켜지는 중이면 실패로 끝내지 않고 준비될 때까지 기다렸다가 이어 간다.
    if (ServerWake.waiting) {
      toast('서버를 준비하고 있어요. 준비되면 바로 코스를 찾을게요.');
      await ServerWake.ready();
    }
    await applyRequest();
    if (!form.reportValidity()) return;
    if (timeRangeInvalid()) {
      toast(TIME_RANGE_TEXT);
      form.elements.end.focus();
      return;
    }
    const data = values();
    data.explicit_fields = [...FormState.edited];
    await PlanningStudy.prepare(data);
    LastConditions.save(data);
    // 네이버 검색 결과의 받은 시각(naver_at·naver_query)은 이 브라우저의 보관 기한에만 쓴다(form-state.js). 서버에는 이름·좌표만 보낸다.
    for (const kind of ['origin', 'home'])
      if (data[kind]) data[kind] = {
        name: data[kind].name,
        lat: data[kind].lat,
        lon: data[kind].lon
      };
    mode = data.mode;
    beginPlanSearch();
    setTab(false);
    showPlannerPage(true);
    $('#progress').append(node('p', '적용 조건: ' + FormState.summary(data), 'applied-conditions'));
    // 축제는 코스와 병렬로 조회한다. 실패해도 코스 흐름에 전파하지 않는다.
    try {
      FestivalPanel.load(data);
    } catch {}
    // 팝업 글도 코스와 따로 조회한다. 코스 결과 표시를 기다리게 하지 않고, 실패해도 코스 흐름에 전파하지 않는다.
    try {
      if (typeof PopupCourse !== 'undefined') PopupCourse.load(data);
    } catch {}
    const result = await createPlanWithProgress(data, FestivalPanel.contextOf(data));
    plans = result.plans;
    selected = plans[0] || null;
    renderResults(result);
    renderDetail();
    $('#progress').textContent = (plans.length ? `추천 완료 · ${plans.length}개의 일정` : (result.reasons?.[0] || '추천 조건을 확인해 주세요.')) + PlanPreview.summary();
    // behavior 를 넘기지 않아 html 의 scroll-behavior 를 따른다(동작 줄이기 설정이면 바로 이동).
    if (window.innerWidth < 720) $('#results').scrollIntoView();
  } catch (error) {
    // 이어보기·취소로 대체된 조회는 화면을 건드리지 않는다(늦게 끝난 앞 조회가 실패 안내를 덮어쓰지 않게).
    if (error.searchKind !== 'superseded') {
      toast(error.message);
      showSearchFailure(error);
    }
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
  if (mode === 'demo') form.elements.region.value = '서울';
  $('#mode-badge').textContent = mode === 'demo' ? '서울 체험 코스' : '실제 장소';
  renderResults();
  renderDetail();
});
form.elements.region.addEventListener('change', () => {
  if (form.elements.mode.value === 'demo' && form.elements.region.value !== '서울') form.elements.mode.value = 'real';
  locationState.origin = null;
  form.elements.origin_name.value = '';
  selected = null;
  locks.clear();
  plans = [];
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
  // 머리글 메뉴의 최종 표시(색과 화면 읽기용 aria-current)는 header-mode.js 가 정한다(홈 · 테마 / 코스 만들기 / 장소 둘러보기 셋 중 하나 — 스크롤 위치까지 본다).
  if (typeof window.syncHeaderNav === 'function') window.syncHeaderNav();
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
  // 한글 조합 중 Enter(isComposing, keyCode 229)는 글자를 확정하는 키라 검색하지 않는다(두 번 검색·덜 입력된 검색 방지).
  if (e.key === 'Enter' && !e.isComposing && e.keyCode !== 229) search().catch(e => toast(e.message));
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
  if (!['#planner-section', '#curation'].includes(hash)) return;
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
  if (['#planner-section', '#curation'].includes(hash)) {
    event.preventDefault();
    navigateHomeSection(hash);
  }
});
$('#nav-plan').onclick = () => navigateHomeSection('#planner-section');
