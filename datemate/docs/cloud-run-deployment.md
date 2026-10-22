# Cloud Run 발표용 배포

저장소 루트의 Dockerfile을 사용한다. 화면과 FastAPI를 한 서비스로 실행한다. 일정·후기·세션·새 장소·색인은 `/tmp/datemate`에 임시 저장하며 인스턴스가 교체되면 사라진다. 최소 인스턴스 1도 영구 저장을 보장하지 않는다. 사진 검색 결과는 외부 URL로 표시한다.

## 1. 변경 파일을 GitHub에 올리기 (로컬 PowerShell)

```powershell
git add Dockerfile .dockerignore .gcloudignore datemate/app/config.py datemate/app/cloud_start.py datemate/app/main.py datemate/docs/cloud-run-deployment.md
git commit -m "Prepare Cloud Run deployment"
git push
```

실제 `.env`는 Git과 빌드에 넣지 않는다. `.gcloudignore`는 소스 업로드에서, `.dockerignore`는 Docker 빌드에서 비밀키·가상환경·로컬 실행 데이터를 제외한다.

## 2. Google Cloud 프로젝트와 결제 계정

Google Cloud 콘솔에서 프로젝트를 만들고 결제 계정을 연결한다. 프로젝트 **ID**를 복사한다. 표시 이름과 ID는 다를 수 있다. 비용 예산 알림도 설정한다. 예산 알림은 과금 상한이 아니다. 최소 인스턴스 유지·빌드·이미지 저장·외부 통신에도 비용이 발생할 수 있다.

## 3. Secret Manager에 실제 설정 등록

Secret Manager에서 `datemate-env` 보안 비밀을 만들고, 로컬 `datemate/.env` 내용을 비밀 값으로 입력한다. 키를 터미널 명령·GitHub·채팅에 붙여 넣지 않는다. 첫 버전 번호는 보통 `1`이며 실제 생성된 번호를 확인한다. 개발용 절대 경로가 포함된 `DATEMATE_RUNTIME`은 비밀 파일에 넣지 않는다.

## 4. Cloud Shell에서 준비 (아래는 Bash)

프로젝트를 선택한 후 콘솔 오른쪽 위 Cloud Shell을 연다. `YOUR_PROJECT_ID`를 실제 ID로 바꾼다.

```bash
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
gcloud iam service-accounts create datemate-run --display-name="DateMate Cloud Run"
gcloud secrets add-iam-policy-binding datemate-env --member="serviceAccount:datemate-run@YOUR_PROJECT_ID.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
git clone https://github.com/chogyuseong/cho-web-pj.git
cd cho-web-pj
```

비공개 GitHub 저장소는 별도 GitHub 인증이 필요하다. Google 로그인과 GitHub 인증은 별개다. 암호 대신 GitHub CLI 브라우저 인증 또는 최소 권한 토큰을 사용하고, 토큰을 URL이나 명령 기록에 넣지 않는다. 접근이 안 되면 우선 GitHub 인증을 완료한다.

소스 업로드 목록을 확인한다.

```bash
gcloud meta list-files-for-upload
```

`.env`, `.venv`, `runtime`, `.git`이 포함되면 배포하지 말고 제외 규칙을 먼저 확인한다.

## 5. 배포 (Cloud Shell Bash, 비용이 발생할 수 있음)

```bash
gcloud run deploy datemate --source . --region asia-northeast3 --allow-unauthenticated --service-account datemate-run@YOUR_PROJECT_ID.iam.gserviceaccount.com --cpu 1 --memory 1Gi --concurrency 4 --timeout 180 --min 1 --max 1 --set-env-vars DATEMATE_ENV_FILE=/secrets/datemate.env --set-secrets /secrets/datemate.env=datemate-env:1
```

`--min 1`은 접속이 없어도 준비된 인스턴스를 유지하는 설정이며 대기 비용이 발생할 수 있다. `--max 1`은 비용 상한이 아니며 배포 중 인스턴스 교체·임시 중복이나 일시 중단 가능성은 남는다. 로컬 SQLite이므로 여러 인스턴스로 늘리기 전에 외부 DB로 바꿔야 한다. Cloud Build 권한 오류가 나면 오류에 표시된 빌드 서비스 계정에 필요한 역할을 설정한다. 임의로 모든 계정에 관리자 권한을 부여하지 않는다.

## 6. 배포 후 확인

1. 출력된 HTTPS 주소의 `/healthz`에서 `{"status":"ok"}`를 확인한다.
2. 네이버 Maps Application의 Web 서비스 URL에 배포 서비스 주소를 추가한다.
3. 주소 검색·지도 선택·추천·사진·블로그·식사 후보·장소 교체·가격 갱신을 확인한다.
4. 같은 주소에서 추천 POST가 403이면 프록시 HTTPS 인식을 확인한다. 배포 실행 파일은 Cloud Run의 전달 헤더를 신뢰하도록 설정되어 있다.
5. `/api/status`에서 장소 색인을 확인한다. 최초 기동 시 기본값인 문자 해시 색인을 만든다. 의미 검색으로 표시하지 않는다. 별도 수집 문서는 이미지에 넣지 않으므로 기존 로컬의 문서 청크와 같지는 않다.
6. 인스턴스 재시작 후 이전 일정 링크·세션이 사라질 수 있음을 발표 전에 고려한다.

## 로컬 Docker 검증 (선택)

Docker Desktop을 실행한 뒤 저장소 루트에서 아래를 실행한다. 실제 키는 컨테이너 실행 시에만 주입한다.

```powershell
docker build -t datemate-cloudrun .
docker run --rm -p 8080:8080 --env-file datemate/.env datemate-cloudrun
```

접속 주소는 `http://127.0.0.1:8080`이다. Docker 테스트는 비밀키를 이미지에 저장하지 않는다.
