# 서울 데이트메이트

서울특별시 내 장소만 검색·추천하는 한국어 데이트 일정 비교 서비스입니다. 서비스 지역은 서울 25개 자치구로 고정하며 경기·인천 등 다른 지역의 장소는 카탈로그에서 제외합니다. 출발지·귀가지는 방문 장소와 구분하므로 서울 밖 위치도 사용할 수 있습니다. 웹사이트와 무관한 상위 Streamlit 실습 파일·중복 가상환경은 사용자 요청으로 정리했습니다. 실행 환경과 키는 이 폴더의 `.venv`, `.env`를 사용합니다.

**현재 실행 범위:** 키 없는 가상 장소 일정 생성·교체·비용 계산·후기·대화와 실제 장소 자료 열람이 가능합니다. GMS 키는 비워 두었습니다. 실제 LLM/의미 임베딩·네이버 지도/자동차 경로는 키를 넣은 뒤 별도 검증이 필요합니다. 실제 장소의 운영정보가 부족한 상황에서는 검증된 방문 일정을 만들어 내지 않습니다.

## 빠른 실행 (Windows PowerShell)

VS Code에서 `streamlit_lab`을 열었다면:

```powershell
cd C:\Users\SSAFY\Desktop\streamlit_lab\datemate
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# .env의 GMS_KEY는 지금은 빈 값으로 둡니다.
.\.venv\Scripts\python.exe scripts/seed_demo.py
.\.venv\Scripts\python.exe scripts/index_data.py --mode demo
.\.venv\Scripts\python.exe scripts/index_data.py --mode real
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

이미 만들어 둔 `.venv`가 있으면 생성·설치 단계는 생략할 수 있습니다. `.env`가 있으면 덮어쓰지 말고 누락 설정만 추가하세요. 활성화 스크립트 실행 정책을 바꿀 필요 없이 위 Python 경로를 직접 사용합니다. 확인한 환경은 Python 3.12 / Windows입니다. 소스는 Python 3.10+ 문법을 사용하지만 다른 Python 버전의 의존성 설치는 별도 검증하지 않았습니다.

- 웹사이트: <http://127.0.0.1:8000>
- API 명세 및 실행: <http://127.0.0.1:8000/docs>
- 상태/실제 색인 수: <http://127.0.0.1:8000/api/status>
- 서버 종료: 실행한 터미널에서 `Ctrl+C`

방문일은 2026-10-24, 시작 11:00, 종료 19:00, 2명, 예산 100,000원, 도보, 3곳으로 시연했습니다. 장소 고정 → 다른 장소 교체 → 되돌리기 → 장소 질문 → 후기 작성·삭제 순서로 확인할 수 있습니다. 추천을 다시 누르면 고정한 순서의 장소를 유지합니다.

## 데이터와 동작의 구분

### 장소 사진 (2026-10-22 추가)

일정 타임라인·장소 상세·실제 장소 목록에서 사진과 설명을 함께 제공합니다. 실제 장소 ID의 공개 대표 이미지와 이용 조건을 확인하며 별도 사진 API 키는 필요하지 않습니다. 최초 사진 조회에는 인터넷 연결이 필요합니다. 가상 장소는 실제 사진을 표시하지 않습니다. 현재 실제 일정 생성은 운영정보 부족으로 제한되므로, 실사진을 바로 보려면 **서울 장소 둘러보기**에서 실제 장소를 선택하세요. [사진 기능·출처·검증 범위](docs/place-photos.md).

### 출발지·귀가지 선택

위도·경도를 직접 입력하지 않습니다. **주소 검색 · 지도에서 선택**을 눌러 위치를 고른 뒤 **이 위치를 출발지/귀가지로 사용**으로 확정하세요. 좌표는 내부에서 처리하며 실제 모드 전환 시 데모 출발지를 자동으로 해제합니다.

- 지도: 네이버 JS 키가 있으면 네이버 지도 우선. 키가 없으면 Leaflet/OpenStreetMap으로 클릭·터치 선택 가능. 인터넷 연결 필요.
- 주소 검색: 도로명 또는 지번을 입력하면 네이버 Geocoding 결과를 보여줍니다. `NAVER_MAPS_KEY_ID`, `NAVER_MAPS_KEY`와 Geocoding 사용 권한이 필요합니다. 키 누락/실패 시 지도 선택 안내.
- 주소 검색 버튼을 눌렀을 때만 검색어를 서버와 네이버에 전달하며 검색어/주소 검색 결과를 영구 캐시하지 않습니다. 확정 후 만든 일정에는 출발지/귀가지가 저장됩니다.
- 네이버 주소 검색의 실호출은 키가 없어 미검증. 결과 선택·좌표 전달은 모의 API와 단위 테스트로 검증했습니다. OpenStreetMap 지도 클릭은 실제 타일을 불러와 검증했습니다.

관련 설정·출처·검증: [위치 선택 변경 기록](docs/location-picker.md).

| 구분 | 현재 자료 | 의미 |
|---|---|---|
| 실제 장소 | 152건 | Wikidata CC0 ID·명칭·좌표·유형. 운영기관이 보증하는 최신 영업 카탈로그가 아님 |
| 실제 외부 문서 | 공식 HTML 2건 | 국립중앙박물관 관람 안내·어린이박물관 예약 안내. 전체 장소에 대한 문서를 확보한 것은 아님 |
| 가상 장소 | 28건 | 이름·운영·가격을 명시적으로 만든 테스트 데이터. 실제 152건에 포함하지 않음 |
| 가상 안내 문서 | 28건 | 데모 검색/청킹/대화 파이프라인용 |
| 로컬 색인 | ChromaDB | 실제/가상 데이터 및 해시/의미 모델별 컬렉션 분리 |
| 기본 검색 | 문자 bigram 해시 | 네트워크 없는 동작 확인용. 의미 임베딩이라고 주장하지 않음 |
| 기본 답변 | 규칙 기반 메타데이터 응답 | 실제 LLM 생성 아님. 알 수 없는 질문에는 확인 불가 표시 |
| 기본 경로 | 직선거리 / 가정 속도 | 실제 경로 아님. 실제 모드는 미지원/키 없음 시 계산 불가 |
| 사진 | 검수 사진 3곳 + 공개 대표 이미지 동적 조회 | 출처·촬영자·라이선스 표시. 없는 장소는 빈 상태 |
| 영상·외부 평점 | 미확보 | 빈 상태, 원문/검색 링크 제공. 가짜 영상·리뷰·평점 없음 |

실제 장소의 가격·시간·예약·휴무는 `null`이며 자료가 확인되지 않았다는 뜻입니다. 공식 문서의 내용과 정규화된 일정 필드는 별개입니다. 날짜별 운영시간·예외일·요금 적용 조건을 검수하여 구조화하기 전까지 실제 일정 검증에 사용하지 않습니다.

## 실제 API 설정

`datemate/.env`만 읽습니다. 비밀값은 서버 환경변수에 넣으며 브라우저에 전달하지 않습니다.

```dotenv
GMS_KEY=
GMS_BASE_URL=https://gms.ssafy.io/gmsapi/api.openai.com/v1/
GMS_MODEL=gpt-5.4-nano
EMBEDDING_MODE=demo
EMBEDDING_MODEL=text-embedding-3-small
NAVER_MAPS_KEY_ID=
NAVER_MAPS_KEY=
NAVER_MAPS_JS_KEY_ID=
```

GMS 모델명/주소는 기존 실습 설정을 재사용했으며 이용 가능한 모델과 임베딩 권한은 발급 계정에서 확인해야 합니다. 키를 받은 뒤 `EMBEDDING_MODE=real`로 바꾸고 양쪽 데이터를 재색인하고 서버를 재시작합니다. 해시 색인을 실제 의미 색인으로 재사용하지 않습니다. LLM만 연결하고 해시 검색을 유지할 수도 있으나 상태에 구분됩니다.

네이버 서버 키 2개는 자동차 Directions에만 사용합니다. `NAVER_MAPS_JS_KEY_ID`는 실제 장소 상세 지도용 공개 클라이언트 ID로, Dynamic Map 사용 설정과 localhost 도메인 등록이 필요합니다. 도보·대중교통·자전거는 앱 길찾기 연결을 제공하며 서버의 실제 경로 계산은 연결하지 않았습니다. 앱 링크는 네이버 지도 앱 설치가 필요할 수 있고 웹 지도 검색도 함께 제공합니다. 가입·결제·배포는 수행하지 않았습니다.

## 수집·색인·갱신

배포된 JSON으로는 네트워크 없이 색인할 수 있습니다. 새로 수집하려면:

```powershell
# Wikidata 공개 장소 목록 재수집 (유형과 서울 행정구역 관계 기준)
.\.venv\Scripts\python.exe scripts/collect_places.py
# robots.txt를 확인한 공식 박물관 안내문 수집, 7일 파일 캐시
.\.venv\Scripts\python.exe scripts/collect_official_html.py
# 색인 재실행: 고정 ID upsert와 이전 청크 정리
.\.venv\Scripts\python.exe scripts/index_data.py --mode real
.\.venv\Scripts\python.exe scripts/index_data.py --mode demo
# 만료 캐시 / 생성 응답 캐시 / 전체 HTTP·응답 캐시 삭제
.\.venv\Scripts\python.exe scripts/cache_admin.py --clear expired
.\.venv\Scripts\python.exe scripts/cache_admin.py --clear answers
# 필요할 때만: --clear all
```

`CHUNK_SIZE`, `CHUNK_OVERLAP`을 바꾸고 `index_data.py`를 다시 실행하면 문서별 낡은 청크가 제거됩니다. 수집된 공식 HTML의 갱신은 7일 후 원문을 다시 요청합니다. 최신 원문 재확인이 급하면 `runtime/html`에서 해당 URL의 캐시 파일만 직접 삭제하고 수집하세요. SQLite 캐시 초기화는 후기·일정·대화에 영향을 주지 않습니다.

추가 수집 어댑터도 제공하나 이번 환경에서 성공한 것으로 표시하지 않습니다:

```powershell
# 위키백과 API: 이번 환경은 403. 접근 제한을 우회하지 않습니다.
.\.venv\Scripts\python.exe scripts/collect_documents.py --limit 5
# 키 수령 후 전문가 검색어/선별 프롬프트 포함 실행
.\.venv\Scripts\python.exe scripts/collect_documents.py --limit 5 --llm --refresh
# 공원 PDF: 조사된 링크가 404. 유효한 공식 URL로 SOURCES를 갱신한 후 사용
.\.venv\Scripts\python.exe scripts/collect_official_pdfs.py
```

원문 페이지를 자동으로 이미지·영상 다운로드 권한으로 취급하지 않습니다. 실제 데이터 JSON의 `photos`는 `url`, `source`, `license`, `videos`는 `source`, `title`을 검수해 입력할 때만 표시됩니다.

## 검증

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
node --check static/app.js
node --check static/maps.js
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts/benchmark.py
.\.venv\Scripts\python.exe scripts/evaluate_rag.py
```

