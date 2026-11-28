# QA-19 설계안: 첫 화면 JS 나눠 받기

> 작성: 2026-11-28 (설계). **같은 날 브랜치 `feat/js-split-qa19` 에 0~2단계를 구현하고, 이 문서를 실제 구현에 맞게 고쳤다** — 구현 결과·측정·설계와 달라진 점은 맨 아래 5절.
> 범위: 첫 화면(`datemate/static/index.html`). 공유 화면(`shared.html`)은 범위 밖(건드리지 않음).
> 조사: 원본 JS 읽기 + 정적 분석(최상위 선언·최상위 실행문·파일 사이 참조). 분석은 이제 `tests/js_globals.py` 에 있고 `tests/test_js_split.py` 가 돌린다.
> 스크립트는 **48개**(원래 47개 + 로더 `later-scripts.js`): 첫 묶음 24개, 나중 묶음 24개.

## 0. 요약

- **구현한 안: (A1)** 모듈로 바꾸지 않고, 두 번째 일반 스크립트 묶음을 `DOMContentLoaded` 뒤에 `<script>`로 붙인다. 파일 사이의 전역 공유는 그대로 둔다.
- **목록 위치**: 나중에 받을 24개 태그를 `index.html`의 `<template id="later-scripts">` 안으로 옮겼다.
  - 묶기 규칙(공백만 사이에 둔 태그 덩어리)이 이 덩어리를 자동으로 `bundles/index-2.js`로 묶고 `?v=`도 붙인다.
  - template 안 스크립트는 실행되지 않으므로 HTML이 직접 받지 않는다.
  - 그래서 `build-edge-pages.mjs`·`static_pages.py` 로직은 바꾸지 않았다(주석만 고침).
- **배포와 개발 모드가 같은 경로**: 로더(`later-scripts.js`, 전역 `DatemateLater`)가 template 안 주소를 읽어 순서대로 붙인다(배포: 묶음 1개, 개발: 원본 24개).
- **대기 처리**: 첫 묶음에서 두 번째 묶음을 부르는 진입점 8곳(G1~G8)이 `DatemateLater.need()`·`ready()`·`whenReady()` 로 기다린다(3.2·3.3).
  - 전역 stub은 쓰지 않는다. 나중 묶음이 `const ExploreView` 등으로 선언하므로, 같은 이름을 먼저 선언해 두면 SyntaxError로 묶음 전체가 멈춘다.
- **크기(실측)**: 한 묶음 724,148B(gzip 전송 226.7KB) → 첫 묶음 286,571B(gzip 전송 92.2KB, 원래의 40%) + 나중 묶음 446,990B(gzip 전송 139.0KB).
- **효과(실측, 로컬·느린 조건 5회 중앙값)**: DOMContentLoaded 6,924ms → 3,642ms(−47%), 첫 화면 준비 7,310 → 4,113ms(−44%). load·FCP 는 같다. 표는 5.2.
- **설계의 추정이 틀렸던 곳**: 느린 조건 DCL 의 큰 몫은 JS 실행(CPU)도 CSS 도 아니고 **글꼴과 회선을 나눠 쓰는 JS 받기**였다(긴 작업 합 0.3초뿐).
  글꼴(Pretendard 4종, 각 약 270KB, 합 1.08MB — 2종은 preload)을 끊고 재면 나누기 전에도 DCL 이 6.9초 → 2.4초(운영 7.8초 → 3.1초)다. 다음 후보는 5.5.

## 1. 스크립트 분류표 (원래 47개 + 로더)

범례
- 최상위 동작: 정의 = 선언만, 즉시 = 로드 때 DOM 조작·호출, 등록 = 리스너만, DCL = DOMContentLoaded 때 실행
- 다른 파일 전역 참조 시점: 로드 = 실행 순간, 동작 = 함수 안(사용자 동작·응답 뒤)
- 분류: **필수** = 첫 묶음(`bundles/index.js`), **나중** = 두 번째 묶음(`bundles/index-2.js`)

