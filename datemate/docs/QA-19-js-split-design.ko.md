# QA-19 설계안: 첫 화면 JS 나눠 받기

> 작성: 2026-11-28 (설계만, 구현 전). 범위: 첫 화면(`datemate/static/index.html`). 공유 화면(`shared.html`)은 범위 밖.
> 조사: 원본 JS 읽기 + 저장소를 바꾸지 않는 node 정적 분석(최상위 선언·최상위 실행문·파일 사이 참조·압축 크기). 숫자는 2026-11-28 작업 트리 기준.
> 지금 스크립트는 **47개**(106차에서 `ko-text.js` 추가). 구현 시작 전에 분류표를 다시 확인할 것(이 문서 뒤에 바뀐 파일이 있으면).

## 0. 요약

- **추천: (A1)** 모듈로 바꾸지 않고, 두 번째 일반 스크립트 묶음을 `DOMContentLoaded` 때 `<script>`로 붙인다. 파일 사이의 전역 공유는 그대로 둔다.
- **목록 위치**: 나중에 받을 24개 태그를 `index.html`의 `<template id="later-scripts">` 안으로 옮긴다.
  - 지금 묶기 규칙(공백만 사이에 둔 태그 덩어리)이 이 덩어리를 자동으로 `bundles/index-2.js`로 묶고 `?v=`도 붙인다.
  - template 안 스크립트는 실행되지 않으므로 HTML이 직접 받지 않는다.
  - 그래서 `build-edge-pages.mjs`·`static_pages.py` 로직은 바꿀 필요가 없다(주석만 고침).
- **배포와 개발 모드가 같은 경로**: 작은 로더(`later-scripts.js`)가 template 안 주소를 읽어 순서대로 붙인다(배포: 묶음 1개, 개발: 원본 24개).
- **대기 처리**: 첫 묶음에서 두 번째 묶음을 부르는 진입점 8곳(G1~G8)에서 `await DatemateLater.ready()`.
  - 전역 stub은 쓰지 않는다. 나중 묶음이 `const ExploreView` 등으로 선언하므로, 같은 이름을 먼저 선언해 두면 SyntaxError로 묶음 전체가 멈춘다.
- **크기**: 첫 묶음 720,689B → 275,431B(+로더 약 2KB), 원래의 38%. gzip 226.8KB → 88.9KB, brotli 172.5KB → 71.7KB.
- **효과 추정**: 느린 기기 DOMContentLoaded 8.0초 → 약 6.5~7.0초 [추정]. 남은 큰 몫은 CSS 13개(약 340KB)일 수 있으므로 0단계 측정을 먼저 한다.

## 1. 스크립트 47개 분류표

범례
- 최상위 동작: 정의 = 선언만, 즉시 = 로드 때 DOM 조작·호출, 등록 = 리스너만, DCL = DOMContentLoaded 때 실행
- 다른 파일 전역 참조 시점: 로드 = 실행 순간, 동작 = 함수 안(사용자 동작·응답 뒤)
- 분류: **필수** = 첫 묶음(`bundles/index.js`), **나중** = 두 번째 묶음(`bundles/index-2.js`)

