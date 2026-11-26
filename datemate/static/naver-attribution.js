/* 네이버 검색 API 특약(2026-10-07 시행 「NAVER API HUB 서비스 이용약관」 1.1~1.4 — 2026-09 개정본의 2.1~2.4 와 같은 내용, 번호만 바뀜.
   네이버 답변 2026-11-24, docs/naver-terms-inquiry-draft-2026-11-20.ko.md): 네이버 검색 데이터가 보이는 곳마다 '네이버 검색결과'임을 표시하고,
   항목마다 원본(데이터 출처)으로 가는 링크를 단다.
   BI: NAVER API HUB 상표·BI 가이드(https://guide.ncloud-docs.com/docs/apihub-brandguide)의 기술 표기 가로형 로고
   'Powered by NAVER OpenAPI'(가이드 PNG 묶음 '2-1. NAVER OpenAPI_c_hor.png' 를 높이 36px 로 줄인 static/brand/naver-openapi-powered.png).
   가이드대로 로고를 누르면 NAVER API HUB 소개가 새 창으로 열린다. 가이드 예시처럼 결과 영역 오른쪽 아래에 둔다.
   (2026-11-24 의 '작은 회색 글자 NAVER 오픈 API, 링크 없음'은 네이버 답 '표시는 BI 가이드에 따라'를 받고 2026-11-26 로고로 바꿈.)
   주소는 대소문자를 가린다 — '/NAVERAPIHUB' 는 404 였다(2026-11-24 확인).
   다른 스크립트보다 먼저 읽힌다(index.html). DOM 도우미(node·link)에 기대지 않는다. */
const NAVER_API_HUB_URL = 'https://www.ncloud.com/product/applicationService/naverApiHub';
const NAVER_RESULT_LABEL = '네이버 검색결과';
const NAVER_LOGO_SRC = '/static/brand/naver-openapi-powered.png'; // 395×36 PNG, 화면에서는 높이 14px(.naver-powered img). 파일을 바꾸면 width·height 도.

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

/* BI 로고 링크 하나('Powered by NAVER OpenAPI' → NAVER API HUB 소개, 새 창). 블록 오른쪽 아래와 아래 naverAttribution 한 줄이 쓴다. */
function naverPoweredBy() {
  const a = naverAnchor('', NAVER_API_HUB_URL, 'Powered by NAVER OpenAPI — NAVER API HUB 소개 새 창');
  a.className = 'naver-powered';
  const img = document.createElement('img');
  img.src = NAVER_LOGO_SRC;
  img.alt = 'Powered by NAVER OpenAPI';
  img.width = 154; // 395×36 을 높이 14px 로 — CLS 를 막으려고 크기를 미리 적는다.
  img.height = 14;
  img.decoding = 'async';
  a.append(img);
  return a;
}

/* 블록 밖 한 줄 출처 표시(예전에 저장한 코스의 네이버 검색 장소 — maps.js·place-dialog.js·plan-detail.js·shared.js).
   kind: '지역 검색' · '블로그 검색' · '이미지 검색'. originalUrl: 이 항목의 원본(없으면 원본 링크 없이 표시만).
   options.logo=false: 로고를 따로 두는 곳(블록 머리글 — 로고는 블록 오른쪽 아래). */
function naverAttribution(kind, originalUrl, tag = 'p', options = {}) {
  const box = document.createElement(tag);
  box.className = 'naver-attribution';
  const label = document.createElement('span');
  label.className = 'naver-attribution-label';
  label.textContent = NAVER_RESULT_LABEL + (kind ? ' · ' + kind : '');
  box.append(label);
  const original = naverSafeUrl(originalUrl);
  if (original) box.append(document.createTextNode(' · '), naverAnchor('원본 ↗', original, NAVER_RESULT_LABEL + ' 원본 보기'));
  if (options.logo !== false) box.append(document.createTextNode(' '), naverPoweredBy());
  return box;
}