| # | 파일 | 바이트 | 최상위 동작 | 참조 시점 / 비고 | 분류 |
|---|---|---:|---|---|---|
| 1 | ko-text.js | 1,991 | 정의 | 동작. 묶음 맨 앞이라 'use strict' 없음 | 필수 |
| 1-1 | later-scripts.js (새 파일) | 6,525 | 정의 + DCL 뒤 나중 묶음 붙이기 | 로더. app.js 가 맨 위 실행 중에 쓰므로 그보다 앞 | 필수 |
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

| 묶음 | 파일 수 | 묶음 파일(B, 머리 포함) | gzip 전송(로컬 측정) |
|---|---:|---:|---:|
| 나누기 전(한 묶음) | 47 | 724,148 | 226,661 |
| 첫 묶음 `bundles/index.js` | 24 (로더 포함) | 286,571 | 92,202 |
| 나중 묶음 `bundles/index-2.js` | 24 | 446,990 | 139,048 |

(위 분류표의 파일별 바이트는 설계 때 숫자다. 그 뒤 주석이 늘어 app.js 등이 조금 커졌다. brotli 크기는 운영 배포 뒤 측정 도구로 본다.)

분석에서 확인한 것(지금은 `tests/test_js_split.py` 가 계속 확인)
- 두 묶음의 최상위 이름(첫 묶음 150여 개, 나중 묶음 280여 개) 사이에 겹침 없음.
- 첫 묶음 파일이 **로드하는 순간** 나중 묶음 이름을 쓰는 곳 없음.
- 나중 묶음 파일에는 DOMContentLoaded 리스너가 없음. 첫 묶음의 DCL 처리(simple-form·experience·recommendation-feedback)도 나중 묶음 이름을 쓰지 않음.
- 첫 묶음 코드가 나중 묶음 변수에 값을 넣는 곳은 한 곳(구현에서 생김): app.js `search()` 가 기다리는 동안 둘러보기 시·도가 바뀌었으면 `ExploreView.regionTouched = true`(3.3 G1).

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
... (나머지 필수 21개, 예전 순서 그대로) ...
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
- `place-dialog.js`의 "app.js보다 먼저 읽힌다" 주석만 고침. 스크립트 태그는 예전처럼 `<head>` 안이고 template 도 그 안에 있다.

### 3.2 로더 `static/later-scripts.js` (주석 포함 약 6KB, 전역 `const DatemateLater`)

- `ready()`: DOMContentLoaded 를 기다린 뒤, template 안 `script[src]` 주소 중 아직 실행되지 않은 것만 `async=false`로 `document.head`에 붙인다.
  모두 끝나면(`Promise.allSettled` — 하나가 실패해도 나머지가 끝날 때까지 기다린다) 진입 약속(`renderResults`·`renderDetail`·`renderPlanMapCard`·`openDialog`·`loadNaverMaps`·`loadLeaflet`·`ExploreView`·`FestivalPanel`·`PopupView`·`PopupCourse`)을 `try` 안에서 typeof로 검사(TDZ 대비).
  통과하면 `state='ready'`, `performance.mark('later:ready')`, `datemate:later-ready` 이벤트. 진행 중이면 같은 Promise 를 돌려준다.
- `need()`: 사용자가 누른 동작용. `ready()` 를 기다리되 0.4초 넘게 걸리면 알림 '화면을 준비하고 있어요. 준비되면 바로 이어 갈게요.'를 띄운다(설계에 없던 것 — 느린 회선에서 눌렀는데 아무 반응이 없는 시간을 없앰).
- `whenReady(fn)`: 기다리지 않는 곳용. 이미 실행됐으면 바로, 아니면 `datemate:later-ready` 때 한 번 부른다(받기에 실패했다가 나중에 다시 눌러 성공해도 불린다).
- 받기 실패: 그 태그를 지우고 `idle`로 되돌린 뒤 거절. 다음 `ready()`/`need()`는 **실패한 주소만** 다시 붙임(실행된 파일을 다시 붙이면 중복 선언 SyntaxError).
- 실행 오류로 약속 검사 실패: `broken`, 재시도 없음, '새로고침해 주세요'.
- template 없음/빔: 약속 검사만 하고 ready(한 묶음으로 되돌린 경우 진입점의 기다림이 무해하게).
- 시작: 파일이 실행될 때 `ready().catch(()=>{})` — 안에서 DOMContentLoaded 를 기다리므로 붙이는 때는 DCL 이다. DCL 전에 붙이지 않는 이유: 첫 묶음과 회선을 나눠 쓰고, 원본 태그를 쓰는 개발 중에는 필수 defer 파일 사이에 끼어 실행될 수 있음.
  `init()` 처럼 DCL 전에 도는 코드가 `ready()` 를 불러도 DCL 까지는 붙이지 않는다.