| # | 파일 | 바이트 | 최상위 동작 | 참조 시점 / 비고 | 분류 |
|---|---|---:|---|---|---|
| 1 | ko-text.js | 1,991 | 정의 | 동작. 묶음 맨 앞이라 'use strict' 없음 | 필수 |
| 2 | naver-attribution.js | 10,363 | 정의 15개 | 동작(검색 결과 표시) | 필수 |
| 3 | server-wake.js | 3,449 | 'use strict', 정의 | app.js init이 사용 | 필수 |
| 4 | location-picker.js | 12,564 | 정의 + #dialog close 등록 | app.js 로드 때 mountLocationFields. 지도 선택은 나중 묶음 사용 → G7 | 필수 |
| 5 | parking.js | 7,823 | 정의 | 동작(결과 상세) | 나중(첫 파일, 'use strict' 없음) |
| 6 | review-facts.js | 2,938 | 정의 | 동작 | 나중 |
| 7 | maps.js | 64,808 | 정의 39개, matchMedia 등록 | 동작 | 나중 |
| 8 | recommendation-feedback.js | 9,859 | 정의 + DCL | useTourMode 첫 화면 사용 | 필수 |
| 9 | date-categories.js | 2,232 | 정의 | init | 필수 |
| 10 | wikimedia-photos.js | 4,263 | 정의 | 동작 | 나중 |
| 11 | place-blogs.js | 5,613 | 정의 | 동작 | 나중 |
| 12 | meal-suggestions.js | 16,280 | 정의 | 동작 | 나중 |
| 13 | place-photos.js | 30,419 | 정의 + beforeprint | 동작 | 나중 |
| 14 | price-controls.js | 4,363 | 정의 | app.js 로드 때 mount | 필수 |
| 15 | execution-summary.js | 4,526 | 정의 | 동작 | 나중 |
| 16 | planning-outcomes.js | 6,628 | 정의 | simple-form DCL에서 mount. '내가 결정한 코스' → G8 | 필수 |
| 17 | experience.js | 25,137 | 정의 + DCL(폼 칸) | 결과용 함수는 나중 묶음에서만 불림 | 필수(3단계 분할 후보) |
| 18 | plan-results.js | 33,826 | 정의 + 등록 | 동작 | 나중 |
| 19 | plan-actions.js | 15,047 | 정의 | 동작 | 나중 |
| 20 | plan-progress.js | 14,799 | 정의 | init→resumePlanSearch → G6 | 필수 |
| 21 | plan-evidence.js | 22,188 | 정의 | app.js에서 typeof 보호 | 나중 |
| 22 | leisure.js | 20,325 | 정의 | 동작 | 나중 |
| 23 | delay-check.js | 42,521 | 정의 | 동작 | 나중 |
| 24 | order-suggestion.js | 6,643 | 정의 | 동작 | 나중 |
| 25 | day-of.js | 12,129 | 정의 | typeof 보호 | 나중 |
| 26 | action-card.js | 9,657 | 정의 | 동작 | 나중 |
| 27 | plan-detail.js | 44,609 | 정의 + print 등록 | 동작 | 나중 |
| 28 | chat-ui.js | 2,455 | 정의 | 동작 | 나중 |
| 29 | share-card.js | 4,026 | 정의 | 동작 | 나중 |
| 30 | explore.js | 15,881 | 정의 + 등록(둘러보기 화면 안) | → G1 | 나중 |
| 31 | festivals.js | 22,764 | 정의 | 제출·결과·복원 → G2·G3·G6 | 나중 |
| 32 | popups.js | 36,280 | 정의 | init의 typeof 보호 mount(로드 전이면 조용히 건너뜀) → G4 | 나중 |
| 33 | api-client.js | 8,263 | 정의 + import('/static/http-client.mjs') | — | 필수 |
| 34 | form-state.js | 6,774 | 정의 + 등록 | — | 필수 |
| 35 | place-dialog.js | 15,588 | 'use strict', 정의 + 등록 | openDialog·showPlace(동작) | 나중 |
| 36 | reviews.js | 4,649 | 'use strict', 정의 | 동작 | 나중 |
| 37 | app.js | 39,638 | 'use strict', 즉시 실행 다수 | 나중 묶음 호출 지점 대부분(G1~G5) | 필수 |
| 38 | request-understanding.js | 7,282 | 정의 | — | 필수 |
| 39 | course-search.js | 4,821 | IIFE | — | 필수 |
| 40 | romance.js | 2,932 | 즉시·등록 | — | 필수 |
| 41 | theme-cards.js | 26,674 | 정의 + IIFE | — | 필수 |
| 42 | privacy-controls.js | 1,902 | IIFE | — | 필수 |
| 43 | weather.js | 4,149 | 정의 | — | 필수 |
| 44 | simple-form.js | 49,405 | DCL 폼 재구성 | 필수 전역만 | 필수 |
| 45 | section-indicator.js | 4,371 | IIFE | DOM만 | 필수 |
| 46 | header-mode.js | 17,688 | IIFE | 필수 전역만 | 필수 |
| 47 | quick-search.js | 10,147 | IIFE | 둘러보기는 #nav-explore 클릭(G1) | 필수 |

