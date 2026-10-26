# 운영 코드 구조 개선 — 2026-10-26

## 적용 내용

- `app/recommendation_service.py`: HTTP 요청 객체 없이 `generate(conditions, owner)`로 추천을 실행한다. 조건 정규화·피드백 반영, 검색, 검증·가격·필수 조건·다양성·설명·저장 순서를 보존했다. 검색 중 조정된 조건은 후속 단계에도 전달한다.
- `main.py`의 추천 API와 `plan_jobs.py`의 작업 실행기가 같은 서비스를 호출한다. 작업 실행기가 HTTP 엔드포인트를 직접 호출하던 의존성을 제거했다. 공통 동시 실행 제한과 호출량 제한은 `execution.recommendation_slot`에서 적용한다.
- `app/migrations/`: 기존 SQLite/PostgreSQL 스키마·트리거를 기준 버전으로 옮겼다. 버전 순서대로 한 트랜잭션에서 적용하고 완료 버전을 기록한다. 기존 DB는 기존 마이그레이션 기록과 데이터를 보존하며 편입한다. 두 인스턴스의 동시 시작을 잠금으로 직렬화하고, 실패 시 DDL과 버전 기록을 함께 롤백한다.
- `0002-operational-indexes`: 공유 만료 정리, 호출량 기록 정리, 종류별 운영 이벤트 조회에 필요한 인덱스를 추가했다.
- 추천 완료·실패와 조건 완화 결과 수를 기록한다. 기록 실패가 저장된 추천 결과까지 실패로 바꾸지 않도록 분리했다. 운영 보고서는 기본 최근 30일의 완료·실패·빈 결과·완료 시간 p95·조건 완화 결과 수와 표본 수를 구분한다. 기존 성공 이벤트도 집계한다.
- `static/place-dialog.js`, `static/reviews.js`: 장소 상세창과 후기 렌더링을 `app.js`에서 분리했다. HTML의 자산 로딩 순서를 줄별로 표시하고 변경 코드에 포맷터를 적용했다. 버튼 동기 예외도 비동기 실패와 동일하게 사용자 안내로 처리한다.
- `scripts/format_sources.py`: 정리된 Python/JS 파일의 포맷을 재현한다. `--check` 검사를 CI에 추가했다. 기존 전체 파일이나 외부 vendor 파일을 강제로 재포맷하지 않는다.

## 다음 DB 변경 방법

1. 적용된 `v0001_baseline.py`, `v0002_operational_indexes.py`는 수정하지 않는다.
2. 새 `v0003_*.py`에 고유 `VERSION`과 `upgrade(db, backend)`를 작성하고 `MIGRATIONS` 끝에 등록한다.
3. 기존 데이터가 있는 DB에서 이전 버전 → 새 버전 및 실패 롤백을 두 백엔드로 검증한다.
4. 앱 시작 시 미적용 버전만 실행한다. 이번 마이그레이션은 트랜잭션 내부 실행이므로 트랜잭션 불가 명령은 넣지 않는다.

자동 다운그레이드는 제공하지 않는다. 운영 데이터 변경 전 백업과 복원 절차를 준비하고, 장시간이 걸리는 대형 테이블 변경은 시작 시 실행 대신 별도 운영 절차로 설계한다.

## 프런트엔드 수정 기준

- 화면 시작·탐색·추천 제출은 `app.js`, 장소 모달은 `place-dialog.js`, 후기 폼·목록은 `reviews.js`가 담당한다.
- 현재는 고전 스크립트의 전역 함수를 공유한다. `place-dialog.js`와 `reviews.js`를 먼저 정의하고 `app.js`에서 공통 UI 초기화를 실행한다. ES 모듈 전환을 완료한 상태는 아니다.
- 스타일의 기존 우선순위를 보존했다. `style.css` → 기능 CSS 및 기존 디자인 레이어 → `editorial.css` 순서다. CSS 중복 제거·디자인 레이어 통합은 아직 남아 있다. 새 디자인 파일을 뒤에 추가하기보다 해당 컴포넌트의 기존 정의를 수정한다.

## 검증 결과

- SQLite: **265 passed, 1 skipped**, 50.46초.
- PostgreSQL 17: **262 passed, 4 skipped**, 51.21초.
- 새 테스트: 기존 DB 편입·동시 시작, 마이그레이션 실패 롤백, 추천 오류 계측, 계측 실패 격리, 운영 보고서 실패/빈 결과 구분.
- 기존 Edge 브라우저 회귀 테스트에 동기 버튼 예외 처리 검사 추가. 기존 추천·고정·교체·되돌리기·채팅·후기·삭제·공유 검증 통과.
- Linux Docker 이미지 빌드와 2개 서버 통합 검사 통과: 프로덕션 보호, 초기 색인, 다른 인스턴스에서 작업·일정 조회, 소유자 격리, 공유, 대화·후기, 재시작 후 데이터 보존, 교차 삭제·공유 철회.
- 실제 외부 연동 Edge 검사: 주소·지도·실제 추천 3개, 사진 5/2/5개, 390/768/1440px, JS 오류 없음. 데스크톱·모바일 스크린샷도 확인했다.
- 메뉴는 이번에도 `unavailable`로 반환됐다. 실제 메뉴 정보 확보 성공으로 보고하지 않는다.
- 포맷 검사, `pip check`, `git diff --check` 통과. 원격 CI 실행은 미확인이다.

실제 브라우저 증거: `runtime/live-browser-check/report.json`, `desktop-viewport.png`, `mobile-viewport.png` (Git 제외).

```powershell
# 프로젝트 루트
datemate/.venv/Scripts/python.exe datemate/scripts/format_sources.py --check
datemate/.venv/Scripts/python.exe -m pytest datemate/tests -q
datemate/.venv/Scripts/python.exe datemate/scripts/check_live_browser.py
docker compose -f compose.test.yaml up -d --build
datemate/.venv/Scripts/python.exe datemate/scripts/check_cloud_containers.py
```

## 남아 있는 운영 한계

PostgreSQL 전체 쓰기 잠금과 웹 프로세스 내부 작업 실행은 유지했다. 이를 바꾸려면 삭제·취소·재시도·중복 과금 방지까지 함께 재설계해야 한다. 큐 및 별도 작업 서비스 도입, CSS 통합, 의미 임베딩 품질 검증은 이번 변경에 포함하지 않았다. 계측된 실패는 서비스가 예외를 처리한 요청 기준이며, 프로세스 강제 종료·접수 제한은 포함하지 않는다. 실제 API 과금과 사용자 만족도도 별도 검증 대상이다.

사용자 `.env`와 기존 사용자 DB는 변경하지 않았다. 외부 Cloud 배포와 Git commit/push도 수행하지 않았다.
