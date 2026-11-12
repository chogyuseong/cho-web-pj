# 데이트메이트 — 실행 및 설정

프로젝트 소개와 주요 기능은 [저장소 README](../README.md)를 참고하세요. 아래 명령은 `datemate` 폴더에서 실행합니다.

## 1. 환경 준비

검증 환경: Windows PowerShell, Python 3.12. 가상환경을 활성화하지 않고 Python 실행 파일을 직접 사용합니다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

테스트까지 돌리려면 `requirements.txt` 대신 `requirements-dev.txt`를 설치합니다. 이미 가상환경과 `.env`가 있으면 재생성하지 않아도 됩니다. 공유용 `.env.example`에는 실제 키를 적지 마세요.

## 2. API 설정

기본 설정 파일은 `datemate/.env`입니다. 서버 환경변수도 사용할 수 있습니다. `DATEMATE_ENV_FILE`을 지정하면 설정 파일 경로를 변경할 수 있습니다. 키 변경 후 서버를 재시작하세요.

| 변수 | 용도 | 필요 조건 |
| --- | --- | --- |
| `NAVER_SEARCH_CLIENT_ID`, `NAVER_SEARCH_CLIENT_SECRET` | 장소·블로그·이미지 검색 | 현재 구현은 NAVER API HUB의 NAVER 검색 엔드포인트 사용. 발급 Application에서 지역·블로그·이미지 권한 활성화 |
| `NAVER_MAPS_KEY_ID`, `NAVER_MAPS_KEY` | 주소 검색, 역지오코딩, 자동차 경로 | 해당 Maps API 사용 권한 |
| `NAVER_MAPS_JS_KEY_ID` | 브라우저 네이버 지도 | Dynamic Map 활성화 및 접속 Web 서비스 URL 등록 |
| `TOUR_API_KEY` | 코스 결과에 함께 보여주는 축제·행사 조회 | 공공데이터포털 "한국관광공사_국문 관광정보 서비스_GW" 활용신청 후 일반 인증키(Decoding). `%`가 들어간 Encoding 키는 인증 실패 |
| `GMS_KEY` (선택) | LLM 답변·조건 해석, 블로그 글 장소 추출, 후기 사진 내용 검사, 의미 임베딩 | `.env.example`에는 없는 선택 항목. 넣을 때만 동작 |
| `GMS_BASE_URL`, `GMS_MODEL` (선택) | GMS 연결 주소·모델 | 비우면 코드의 기본값 사용 |
| `EMBEDDING_MODE` | `demo`: 문자 해시 / `real`: 의미 임베딩 | `real` 사용 시 키·모델 권한 및 재색인 필요 |
| `EMBEDDING_MODEL` | 의미 임베딩 모델 | 계정에서 사용 가능한 모델 |

일반 NAVER Developers용 키와 NAVER API HUB용 키를 혼동하지 마세요. 현재 서버가 호출하는 API의 발급 키를 사용해야 합니다. 서버 비밀키는 브라우저에 전달하지 않으며, 지도 JS용 공개 클라이언트 ID는 브라우저에서 사용합니다.

그 밖의 타일 주소·청크 크기 등은 [.env.example](.env.example)에 있습니다. 실제 장소 코스는 전국 17개 시·도를 지원하고, 가상 장소 데모는 서울만 지원합니다.

로컬(`http://127.0.0.1:8000`, `http://localhost:8000`)에서 네이버 지도를 쓰려면 Dynamic Map의 Web 서비스 URL에 그 주소를 등록해야 합니다. 넣은 키의 실제 동작은 `scripts/check_external_integrations.py`로 제공자별 1회씩 확인할 수 있습니다.

### 키가 없는 경우

- 실제 네이버 장소·블로그·이미지 검색은 제한됩니다. 사진은 다른 공개 출처가 있는 장소만 표시될 수 있습니다.
- 네이버 지도 JS 키가 없으면 위치 선택에 Leaflet/OpenStreetMap을 사용합니다. 지도 타일에는 인터넷 연결이 필요합니다.
- `TOUR_API_KEY`가 없으면 축제 구역에 키 미설정 안내만 표시하고 코스 추천은 그대로 동작합니다.
- GMS 키가 없으면 규칙 기반 답변을 사용하며, 실제 LLM 답변으로 표시하지 않습니다.
- 기본 임베딩 `demo`는 문자 bigram 해시로, 의미 임베딩이 아닙니다.
- API로 만든 가상 시연 일정은 실제 방문할 수 있는 장소가 아닙니다.