| 묶음 | 파일 수 | 원본(B) | gzip | brotli |
|---|---:|---:|---:|---:|
| 지금(한 묶음) | 47 | 720,689 | 226,804 | 172,510 |
| 필수(첫 묶음) | 23 (+로더) | 275,431 | 88,857 | 71,747 |
| 나중(두 번째 묶음) | 24 | 445,258 | 139,129 | 109,106 |

분석에서 확인한 것
- 최상위 이름 432개 사이에 겹침 없음.
- 첫 묶음 파일이 **로드하는 순간** 나중 묶음 이름을 쓰는 곳 없음.
- 나중 묶음 파일에는 DOMContentLoaded 리스너가 없음. 첫 묶음의 DCL 처리(simple-form·experience·recommendation-feedback)도 나중 묶음 이름을 쓰지 않음.
- 첫 묶음 코드가 나중 묶음 변수에 값을 넣는 곳 없음(읽기만).

## 2. 접근안 비교

| 기준 | (A) 두 번째 일반 묶음을 동적으로 붙임 | (B) ES 모듈 전환 + import() |
|---|---|---|
| 바꿀 코드 | 로더 1개, index.html 태그 이동, 게이트 8곳(각 1~3줄) | 47개 전부, 432개 전역을 import·export로, app.js 순환 참조 |
| 공유 상태 | 그대로 | app.js 변수(`selected`·`plans`·`locks`·`mode`)에 다른 파일이 값을 넣는 곳 15곳 이상 → 상태 객체·setter로 재설계 |
| 엄격 모드 | 지금과 같음 | 모두 엄격 모드로 바뀜(동작 변화 위험) |
| 묶기·대조 | 로직 변경 없음 | 번들러 필요, `test_js_bundle.py` 대조 구조 재설계 |
| CSP | 변경 없음 | 변경 없음 |
| 테스트 영향 | 2~3개 | 57개 파일 112줄 이상이 전역 직접 사용 |
| 효과 | 첫 화면 기준 B와 거의 같음 | 더 잘게 나눌 수 있으나 추가 이득 작음 |
| 되돌리기 | HTML 태그만 원위치 | 어려움 |

(A) 변형: **A1 DCL 때 바로 붙임(추천)** · A2 한가할 때/첫 입력 때(테스트 31개 파일 이상에 기다림 필요, 3단계 검토) · A3 결과 화면 직전(클릭 뒤 대기, 비추천) · 두 번째 `defer` 태그(DCL을 막음, 기각) · `async` 태그(순서 위험, 기각).

## 3. 추천안 상세 설계

### 3.1 index.html 구조

```html
<script src="/static/ko-text.js" defer></script>          <!-- 맨 앞 유지('use strict' 없음) -->
<script src="/static/later-scripts.js" defer></script>    <!-- 새 로더('use strict' 없음) -->
<script src="/static/naver-attribution.js" defer></script>
... (필수 21개, 지금 순서) ...
<script src="/static/quick-search.js" defer></script>
<!-- QA-19: 첫 화면 뒤 기능. 실행되지 않는 template, later-scripts.js 가 DOMContentLoaded 때 이 순서로 붙인다. -->
<template id="later-scripts">
<script src="/static/parking.js" defer></script>          <!-- 첫 파일: 'use strict' 없음 -->
... parking, review-facts, maps, wikimedia-photos, place-blogs, meal-suggestions, place-photos,
    execution-summary, plan-results, plan-actions, plan-evidence, leisure, delay-check, order-suggestion,
    day-of, action-card, plan-detail, chat-ui, share-card, explore, festivals, popups, place-dialog, reviews ...
</template>
```

- 두 묶음 모두 상대 순서는 지금 그대로.
- `place-dialog.js`의 "app.js보다 먼저 읽힌다" 주석만 고침.

### 3.2 로더 `static/later-scripts.js` (약 2KB, 전역 `const DatemateLater`)