- 동적 스크립트도 받는 동안 `load` 이벤트를 늦춘다 — **확인함**(`test_later_bundle_runs_before_load_event_under_the_real_csp`): Playwright `goto`(load)·`audit_page`(networkidle)는 나중 묶음까지 실행된 뒤 돌아온다.
- 게터 `loaded`, `state`. 문구: 받기 실패 '코스 화면을 불러오지 못했어요. 연결을 확인하고 다시 시도해 주세요.'(설계의 '다시 눌러 주세요'는 누를 것이 없는 `?plan=`·이어보기 안내에도 쓰여 바꿈), 실행 실패 '화면 일부를 불러오지 못했어요. 새로고침해 주세요.'
- 받는 시간 제한(타임아웃)은 두지 않았다: 늦게 도착한 파일이 다시 붙인 파일과 겹쳐 실행되는 문제를 피하려고. 멈춘 연결은 브라우저의 요청 시간 제한이 실패로 바꾼다 [추정: 실제 기기에서 확인 못 함].

### 3.3 진입점(게이트) — 구현 그대로. 전체 목록의 원본은 `tests/test_js_split.py` 의 `ENTRY`

| ID | 위치 | 나중 묶음 이름 | 처리 |
|---|---|---|---|
| G1 | `app.js` `search()` | ExploreView | 아직이면 `await DatemateLater.need()` 뒤 `ExploreView.search()`. 둘러보기 메뉴·검색 단추·Enter·hashchange·init 해시(`#explore-section`)·빠른 검색(`#nav-explore` 클릭)이 모두 이 함수를 거침. 실패는 호출 쪽 catch가 toast(init 해시는 안내 배너). 기다리는 동안 `#explore-region` 값이 바뀌었으면 `regionTouched=true`(explore.js 의 change 처리가 아직 없어, 안 하면 조건 화면 지역으로 덮어씀) |
| G2 | `app.js` 제출 처리, 입력 검증 뒤·`values()` 바로 앞 | FestivalPanel·PopupCourse·renderResults·renderDetail (+ values·beginPlanSearch 안의 FestivalPanel·includedPlaces·renderPlanMapCard) | `try{await DatemateLater.need()}catch(e){toast(e.message);return;}` — **plan-job 요청 전에 끊어** 서버에 추천 작업이 생기지 않음. 설계(ServerWake 바로 뒤)보다 뒤에 둔 이유: 필수 칸·시간 검증 안내는 기다리지 않고 바로 뜨게. 테마 카드·바구니의 '바로 추천받기'도 `form.requestSubmit()` 으로 여기를 거침 |
| G3 | `app.js` init `?plan=` 분기 | renderResults·renderDetail·FestivalPanel·PopupCourse | `Promise.all([api('/plans/…'), DatemateLater.ready()])`, 실패 시 init 의 catch 가 안내 배너(showServiceNotice) |
| G4 | `app.js` init `PopupView.mount` | PopupView | `DatemateLater.whenReady(() => PopupView.mount(…))` — 기다리지 않음. 예전 typeof 보호는 로드 전이면 조용히 빠져 버그가 되므로 없앰. 받기에 실패했다가 나중에 성공해도 그려짐 |
| G5 | `app.js` 코스 종류(mode) change | renderResults·renderDetail | 상태 초기화는 바로, 그리기는 `whenReady`(그동안 결과 화면은 숨어 있음) |
| G6 | `plan-progress.js` `resumeOnce` | FestivalPanel·PopupCourse·renderResults·renderDetail (+ beginPlanSearch) | 제출 단추를 끈 바로 뒤 `need()`(기다리는 동안 새 검색이 겹치지 않게 예전처럼 꺼 둠), 실패 시 단추를 다시 켜고 toast 하고 그만둠 — 남은 검색 ID 는 그대로라 새로고침하면 다시 이어 봄. 처음 방문은 남은 ID 가 없어 기다리지 않음 |
| G7 | `location-picker.js` `openLocationPicker` | openDialog·loadNaverMaps·loadLeaflet | 맨 앞 `need()`, 실패 시 toast |
| G8 | `planning-outcomes.js` `PlanningStudy.showDecisions` | openDialog | 맨 앞 `need()`, 실패 시 toast |