## 3. 색인 및 서버 실행

배포된 장소·문서 JSON으로 초기 색인을 생성합니다. 기본 실행을 위해 장소를 다시 수집할 필요는 없습니다.

```powershell
.\.venv\Scripts\python.exe scripts/index_data.py --mode demo
.\.venv\Scripts\python.exe scripts/index_data.py --mode real
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

<http://127.0.0.1:8000>에 접속합니다. `/docs`에서 API를 확인하고 `/api/status`에서 키·색인 상태를 확인합니다. 종료는 `Ctrl+C`입니다. 개발 중 자동 재시작이 필요하면 서버 명령 뒤에 `--reload`를 추가하세요.

의미 임베딩으로 전환했다면 `EMBEDDING_MODE=real` 설정 후 위 두 색인을 다시 만들고 서버를 재시작하세요. 해시 색인과 의미 색인은 분리합니다.

### 키 없이 API로 데모 확인

서버를 켠 상태에서 새 PowerShell 터미널에서 실행합니다. 반환되는 이름에 ‘가상’이 표시되며 실제 장소 추천이 아닙니다.

```powershell
$demoBody = @{ visit_date = (Get-Date).AddDays(1).ToString('yyyy-MM-dd'); mode = 'demo' } | ConvertTo-Json
$demo = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/plans' -Method Post -ContentType 'application/json' -Body $demoBody
$demo.plans | Select-Object id, finish, minutes
```

일반 웹 입력 화면은 실제 장소 검색을 기본으로 합니다. 위 API 데모는 외부 키가 없는 환경에서 계산 로직을 확인하는 용도입니다.

## 4. 사용 흐름

1. 원하는 지역의 주소를 검색하거나 지도에서 위치를 선택합니다. 시·도는 고른 주소에 맞춰 자동으로 정해집니다. 테마 카드를 눌러 지역과 분위기를 한 번에 채울 수도 있습니다.
2. 방문 날짜·시간·전체 예산과 원하는 활동을 입력합니다. 인원·교통 등은 선택 설정에서 바꿉니다.
3. 추천받은 최대 3개 옵션의 장소·비용·이동·조건 차이를 비교합니다. 같은 지역·방문일의 축제·행사가 결과 아래에 함께 나오며, 결과 제목 옆 버튼으로 바로 이동합니다.
4. 사진·블로그 검색 결과·메뉴 근거를 확인하고, 원하는 장소를 고정하거나 교체합니다.
5. 추천 근거와 상세 일정 사이의 **이 동선에서 즐길 레저 골라보기**에서 방문지별 항목을 펼쳐 반경 1.5km의 스포츠 후보를 확인합니다. 선택 시 해당 방문지만 교체하며 다른 방문지는 유지합니다. 고정한 장소는 먼저 해제해야 합니다.
6. 코스 카드 PNG 저장, 링크 공유 또는 인쇄/PDF로 일정을 활용합니다.

후보 부족 시 조건을 단계적으로 넓혀 찾고 차이를 표시하지만 결과를 항상 보장하지는 않습니다. 필수 조건과 제외 활동은 별도 검사합니다. 레저 후보의 거리는 직선거리이며 영업·예약 여부는 별도 확인해야 합니다.

## 5. 데이터와 한계

| 구분 | 동작과 한계 |
| --- | --- |
| 장소 | 로컬 실제 장소 자료와 네이버 검색으로 확보한 장소·캐시를 사용. 가상 데이터와 분리 |
| 장소 둘러보기 | 고른 시·도·활동·검색어로 네이버 지역 검색을 요청 시 조회(요청당 질의 16개 이하, 조건별 6시간 캐시)하고 중복 제거해 표시. 통합 인기순·평점순 목록이 아님 |
| 사진 | 장소 일치 여부를 비교해 검색 이미지·공개 장소 사진·일부 검수 자료 사용. 원본/썸네일 대체 및 실패 안내 제공. 모든 장소의 사진 확보를 보장하지 않음 |
| 블로그 | 네이버 검색 결과의 링크·검색 요약. 전체 본문이나 방문 사실을 검증한 리뷰가 아님 |
| 메뉴·가격 | 식당명과 도로명 건물번호까지 정리해 공개 자료 조회. 숫자 메뉴 또는 메뉴 이미지 제공. 확인되지 않은 가격을 만들어 채우지 않음 |
| 축제·행사 | 한국관광공사 관광정보 API에서 방문일과 개최 기간이 겹치는 항목을 조회(1시간 캐시), 기간이 짧은 행사부터 표시. 사진은 공공누리 제1·제3유형만 출처를 표기해 원본 그대로 사용. 개최·취소·시간·요금은 보장하지 않음 |
| 이동 | 직선거리와 가정 속도에 기반한 추정 포함. 자동차 실제 경로는 네이버 길찾기 연결·권한 필요. 도보·대중교통은 실제 경로 공급자 없이 추정 시간만 제공 |
| 운영정보 | 영업·휴무·예약·가격의 미확인 항목을 표시. 예상 코스는 방문 가능 여부를 보증하지 않음 |
| 평점·방문자 수 | 네이버 공식 검색 API로 확보하지 않음. 서비스 자체 후기는 외부 평점과 별개이며 방문 사실은 자기 신고 |
| 저장·공유 | SQLite와 로컬 캐시 사용. 공유 링크는 해당 서버에 접속 가능해야 사용 가능 |

사진·블로그·메뉴 원문은 각 권리자의 자료입니다. 출처 링크 표시는 모든 자료의 재사용 허가를 뜻하지 않습니다. 공개 운영 전 외부 서비스 이용 조건과 미디어 권리를 검토해야 합니다.

## 6. 테스트

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m pip check
```