- `ready()`: template 안 `script[src]` 주소 중 아직 실행되지 않은 것만 `async=false`로 `document.head`에 붙인다. 모두 onload되면 진입 계약(`renderResults`·`renderDetail`·`ExploreView`·`FestivalPanel`·`PopupView`·`PopupCourse`·`openDialog`·`loadNaverMaps`)을 `try` 안에서 typeof로 검사(TDZ 대비). 통과하면 `state='ready'`, `performance.mark('later:ready')`, `datemate:later-ready` 이벤트.
- 받기 실패: 그 태그를 지우고 `idle`로 되돌린 뒤 거절. 다음 `ready()`는 **실패한 주소만** 다시 붙임(실행된 파일을 다시 붙이면 중복 선언 SyntaxError).
- 실행 오류로 계약 검사 실패: `broken`, 재시도 없음, '새로고침해 주세요'.
- template 없음/빔: 계약 검사만 하고 바로 ready(한 묶음으로 되돌린 경우 게이트가 무해하게).
- 시작: `DOMContentLoaded`에서 `ready().catch(()=>{})`. DCL 전에 붙이지 않는 이유: 동적 스크립트가 필수 defer 파일 사이에 끼어 실행될 수 있음.
- 동적 스크립트도 받는 동안 `load` 이벤트를 늦춘다 [추정, 1단계 테스트로 확인] → Playwright `goto`(load)·`audit_page`(networkidle)는 나중 묶음까지 실행된 뒤 돌아옴.
- 게터 `loaded`, `state`. 문구: 받기 실패 '코스 화면을 불러오지 못했어요. 연결을 확인하고 다시 눌러 주세요.', 실행 실패 '화면 일부를 불러오지 못했어요. 새로고침해 주세요.'

### 3.3 진입점(게이트) — 줄 번호는 2026-11-28 기준

| ID | 위치 | 나중 묶음 이름 | 처리 |
|---|---|---|---|
| G1 | `app.js` `search()` (~796) | ExploreView | `await DatemateLater.ready(); return ExploreView.search();` — 둘러보기 메뉴·검색·Enter·hashchange·init 해시·빠른 검색이 모두 이 함수를 거침. 호출 쪽 catch가 toast |
| G2 | `app.js` 제출 처리(~676-737), `values()` 전 | FestivalPanel·PopupCourse·renderResults·renderDetail·renderPlanMapCard | ServerWake 대기 바로 뒤 `try{await DatemateLater.ready()}catch(e){toast(e.message);return;}` — **plan-job 요청 전에 끊어** 서버에 고아 작업 없음 |
| G3 | `app.js` init `?plan=` 분기(~449-466) | renderResults·renderDetail·restore | `selected` 조회와 병렬로 ready, 실패 시 showServiceNotice |
| G4 | `app.js` `PopupView.mount`(~448) | PopupView·PopupCourse | 지금 typeof 보호라 로드 전이면 조용히 빠짐(버그가 됨) → `ready().then(mount).catch(()=>{})`, 기다리지 않음 |
| G5 | `app.js` mode change(~738-749) | renderResults·renderDetail | 상태 초기화는 바로, 그리기는 ready 뒤 |
| G6 | `plan-progress.js` `resumeOnce`(~140-156) | beginPlanSearch 경로 | 맨 앞 ready, 실패 시 toast·submit 다시 켬(처음 방문은 남은 id가 없어 기다리지 않음) |
| G7 | `location-picker.js` `openLocationPicker`(~27-30) | openDialog·loadNaverMaps·loadLeaflet | 맨 앞 ready, 실패 시 toast. 가장 이른 동작이라 지연 테스트 필수 |
| G8 | `planning-outcomes.js` `PlanningStudy.showDecisions`(~3) | openDialog | 맨 앞 ready, 실패 시 toast |

게이트가 필요 없는 곳(나중 묶음 코드에서만 불림): app.js rememberVerifiedMapTarget의 typeof 2곳, beginPlanSearch(G2·G6 뒤에서만 — 주석 남김), api-client copyPlanShare·copyKakaoItinerary, experience.js 결과용 함수, emptyRecommendation, courseSearchPanel.

나중 묶음이 첫 화면 고정 요소에 붙이는 리스너(로드 전 없어도 무해): explore.js(둘러보기 화면 안, regionTouched 처음 값도 false), popups.js #nav-explore(G4 mount에서), place-dialog #dialog close(openDialog로만 열림), print 리스너들(결과 없음).

### 3.4 빌드·서버·CSP·해시·개발 모드