게이트가 필요 없는 곳 — 기다리지 않지만 부르는 곳이 모두 게이트 뒤거나 나중 묶음 코드(테스트가 호출 지점을 확인):
app.js `values`·`beginPlanSearch`(G2·G6 뒤에서만), `rememberVerifiedMapTarget`(typeof 보호 2곳), recommendation-feedback.js `conditionDifferences`,
experience.js `togglePlanLock`·`showPlaceReport`·`showMealChange`·`showDraft`·`partnerAgreementPanel`·`experiencePanel`,
api-client.js `copyPlanShare`·`kakaoItineraryText`·`copyKakaoItinerary`, course-search.js `courseSearchPanel`, planning-outcomes.js `decisionPanel`(앞의 둘을 부름).

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
| 나중 묶음 받기 실패 | 첫 화면 정상(페이지 오류 0). G1·G2·G7·G8 은 toast + 다시 누르면 실패한 주소만 다시 받음, 제출은 plan-job 전에 멈춤. G3·처음 주소 `#explore-section` 은 안내 배너, G6 은 toast(남은 검색 ID 유지), G4·G5 는 나중에 성공한 때 실행 |
| 나중 묶음이 늦음 | 누른 동작은 기다렸다 이어 감. 0.4초 넘으면 '화면을 준비하고 있어요…' 알림. 제출 단추는 기다리는 동안 꺼져 있음(서버 깨우기 대기와 같은 모양) |
| 나중 묶음 실행 오류 | `broken`, '새로고침해 주세요', 다시 받지 않음. 한 묶음일 때도 같은 오류는 뒤 파일을 멈췄으므로 새 위험 아님 |
| 배포 직후 버전 섞임 | 배포 순간에 첫 묶음만 받은 페이지가 새 나중 묶음을 받을 수 있다(주소의 `?v=` 는 파일을 고르지 않고 캐시 정책만 정한다). DCL 때 바로 받으므로 노출은 수 초 [추정: 위험 낮음, 확인 못 함] |

### 3.6 고친 테스트(구조가 바뀌어 단정이 틀려진 것만)

| 테스트 | 바꾼 것 |
|---|---|
| `tests/test_js_bundle.py::test_page_loads_one_bundle_in_source_order` → `…_its_bundles_in_source_order` | 덩어리별로 같은 단정(머리 해시·원본 순서·`node --check`·페이지의 script 태그 목록·200 응답)을 하고, 첫 화면은 둘째 태그가 `template#later-scripts` 안인지 더 봄. 덩어리 밖에 남은 태그가 없는지도 봄 |
| `tests/test_asset_versions.py` 첫 화면 | 예전 '한 묶음 안에서 maps.js 가 app.js 앞' → 두 묶음 주소 모두 `?v=`·200, app.js 는 첫 묶음·maps.js 는 나중 묶음, 로더가 app.js 앞 |
| `cloudflare/edge.test.mjs` | 그대로 통과. `bundles/index-2.js?v=<해시>` immutable·틀린 해시 must-revalidate 를 더함 |
| `tests/test_functional_audit.py` `audit_page` | 여는 기다림에 `DatemateLater.loaded` 를 더함(안전망 — networkidle 이면 이미 참) |

그 밖의 브라우저 테스트는 고치지 않았다(모두 `load`·`networkidle` 로 연다).

### 3.7 새 테스트 `tests/test_js_split.py` (23개) + 분석 도구 `tests/js_globals.py`

