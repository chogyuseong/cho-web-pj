# Cloud Run 운영 배포

운영 구성은 **Cloud Run + Cloud SQL PostgreSQL 17 + Secret Manager**다. 컨테이너 내부에는 재생성 가능한 Chroma 색인만 두고, 일정·후기·세션·공유·대화·검색 상태·캐시는 PostgreSQL에 저장한다. `.env`와 로컬 SQLite는 이미지에 포함하지 않는다.

## 준비

- Google Cloud 프로젝트 ID, 결제 계정, 배포 권한.
- 서울 리전 `asia-northeast3`의 Cloud SQL PostgreSQL 인스턴스, `datemate` 데이터베이스와 사용자.
- Cloud SQL 자동 백업·시점 복구(PITR)·삭제 보호. 별도 테스트 인스턴스에서 복원 점검.
- Secret Manager의 `datemate-env`: 네이버/GMS 운영 설정.
- Secret Manager의 `datemate-database-url`: PostgreSQL URL. 암호의 특수문자는 URL 인코딩.

Cloud SQL 연결 이름이 `PROJECT_ID:asia-northeast3:datemate-db`인 경우 URL 형태:

```text
postgresql://datemate:URL_ENCODED_PASSWORD@/datemate?host=/cloudsql/PROJECT_ID:asia-northeast3:datemate-db
```

비밀 값은 Secret Manager 콘솔에서 입력한다. 운영 설정에 `DATEMATE_EPHEMERAL_DEMO=1`을 넣지 않는다. `DATABASE_URL` 없이 운영 서버를 시작하면 오류로 중단한다. 기존 로컬 데이터는 자동으로 업로드되지 않는다.

## 실행 계정과 연결

다음은 **Cloud Shell Bash** 명령이다. 대문자 자리표시자를 실제 값으로 바꾼다. 실제 클라우드 리소스 생성과 배포에는 비용이 발생한다.

```bash
gcloud config set project PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com sqladmin.googleapis.com
gcloud iam service-accounts create datemate-run --display-name="DateMate runtime"
gcloud projects add-iam-policy-binding PROJECT_ID --member="serviceAccount:datemate-run@PROJECT_ID.iam.gserviceaccount.com" --role="roles/cloudsql.client"
gcloud secrets add-iam-policy-binding datemate-env --member="serviceAccount:datemate-run@PROJECT_ID.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
gcloud secrets add-iam-policy-binding datemate-database-url --member="serviceAccount:datemate-run@PROJECT_ID.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
```

Cloud SQL 공개 IP 연결은 Cloud Run의 관리형 Cloud SQL 연결을 사용한다. DB 승인 네트워크를 인터넷 전체에 개방하지 않는다. 사설 IP 전용 인스턴스는 별도 VPC 연결이 필요하다.

## 운영 배포

저장소 루트에서 실행한다. 비밀 버전 `1`을 실제 등록한 버전 번호로 바꾼다.

```bash
gcloud run deploy datemate \
  --source . \
  --project PROJECT_ID \
  --region asia-northeast3 \
  --execution-environment gen2 \
  --allow-unauthenticated \
  --service-account datemate-run@PROJECT_ID.iam.gserviceaccount.com \
  --add-cloudsql-instances PROJECT_ID:asia-northeast3:datemate-db \
  --cpu 1 --memory 2Gi --concurrency 8 --timeout 360 \
  --min 1 --max 2 --no-cpu-throttling \
  --set-env-vars DATEMATE_ENV=production,DATEMATE_ENV_FILE=/secrets/datemate.env,DATEMATE_RUNTIME=/data/runtime,DATEMATE_BOOTSTRAP_INDEX=1,EMBEDDING_MODE=demo \
  --set-secrets DATABASE_URL=datemate-database-url:1,/secrets/datemate.env=datemate-env:1
```

**`--no-cpu-throttling`은 필수다.** HTTP 응답 이후에도 검색과 하트비트가 진행되어야 한다. 최소 인스턴스와 인스턴스 기반 CPU는 대기 비용을 발생시킬 수 있다. 예산 알림은 비용 상한이 아니다.

