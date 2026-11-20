/* 네이버 검색 API 특약 2.1·2.2(2026-09 개정): 네이버 검색 데이터가 보이는 곳마다 '네이버 검색결과'임을 표시하고,
   항목마다 원본(데이터 출처)으로 가는 링크를 단다.
   표기: NAVER API HUB 상표·BI 가이드(https://guide.ncloud-docs.com/docs/apihub-brandguide)의 텍스트 표기 —
   'NAVER 오픈 API' 를 API HUB 포털로 새 창 링크. 로고 이미지는 쓰지 않는다(가이드가 텍스트 표기를 허용, 로고 파일은 받지 않음).
   다른 스크립트보다 먼저 읽힌다(index.html). DOM 도우미(node·link)에 기대지 않는다. */
const NAVER_API_HUB_URL = 'https://www.ncloud.com/product/applicationService/NAVERAPIHUB';
const NAVER_RESULT_LABEL = '네이버 검색결과';

function naverSafeUrl(url) {
  try {
    const parsed = new URL(String(url || ''), location.origin);
    return parsed.protocol === 'https:' && !parsed.username && !parsed.password ? parsed.href : null;
  } catch {
    return null;
  }
}

function naverAnchor(text, url, label) {
  const a = document.createElement('a');
  a.textContent = text;
  a.href = url;
  a.target = '_blank';
  a.rel = 'noopener noreferrer';
  if (label) a.setAttribute('aria-label', label);
  return a;
}

/* kind: '지역 검색' · '블로그 검색' · '이미지 검색'. originalUrl: 이 항목의 원본(없으면 원본 링크 없이 표시만). */
function naverAttribution(kind, originalUrl, tag = 'p') {
  const box = document.createElement(tag);
  box.className = 'naver-attribution';
  const label = document.createElement('span');
  label.className = 'naver-attribution-label';
  label.textContent = NAVER_RESULT_LABEL + (kind ? ' · ' + kind : '');
  box.append(label);
  const original = naverSafeUrl(originalUrl);
  if (original) box.append(document.createTextNode(' · '), naverAnchor('원본 ↗', original, NAVER_RESULT_LABEL + ' 원본 보기'));
  box.append(document.createTextNode(' · '), naverAnchor('NAVER 오픈 API', NAVER_API_HUB_URL, 'NAVER 오픈 API (NAVER API HUB)'));
  return box;
}

/* 네이버 검색으로 찾은 장소인지(app/naver_terms.is_naver_place 와 같은 기준). */
function isNaverResult(place) {
  if (!place) return false;
  return Boolean(place.naver_result || place.naver_expired || /^(discovered:|food:naver-|parking:naver-)/.test(String(place.id || '')) || /네이버/.test(String(place.source_type || '')));
}

/* 21일 보관 기한이 지나 네이버 유래 정보를 지운 장소의 안내. */
function naverExpiredNote() {
  const p = document.createElement('p');
  p.className = 'hint naver-expired';
  p.textContent = '네이버 검색으로 찾은 장소라 보관 기간(21일)이 지나 이름·주소·위치 등 검색 정보를 지웠어요. 일정 시간 계산은 그대로예요.';
  return p;
}

/* 보관 기한(21일)이 지나 좌표까지 지운 장소가 있는 코스인지(app/naver_terms.has_expired_places 와 같은 기준).
   이런 코스는 서버가 장소·이동 수단 바꾸기, 주변 식당·주차장 찾기를 409 로 거절한다(경로를 다시 계산할 좌표가 없음).
   화면은 그 단추와 패널을 그리지 않고 아래 안내만 보여 준다. */
function planHistoryExpired(plan) {
  return Boolean(plan?.places?.some(place => place?.naver_expired));
}

function planHistoryExpiredNote() {
  const p = document.createElement('p');
  p.className = 'warning naver-expired-plan';
  p.textContent = '만든 지 21일이 지나 네이버 검색으로 찾은 장소의 정보를 지운 코스예요. 장소·이동 수단 바꾸기, 주변 식당·주차장 찾기는 같은 조건으로 새로 추천받은 코스에서 할 수 있어요.';
  return p;
}