전체 실행은 약 5분 걸리며 브라우저 테스트가 포함되어 Microsoft Edge가 필요합니다. 단위/API 테스트는 임시 저장소를 사용하며 외부 검색 키를 비워 실제 검색 API 사용을 막습니다. 외부 API의 현재 응답이나 모든 장소의 정보 정확성을 보증하는 검사는 아닙니다.

브라우저 검증은 서버가 켜진 상태에서 실행합니다. Playwright는 별도 개발 도구이며 아래 스크립트는 설치된 Microsoft Edge를 사용합니다.

```powershell
.\.venv\Scripts\python.exe -m pip install playwright
.\.venv\Scripts\python.exe scripts/check_editorial_design.py
.\.venv\Scripts\python.exe scripts/check_photo_carousel_ui.py
.\.venv\Scripts\python.exe scripts/check_leisure_results_ui.py
```

일부 브라우저 검증은 현재 로컬 DB에 테스트 일정을 만듭니다. 모바일 모의 환경과 실제 휴대폰 검증은 구분합니다. 위 스크립트 전체를 실기기/iOS Safari 검증으로 간주하지 마세요.

## 7. 구조 및 참고 문서

```text
app/       FastAPI, 추천·조건 검사, 검색·RAG, 가격·이동, 저장
static/    HTML / CSS / JavaScript
data/     실제·가상 장소와 문서 JSON
scripts/   색인·수집·진단·브라우저 점검
tests/     단위·API 테스트
runtime/   실행 중 DB·캐시·색인 (Git 제외)
docs/      설계·출처·기능별 검증 기록
```

- [API 문서(실행 서버)](http://127.0.0.1:8000/docs)
- [(과거 방식) 장소 탐색 500곳](docs/explore-500.md)
- [사진 복구와 한계](docs/explore-photo-recovery.md)
- [메뉴·사진 검색 주소 정규화](docs/road-address-search.md)
- [결과창 레저 선택 및 검증](docs/leisure-selection.md)
- [모바일 점검](docs/mobile-check-2026-10-23.md)
- [디자인 참고·독립 구현 기록](docs/reference-design-selection.md)
- [Cloudflare 배포 순서](docs/cloudflare-deployment.md)

기존 `docs/`의 날짜별 기록은 해당 시점의 검증 결과입니다. 초기 기록의 건수·제한은 현재 기능과 다를 수 있습니다. 현재 기능 설명은 이 README와 최신 기능별 기록을 함께 참고하세요.

운영용 저장소는 `DATABASE_URL`로 PostgreSQL을 연결하며, 로컬 개발은 SQLite를 유지합니다. 공유 검색 상태와 취소·세션·일정·후기는 외부 DB를 사용하고, Chroma 색인은 컨테이너 시작 시 재생성합니다. [Cloudflare 배포 안내](docs/cloudflare-deployment.md)를 따르세요. 공개 클라우드 배포와 계정 생성은 별도 작업입니다.