1. 구조 4개: 덩어리 정확히 둘·둘째는 template 안·로더 위치, 두 묶음 첫 파일에 'use strict' 없음, 첫 묶음 원본 합 320KB 미만(지금 약 285KB — 설계의 300KB 는 여유가 16KB 뿐이라 넓힘), 나중 파일에 DOMContentLoaded 없음.
2. 정적 허용 목록 3개: 두 묶음에 같은 전역 이름 없음, 첫 묶음이 나중 묶음 이름을 쓰는 (파일·맨 위 문장)별 이름 집합 = `ENTRY` 와 정확히 같음, 게이트 문장 안에 `DatemateLater.need|ready|whenReady(` 가 있고 기다리지 않는 함수는 표 안의 문장에서만 불림.
3. 브라우저 — 나중 묶음을 붙잡아 둠(요청을 보류했다 놓음) 9개: 둘러보기(기다리는 동안 시·도 변경 포함), 처음 주소 `#explore-section`, 제출(POST 정확히 1회), 테마 카드 '바로 추천받기', 지도에서 고르기·'내가 결정한 코스 다시 보기', `?plan=` 직접 열기, 남은 검색 이어보기, 팝업 전환 그리기, 모드 전환(머리글 데이트/여행 + 코스 종류) 뒤 화면이 붙잡지 않은 페이지와 같음. 놓기 전: 페이지 오류·콘솔 오류 0, `renderResults` 없음.
4. 브라우저 — 받기 실패(abort) 3개: 첫 화면 오류 0, 둘러보기·제출·지도·결정에서 안내, `POST /api/plan-jobs` 0회, 연결이 돌아온 뒤 다시 누르면 성공(POST 1회)·팝업 전환도 그려짐. `?plan=`·`#explore-section` 은 안내 배너. 이어보기는 ID 를 남기고 다음 방문에 이어 봄.
5. 브라우저 — 받았는데 이름이 없음(빈 파일) 1개: `broken`, 새로고침 안내, 다시 받지 않음.
6. 브라우저 — CSP 를 끄지 않은 페이지에서 `securitypolicyviolation` 0, 나중 묶음이 DCL 뒤에 요청되고 load 전에 실행됨 1개(모든 브라우저 테스트가 끝날 때 CSP 위반·페이지 오류 0 을 확인).
7. 브라우저 — 원본 태그(개발 중, 묶음이 오래됨) 2개: 로더가 원본 24개를 순서대로 실행, 한 파일만 실패하면 그 파일만 다시 받음.
8. app·edge 대조·오래된 묶음 되돌림은 기존 `tests/test_js_bundle.py`(통과).

테스트가 실패를 잡는지: 진입점의 기다림을 모두 뺀 변형으로 돌려 23개 중 15개가 실패하는 것을 확인했다(원복함).

### 3.8 측정 — 도구 `tests/js_split_measure.py`(수동, 일반 pytest 에 수집되지 않음)

- 조건: Playwright Chromium(msedge), 시도마다 새 context, 402×874. CDP: `Network.setCacheDisabled(true)`, `emulateNetworkConditions({latency:150, downloadThroughput:1.6e6/8, uploadThroughput:750e3/8})`, `Emulation.setCPUThrottlingRate({rate:4})`. 데우기 1회 뒤 5회 중앙값.
- 로컬은 앱이 압축 없이 보내므로 도구가 gzip 으로 감싸 띄운다(운영은 Cloudflare 가 압축). 로컬은 HTTP/1.1.
- 지표: DCL·load(navigation timing), FCP·LCP, 첫 화면 준비(`statusData && .simple-plan-form`), `later:start`/`later:ready`, 긴 작업 합(DCL 전 / FCP~later:ready+2초), 주소별 전송 크기, 마지막 CSS 응답 끝·DCL 전 마지막 JS 응답 끝, 전체 받기 순서.
  선택: `MEASURE_EXPLORE=1`(DCL+100ms 둘러보기 클릭 → 목록), `MEASURE_COVERAGE=1`(실행된 JS 비율), `MEASURE_ABORT=정규식`(원인 나누기), `MEASURE_URL`(운영).
