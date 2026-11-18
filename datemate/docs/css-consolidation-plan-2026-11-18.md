# CSS 18개 정리 설계 (2026-11-18, Fable 설계 · 아직 적용 안 함)

사용자가 'Fable로 설계부터'를 골라 fable-designer 가 코드를 읽기만 하고 낸 설계다(실행 확인 없음). 적용은 단계별로 사용자 지시를 받아 한다.
적용할 때마다 이 문서 아래 '진행 기록'에 날짜·커밋을 적는다.

## 요약
1. 지금 구조는 테마 5벌(style → selle → calm → editorial → readability → line)이 같은 요소를 차례로 덧칠한 것이고, `!important`(333개)의 대부분은 앞 테마의 `!important`를 이기려고 붙었다.
2. 추천: 계산값 전후 비교 장치를 먼저 만들고, 부품 단위로 "이기는 선언만 남겨 한 파일로" 옮긴다(작은 단계 약 16개). 최종 9개 안팎, `@layer`는 쓰지 않는다.
3. 첫 단계는 `location-picker.css`의 `@import` 합치기. 가장 위험한 4개 화면 공통 규칙(머리글·단추·입력)은 맨 마지막.

## 1. 현재 진단
- 화면별 로드 집합(`datemate/static/`): index 16개 / feedback: style·selle·calm·editorial·readability·clarity·feedback·line / feedback-admin: style·readability·feedback·line / shared: style·readability·line·server-wake.
  공통은 style·readability·line 셋뿐이라, 규칙을 공통 파일로 옮기면 shared·admin 에 새로 적용될 수 있다.
- 파일 역할(테마 층): style = 토큰·초기 테마·인쇄·축제 카드 / selle = 2차 테마(코스 탭·식당 카드, `!important` 시작점) / calm = 3차 테마 + 지도 레일 + 글자 키우기 + 검색 중 상자 + 조건 폼 /
  editorial = 4차 배치 층(머리글 sticky, 표, 사진 넘김, 빠른 칩) / readability = `main :is()`로 명시도를 올린 글자 크기·단추 체계·shared 화면 / clarity = 축제 기준·근거 배지·구역 표시줄 /
  line = 최종 '노선' 테마 + 주차·대중교통 비교·가독성 1~8단계.
- 파일 역할(기능): place-photos, plan-map, location-picker(+`@import` layout), date-categories, planner-layout(화면 전환), execution-summary, planning-outcomes, popups(`!important` 금지를 스스로 지킴), feedback, server-wake.
- 주요 충돌(선택자 · 속성 → 이기는 곳):
  1. `header` height/padding: style 92 → selle 84 → calm 76 → editorial 88 + sticky. 720px 이하는 line.css `body > header … !important`.
  2. `main` max-width/padding: 1320 → 1460 → 1400 → editorial 1440, 좌우 여백은 line `--gutter`, 지도 있을 때 calm `main:has(.has-plan-map)` 1760.
  3. `body` font-size: 16 → 15 → 16 → 16 → readability 17 → line 16.
  4. `.primary`, `.secondary,#parse`: calm `!important` → line `!important`(순서로 이김).
  5. `.plan-option-tabs`와 단추: selle → calm → editorial `#results>` → line `#results …` 모두 `!important`. 801~1279px 열 수는 readability.
  6. `.plan-card` radius/padding: 15 → 22 → 14 → 26 → line 10/24. 800px 이하 line 이 readability 를 이김.
  7. `.stats`: style flex → editorial 상자 → readability → clarity grid → line `!important` 상자 제거 → 720px 이하 line 2×2.
  8. `.stop`, `.timeline-stamp`, `.stop-number`: style → selle → calm → line `.detail .stop` 3열 격자.
  9. `.timeline-card h4` 크기: 21 → 22 → 24 → readability 25/23 → line 24·19 → line 21 이 모든 폭에서 이김(일부 죽은 규칙).
  10. `.route-line`: 5개 파일 → line `.detail .route-line`.
  11. `.stop-cost`: 알약(editorial) → line `!important`로 글자만.
  12. `.meal-suggestions` margin-left: selle 113 → calm 0 → line `var(--band)` 모두 `!important`. 배경도 4번 뒤집힘.
  13. `.meal-actions>*`: selle 6속성 `!important` → editorial 999px → line 10px.
  14. `.place-blogs`, `.place-photo-panel`, `.place-evidence`: 4개 파일 모두 `!important`, line 이 이김.
  15. `#progress`, `.search-spinner`: calm → editorial → line 모두 `!important`.
  16. `.tag,.step-category`: 색은 line `!important`, 글자 크기는 readability `main :is()` 13.5px.
  17. 입력칸: editorial → readability `.conditions` 48px/17px → line 1px/10px → line 테두리 색.
  18. `.hero .hero-description`: line `19px!important`가 readability `main … 18px!important`에 명시도로 짐(계산값으로 확인 필요).
  19. `main .eyebrow`: line `display:none`이라 다른 파일의 eyebrow 규칙이 모두 죽음.
  20. 포커스 테두리: calm 홍 `!important` → line 청 `!important`. 위치 대화상자만 editorial 의 ID 규칙.
