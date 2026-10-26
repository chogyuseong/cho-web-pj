# Cloud Run 운영 코드 전환 및 검증

검증 기간: 2026-10-25~26, 최종 회귀 검사: 2026-10-26.
Google Cloud에 실제 리소스를 생성하거나 공개 배포하지 않았다. 로컬에서 PostgreSQL 17과 Linux 컨테이너를 사용해 운영 저장 구조를 검증했다.

## 구현

- `DATABASE_URL`이 있으면 PostgreSQL, 없으면 로컬 SQLite. 운영 모드에서 영속 DB가 없으면 시작 차단.
- PostgreSQL 연결 풀, 공통 SQL, 스키마 초기화, 트랜잭션 잠금, 삭제된 세션의 늦은 쓰기를 차단하는 DB 트리거.
- 공유 DB의 검색 상태·하트비트·취소. 다른 인스턴스에서도 진행 조회와 취소 가능. 만료된 작업을 재시도할 때 이전 작업이 다시 결과를 게시하지 못하도록 차단.
- 장소 탐색 수집의 공유 소유권과 만료 시간으로 여러 인스턴스의 중복 수집 방지.
- 장소뿐 아니라 배포된 근거 문서도 초기 색인. Chroma 파일은 컨테이너에서 다시 만들 수 있는 자료로 취급.
- 허용 호스트·동일 출처 검사, HTTPS 보안 쿠키, 오류 응답 보안 헤더, 요청 본문 크기·전송 시간 제한, IP별 요청 및 사용자별 질문 제한.
- 메뉴·블로그 원문·경로·LLM·임베딩 호출에 공통 외부 호출 한도와 계측 적용. SDK 계측은 논리 호출 수이며 실제 청구 금액은 아님.
- 서울 기준 날짜 판정. 데이터 삭제 후 브라우저의 진행 중 검색 복구 정보도 제거.
- Linux 의존성 잠금 파일, Docker 빌드, GitHub Actions의 SQLite/PostgreSQL·브라우저·컨테이너 검사 구성.
- Cloud SQL·Secret Manager·백그라운드 CPU를 사용하는 Cloud Run 운영 배포 문서 작성.

## 최종 자동 검사

| 환경 | 결과 | 비고 |
|---|---|---|
| Windows Python 3.13 / SQLite | 260 passed, 1 skipped / 64.34초 | PostgreSQL 전용 검사만 제외 |
| Windows Python 3.13 / PostgreSQL 17 | 257 passed, 4 skipped / 65.13초 | SQLite 파일 백업·복원 검사만 제외 |
| Docker Linux Python 3.12 이미지 | 빌드 성공 | requirements-cloud.lock.txt 사용 |
| 의존성 검사 | 로컬·컨테이너 pip check 통과 | 깨진 의존성 없음 |
| 빈 실행 디렉터리 초기화 | 통과 | 실제 장소 159건 및 양쪽 모드의 근거 문서 색인 |
| 이미지 비밀 파일 확인 | `/app/.env` 없음 | .dockerignore와 명시적 COPY 적용 |

브라우저 회귀 검사에는 고정·교체·되돌리기, 질문, 후기 작성/삭제, 피드백, 개인 데이터 삭제, 공유·철회, 주소 선택, 잘못된 입력, 뒤로/앞으로 이동, 늦게 도착한 응답의 화면 덮어쓰기 방지가 포함된다. 자동 브라우저는 Edge이며 모바일은 화면 크기 모의 검사다.

## 두 컨테이너 + 공유 PostgreSQL

`compose.test.yaml`과 `scripts/check_cloud_containers.py`로 다음을 통과했다.

1. 운영 모드 보안 쿠키, API 문서 비공개, 장소·문서 색인 초기화.
2. 서버 A에서 검색 시작 → 서버 B에서 진행·완료 조회와 일정 읽기.
3. 다른 브라우저의 원본 일정 접근 차단, 공유용 정보 조회.
4. 대화·후기 저장.
5. 두 서버를 모두 재시작한 뒤 기존 쿠키로 일정·후기·대화 조회.
6. 서버 B에서 데이터 삭제 → 서버 A에서도 일정과 공유 링크 조회 차단.

테스트는 격리된 가상 데이터와 테스트 DB만 사용했다. 테스트 컨테이너는 검사 후 종료·정리한다.

## 실제 외부 연동과 화면

- 네이버 지역·이미지·블로그·주소·자동차 경로 API: 10월 25일 실제 호출에서 모두 HTTP 200 및 응답 내용 확인.
- 실제 공개 지역의 코스 생성: 3개 코스, 각각 실제 장소 3곳·시간표·비용·소유자 조회 확인. 대표 실행 6,818ms이며 평균 성능이나 부하 처리량은 아니다.
- 10월 26일 실제 Edge 화면: 공개 주소 검색·지도 선택·코스 3개 생성·사진 자료 5/2/5장 조회, JavaScript 오류 없음.
- 화면 폭 390·768·1440px에서 가로 넘침 없음. 데스크톱·모바일 캡처 육안 확인.
- 메뉴: 중단 전 실행에서는 두 업체의 숫자 메뉴 16개·20개 조회. **10월 26일 재검사에서는 공개 검색 원문 HTTP 403으로 메뉴 조회 불가.** 앱은 실패 안내와 출처 링크를 제공한다. 차단을 우회하거나 가격을 만들어 채우지 않았다.
- 실제 LLM 생성과 의미 임베딩은 미검증이다. 가상 응답과 실제 모델 검증을 구분한다.

스크린샷·실행 로그·JSON 결과는 Git에서 제외한 `runtime/live-browser-check/`에 있다. 검사 도구는 운영 DB를 사용하지 않고, 임시 서버와 Windows 자식 프로세스까지 종료한 뒤 정상 종료했다.

## 재실행

저장소 루트:

```powershell
.\datemate\.venv\Scripts\python.exe -m pytest datemate/tests -q
docker compose -f compose.test.yaml up -d --build
.\datemate\.venv\Scripts\python.exe datemate/scripts/check_cloud_containers.py
docker compose -f compose.test.yaml down --volumes
.\datemate\.venv\Scripts\python.exe datemate/scripts/check_live_browser.py
```

실제 화면 검사는 8000번 포트가 비어 있어야 하며 설정된 네이버 API를 호출한다. PostgreSQL 전체 테스트는 **테스트 DB 주소만** `DATEMATE_TEST_DATABASE_URL`로 전달한다. 검사마다 별도 스키마를 만든다.

## 실제 공개 전에 남은 외부 설정

Cloud 프로젝트·Cloud SQL·백업/PITR·Secret Manager·서비스 계정 권한·네이버 운영 도메인 등록이 필요하다. [배포 안내](cloud-run-deployment.md)를 따른다. 실제 Cloud Run IAM·TLS·Cloud SQL 복원, 대규모 부하, 실제 모바일 기기·Safari는 이번 검증 범위에 포함되지 않는다. GitHub Actions 구성은 추가했지만 원격 실행 결과를 확인한 것은 아니다.

로그인·기기 간 계정 복구는 구현하지 않았다. 사용자는 브라우저 쿠키로 식별된다. 위치·대화 등의 운영 보관 정책과 운영자 연락처는 실제 서비스 기준으로 정해야 한다.