- 실행: `python -m pytest tests/js_split_measure.py -q -s` (datemate 폴더). 결과와 원인 나누기는 5.2·5.3.
- 수용 기준(설계 제안: 느린 조건 DCL 중앙값 15% 이상 감소, later:ready 뒤 둘러보기 응답 악화 없음, 전체 테스트 통과, 페이지 오류 0) — 로컬 측정으로 충족. 운영 측정은 배포 뒤.

### 3.9 되돌리는 법

1. 가장 빠름: template 안 24개를 첫 덩어리 끝으로 옮기고 template 삭제(로더·게이트는 남겨도 무해, 바로 ready).
2. 전체: 2단계 병합 커밋 git revert 후 재배포(1단계는 남겨도 무해).
3. `static/bundles/` 삭제는 나누기를 되돌리지 않음(원본 24개를 나중에 받는 개발 모드 경로가 될 뿐).

### 3.10 단계

| 단계 | 내용 | 상태 |
|---|---|---|
| 0 | 기준선 측정, DCL 원인 나누기, 측정 도구 | 함(5.2·5.3) |
| 1 | `later-scripts.js`, G1~G8, 테스트 도우미, 정적 허용 목록·로더 테스트 | 함(2단계와 한 브랜치) |
| 2 | template + 24개 이동, 주석, 깨지는 테스트 수정, 새 테스트, 측정 | 함. 배포·운영 확인은 남음(5.6) |
| 3(선택) | 글꼴과 회선 다툼 줄이기(5.5 — 효과가 가장 큼), experience.js 폼/결과 분리(약 20KB), 결과 전용 CSS 나중 받기, 버전 섞임 대응 | 안 함 |

### 3.11 불확실한 부분

- 동적 스크립트가 `load`를 늦추는지 — 확인함(늦춘다).
- 효과 숫자 — 로컬 측정으로 확인함(−47%). 운영 숫자는 배포 뒤 [추정: 운영 기준선 7.8초 → 4초대 초반. 로컬과 받기 순서·원인이 같아서].
- DCL 직후 나중 묶음 실행이 CPU 4배에서 긴 작업을 만드는지 — 측정상 50ms 넘는 작업이 잡히지 않았다(긴 작업 합: 전 335ms, 후 382ms, 모두 DCL 전 한 덩어리).
- 정적 분석은 글자 단위(지역 변수 동명은 참조로 셈 — `theme-cards.js` 의 `values` 한 곳을 예외로 적음). 붙잡기·끊기 브라우저 테스트로 한 번 더 확인.
- [추정·확인 못 함] 멈춘 연결(실패도 성공도 아닌 상태)이 얼마나 가는지, 실제 아이폰 Safari 에서의 동작(테스트는 Chromium 계열뿐).

## 4. 구현을 맡길 때 (Fable, 새 터미널 `ccf`)

> 데이트메이트 첫 화면이 느린 휴대폰(CPU 4배·느린 4G)에서 DOMContentLoaded 8초 걸린다(QA-19). `datemate/docs/QA-19-js-split-design.ko.md` 설계안(A1: 결과·둘러보기·지도용 스크립트 24개를 template 안 두 번째 묶음으로 옮기고 작은 로더가 DOMContentLoaded 때 붙임, 진입점 8곳은 ready 를 기다림)을 바탕으로, 먼저 0단계 측정으로 JS가 실제로 병목인지 확인하고, 효과가 있으면 기능·화면 변화 없이 첫 화면이 빨라진 상태로 만들어 달라. 나중 묶음이 늦거나 실패해도 어떤 버튼도 오류 없이 동작하거나 안내가 떠야 하고, 서버에 빈 추천 작업이 생기면 안 된다. 설계와 실제 코드가 다르면 코드를 기준으로 판단하고 문서를 고쳐라. 결과는 전후 측정 수치, 전체 테스트·CI 결과, 운영 확인 방법이 포함된 브랜치로.

## 5. 구현 결과 (2026-11-28, 브랜치 `feat/js-split-qa19`)

### 5.1 바뀐 파일

