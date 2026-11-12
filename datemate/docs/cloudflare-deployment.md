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

## 로컬에서 직접 배포하는 경우

`npm ci` 후 Docker Desktop을 실행하고 `npm run cloudflare:deploy`를 실행합니다. 이때 Docker는 **배포 이미지 빌드에만** 필요하며, 운영 서버로 계속 실행할 필요는 없습니다. 로컬 Docker 없이 배포하려면 위의 Workers Builds를 사용하세요.

`PUBLIC_ORIGIN`을 다른 도메인으로 바꿀 때는 Worker Secret과 도메인 설정을 함께 변경하고, 컨테이너를 재시작해 새 주소를 반영해야 합니다. 새 컨테이너가 시작될 때 Secret 값이 전달됩니다.

Cloudflare 참고: [Containers 개요](https://developers.cloudflare.com/containers/), [Workers Builds의 컨테이너 배포](https://developers.cloudflare.com/containers/guides/deploy/), [컨테이너 환경 변수와 Secret](https://developers.cloudflare.com/containers/examples/env-vars-and-secrets/).