/* 네이버 검색결과 블록 — 특약 1.2 '독립적으로, 가공 없이 노출'(docs/naver-terms-stage2-design.ko.md 3.7(a)).
   화면에 남는 네이버 검색 결과는 모두 이 블록 하나로 그린다: 블로그 글(place-blogs.js·course-search.js), 팝업 글(popups.js),
   둘러보기의 '네이버에서 더 찾기'(explore.js), 출발지 이름 검색(location-picker.js·simple-form.js).
   모양: 테두리로 두른 독립 영역 = 머리글(.naver-result-head: 제목[검색어·건수] + '네이버 검색결과 · 종류 · 원본 ↗')
         + 본문(.naver-result-body) + 바닥(.naver-result-foot: 왼쪽 「더 보기」 자리 block.foot, 오른쪽 BI 로고).
   네이버 답변(2026-11-24, 첫 문의 2-1·2-2):
     · 블록 앞·뒤·중간에 다른 정보를 넣지 않는다. 같은 카드 안에서 블록 바로 위·아래에 우리 정보를 붙이는 것도 앞·뒤 삽입이다
       → 블록이 든 칸에는 블록만 둔다. 우리 정보(메모·안내·단추·사진·메뉴)는 테두리로 나뉜 다른 칸에(예: 코스 조사의 메모 상자와 블로그 칸).
     · 블록 앞의 안내 문구(예: '광고 글이 섞일 수 있어요')도 앞 삽입 → 두지 않는다. 네이버 결과임은 머리글 표시 + BI 로고로만 알린다.
   본문에는 API 가 준 필드(제목·요약·주소·분류·작성자·날짜·전화·원본 링크)만. 받은 순서·건수를 바꾸지 않는다.
   「더 보기」(block.foot)는 받은 결과의 뒤쪽을 같은 순서로 펴는 쪽 넘김이라 블록 안 바닥에 둔다 — 정보 삽입이 아니라 네이버 결과 목록의 일부로 본다
   (네이버 검색 화면의 '더보기'와 같은 역할. 문서 docs/naver-terms-inquiry-draft-2026-11-20.ko.md 에 판단 기록).
   kind: '지역 검색' · '블로그 검색' · '이미지 검색'. originalUrl: 같은 검색어의 네이버 화면. options.heading: 머리글 맨 위에 둘 제목 요소(검색어·건수).
   돌려주는 요소의 body 가 본문, foot 이 「더 보기」 자리다. */
function naverResultBlock(kind, originalUrl, options = {}) {
  const block = document.createElement(options.tag || 'section');
  block.className = 'naver-result-block' + (options.className ? ' ' + options.className : '');
  block.setAttribute('aria-label', NAVER_RESULT_LABEL + (kind ? ' · ' + kind : ''));
  const head = document.createElement('div');
  head.className = 'naver-result-head';
  if (options.heading) head.append(options.heading);
  head.append(naverAttribution(kind, originalUrl, 'p', { logo: false }));
  const body = document.createElement('div');
  body.className = 'naver-result-body';
  const foot = document.createElement('div');
  foot.className = 'naver-result-foot';
  const pager = document.createElement('div');
  pager.className = 'naver-result-pager';
  foot.append(pager, naverPoweredBy());
  block.append(head, body, foot);
  block.body = body;
  block.foot = pager;
  return block;
}

/* 예전에 저장한 코스에 남아 있는 네이버 검색 장소인지(app/naver_terms.is_naver_place 와 같은 기준).
   2026-11-20 2단계부터 새 코스·둘러보기·주변 식당·주차장·레저 후보는 공공 자료에서만 나와 여기에 해당하지 않는다.
   저장 코스의 네이버 장소는 만든 지 21일 뒤 정보가 지워진다(naver_expired). */
function isNaverResult(place) {
  if (!place) return false;
  return Boolean(place.naver_result || place.naver_expired || /^(discovered:|food:naver-|parking:naver-)/.test(String(place.id || '')) || /네이버/.test(String(place.source_type || '')));
}

/* 공공 자료에서 찾은 장소(app/public_places.py)의 출처 한 줄. 한국관광공사 항목은 관광공사 상세로, 상가정보는 공공데이터포털 자료 설명으로 잇는다. */
function isPublicDataPlace(place) {
  return /^public:/.test(String(place?.id || ''));
}

function publicDataSource(place) {
  const p = document.createElement('p');
  p.className = 'public-data-source';
  const tour = place.public_source === 'tour';
  p.append(document.createTextNode('공공 자료 · '));
  const url = naverSafeUrl(place.source);
  const name = tour ? '한국관광공사 관광정보' : '소상공인 상가정보';
  p.append(url ? naverAnchor(name + ' ↗', url, name + ' 출처 보기') : document.createTextNode(name));
  return p;
}

/* 공공 자료 장소에 '확인 필요'가 많은 까닭 한 줄(카드의 정보 확인 칸, plan-evidence.js). */
function publicDataNote(place) {
  if (!isPublicDataPlace(place)) return null;
  const p = document.createElement('p');
  p.className = 'hint public-data-note';
  p.textContent = place.public_source === 'tour' ?
    '한국관광공사 관광정보에서 찾은 곳이에요. 이 자료에는 가격·후기가 없고 영업시간은 안내 글뿐이라, 방문 전에 네이버 지도에서 확인해 주세요.' :
    '소상공인 상가정보(공공 자료)에서 찾은 곳이에요. 이 자료에는 상호·업종·주소만 있어 사진·영업시간·가격·후기는 네이버 지도에서 확인해 주세요. 상호가 간판과 다를 수 있어요.';
  return p;
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