- `!important` 유형: (가) 앞 테마의 `!important` 다시 이기기(대부분) (나) readability 의 높은 명시도 이기기 (다) 같은 파일 앞 규칙 이기기 (라) 정당: `[hidden]`, `.visually-hidden`, 인쇄, 동작 줄이기, 네이버 SDK 인라인 대응, 사진 뷰어 (마) JS 인라인 대응 추정(selle 코스 탭 z-index/top).

## 2. 선택지와 추천
- A. 순서대로 이어 붙이기만: 빠르지만 '누가 이기는지'와 `!important`가 그대로, 화면별 로드 집합 때문에 한 파일로는 못 합침.
- B. 기존 파일을 `@layer`로 감싸기: `!important`는 층 순서가 거꾸로라 앞 테마가 이기게 뒤집히고, 미지원 브라우저는 블록 전체를 버림.
- **C. 부품별 평탄화(추천)**: 부품마다 전 파일의 규칙을 모아 이기는 선언만 한 파일에 쓰고 나머지 삭제. 단계가 많고 검증 장치 필수.
- 최종 파일(index 순서): `style.css`(토큰·폰트·요소 기본·유틸·공통 부품·머리글·바닥글·대화상자·토스트·shared 전용·축제 카드) → `home.css` → `results.css` → `place-photos.css` → `plan-map.css`
  → `location-picker.css` → `popups.css` → `server-wake.css`. feedback·admin 은 style + feedback, shared 는 style + server-wake. 조건부 `shell.css`(index·feedback 만): 공통 요소 규칙이 shared·admin 에서 계산값을 바꿀 때만.
- 이름 `style.css`·`plan-map.css` 유지(테스트 참조). 인쇄 규칙은 각 파일 끝 '인쇄' 구역. `@layer` 쓰지 않음.
- 과도기: 평탄화한 부품은 line.css 바로 뒤의 새 파일(results·home)에 쓰고 같은 커밋에서 다른 파일의 그 부품 규칙을 지운다. 비워진 테마 파일은 링크를 유지하다 6단계에서 뺀다.

## 3. 위험과 하지 말 것
- 장면에 안 나온 부품(오류·빈 상태, 주차, 대중교통 비교, 레저, 축제 기준) 회귀: CDP `CSS.startRuleUsageTracking`으로 '한 번도 맞지 않은 규칙' 목록을 내고, 장면을 추가하기 전에는 건드리지 않는다.
- `:hover`, `:focus-visible`, `[aria-pressed]`, `:disabled`, 인쇄, 동작 줄이기, 강제 색상은 정적 캡처에 안 잡힘 → 상태 표본과 매체 에뮬레이션을 장면에 넣는다.
- 옮긴 규칙이 다른 요소에서 새로 이길 수 있음 → 선택자를 좁히고, 명시도를 올리거나 `!important`를 새로 붙이지 않는다.
- 하지 말 것: 여러 부품을 한 커밋에 / 값 '정리'(13.5→14px 반올림, 색 통일) / 선택자 이름·DOM·JS 변경 / line.css 끝에 덧붙이기 계속 / 허용 오차로 차이 덮기 / 평탄화 전 `@layer`·CSS 중첩·압축 도구 / `git add -A`.
- 검증은 Chromium 뿐 → 5단계 뒤 사람이 아이폰으로 확인. 죽은 규칙 삭제 목록을 커밋 메시지에 남긴다.
- 파일명 변경 영향: `cloudflare/build-edge-pages.mjs`는 정규식이라 따라감. `datemate/scripts/operations_check.py`의 `readability.css`와 테스트 주석은 6단계에서 고침.

