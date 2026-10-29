import os
from urllib.parse import urlsplit
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
# 실제 비밀키는 서비스 폴더의 .env에서 읽는다. .env.example은 공유용 빈 양식이다.
load_dotenv(Path(os.getenv('DATEMATE_ENV_FILE', str(ROOT / '.env'))))
RUNTIME = Path(os.getenv('DATEMATE_RUNTIME', str(ROOT / 'runtime')))
RUNTIME.mkdir(parents=True, exist_ok=True)
REGION = '서울'  # 이번 프로젝트의 서비스 범위는 서울특별시로 고정한다.

def production():
    return os.getenv('DATEMATE_ENV') == 'production' or bool(os.getenv('K_SERVICE'))


def public_origin():
    return os.getenv('DATEMATE_PUBLIC_ORIGIN', '').strip().rstrip('/')


def validate_runtime():
    if os.getenv('DATEMATE_OPERATING_EVIDENCE_FILE','').strip():
        try:
            from .operating_evidence import evidence_rows
            evidence_rows()
        except (OSError,ValueError,TypeError,AttributeError,KeyError):raise RuntimeError('운영 자료 파일의 경로와 가져오기 형식을 확인하세요.') from None
    try:limit=int(os.getenv('DATEMATE_EXTERNAL_CALLS_PER_RECOMMENDATION','60'))
    except ValueError:raise RuntimeError('추천당 외부 호출 제한은 정수여야 합니다.')
    if not 1<=limit<=500:raise RuntimeError('추천당 외부 호출 제한은 1~500이어야 합니다.')
    database = os.getenv('DATABASE_URL', '').strip()
    if database and urlsplit(database).scheme not in ('postgres', 'postgresql'):
        raise RuntimeError('DATABASE_URL은 PostgreSQL 연결 주소여야 합니다.')
    if production() and not database and os.getenv('DATEMATE_EPHEMERAL_DEMO') != '1':
        raise RuntimeError('운영 환경에는 PostgreSQL DATABASE_URL이 필요합니다. 임시 시연만 DATEMATE_EPHEMERAL_DEMO=1을 사용하세요.')
    origin = public_origin()
    if origin:
        parsed = urlsplit(origin)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username
                or parsed.password or parsed.path or parsed.query or parsed.fragment
                or (production() and parsed.scheme != 'https')):
            raise RuntimeError('DATEMATE_PUBLIC_ORIGIN에는 경로 없는 HTTPS 사이트 주소를 입력하세요.')

def llm():
    from langchain_openai import ChatOpenAI
    key = os.getenv('GMS_KEY')
    if not key:
        raise ValueError('GMS 키가 없어 실제 LLM을 사용할 수 없습니다.')
    return ChatOpenAI(api_key=key, base_url=os.getenv('GMS_BASE_URL', 'https://gms.ssafy.io/gmsapi/api.openai.com/v1/'),
                      model=os.getenv('GMS_MODEL', 'gpt-5.4-nano'), temperature=0, timeout=30, max_retries=1)
