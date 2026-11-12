# Cloudflare에 전체 앱 배포

이 저장소는 FastAPI와 정적 화면을 하나의 컨테이너 이미지로 실행하고, Cloudflare Worker가 모든 요청을 그 컨테이너에 전달합니다. 운영용 개인 Docker 서버는 필요하지 않습니다. Cloudflare **Workers Paid** 플랜의 Containers가 필요합니다. 현재 저장 코드는 PostgreSQL을 사용하므로, 데이터 보존에는 외부에서 접속 가능한 **관리형 PostgreSQL**이 필요합니다. Cloudflare D1은 PostgreSQL 대체 설정만으로 연결되지 않습니다.

## 권장: Cloudflare Workers Builds로 배포

Cloudflare의 Git 빌드를 사용하면 로컬 Docker 실행 없이 Cloudflare 빌드 환경에서 이미지를 만듭니다.

1. 이 저장소를 GitHub 또는 GitLab에 올립니다. `.env` 파일은 올리지 않습니다.
2. Cloudflare 대시보드의 **Workers & Pages → Create application**에서 저장소를 연결합니다. Worker 이름은 `wrangler.jsonc`의 `name`과 같은 `datemate`로 지정합니다.
3. 프로젝트 루트는 저장소 최상위 폴더로 설정합니다. Build command는 `npm ci`, production Deploy command는 `npx wrangler deploy`로 설정합니다. 컨테이너 이미지는 배포 명령이 `Dockerfile`에서 빌드합니다.
4. Worker의 **Settings → Variables and Secrets**에서 다음 값을 Secret으로 등록합니다.

   | 이름 | 값 |
   | --- | --- |
   | `PUBLIC_ORIGIN` | 실제 공개 주소, 예: `https://datemate.<계정>.workers.dev` 또는 `https://date.example.com` (끝에 `/` 없음) |
   | `DATABASE_URL` | 외부 접속과 TLS가 가능한 PostgreSQL 연결 주소. 예: `postgresql://사용자:비밀번호@호스트:5432/데이터베이스?sslmode=require` |

   실제 장소 검색에는 `NAVER_SEARCH_CLIENT_ID`, `NAVER_SEARCH_CLIENT_SECRET`도 Secret으로 등록합니다. 다른 선택 키는 `datemate/.env.example`을 참조하세요. Worker는 등록된 선택 키만 컨테이너에 전달합니다. Naver Dynamic Map을 쓰면 `NAVER_MAPS_JS_KEY_ID`와 해당 공개 도메인의 사용 허용 설정이 필요합니다.
5. 프로덕션 브랜치를 푸시해 빌드와 배포를 실행합니다. 첫 배포 시 컨테이너 프로비저닝에 몇 분이 걸릴 수 있습니다. 이후 `https://<공개주소>/readyz`에서 준비 상태를 확인하고, `/api/status`와 추천 화면을 점검합니다.

Cloudflare에서 관리형 PostgreSQL 서버를 제공하는 구성은 이 앱에 아직 적용하지 않았습니다. `DATABASE_URL` 없이 운영 배포하면 Worker가 503을 반환합니다. 컨테이너의 로컬 `/data/runtime`은 색인 캐시 용도이며, 컨테이너가 교체되거나 유휴 종료되면 다시 만들어집니다. 후기·세션·공유 링크 등 영속 데이터는 PostgreSQL에 남습니다. PostgreSQL의 백업은 해당 제공자에서 별도로 설정하세요.

## 배포 전 보안 설정

- PostgreSQL에는 앱 전용 계정을 만들고, 필요한 데이터베이스에만 권한을 부여합니다. `DATABASE_URL`은 Worker Secret에만 저장하고 `sslmode=require`, `verify-ca`, `verify-full` 중 하나를 지정합니다. 가능하면 서버 인증서와 호스트 이름까지 확인하는 `verify-full`을 사용하세요. TLS 설정이 없으면 Worker가 요청을 받지 않습니다.
- 네이버·GMS 키도 Worker Secret으로 저장하고, 제공자 콘솔에서 필요한 API와 공개 도메인만 허용합니다. `.env` 파일과 DB 암호를 Git 또는 빌드 변수에 넣지 않습니다.
- 공유 링크는 URL 프래그먼트에 토큰을 넣어 생성하며, 원본 일정의 개인 조건은 공유 응답에 포함하지 않습니다. 운영에서는 HTTPS 공개 주소 하나를 `PUBLIC_ORIGIN`으로 지정합니다.
- ChromaDB는 컨테이너 내부의 `PersistentClient`로만 사용합니다. 별도의 Chroma HTTP 서버나 포트를 공개하지 않습니다. 현재 ChromaDB 서버 API 관련 보안 공지가 있으므로, 해당 포트를 추가로 노출하거나 원격 모델 실행 기능을 활성화하지 마세요. CI의 `pip-audit`는 이 공지 4건(PYSEC-2026-311, -3813, -3814, -3815)만 예외로 두며, 수정 버전이 나오면 업그레이드하고 예외를 지웁니다.
- Worker는 컨테이너로 넘기기 전에 IP(IPv4는 주소, IPv6는 /64)마다 요청 수를 셉니다(`wrangler.jsonc`의 `ratelimits`). 화면·API는 60초에 600회, `/static/` 파일은 60초에 1200회를 넘으면 컨테이너를 깨우지 않고 `429`와 `Retry-After: 60`을 돌려줍니다. 앱 자체 제한(분당 240회)보다 넉넉한 앞단 방패이며, 제한 기능이 없거나 오류가 나면 요청을 통과시킵니다. Cloudflare의 이 제한은 데이터센터별로 세는 근사값입니다.
- 운영 이미지는 `requirements.txt`(실행에 필요한 패키지)만 설치합니다. `pytest`, `pypdf` 같은 테스트·관리 도구는 `requirements-dev.txt`에 있습니다.

## 로컬에서 직접 배포하는 경우

`npm ci` 후 Docker Desktop을 실행하고 `npm run cloudflare:deploy`를 실행합니다. 이때 Docker는 **배포 이미지 빌드에만** 필요하며, 운영 서버로 계속 실행할 필요는 없습니다. 로컬 Docker 없이 배포하려면 위의 Workers Builds를 사용하세요.

`PUBLIC_ORIGIN`을 다른 도메인으로 바꿀 때는 Worker Secret과 도메인 설정을 함께 변경하고, 컨테이너를 재시작해 새 주소를 반영해야 합니다. 새 컨테이너가 시작될 때 Secret 값이 전달됩니다.

Cloudflare 참고: [Containers 개요](https://developers.cloudflare.com/containers/), [Workers Builds의 컨테이너 배포](https://developers.cloudflare.com/containers/guides/deploy/), [컨테이너 환경 변수와 Secret](https://developers.cloudflare.com/containers/examples/env-vars-and-secrets/).