인스턴스당 추천 계산은 2개, DB 연결은 최대 12개다. PostgreSQL 쓰기는 트랜잭션 잠금으로 직렬화한다. 작은 규모의 운영 기준이며 인스턴스를 늘리기 전에 부하와 DB 연결 수를 측정한다. 배포 중 여러 리비전이 실행되어도 조회·취소·저장 데이터는 같은 DB를 사용한다.

문자 해시 색인이 기본값이다. 실제 장소 추천과 의미 임베딩은 별개다. `EMBEDDING_MODE=real`은 GMS 임베딩 설정이 필요하며 새 인스턴스마다 색인 생성 호출이 발생한다. 대규모 의미 검색에는 별도 영속 벡터 저장소가 필요하다.

## 주소와 외부 API

1. 배포된 HTTPS URL을 네이버 Maps 애플리케이션의 Web 서비스 URL에 등록한다.
2. 기본 `*.run.app` 주소는 자동 허용된다. 사용자 도메인은 `DATEMATE_PUBLIC_ORIGIN=https://date.example.com`, `DATEMATE_ALLOWED_HOSTS=date.example.com`을 설정한다.
3. 대표 주소를 설정하면 그 주소에서 온 변경 요청만 허용한다. 사용자에게 대표 주소를 안내한다.
4. 검색 키·Maps 서버 키·지도 JS 공개 ID의 권한을 각각 확인한다.
5. 운영에서는 `/docs`, `/redoc`, `/openapi.json`이 404를 반환한다. 로컬 개발에서는 제공한다.

공급자별 기본 시간당 한도는 600회다. 네이버 지역·사진·블로그 검색은 같은 공급자 호스트의 한도를 함께 사용한다. 장소 500곳 초기 수집이 여러 검색을 수행하므로 이용량을 보고 한도를 설정한다. SDK 계측은 논리 호출 수이며 재시도·토큰 비용을 포함하는 청구 금액이 아니다.

## 배포 후 확인

- `/healthz`는 프로세스, `/readyz`는 DB 접근을 확인한다. 외부 API 정상 여부는 별도 확인한다.
- 주소 선택 → 추천 → 사진·메뉴·블로그 → 장소 고정·교체·되돌리기.
- 별도 브라우저 공유 → 의견 전달 → 공유 취소.
- 새 리비전 배포 후 기존 쿠키로 일정·후기·대화 재조회.
- 검색 중 인스턴스가 종료되면 약 45초의 하트비트 만료 후 중단을 안내한다. 검색은 자동 재실행하지 않는다.
- 데이터 삭제 후 다른 인스턴스에서 이전 일정과 공유 링크가 조회되지 않는지 확인한다.
- Cloud SQL 백업·복원, 오류율·DB 연결·검색 지연·호출 한도에 대한 알림을 설정한다.

브라우저 쿠키로 사용자를 식별하며 로그인·기기 간 계정 복구는 제공하지 않는다. 공개 전 운영자 연락처와 실제 개인정보 보관 정책·자료 이용 안내를 준비한다.

## 로컬 운영 구조 검사

운영 키를 사용하지 않는 PostgreSQL + 두 컨테이너 검사:

```powershell
docker compose -f compose.test.yaml up -d --build
.\datemate\.venv\Scripts\python.exe datemate/scripts/check_cloud_containers.py
docker compose -f compose.test.yaml down
```

검사는 테스트 컨테이너 두 개를 재시작하고 데이터 유지·다른 인스턴스 조회·삭제를 확인한다. Google Cloud IAM·실제 도메인 인증 검증과 구분한다.

`compose.yaml`은 기존 SQLite 로컬 개발용이다. `backup_database.py`와 `restore_database.py`는 SQLite용이다. 운영에는 Cloud SQL 백업/PITR 또는 `pg_dump`/`pg_restore`를 사용한다.

## 공식 참고

- [Cloud SQL PostgreSQL 연결](https://docs.cloud.google.com/sql/docs/postgres/connect-run)
- [백그라운드 CPU 할당](https://docs.cloud.google.com/run/docs/configuring/billing-settings)
- [컨테이너 수명과 종료](https://docs.cloud.google.com/run/docs/container-contract)
- [신뢰 프록시 설정](https://uvicorn.dev/settings/)
