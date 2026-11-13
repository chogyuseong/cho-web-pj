# 데이트메이트

**지역·시간·예산·취향을 바탕으로 전국 데이트 코스를 추천하고, 그날 그 지역의 축제까지 함께 보여주는 웹 서비스**입니다. 장소 사진과 블로그 검색 결과, 예상 비용, 이동 정보를 한 화면에서 확인할 수 있습니다.

> 다른 컴퓨터에서 클론해 바로 이어서 작업하려면 [배포-이어가기.txt](배포-이어가기.txt)를 먼저 보세요.

## 주요 기능

- **맞춤 코스 추천**: 꼭 정할 것은 지역 하나입니다. 인기 동네 칩이나 "현재 위치"로 한 번에 고르고, 목록에 없는 곳은 "다른 곳 찾기"(주소 검색·지도)로 고릅니다. 날짜·시간·예산·인원·장소 수·교통은 기본값이 요약 한 줄로 보이고 "바꾸기"에서 칩이나 "직접" 입력으로 고칩니다. 다시 방문하면 "지난번처럼 추천" 한 번으로 같은 조건을 쓸 수 있습니다. 실제 장소 코스는 전국 17개 시·도 중 선택한 시·도 안의 장소만 사용합니다. 가상 장소 데모는 서울만 지원합니다.
- **축제 연계**: 코스를 추천받으면 같은 지역·같은 방문일에 열리는 축제·행사를 결과 화면에 함께 보여줍니다(한국관광공사 자료, 사진 포함). 결과 제목 옆 버튼으로 축제 구역으로 바로 이동합니다.
- **대안 비교**: 최대 3개 옵션을 비교하고 장소 고정·교체·되돌리기를 지원합니다. 후보가 부족하면 조건을 단계적으로 넓혀 찾고 변경 사항을 표시합니다.
- **장소 둘러보기**: 시·도와 활동을 고르거나 검색어를 넣으면 네이버 지역 검색 결과를 중복 제거해 보여줍니다. 요청할 때 조회하며 전체 인기순·평점순 목록은 아닙니다.
- **테마별 시작**: 서울 성수, 부산 해운대, 제주 애월, 경주 황리단길, 전주 한옥마을, 강릉 안목해변 카드를 누르면 지역과 분위기가 코스 조건에 채워집니다.
- **사진·후기·가격 근거**: 장소 사진을 좌우로 넘기고 블로그 검색 결과와 메뉴·가격 출처를 확인합니다. 확보하지 못한 자료는 미확인으로 표시합니다.
- **주변 식당·레저**: 코스 주변 식당과 거리 정보를 제공합니다. 결과창에서 각 장소 주변 스포츠 후보를 골라 해당 방문지를 교체할 수 있습니다.
- **일정 활용**: 일정 질문, 코스 카드 PNG 저장, 링크 공유, 인쇄/PDF, 서비스 자체 후기를 지원합니다.

## 빠른 실행

Windows PowerShell / Python 3.12 기준입니다. **저장소 최상위 폴더에서** 실행하세요.

```powershell
cd datemate
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

`datemate/.env`에 사용할 API 키를 입력합니다. 기존 `.env`는 덮어쓰지 않습니다. 키 없이도 서울 가상 데이터로 시연할 수 있지만, 실제 장소 검색에는 네이버 검색 API 설정이 필요합니다.

| 키 | 용도 | 발급처 |
| --- | --- | --- |
| `NAVER_SEARCH_CLIENT_ID`, `NAVER_SEARCH_CLIENT_SECRET` | 장소·이미지·블로그 검색 | NAVER API HUB의 NAVER 검색 |
| `NAVER_MAPS_KEY_ID`, `NAVER_MAPS_KEY` | 주소 검색, 자동차 길찾기 | 네이버 클라우드 플랫폼 Maps |
| `NAVER_MAPS_JS_KEY_ID` | 브라우저 네이버 지도 | 같은 콘솔의 Dynamic Map (접속 주소 등록 필요) |
| `TOUR_API_KEY` | 축제 조회 | 공공데이터포털 "한국관광공사_국문 관광정보 서비스_GW" 일반 인증키(Decoding) |

테스트까지 돌리려면 `requirements.txt` 대신 `requirements-dev.txt`를 설치하세요. `requirements.txt`는 운영 실행에 필요한 것만 담고 있습니다.

```powershell
.\.venv\Scripts\python.exe scripts/index_data.py --mode demo
.\.venv\Scripts\python.exe scripts/index_data.py --mode real
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- 웹사이트: <http://127.0.0.1:8000>
- API 문서: <http://127.0.0.1:8000/docs>
- 기능별 연결 상태: <http://127.0.0.1:8000/api/status>
- 종료: 실행 터미널에서 `Ctrl+C`

자세한 키 설정과 키 없는 데모 실행은 [실행·설정 안내](datemate/README.md)를 참고하세요.

## 기술 구성

