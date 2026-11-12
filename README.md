# 서울 데이트메이트

**지역·시간·예산·취향을 바탕으로 서울 데이트 코스를 추천하고 비교하는 웹 서비스**입니다. 장소 사진과 블로그 검색 결과, 예상 비용, 이동 정보를 한 화면에서 확인할 수 있습니다.

## 주요 기능

- **맞춤 코스 추천**: 서울 지역을 주소 검색 또는 지도에서 선택하고 일시·예산·원하는 활동을 입력합니다.
- **대안 비교**: 최대 3개 옵션을 비교하고 장소 고정·교체·되돌리기를 지원합니다. 후보가 부족하면 조건을 단계적으로 넓혀 찾고 변경 사항을 표시합니다.
- **장소 탐색**: 지역·활동별 네이버 검색 결과를 중복 제거해 최대 500곳을 보여줍니다. 네이버 전체 인기순 500위 목록은 아닙니다.
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

`datemate/.env`에 사용할 API 키를 입력합니다. 기존 `.env`는 덮어쓰지 않습니다. 키 없이도 가상 데이터로 시연할 수 있지만, 실제 네이버 장소 검색에는 검색 API 설정이 필요합니다.

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
| 검색·질문 | ChromaDB, LangChain, 선택적 GMS LLM/임베딩 연결 |
| 외부 정보 | 네이버 검색 API, Maps API, 공개 장소 자료, 선택적 TMAP 도보·대중교통 연결 |
| 지도 | 네이버 지도, Leaflet/OpenStreetMap 대체 지도 |
| 운영 배포 | Cloudflare Worker + Containers, 외부 PostgreSQL |

## Cloudflare 배포 현황

**2026-11-12 기준: 배포용 코드와 검증은 완료했고, 실제 운영 배포는 아직 하지 않았습니다.** FastAPI 앱은 Cloudflare Containers에서 실행하고 Worker가 공개 요청을 전달합니다. 상시 실행할 개인 Docker 서버는 필요하지 않습니다. Cloudflare Workers Builds를 쓰면 이미지도 Cloudflare에서 빌드하므로 로컬 Docker 실행 없이 배포할 수 있습니다.

운영 데이터는 `DATABASE_URL`로 연결한 **외부 관리형 PostgreSQL**에 저장합니다. Cloudflare D1을 PostgreSQL 대신 설정만 바꿔 연결할 수는 없습니다. 컨테이너의 Chroma 장소·문서 색인은 시작 시 다시 만들며, PostgreSQL 백업은 DB 제공자에서 별도로 설정해야 합니다.

실제 배포 전에 남은 작업은 다음과 같습니다.

1. Cloudflare Workers Paid 플랜과 외부 접속 가능한 PostgreSQL을 준비하고, 앱 전용 DB 계정·백업을 설정합니다.
2. Cloudflare Workers Builds에 이 저장소를 연결하고 저장소 루트의 `wrangler.jsonc`, `Dockerfile`로 빌드합니다.
3. Worker Secret에 실제 HTTPS 주소 `PUBLIC_ORIGIN`과 TLS를 필수로 하는 `DATABASE_URL`을 등록합니다. 실제 장소 검색을 쓰려면 네이버 API 키도 등록합니다.
4. 배포 후 `/readyz`, `/api/status`, 추천·공유 동작을 공개 주소에서 확인합니다.

운영 요청에는 출처 검사, 브라우저 스크립트 실행 정책(CSP), 세션 응답 캐시 방지가 적용됩니다. PostgreSQL 연결은 `sslmode=require`, `verify-ca`, `verify-full` 중 하나가 필수입니다. 수정 가능한 의존성 경고는 반영했고, npm 감사는 취약점 0건입니다. **ChromaDB 1.5.9에는 수정 버전이 없는 보안 공지가 남아 있습니다.** 현재 앱은 Chroma를 컨테이너 내부 `PersistentClient`로만 사용하며 Chroma HTTP 포트를 공개하지 않습니다. 해당 포트나 원격 모델 실행 기능을 추가할 때는 보안을 다시 검토해야 합니다.

최근 커밋 `0473e48`의 [GitHub Actions 검사](https://github.com/chogyuseong/cho-web-pj/actions/runs/43148595094)는 보안 검사, SQLite·PostgreSQL 테스트, 컨테이너 통합 검사를 모두 통과했습니다. 배포 설정과 Secret 등록 절차는 [Cloudflare 배포 안내](datemate/docs/cloudflare-deployment.md)에 있습니다.

## 데이터와 검증 범위

실제 장소와 가상 시연 데이터를 구분합니다. 네이버 평점·방문자 수는 공식 검색 API에서 확보하지 않으며, 인기나 별점을 임의로 생성하지 않습니다. 이동 시간·비용에는 추정이 포함될 수 있고 영업시간·휴무·예약·실시간 가격을 보장하지 않습니다. 검색 사진과 블로그 원문의 권리는 각 제공자에게 있으며 출처 링크를 제공합니다.

모바일 브라우저 모의 환경에서 추천·조건 수정·옵션 전환·사진·장소 탐색·저장을 점검했습니다. 실기기와 iOS Safari 전체 검증을 완료했다는 의미는 아닙니다. 외부 API의 결과와 응답 가능 여부는 권한·네트워크·제공자 정책에 영향을 받습니다.

## 문서

- [사용자 제공 디자인 적용·PC/모바일 확인](datemate/docs/design-import-2026-10-30.md)

- [데이트 플랜 기능 오류 수정·PC/모바일 점검](datemate/docs/results-functional-audit-2026-10-29.md)

- [상세 실행·환경변수·테스트](datemate/README.md)
- [디자인 선정 근거](datemate/docs/reference-design-selection.md)
- [모바일 점검 기록](datemate/docs/mobile-check-2026-10-23.md)
- [결과창 주변 레저 선택](datemate/docs/leisure-selection.md)
- [장소 500곳 탐색 방식](datemate/docs/explore-500.md)
- [Cloudflare 전체 앱 배포 안내](datemate/docs/cloudflare-deployment.md)
- [추천 서비스·DB 마이그레이션·프런트엔드 구조 개선](datemate/docs/architecture-improvements-2026-10-26.md)
- [2026-10-26 전체 기능·코드 점검 및 오류 수정 결과](datemate/docs/full-functional-code-audit-2026-10-26.md)
- [코스 결정·공동 선택·선택적 효과 측정](datemate/docs/planning-outcomes-2026-10-29.md)
- [운영 자료·공급처·동선·피드백·비용·인수인계 개선](datemate/docs/improvements-three-eight-2026-10-29.md)
- [운영 점검·격리 복원 훈련·메뉴 자료 반영 방법](datemate/docs/operations-handoff.md)

운영 자료는 항목별 출처·확인일·유효기간으로 관리합니다. 업체 제공 메뉴를 가져오는 도구와 요청별 외부 호출 제한을 제공합니다. TMAP 연결은 해당 상품 키 설정 후 사용하며, 키가 없는 현재 환경에서는 실제 도보·대중교통 경로가 연결됐다고 표시하지 않습니다. 사진·자료·API의 사용 및 양도 범위는 제공처별 확인이 필요합니다.

`.env`, 가상환경, `runtime/`은 Git에 포함하지 않습니다. 로컬 개발은 SQLite를 사용합니다. `compose.test.yaml`은 운영 키 없이 두 인스턴스와 PostgreSQL을 검증하는 로컬 전용 구성입니다.
