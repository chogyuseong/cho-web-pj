import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
# 실제 비밀키는 서비스 폴더의 .env에서 읽는다. .env.example은 공유용 빈 양식이다.
load_dotenv(ROOT / '.env')
RUNTIME = Path(os.getenv('DATEMATE_RUNTIME', str(ROOT / 'runtime')))
RUNTIME.mkdir(parents=True, exist_ok=True)
REGION = '서울'  # 이번 프로젝트의 서비스 범위는 서울특별시로 고정한다.

def llm():
    from langchain_openai import ChatOpenAI
    key = os.getenv('GMS_KEY')
    if not key:
        raise ValueError('GMS 키가 없어 실제 LLM을 사용할 수 없습니다.')
    return ChatOpenAI(api_key=key, base_url=os.getenv('GMS_BASE_URL', 'https://gms.ssafy.io/gmsapi/api.openai.com/v1/'),
                      model=os.getenv('GMS_MODEL', 'gpt-5.4-nano'), temperature=0, timeout=30, max_retries=1)