| 영역 | 사용 기술 |
| --- | --- |
| 웹 화면 | HTML, CSS, JavaScript, 반응형 UI |
| 서버 | Python, FastAPI, Uvicorn |
| 저장 | 로컬 SQLite / 운영 PostgreSQL, 공유 캐시·세션 |
| 검색·질문 | ChromaDB, LangChain. LLM 키(`GMS_KEY`)는 선택이며 없으면 규칙 기반으로 동작 |
| 외부 정보 | 네이버 검색 API, Maps API, 한국관광공사 관광정보 API(축제), 공개 장소 자료, 네이버 자동차 길찾기 (도보·대중교통은 추정 시간) |
| 지도 | 네이버 지도, Leaflet/OpenStreetMap 대체 지도 |
| 운영 배포 | Cloudflare Worker + Containers, 외부 PostgreSQL |

## Cloudflare 배포 현황

**2026-11-12에 운영 배포했습니다: <https://datemate.guseong-family.workers.dev>**

FastAPI 앱은 Cloudflare Containers(Workers Paid 플랜)에서 실행하고 Worker가 공개 요청을 전달합니다. 상시 실행할 개인 Docker 서버는 필요하지 않고, Docker는 배포할 이미지를 만들 때만 씁니다. 10분쯤 접속이 없으면 컨테이너가 꺼지며, 다음 첫 접속은 20~40초 걸립니다.

운영 데이터는 `DATABASE_URL`로 연결한 **Neon PostgreSQL**(무료 플랜)에 저장합니다. Cloudflare D1을 PostgreSQL 대신 설정만 바꿔 연결할 수는 없습니다. 컨테이너의 Chroma 장소·문서 색인은 시작 시 다시 만들며, PostgreSQL 백업은 DB 제공자에서 별도로 설정해야 합니다.

배포하면서 확인한 내용입니다.

- **컨테이너 위치**: 처음에는 한국에서 먼 지역에 떠서 DB를 쓰는 요청이 2~3초 걸리고 축제 조회가 시간 초과로 실패했습니다. Worker가 Durable Object를 아시아(`locationHint: "apac"`)에 만들도록 바꾼 뒤 서버 처리 시간이 0.06초 수준으로 줄었습니다.
- **Secret**: `PUBLIC_ORIGIN`, `DATABASE_URL`, 네이버 검색·지도 키, `TOUR_API_KEY`를 Worker Secret으로 등록했습니다. 키는 Git·빌드 변수·이 문서에 두지 않습니다.
- **네이버 지도**: 네이버 클라우드 콘솔의 Dynamic Map Web 서비스 URL에 배포 주소를 등록해 지도 인증이 통과합니다.
- **동작 확인**: 공개 주소에서 코스 추천, 축제(요금 포함), 축제 주변 코스, 장소 둘러보기를 브라우저로 확인했습니다.
- **재배포**: 저장소 최상위에서 Docker를 켠 뒤 `npx wrangler deploy`. 새 버전은 떠 있던 컨테이너가 꺼진 뒤(10분쯤 접속이 없어야 함)에야 응답에 나옵니다. 자세한 확인 방법은 [배포-이어가기.txt](배포-이어가기.txt) 8번에 있습니다.

### 보안

배포 후 전체 보안 점검을 했습니다. 권한 우회, XSS, SQL 주입, SSRF, Git 이력의 비밀값은 발견되지 않았고, 자원 고갈과 제한 우회 문제를 고쳤습니다.

- 모든 입력에 길이 상한, 요청 본문 64KiB, 저장되는 코스 1건 300KB 상한
- 요청 제한을 세션과 접속 IP 범위(IPv6는 /64) 양쪽에 적용, IP 범위별 외부 호출 몫 제한
- 세션은 `/api/` 요청에서만 발급하고 쿠키는 `HttpOnly; Secure; SameSite=Lax`
- 공개 요청의 `/healthz`, `/readyz` 차단, 전역 잠금 대기 시간 제한

한도 이름과 기본값은 [datemate/.env.example](datemate/.env.example)의 `DATEMATE_IP_*` 항목에 있습니다. 운영에는 기본값이 적용돼 있고, 바꾸려면 `cloudflare/worker.js`가 컨테이너에 넘기는 환경변수에 추가한 뒤 재배포합니다. 같은 IP를 함께 쓰는 사용자는 한도를 나눠 씁니다.

**2차 수정(커밋 `f794796`)은 2026-11-12에 운영에 배포했습니다.** 배포 후 확인 결과와 롤백 주의점은 [배포-이어가기.txt](배포-이어가기.txt) 맨 위에 있습니다.

- 세션 토큰을 DB에 SHA-256 해시로만 저장하고 운영 쿠키 이름을 `__Host-dm_session`으로 변경. 기존 세션은 마이그레이션으로 유지되며, 이 변환은 되돌릴 수 없습니다.
- 90일 동안 이용이 없는 세션과 그 데이터를 자동 삭제(`DATEMATE_RETENTION_DAYS`). 공개 후기는 남기고 작성자 연결만 끊습니다.
- CSP에 `default-src 'self'`와 종류별 허용 출처를 추가. 실제 브라우저에서 위반 0건을 확인했습니다.
- Cloudflare Worker가 컨테이너를 깨우기 전에 IP별 요청 제한을 먼저 적용(화면·API 60초 600회, 정적 파일 1200회)
- 운영 이미지에서 `pytest`·`pypdf` 제외, CI에 Python 의존성 취약점 검사(`pip-audit`) 추가