브라우저 검증은 별도 터미널에서 서버가 켜진 상태로 실행합니다. 이 환경에 설치된 Edge를 사용했으며 브라우저를 추가 다운로드하지 않았습니다.

```powershell
.\.venv\Scripts\python.exe -m pip install playwright==1.64.0
.\.venv\Scripts\python.exe scripts/browser_check.py
```

스크린샷은 `docs/screenshots`, 실제 실행 결과는 `docs/test-results.md`, `docs/browser-results.json`에 있습니다. 단위 테스트는 임시 DB를 쓰고 브라우저 테스트는 현재 로컬 DB에 테스트 일정을 만들고 후기는 삭제합니다. `benchmark.py`는 생성 응답 캐시만 초기화한 뒤 첫 요청과 캐시 요청을 측정합니다. F2015는 GMS 키가 없어 대표 질문 5개가 **미실행** 상태입니다. 정확도·상호평가 점수를 생성해 채우지 않았습니다.

## 구성 및 문서

```text
app/       설정, 검증 모델, SQLite, 수집, Chroma 색인, RAG, 경로, 일정, FastAPI
static/    직접 작성한 HTML / CSS / JavaScript
data/      실제/가상 장소 및 문서 JSON, 수집 원본 메타데이터
scripts/   재현 가능한 수집·색인·캐시·평가·브라우저 검증
tests/     핵심 로직과 API 테스트
runtime/   로컬 DB·캐시·색인 (Git 제외)
docs/      요구사항·설계·출처·검증·제한·스크린샷
```

- [요구사항 및 F/NF 대조표](docs/requirements.md)
- [RAG·데이터·일정·후기 설계](docs/design.md)
- [API 명세](docs/api.md)
- [외부 의존성 조사](docs/dependencies.md)
- [데이터 출처와 이용 조건](docs/sources.md)
- [검증 결과](docs/test-results.md)
- [남은 작업·문제 해결 기록](docs/limitations.md)
- [셀프·상호 점검 양식](docs/checklists.md)

공개 운영 전 실인증, 실제 이용 확인, 다중 계정/스팸 차단, 관리자 신고 검토, 외부 API 계약·미디어 권리·운영정보 검수를 추가해야 합니다. 현재 후기 식별은 서버 발급 브라우저 쿠키에 한정하며 새 브라우저로 위장할 수 있습니다.
