import os
import sys
import tempfile
from pathlib import Path
os.environ['DATEMATE_RUNTIME']=tempfile.mkdtemp(prefix='datemate-tests-')
# Never run tests against the application's database or credentials.
os.environ['DATABASE_URL']=os.getenv('DATEMATE_TEST_DATABASE_URL','')
if os.environ['DATABASE_URL']:
    import uuid
    import psycopg
    from psycopg import sql
    os.environ['DATEMATE_DB_SCHEMA']='datemate_test_'+uuid.uuid4().hex
    with psycopg.connect(os.environ['DATABASE_URL']) as db:
        db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(os.environ['DATEMATE_DB_SCHEMA'])))
os.environ['DATEMATE_ENV_FILE']=str(Path(os.environ['DATEMATE_RUNTIME'])/'absent.env')
os.environ['DATEMATE_IP_REQUESTS_PER_MINUTE']='100000'
os.environ['DATEMATE_USER_CHATS_PER_MINUTE']='10000'
os.environ['EMBEDDING_MODE']='demo'
os.environ['GMS_KEY']=''
os.environ['DATEMATE_BACKUP_DIR']=''
os.environ['DATEMATE_RECOMMENDATIONS_PER_MINUTE']='10000'
os.environ['DATEMATE_USER_RECOMMENDATIONS_PER_MINUTE']='10000'
os.environ['DATEMATE_PROVIDER_CALLS_PER_HOUR']='10000'
# Every test request comes from the same TestClient address within a few minutes,
# far beyond one real visitor; tests of these limits lower them with monkeypatch.
for _name in ('SESSIONS','EXPENSIVE_REQUESTS','RECOMMENDATIONS','CHATS','GEOCODE','REVERSE_GEOCODE',
              'LOCAL_SEARCHES','REFRESHES','REVIEWS','EXPLORE_SEARCHES','POPUP_SEARCHES','PHOTO_THUMBS'):
    os.environ[f'DATEMATE_IP_{_name}_PER_MINUTE']='100000'
os.environ['DATEMATE_IP_POPUP_SEARCHES_PER_HOUR']='100000'
# 로컬 단위 테스트가 사용자 실제 검색 키로 외부 API를 호출하지 않게 한다.
os.environ['NAVER_SEARCH_CLIENT_ID']=''
os.environ['NAVER_SEARCH_CLIENT_SECRET']=''
# 셸에 실제 키가 설정돼 있어도 축제·지도 API를 실제로 호출하지 않게 한다. 필요한 테스트는 monkeypatch로 넣는다.
for _name in ('TOUR_API_KEY','NAVER_MAPS_KEY_ID','NAVER_MAPS_KEY','NAVER_MAPS_JS_KEY_ID'):
    os.environ[_name]=''
os.environ['DATEMATE_OPERATING_EVIDENCE_FILE']=''
os.environ['DATEMATE_EXTERNAL_CALLS_PER_RECOMMENDATION']='60'
os.environ['DATEMATE_HTTP_USD_PER_1000']='{}'
# 테스트는 과거의 고정 방문일(2026-10-24 등)을 쓴다. 새 추천의 지난 날짜 검사만 이 시각(한국 시각) 기준으로 한다.
# 검사 자체를 확인하는 테스트는 monkeypatch 로 바꾼다(tests/test_past_visit.py).
os.environ['DATEMATE_PLANNING_NOW']='2026-01-01T00:00'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from app import store

@pytest.fixture(autouse=True)
def storage():
    store.init()


# 분·시간 한도는 int(time.time() // 60) 같은 고정 구간으로 센다. 한도를 낮춘 테스트의 요청 사이에 분이 바뀌면
# 둘째 요청이 새 구간에서 다시 허용돼 429 를 기대한 검사가 가끔 실패한다(2026-11-18 CI postgres, test_parking:258 이 [200, 200]).
# 이 여유보다 짧게 남았으면 다음 분까지 기다렸다 시작한다. 정시는 분 경계이기도 해서 시간 한도도 함께 지킨다.
# 15초 = 한도 테스트 하나가 느린 CI(postgres)에서 걸리는 시간보다 넉넉한 값. 테스트가 그보다 길어지면 이 값을 키운다
# (기다림은 테스트 시작이 분의 마지막 15초에 걸렸을 때만, 최대 15초).
RATE_WINDOW_MARGIN_SECONDS = 15


@pytest.fixture
def same_rate_window():
    """한도를 낮추고(monkeypatch.setenv('…_PER_MINUTE'/'…_PER_HOUR', 작은 수)) 429 를 기대하는 테스트에 붙인다:
    @pytest.mark.usefixtures('same_rate_window'). 한도가 넉넉해 200 만 기대하는 테스트에는 필요 없다.

    시계를 가짜로 바꾸지 않은 까닭: 구간 계산(time.time() // 60)이 web_security·execution·main·popup_api·telemetry 에 흩어져 있고,
    같은 모듈의 time.time() 을 작업 마감·하트비트도 쓴다. 모듈마다 시계를 멈추면 그 기다림이 끝나지 않을 수 있다.
    구간 계산을 한 함수로 모으면(app 쪽 변경) 그 함수만 바꿔 끼우는 방식으로 바꿀 수 있다."""
    import time
    left = 60 - time.time() % 60
    if left < RATE_WINDOW_MARGIN_SECONDS:
        time.sleep(left + 0.05)


def pytest_runtest_logreport(report):
    """GitHub Actions 에서 실패한 테스트를 주석(::error)으로 남긴다.

    작업 로그는 로그인해야 받을 수 있지만 주석은 공개 API(check-runs/{id}/annotations)로 읽힌다.
    원인 모를 CI 실패(2026-11-16 Run 100, 2026-11-17 postgres)를 로그 없이 확인하려는 것이다. 테스트 이름과 마지막 오류 줄만 남긴다.
    """
    if not os.getenv('GITHUB_ACTIONS') or not report.failed:
        return
    lines = [line for line in str(report.longrepr).splitlines() if line.strip()]
    detail = ' | '.join(lines[-3:])[:900]
    for old, new in (('%', '%25'), ('\r', '%0D'), ('\n', '%0A')):
        detail = detail.replace(old, new)
    # pytest 진행 표시(.F) 뒤에 붙으면 GitHub 가 명령으로 읽지 않으므로 줄을 바꿔 시작한다.
    print(f'\n::error title=pytest {report.when} failed::{report.nodeid} :: {detail}', file=sys.__stdout__, flush=True)


@pytest.fixture
def naver_pages_allowed(monkeypatch):
    """네이버 화면 자동 조회(app/naver_pages.py)는 운영에서 꺼져 있다. 남겨 둔 파서·제한 로직을 시험하는 테스트만 켠다
    (실제 호출은 하지 않는다 — 각 테스트가 가짜 응답을 쓴다)."""
    monkeypatch.setattr('app.naver_pages.ALLOWED', True)
