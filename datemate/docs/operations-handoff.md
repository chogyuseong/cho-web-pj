# 운영 인수인계: 시작·자료 반영·장애·복구

아래 명령은 저장소 루트의 PowerShell 기준이다. 현재 개발 환경의 가상환경은 루트 `.venv`다.

## 1. 서비스 상태 확인

```powershell
.\.venv\Scripts\python.exe datemate/scripts/operations_check.py --strict
```

설정·DB 조회·필수 정적 파일·운영 자료 파일을 확인한다. 키 값·주소·요청·대화는 출력하지 않는다.
`ok: true`는 이 로컬 검사 범위에 한정된다. 실제 API 권한, 이용 계약, 복원과 운영 부하까지 확인한 결과는 아니다.
TMAP 키 미설정과 제공처별 이용 범위는 `warnings`에 별도로 표시한다.

## 2. 새 담당자의 격리 운영 훈련

```powershell
.\.venv\Scripts\python.exe datemate/scripts/rehearse_operations.py
```

사용자 DB·키를 쓰지 않는 임시 SQLite 환경에서 시작→시연 추천→코스 결정→백업→새 디렉터리 복원→무결성 검사→삭제를 실행한다.
이 훈련은 실제 운영 DB 백업, Cloud SQL 복원 및 실제 API 접속 시험을 대신하지 않는다.

## 3. 운영 자료와 메뉴 반영

입력은 운영자가 업체 정체성·주소와 원문을 대조한 자료다. 자동 검색 결과를 그대로 검증 완료로 반영하지 않는다.
`docs/operating-submission.example.json`은 형식 설명용이며, 실제 업체 사실로 사용하면 안 된다.
카탈로그의 정확한 장소 ID, 실제 출처, 확인일, 범위, 검토자를 적는다. 업체 제공 자료에는 제공·사용 동의 증빙의 내부 위치가 필요하다.

```powershell
.\.venv\Scripts\python.exe datemate/scripts/import_operating_data.py datemate/runtime/merchant-input.json datemate/runtime/evidence-reviewed.json
```

도구는 미등록 ID·중복 필드·가격 단위 누락·미래 확인일·잘못된 시간·인증정보가 들어간 출처 등을 거부한다. 기존 출력 파일은 덮어쓰지 않는다.
새 장소의 식별·좌표 검증이나 제공자의 법적 권한을 자동으로 확인하는 도구는 아니다.

서비스의 `.env`에 로컬 파일 경로를 설정한 뒤 서버를 재시작한다.

```dotenv
DATEMATE_OPERATING_EVIDENCE_FILE=C:/your-project/datemate/runtime/evidence-reviewed.json
```

가져온 자료는 필드별 확인일을 기준으로 기존 자료와 비교해 반영된다. 유효기간이 지나면 재확인 대상으로 표시한다.
유효한 메뉴 제공 자료가 있으면 네이버 공개 페이지를 재조회하지 않고 해당 자료와 출처를 먼저 표시한다.
검색·RAG 색인에도 새 자료를 반영하려면 기존 README의 색인 명령을 수행한다.

## 4. 실제 도보·대중교통 연결

현재 TMAP 키가 없어 연결 코드는 준비됐지만 실제 응답은 검증하지 않았다.
각 상품의 이용 권한과 표시·캐시·상업 이용 조건을 확인한 뒤 발급한 키를 `.env`에 넣는다. 채팅·Git에 키를 적지 않는다.

```dotenv
TMAP_APP_KEY=
TMAP_TRANSIT_APP_KEY=
```

- 도보: [TMAP 보행자 API](https://tmap-skopenapi.readme.io/reference/%EB%B3%B4%ED%96%89%EC%9E%90-%EA%B2%BD%EB%A1%9C%EC%95%88%EB%82%B4)
- 대중교통: [TMAP 공식 이용 절차와 응답 예제](https://transit.tmapmobility.com/guide/procedure)

후보 조합은 추정으로 비교하고, 연결된 공급처가 있으면 최종 후보의 시간·거리·도보·운임을 확인해 재계산한다.
TMAP 결과는 조회 시점 기준으로 표시한다. 미래 방문일 시간표·좌석·대기를 보장하지 않는다.
키 누락·오류·잘못된 응답은 실제 조회 성공으로 표시하지 않는다. 추정을 허용한 경우 추정 유지 사실을 알린다.
TMAP 경로 좌표를 다른 공급자의 지도에 새로 그리는 기능은 이번에 추가하지 않았다.

## 5. 호출·비용·품질 관찰

```powershell
.\.venv\Scripts\python.exe datemate/scripts/operations_report.py
.\.venv\Scripts\python.exe datemate/scripts/data_quality_report.py
```

`recommendation_resources`는 실패한 추천 시도도 포함한 관측 호출·캐시·한도 도달 횟수다.
`DATEMATE_EXTERNAL_CALLS_PER_RECOMMENDATION` 기본값은 60이며, 공유 컨텍스트를 전달한 작업 스레드에도 같은 한도를 적용한다.
`DATEMATE_HTTP_USD_PER_1000`에는 실제 계약상 HTTP 단가를 호스트별 JSON으로 설정할 수 있다. 가격 미설정은 무료가 아니라 미확인이다.
이는 청구서가 아니며, SDK 재시도·토큰·나중에 불러오는 사진/메뉴·서버/DB 비용은 해당 HTTP 추정에서 제외된다.
공급처 전체 호출은 기존 `providers`, 모델 응답 토큰은 `model_usage`로 별도 확인한다.

## 6. 장애 대응

| 증상 | 확인 및 처리 |
| --- | --- |
| 시작 실패 | `operations_check.py`, 설정 범위, DB 연결, 가져온 JSON 경로와 형식 확인 |
| 메뉴 403·429 | 기존 5분 cooldown과 원문 링크 사용. 차단 우회 금지. 업체 제공 자료 확보 |
| 경로 미확인 | 해당 상품 키·권한 확인. 추정 표시를 실제 경로로 바꾸지 않음 |
| 자료가 오래됨 | `data_quality_report.py`와 원문 대조 후 새 확인 기록 반영 |
| 검색 호출 한도 도달 | 누락된 자료를 확인하고 사용량·캐시·제공처 예산 조사. 한도를 무조건 높이지 않음 |
| 쓰기 잠금 지연 | `database_write_lock_wait_ms` 로그 확인. 전역 잠금은 PostgreSQL 동시성 검사 없이 제거하지 않음 |

실제 SQLite 백업은 `backup_database.py`를 사용하고, 복원은 반드시 실행 중인 DB와 다른 새 디렉터리로 수행한다.
백업은 사용자 데이터를 포함할 수 있으므로 접근·보관·삭제 정책을 정한다. 운영 PostgreSQL은 기존 Cloud SQL 백업/PITR 문서를 따른다.

## 7. 배포 전 확인

```powershell
Set-Location datemate
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe scripts/format_sources.py --check
```

실제 API를 키로 호출해 서울 표본을 확인하고, PostgreSQL 전용 검사·부하·백업 복원·자료 이용 범위는 별도로 검증한다.