남은 과제는 DB 앱 전용 계정 교체입니다.

운영 요청에는 출처 검사, 브라우저 스크립트 실행 정책(CSP), 세션 응답 캐시 방지가 적용됩니다. PostgreSQL 연결은 `sslmode=require`, `verify-ca`, `verify-full` 중 하나가 필수입니다. 수정 가능한 의존성 경고는 반영했고, npm 감사는 취약점 0건입니다. **ChromaDB 1.5.9에는 수정 버전이 없는 보안 공지가 남아 있습니다.** 현재 앱은 Chroma를 컨테이너 내부 `PersistentClient`로만 사용하며 Chroma HTTP 포트를 공개하지 않습니다. 해당 포트나 원격 모델 실행 기능을 추가할 때는 보안을 다시 검토해야 합니다.

배포 준비 시점 커밋 `0473e48`의 [GitHub Actions 검사](https://github.com/chogyuseong/cho-web-pj/actions/runs/43148595094)는 보안 검사, SQLite·PostgreSQL 테스트, 컨테이너 통합 검사를 모두 통과했습니다. 배포 설정과 Secret 등록 절차는 [Cloudflare 배포 안내](datemate/docs/cloudflare-deployment.md)에 있습니다.

## 데이터와 검증 범위

실제 장소와 가상 시연 데이터를 구분합니다. 축제·행사 정보와 사진은 한국관광공사 자료이며, 사진은 공공누리 제1·제3유형만 출처를 표기해 원본 그대로 보여줍니다. 개최·취소·시간·요금은 방문 전 주최 측 안내를 확인해야 합니다. 네이버 평점·방문자 수는 공식 검색 API에서 확보하지 않으며, 인기나 별점을 임의로 생성하지 않습니다. 이동 시간·비용에는 추정이 포함될 수 있고 영업시간·휴무·예약·실시간 가격을 보장하지 않습니다. 검색 사진과 블로그 원문의 권리는 각 제공자에게 있으며 출처 링크를 제공합니다.

모바일 브라우저 모의 환경에서 추천·조건 수정·옵션 전환·사진·장소 탐색·저장을 점검했습니다. 실기기와 iOS Safari 전체 검증을 완료했다는 의미는 아닙니다. 외부 API의 결과와 응답 가능 여부는 권한·네트워크·제공자 정책에 영향을 받습니다.

## 문서

날짜가 붙은 문서는 해당 시점의 기록입니다. 서울 전용, TMAP 연동, 장소 500곳 수집 등 지금은 바뀐 내용이 남아 있습니다.

- [다른 컴퓨터에서 이어서 작업하기·배포 이어가기](배포-이어가기.txt)
- [사용자 제공 디자인 적용·PC/모바일 확인](datemate/docs/design-import-2026-10-30.md)

- [데이트 플랜 기능 오류 수정·PC/모바일 점검](datemate/docs/results-functional-audit-2026-10-29.md)

- [상세 실행·환경변수·테스트](datemate/README.md)
- [디자인 선정 근거](datemate/docs/reference-design-selection.md)
- [모바일 점검 기록](datemate/docs/mobile-check-2026-10-23.md)
- [결과창 주변 레저 선택](datemate/docs/leisure-selection.md)
- [(과거 방식) 장소 500곳 탐색](datemate/docs/explore-500.md)
- [Cloudflare 전체 앱 배포 안내](datemate/docs/cloudflare-deployment.md)
- [추천 서비스·DB 마이그레이션·프런트엔드 구조 개선](datemate/docs/architecture-improvements-2026-10-26.md)
- [2026-10-26 전체 기능·코드 점검 및 오류 수정 결과](datemate/docs/full-functional-code-audit-2026-10-26.md)
- [코스 결정·공동 선택·선택적 효과 측정](datemate/docs/planning-outcomes-2026-10-29.md)
- [운영 자료·공급처·동선·피드백·비용·인수인계 개선](datemate/docs/improvements-three-eight-2026-10-29.md)
- [운영 점검·격리 복원 훈련·메뉴 자료 반영 방법](datemate/docs/operations-handoff.md)

운영 자료는 항목별 출처·확인일·유효기간으로 관리합니다. 업체 제공 메뉴를 가져오는 도구와 요청별 외부 호출 제한을 제공합니다. 도보·대중교통은 추정 시간으로 표시하며 실제 경로 공급자는 연결하지 않습니다. 사진·자료·API의 사용 및 양도 범위는 제공처별 확인이 필요합니다.

`.env`, 가상환경, `runtime/`은 Git에 포함하지 않습니다. 로컬 개발은 SQLite를 사용합니다. `compose.test.yaml`은 운영 키 없이 두 인스턴스와 PostgreSQL을 검증하는 로컬 전용 구성입니다.