| 항목 | 변경 |
|---|---|
| `cloudflare/build-edge-pages.mjs` writeBundles·bundledPage | 로직 변경 없음(`index.js`·`index-2.js` 자동). 주석 추가 |
| `datemate/app/static_pages.py` bundled_page | 로직 변경 없음, 주석만 |
| `?v=` | 자동(정규식이 template 안 주소에도 붙음), immutable 캐시 그대로 |
| CSP `script-src` | 변경 없음('self', 인라인 없음) |
| 개발 모드 | 덩어리별 판정. 나중 덩어리가 오래되면 원본 24개를 로더가 차례로 붙임 |
| `.gitignore`·`.dockerignore` | 변경 없음 |
| 공유 화면 | 영향 없음 |
| 묶음 이름 | 1~2단계는 `index-2.js` 그대로(양쪽 대조 위험 0) |

### 3.5 실패할 때

| 상황 | 동작 |
|---|---|
| 나중 묶음 받기 실패 | 첫 화면 정상. G1·G2·G7·G8 toast + 실패 주소만 재시도, 제출은 plan-job 전에 멈춤. G3 안내 배너, G4·G5 조용히 건너뜀 |
| 나중 묶음 실행 오류 | `broken`, '새로고침해 주세요'. 지금 한 묶음에서도 같은 오류는 뒤 파일을 멈추므로 새 위험 아님 |
| 배포 직후 버전 섞임 | DCL 때 바로 받으므로 노출 수 초 [추정: 위험 낮음]. 필요하면 3단계에서 "오래된 페이지 재시도 → 새로고침 안내" |

### 3.6 깨질 수 있는 테스트

| 테스트 | 이유 | 방향 |
|---|---|---|
| `tests/test_js_bundle.py::test_page_loads_one_bundle_in_source_order` | 태그 하나·묶음 하나 단정 | 덩어리별로 확인, 두 번째는 template 안 |
| `tests/test_asset_versions.py:20` | maps.js가 index.js 안 app.js 앞 | index-2.js·template 안 확인으로 |
| `cloudflare/edge.test.mjs` | 그대로 통과 [추정] | index-2.js immutable 확인 추가 |
| 브라우저 테스트 31개 파일+ | goto 직후 나중 묶음 함수 직접 사용 | load/networkidle 기다리면 통과. 안전망으로 `audit_page`·공용 도우미에 `wait_for_function("DatemateLater.loaded")` |

### 3.7 새 테스트

1. 구조: 덩어리 정확히 둘, 두 번째는 `template#later-scripts` 안, 두 첫 파일(ko-text·parking) 'use strict' 없음, 두 묶음 `node --check`.
2. 크기 예산: `bundles/index.js` 원본 300KB 미만(퇴행 방지).
3. 정적 허용 목록: 필수 파일이 참조하는 나중 파일 최상위 이름 목록 = 허용 목록(G1~G8·typeof 보호·결과 전용). 새 참조가 생기면 실패.
4. 브라우저 — 나중 묶음 막기(`page.route` abort): 첫 화면 pageerror 0, 둘러보기·추천받기·지도 선택·'내가 결정한 코스'에서 toast, `/api/plan-jobs` POST 0회, route 해제 후 재시도 성공.
5. 브라우저 — 나중 묶음 3초 지연: goto(domcontentloaded) 직후 둘러보기·제출(테마 카드 포함)·지도 선택·`?plan=` 직접 열기·이어보기·팝업 mount·처음 해시 `#explore-section` 모두 정상, POST 정확히 1회, pageerror 0.
6. CSP 실제 적용: `securitypolicyviolation` 0, `DatemateLater.loaded === true`.
7. app·edge 대조(`test_app_and_edge_build_the_same_pages`) 통과.
8. edge 캐시: `/static/bundles/index-2.js?v=<해시>` immutable, 해시 틀리면 must-revalidate.
9. 개발 모드: 나중 덩어리가 오래되면 template에 원본 24개, 로더가 순서대로 실행해 ready.

### 3.8 측정 (지난번 조건)

