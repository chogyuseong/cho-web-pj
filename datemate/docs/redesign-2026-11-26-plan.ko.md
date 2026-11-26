# 2026-11-26 리디자인 — Phase 0 분석과 단계 계획

사용자 요구 문서(2026-11-26 오후 붙여 넣음: 'Crisp Daylight & Semantic Palette', Phase 0~4, 완료 기준 8개)와
같은 날 Gemini Canvas 시안(Downloads\datemate-시안-2026-11-26)을 함께 기준으로 삼는다.
원칙: 추천·지연·축제 배치·되돌리기 로직은 그대로 두고 화면에 연결만 한다. 확인 안 된 정보는 지어내지 않는다.

## Phase 0. 지금 구조

### 1. 프레임워크·스타일·명령
- 프론트: 빌드 도구 없는 순수 HTML·JS(전역 함수, `<script defer>` 약 45개) — `datemate/static/`. 번들러·Tailwind 없음.
- 스타일: 순수 CSS 층 11개(style → shell → readability → line → home → results → place-photos → plan-map → popups → server-wake → redesign). `redesign.css` 가 맨 뒤 덮는 층(!important 0개 규칙, tests/test_css_structure.py).
- 백엔드: FastAPI(Python 3.12, `datemate/app/`), SQLite(로컬)·PostgreSQL(운영).
- 배포: Cloudflare Worker(`cloudflare/worker.js`, `edge.mjs`) + Containers(Dockerfile). `npx wrangler deploy` 가 `cloudflare/build-edge-pages.mjs` 로 정적 파일 해시(?v=)를 붙인다.
- 테스트: `datemate/.venv/Scripts/python.exe -m pytest -q`(약 1,650개, 대부분 Playwright 화면 테스트, 30분), `npm run test:security`(27). CI: GitHub Actions 'Application checks'(sqlite·postgres·container·security·python-audit).

### 2. 다섯 영역 파일과 상태
| 영역 | 파일 | 상태 |
|---|---|---|
| 코스 만들기 | index.html `#conditions`, simple-form.js(폼 재배치), app.js(제출·해석), form-state.js(FormState.edited, 지난번처럼), theme-cards.js(테마 → 조건) | 전역 `form`, `locationState`, `FormState`, localStorage |
| 추천 결과 | plan-results.js(탭·윗줄), plan-detail.js(renderDetail·장소 카드), delay-check.js, order-suggestion.js, plan-actions.js(구간·수단), maps.js, price-controls.js, share-card.js | 전역 `plans`, `selected` |
| 장소 둘러보기 | explore.js(ExploreView), popups.js | ExploreView 객체 |
| 테마별 추천 | index.html `#curation`, theme-cards.js(SITUATION_THEMES·동네 카드·계절) | ThemePresets |
| 피드백 | feedback.html, feedback.js, app/user_feedback.py | 독립 페이지 |
| 머리글 | header-mode.js(메뉴·데이트/여행), quick-search.js(⌘K, 11-26) | body.mode-travel, localStorage 'datemate-mode' |

### 3. API(주요)
- 추천: POST /api/plan-jobs(비동기 작업) → GET /api/plan-jobs/{key}; POST /api/plans; POST /api/conditions/parse
- 결과 조작: POST /api/plans/{id}/replace · /alternatives · /transport · /reorder(제안 순서만) · /undo; POST /plans/{pid}/locks; GET /plans/{pid}/delay-check?index&minutes&stays(11-26); POST /plans/{pid}/delay-recovery; GET /api/plans/{id}/order-suggestion
- 장소: GET /api/places/{id} · /media · /blogs · /menu · /identity · /review-facts; POST /api/locations/search · /region
- 둘러보기·축제: GET /api/explore · /api/explore/naver · /api/festivals · /api/popups
- 공유: POST/GET/DELETE /api/plans/{id}/shares, GET /api/shared-plan, /shared
- 피드백: POST /api/feedback, 관리자 /api/feedback/admin/entries

### 4. 데이터 모드·키 분기
- 화면: index.html 의 `select[name=mode]`(real/demo) — simple-form.js 가 '상세 조건' 쪽으로 옮김. 테스트(generate 등)가 demo 를 많이 쓴다.
- 서버: GET /api/status 가 키 유무(검색·지도·관광공사)를 알려 주고, app/festivals.py·blog_search.py 등이 키 없을 때 문구를 돌려준다(일부 '…API 키…' 문구 — 일반 화면에 나오는지 확인해 고칠 대상).

### 5. 기존 기능 위치
- 늦어지면: delay-check.js(delaySimBar·delayCheckPanel·openDelayRecovery) ↔ app/delay_check.py, app/delay_recovery.py
- 장소 고정·교체·되돌리기: plan-detail.js(togglePlanLock·showAlternatives), app.js·plan-actions.js(undo), app/plan_changes.py
- 합의 코스: app/agreement*, static 의 agreement 관련 패널(plan-detail.js)
- 축제 시간 배치: app/festival_time.py, plan-detail.js festivalVisitBlock

## 요구와 지금의 차이 (11-26 1차 작업 뒤)
이미 됨: ⌘K 팔레트, 슬라이딩 메뉴 표시, 분류 색 띠(장소 카드), 체류 ±15분 재계산, 지연 +15/30/60, 귀가 토글, 공유 티켓·카톡 복사, 카카오맵 링크(실제 장소), 피드백 유형·만족도·FAQ, 휴대폰 하단 바, 테마 2트랙·계절 배지.
남은 것(계획 순서):
1. Phase 1 — tokens.css(요구 토큰 + `html[data-mode]`), 여행 모드 포인트색 파랑 전환, 추천 결과 탭 메뉴 노출+개수 배지, 되돌리기 단추 달린 토스트, 정상 상태의 '서비스 상태 확인' 숨김, 개발자 문구 정리, 데모 선택 숨김(`?demo=1`). 날씨 필은 외부 날씨 API 가 없어 '어댑터 + 방문일 날씨 직접 고르기'로만(지어낸 예보를 보이지 않음).
2. Phase 2 — 코스 만들기 1단계/2단계 정리(이미 대부분), 테마 해제 단추·전환 시 잔여 필터 초기화 확인, 계절 히어로 문구 4종.
3. Phase 3 — 순서 ↑/↓(서버에 '사용자 순서' 계산 추가: order_suggestion 의 평가 재사용), 교체 뒤 토스트 되돌리기, 지연 문제 장소 '자동 조정'(서버 지각 복구 후보 1순위 적용 + 되돌리기), 모바일 [타임라인/지도] 토글, 카드↔핀 강조 확인, 축제 '내 코스에 끼워 넣기' 확인, 체크리스트.
4. Phase 4 — 둘러보기 바구니 도크 → 필수 장소 여러 곳(서버가 여러 곳 고정을 받는지 확인 후), 장소 상세 드로어, 컴팩트 리스트.
안 하거나 바꾸는 것: 지도는 실제 네이버 지도 유지(벡터 그림 지도 대신 핀 색만), 날씨 예보 지어내기 안 함, 공유 링크는 기존 공유 토큰(/shared) 사용(URL 쿼리 직렬화 대신 — 서버 저장본이라 상대가 같은 코스를 본다).