## 4. 단계 (각 단계: before 캡처 → 수정 → after 캡처 → 차이 0 → Docker 전체 → 파일별 커밋 → 배포-이어가기.txt 기록, 되돌리기는 git revert)
- **5-0 검증 장치(CSS 변경 없음)**: 새 `datemate/tests/css_snapshot.py`(`capture --out DIR`, `compare A B`), `test_functional_audit`의 audit_page·generate·wait_for_selected_detail 재사용.
  장면: 홈 / 조건 펼침 / 검색 중 / 결과(details 모두 열기, 코스 1·2) / 결과 인쇄 / 둘러보기·팝업 / 위치 대화상자·사진 뷰어 / shared / feedback / feedback-admin. 결과는 동작 줄이기·강제 색상도.
  폭: 320·390·450·560·700·740·780·900·1050·1200·1440·1600. 수집: 전 요소와 가상 요소의 getComputedStyle 전 속성 + getBoundingClientRect, 전체 스크린샷,
  상태 표본(hover·Tab 포커스). 안정화: fonts.ready, 애니메이션 정지, 시계 고정. 허용 오차 0. 완료: 무변경 2회 차이 0 / 1px 바꾸면 차이 보고 / 규칙 사용률·미사용 목록.
- **5-1 `@import` 합치기(최저 위험)**: `location-picker-layout.css`를 `location-picker.css` 앞에 합치고 layout 파일 삭제(사용자 확인).
- **5-2 죽은 것 지우기**: 완전 중복(planner-layout `[hidden]`, selle `.mode-badge`), html·js 어디에도 없는 클래스(`.hero-art`, `.orbit`, `.ticket*`, `.flower`, `.art-*`, `.route-feature`, `.route-art`,
  `.feature-tags`, `.journal-*`, `.preset-*`, `.data-point`, `.ai-label`, `.big-symbol`, `.empty-tags` — 각각 Grep 확인), line `display:none` 때문에 죽은 `main .eyebrow` 규칙.
- **5-3 결과 화면 평탄화 → 새 `results.css`**: 3a 코스 탭(먼저 JS 인라인 스타일 Grep) / 3b `.plan-card`·`.stats`·`.path-text`·`.fit-reasons`·`.plan-preview*` /
  3c `.detail`·`.stop`·`.timeline-*`·`.route-line*`·`.transport-*`·`.transit-*`·`.parking-*` / 3d `.meal-*`·`.restaurant-menu`·`.menu-*`·`.place-blogs`·`.place-evidence` (사진은 place-photos.css) /
  3e 표·`.execution-summary`·`.planning-decision`(execution-summary·planning-outcomes 흡수) / 3f 지도 → plan-map.css / 3g 축제·레저·대화·후기·둘러보기 카드.
  방법: 전 파일 Grep → before 계산값으로 이기는 선언 판정 → 한 규칙 세트로 쓰고 `!important` 떼기 → 다른 파일 규칙 삭제. 하위 단계당 선언 50~150개.
- **5-4 홈·조건 평탄화 → 새 `home.css`**: 히어로·큐레이션 / 조건·빠른 칩·요청(date-categories 흡수) / 화면 전환(planner-layout, `body.show-*`).
- **5-5 4개 화면 공통 → `style.css`(최고 위험, 마지막)**: body·제목·링크·포커스·유틸 / header·nav·footer·구역 표시줄 / 단추·칩·tag·hint·warning / 입력·summary·dialog·toast·shared.
  shared·admin 장면 차이가 나면 그 선언만 `shell.css`로.
- **5-6 빈 파일·링크 정리**: 빈 테마 파일 링크를 html 4개에서 빼고 삭제(사용자 확인), line 의 `@font-face`는 style 로, operations_check·테스트 주석·배포 기록 갱신.
- **5-7 재발 방지 테스트**: 새 `datemate/tests/test_css_structure.py` — `!important`는 허용 목록만 / 같은 선택자가 두 파일에 있으면 실패 / html 링크 순서 고정. 각 파일 머리 주석에 '맡는 범위·넣지 말 것'.