- Playwright Chromium, 시도마다 새 context, 402×874. CDP: `Network.setCacheDisabled(true)`, `emulateNetworkConditions({latency:150, downloadThroughput:1.6e6/8, uploadThroughput:750e3/8})`, `Emulation.setCPUThrottlingRate({rate:4})`. 각 5회 중앙값, 바뀌기 전/후, 운영은 컨테이너가 깨어 있을 때.
- 지표: DCL·load(navigation timing), FCP·LCP, 첫 화면 준비 시각(`statusData && .simple-plan-form`), `later:start`/`later:ready`, longtask 합계(FCP~later:ready+2초), 묶음별 transferSize, CDP precise coverage 사용률, DCL+100ms 둘러보기 클릭 → 첫 카드 시간.
- **0단계 원인 나누기**: CSS 마지막 응답 끝·JS 묶음 응답 끝·DCL을 나란히 기록. defer 스크립트는 앞선 스타일시트를 기다리므로 CSS가 지배적이면 이번 작업 효과가 작음.
- 수용 기준(제안): 느린 조건 DCL 중앙값 15% 이상 감소, later:ready 뒤 둘러보기 응답 악화 없음, 전체 테스트 통과, 운영 콘솔·페이지 오류 0.
- 다음 후보: 결과 전용 CSS(results.css 92KB, place-photos.css 16KB, popups.css 14KB, plan-map.css 11KB)를 같은 로더로 나중에.

### 3.9 되돌리는 법

1. 가장 빠름: template 안 24개를 첫 덩어리 끝으로 옮기고 template 삭제(로더·게이트는 남겨도 무해, 바로 ready).
2. 전체: 2단계 병합 커밋 git revert 후 재배포(1단계는 남겨도 무해).
3. `static/bundles/` 삭제는 나누기를 되돌리지 않음(원본 24개를 나중에 받는 개발 모드 경로가 될 뿐).

### 3.10 단계

| 단계 | 내용 | 동작 변화 | 배포 |
|---|---|---|---|
| 0 | 기준선 측정, DCL 원인 나누기(CSS 대 JS), 측정 스크립트를 tests/ 아래 수동 도구로 | 없음 | — |
| 1 | `later-scripts.js`(template 없음 → 바로 ready), G1~G8, 테스트 도우미, 정적 허용 목록·로더 테스트 | 없음 | 가능 |
| 2 | template + 24개 이동, 주석, 깨지는 테스트 수정, 새 테스트, 측정 후 배포(운영: 두 묶음 ?v= = 로컬 sha256, 콘솔 오류 0, 결과 화면·지도 선택·둘러보기) | 있음 | 가능 |
| 3(선택) | 시작 시점 조정, experience.js 폼/결과 분리(약 20KB), 결과 전용 CSS 나중 받기, 묶음 이름 명시, 버전 섞임 대응 | 있음 | 측정 후 |

### 3.11 불확실한 부분

- [추정] 동적 스크립트가 `load`를 늦추는지 — 1단계 테스트로 확인.
- [추정] 효과 숫자 — 0단계로 보정.
- [추정] DCL 직후 445KB 실행이 CPU 4배에서 긴 작업을 만들어 첫 입력을 늦출 수 있음 — 3단계 판단.
- 정적 분석은 정규식 기반(지역 변수 동명 오탐 가능) — 지연 주입 브라우저 테스트로 한 번 더 확인.

## 4. 구현을 맡길 때 (Fable, 새 터미널 `ccf`)

> 데이트메이트 첫 화면이 느린 휴대폰(CPU 4배·느린 4G)에서 DOMContentLoaded 8초 걸린다(QA-19). `datemate/docs/QA-19-js-split-design.ko.md` 설계안(A1: 결과·둘러보기·지도용 스크립트 24개를 template 안 두 번째 묶음으로 옮기고 작은 로더가 DOMContentLoaded 때 붙임, 진입점 8곳은 ready 를 기다림)을 바탕으로, 먼저 0단계 측정으로 JS가 실제로 병목인지 확인하고, 효과가 있으면 기능·화면 변화 없이 첫 화면이 빨라진 상태로 만들어 달라. 나중 묶음이 늦거나 실패해도 어떤 버튼도 오류 없이 동작하거나 안내가 떠야 하고, 서버에 빈 추천 작업이 생기면 안 된다. 설계와 실제 코드가 다르면 코드를 기준으로 판단하고 문서를 고쳐라. 결과는 전후 측정 수치, 전체 테스트·CI 결과, 운영 확인 방법이 포함된 브랜치로.