- 새 파일: `static/later-scripts.js`(로더), `tests/test_js_split.py`, `tests/js_globals.py`(전역 이름 분석), `tests/js_split_measure.py`(측정 도구).
- `static/index.html`: 스크립트 태그를 두 덩어리로(첫 24개 / `<template id="later-scripts">` 안 24개). 두 덩어리 안의 상대 순서는 그대로.
- 진입점: `static/app.js`(G1~G5), `plan-progress.js`(G6), `location-picker.js`(G7), `planning-outcomes.js`(G8). `place-dialog.js` 는 주석만.
- 주석만: `cloudflare/build-edge-pages.mjs`, `app/static_pages.py`. 테스트: 3.6.

### 5.2 전후 측정 (로컬, 느린 조건, 5회 중앙값, ms)

| 지표 | 전(main bdf65ee) | 후 | 차이 |
|---|---:|---:|---:|
| DOMContentLoaded | 6,924 | 3,642 | −47% |
| 첫 화면 준비(상태 응답·폼 그림) | 7,310 | 4,113 | −44% |
| load | 7,584 | 7,625 | 같음 |
| FCP(=LCP) | 2,168 | 2,188 | 같음 |
| later:start / later:ready | — | 3,643 / 7,058 | (전의 DCL 6,924 와 비슷한 때 모든 기능 준비) |
| DCL 전 JS 응답 끝 | 6,733 | 3,447 | |
| 마지막 CSS 응답 끝 | 1,741 | 1,742 | |
| 긴 작업 합(전부 DCL 전 한 덩어리) | 335 | 382 | 잡음 범위 |
| DCL 전 JS 전송(gzip) | 226,661B | 92,202B | −59% |
| JS 전송 합(http-client.mjs 포함) | 228,890B | 233,479B | +4.6KB(로더·주석·gzip 둘로 나뉨) |
| DCL+100ms 둘러보기 클릭 → 목록 | 60 | 3,193 | 누른 뒤 기다림은 늘지만, 목록이 뜨는 절대 시각은 약 7.1초 → 6.9초로 같다 |
| 첫 화면에서 실행된 JS 비율 | 18.5%(한 묶음) | 첫 묶음의 30.9%, 전체 18.9% | |

운영 기준선(배포 전, 같은 조건, 5회): DCL 7,823 · load 8,195 · FCP 2,324 · 첫 화면 준비 8,572 · JS 응답 끝 7,628 · 긴 작업 326ms · `bundles/index.js` 전송 223.5KB.

### 5.3 원인 나누기 (나누기 전 코드, 느린 조건, 3회 중앙값)

| 끊은 것 | 로컬 DCL | 운영 DCL |
|---|---:|---:|
| 없음 | 6,924 | 7,823 |
| 글꼴(`.woff2`) | 2,379 | 3,063 |
| JS | 2,080 | — |
| CSS | 3,897 | — |

읽는 법: 200KB/초 회선을 글꼴 4개(각 약 270KB, Regular·ExtraBold 는 preload 라 처음부터, SemiBold·Bold 는 CSS 뒤)와 JS 묶음이 나눠 쓴다.
JS 묶음(227KB)은 혼자면 1.2초면 받지만 글꼴과 나눠 6.7초에 끝났다. CPU 4배에서도 묶음 실행은 0.3초 남짓이다.
그래서 첫 묶음을 92KB 로 줄이면 받는 시간이 3.4초로 줄어든다(나중 묶음은 여전히 글꼴과 나눠 7초쯤 끝난다).

### 5.4 설계와 달라진 점