## 진행 기록
- 2026-11-18 **5-0 검증 장치** — `datemate/tests/css_snapshot.py`(찍기, 장면 10 × 폭 12, 약 3분·94MB) + `datemate/scripts/css_snapshot_compare.py`(비교).
  장면: home, home_expanded, results_demo, results_course2, results_real(사진·메뉴·주차·대중교통 비교 패널 포함), results_print, explore, shared, feedback, feedback_admin.
  무변경 두 번 찍기의 차이를 0 으로 만들며 고친 것: CSS 변수 나열 순서가 실행마다 달라 속성 이름 정렬 / sticky 머리글 때문에 찍기 전 맨 위로 /
  늦게 그려지는 칸 때문에 networkidle + 500ms 대기 / 스크린샷에서 지도 칸·알림(#toast)·지도 설명 줄을 가림(실행마다 내용이 달라짐, 스타일 비교는 그대로).
  민감도: 복사본에서 '일정에서 보기' 단추 여백만 1px 바꾸자 모든 폭에서 스타일·스크린샷 차이를 보고함.
  아직 안 한 것: 규칙 사용률(미사용 규칙 목록, CDP CSS.startRuleUsageTracking) → 5-2 때, :hover·:focus-visible 표본·강제 색상 → 5-5 전에.
  쓰는 법: 같은 Docker 컨테이너에서 `CSS_SNAPSHOT_OUT=/snap/before python -m pytest tests/css_snapshot.py -q -p no:cacheprovider` → CSS 수정 → after 로 다시 → `python scripts/css_snapshot_compare.py /snap/before /snap/after`.
- 2026-11-18 **5-1 @import 합치기** — `location-picker-layout.css` 내용을 `location-picker.css` 맨 앞(예전 @import 자리)에 넣고 layout 파일 삭제(사용자 확인).
  검증 장치에 장면 `location_dialog`(출발지 '지도에서 고르기' 대화상자) 추가. 전후 11장면 × 12폭 차이 0(layout 파일을 뺀 상태로 찍음),
  위치 선택·자산·CSP 관련 테스트 17개, 엣지 테스트 13개 통과.
- 2026-11-18 **5-2 죽은 규칙 지우기(일부)** — 새 `datemate/scripts/css_dead_rules.py`(목록만 / `--apply`)로 '정적 HTML·JS·서버·엣지 코드 어디에도 없는 클래스'만 가리키는
  선택자 120곳을 지움(7개 파일, 43줄 삭제·27줄 수정). 지운 클래스: .ai-label .art-blue .art-label .art-mint .art-number .art-pink .big-symbol .date-note .empty-tags
  .feature-tags .flower .hero-art .hero-pill .journal-heart .journal-illustration .journal-orbit .journal-spark .journal-steps .journal-top .leisure-choices .media-empty
  .nav-cta .option-heading(.inspect-plan 은 이 안에서만) .orbit .photo-choices .preset-art .preset-copy .route-art .route-feature .ticket .ticket-dots.
  도구가 처음에 `popup-${kind}` 템플릿으로 만드는 .popup-kind 를 죽었다고 잘못 봐서 템플릿 앞부분 검사를 더했고, 지울 이름은 사람이 단어 검색으로 한 번 더 확인함.
  전후 11장면 × 12폭: 스타일·상자 차이 0. 스크린샷은 location_dialog 560px 한 곳 4픽셀이 실행마다 흔들림(같은 CSS 로 찍어도 세 번 중 두 번 다름, 위치 544,52) — CSS 탓 아님, 알려진 흔들림.
  관련 화면 테스트 44개 통과.
  아직 안 한 것(5-2 의 나머지): 완전 중복 규칙(planner-layout `[hidden]`, selle `.mode-badge`), line `main .eyebrow{display:none}` 때문에 죽은 eyebrow 규칙,
  규칙 사용률(CDP) 목록 — 화면에 쓰이는 이름이지만 이기지 못해 죽은 규칙은 5-3 이후 부품 평탄화 때 함께 정리하는 편이 안전함.