| 설계 | 구현 | 이유 |
|---|---|---|
| 효과 6.5~7.0초, 큰 몫은 CSS 일 수 있음 | −47%, 큰 몫은 글꼴과의 회선 다툼 | 0단계 측정(5.3) |
| `ready()` 하나 | `ready`·`need`(늦으면 알림)·`whenReady`(실패 뒤 성공에도 실행) | 누른 뒤 무반응 시간, 실패 뒤 조용히 사라지는 팝업 전환을 없애려고 |
| G2 는 ServerWake 바로 뒤 | 입력 검증 뒤·`values()` 앞 | 검증 안내가 기다리지 않게 |
| G4·G5 `ready().then(…).catch(()=>{})` | `whenReady` | 받기 실패 뒤 다시 성공했을 때도 그려지게 |
| G1 은 기다렸다 부르기만 | 기다리는 동안 바꾼 시·도를 지킴 | explore.js 의 change 처리가 아직 없어 고른 값이 덮어쓰였다 |
| 받기 실패 문구 '다시 눌러 주세요' | '다시 시도해 주세요' | 누를 것이 없는 안내 배너·이어보기에도 쓰임 |
| 약속 이름 8개 | 10개(`renderPlanMapCard`·`loadLeaflet` 더함) | 진입점이 실제로 쓰는 이름 |
| 첫 묶음 예산 300KB | 320KB | 실제 285KB 라 여유가 너무 작음 |
| 로더 약 2KB | 6.5KB(주석이 절반 이상) | 이유·되돌리는 법을 파일에 적음 |
| DCL 리스너에서 시작 | 파일 실행 때 `ready()` 를 부르고 안에서 DCL 을 기다림 | `init()` 이 DCL 전에 `ready()` 를 불러도 일찍 붙지 않게 한 곳에서 막음 |
| 분류표 [추정] | 24/24 분류 그대로 맞았다 | 정적 분석 + 붙잡기 테스트 |

### 5.5 다음 후보 (효과 큰 순, 모두 안 함)

1. **글꼴과의 회선 다툼**: 글꼴 4종 1.08MB 가 느린 회선 DCL 의 약 60%(5.3). 후보 — preload 를 본문 굵기 하나로 줄이기, 쓰는 글자만 남긴 더 작은 subset, 굵기 수 줄이기(가변 글꼴 1개).
   화면이 뜬 직후의 글자 모양(글꼴 바뀜)에 영향이 있어 이번 범위('화면 모양 변경 없음') 밖이다. 나눈 뒤에도 `later:ready`(약 7초)는 이 다툼에 묶여 있다.
   → 2026-11-28 브랜치 `perf/font-loading` 에서 진행: 굵기마다 작은 core 파일(약 82KB)을 먼저 쓰고 전체 파일은 모든 기능 준비 뒤에 받는다(`static/full-fonts.js`, `scripts/build_core_fonts.py`). 로컬 느린 조건 DCL 3.6 → 2.5초, `later:ready` 7.1 → 3.9초. 측정·버린 후보는 `배포-이어가기.txt` 의 브랜치 기록.
2. 결과 전용 CSS(results.css·place-photos.css·popups.css·plan-map.css, gzip 약 38KB)를 나중에 — CSS 는 1.7초에 끝나 FCP(2.2초)에만 조금 영향.
3. experience.js 폼/결과 분리(약 20KB), 버전 섞임 대응.

### 5.6 배포 뒤 운영에서 볼 것

- `/` 의 script 태그가 둘: `bundles/index.js?v=…`(바로) 와 `<template id="later-scripts">` 안의 `bundles/index-2.js?v=…`. 두 `?v=` = 로컬 sha256 앞 12자, 둘 다 200·`immutable`.
- 콘솔: `DatemateLater.state === 'ready'`, 페이지·콘솔 오류 0, CSP 위반 0. 컨테이너가 잠든 때(엣지가 주는 페이지)와 깬 때 모두.
- 손으로: 둘러보기(시·도 바꾸기·검색), 지도에서 고르기, 내가 결정한 코스 다시 보기, 코스 추천 1회 → 결과·상세·지도·축제, `?plan=` 링크 새 탭, 검색 중 새로고침(이어보기).
- 측정: `MEASURE_URL=https://… python -m pytest tests/js_split_measure.py -q -s` 로 운영 기준선(5.2 아래 줄)과 비교. 개발자 도구에서 '느린 4G'로 열고 DCL 직후 둘러보기를 눌러 '준비하고 있어요' 알림 뒤 목록이 뜨는지.
- 실제 아이폰 Safari 에서 위 손 확인(테스트는 Chromium 계열뿐).
