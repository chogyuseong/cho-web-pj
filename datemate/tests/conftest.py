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
# IP 범위당 진행 중 추천 작업 수(app/plan_jobs.start). 화면 테스트는 모두 같은 주소에서 여러 작업을 띄운다.
os.environ['DATEMATE_IP_CONCURRENT_PLAN_JOBS']='100000'
# 로컬 단위 테스트가 사용자 실제 검색 키로 외부 API를 호출하지 않게 한다.
os.environ['NAVER_SEARCH_CLIENT_ID']=''
os.environ['NAVER_SEARCH_CLIENT_SECRET']=''
# 셸에 실제 키가 설정돼 있어도 축제·지도 API를 실제로 호출하지 않게 한다. 필요한 테스트는 monkeypatch로 넣는다.
# SEOUL_OPEN_API_KEY: 서울 주차 실시간(app/seoul_parking_live.py)·착한가격업소(app/good_price.py). 필요한 테스트는 monkeypatch.setenv.
for _name in ('TOUR_API_KEY','NAVER_MAPS_KEY_ID','NAVER_MAPS_KEY','NAVER_MAPS_JS_KEY_ID','SEOUL_OPEN_API_KEY'):
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


# 2026-11-25 상세 결과 시안: 시안에 없는 기능(수단 바꾸기·지각 확인·순서 제안·비용표·결정·공유·레저·질문·후기)은 접힌 칸 두 개
# (static/plan-detail.js planMoreFold, 키 PLAN_MORE_KEY·PLAN_EXTRAS_KEY)에 모였다. 펼침 여부는 브라우저 localStorage 에 기억한다.
# 예전 화면 테스트 수백 개가 그 안의 단추를 바로 누르므로, 모든 브라우저 페이지에 '펼침'을 미리 넣는다.
# 기본(접힘)을 보는 테스트는 sessionStorage 'datemate-test-folds' 를 'default' 로 두면 이 값을 넣지 않는다(tests/test_plan_more_ui.py).
# 피드백 화면(/feedback…)은 저장소를 쓰지 않는지 시험하므로 넣지 않는다(test_user_feedback_ui).
PLAN_FOLDS_OPEN = """try{if(sessionStorage.getItem('datemate-test-folds')!=='default'&&!location.pathname.startsWith('/feedback')){
localStorage.setItem('datemate:plan-more','open');localStorage.setItem('datemate:plan-extras-more','open');}}catch(e){}"""
try:
    from playwright.sync_api import Browser as _Browser

    _new_context, _new_page = _Browser.new_context, _Browser.new_page

    def _context_with_folds(self, *args, **kwargs):
        context = _new_context(self, *args, **kwargs)
        context.add_init_script(PLAN_FOLDS_OPEN)
        return context

    def _page_with_folds(self, *args, **kwargs):
        page = _new_page(self, *args, **kwargs)
        page.add_init_script(PLAN_FOLDS_OPEN)
        return page

    _Browser.new_context, _Browser.new_page = _context_with_folds, _page_with_folds
except ImportError:  # 브라우저 도구가 없는 환경(단위 테스트만)
    pass

@pytest.fixture(autouse=True)
def storage():
    store.init()
    # 테스트 실행 전체가 DB 하나(DATEMATE_RUNTIME·DATEMATE_DB_SCHEMA)를 같이 쓴다. 캐시 표를 비우지 않으면 앞 테스트가 남긴
    # 결과가 뒤 테스트의 가짜 응답을 가린다. 2026-11-20 실제 사례: test_festivals 가 '2026-11-20·서울' 목록을 1시간 캐시에 두자,
    # 같은 날 today() 로 같은 키를 만든 test_security_limits::test_festival_detail_only_for_listed_ids 가 그 목록을 받아 실패했다
    # (단독 실행은 통과, 실제 날짜가 그 고정 날짜와 같은 날에만 실패). 캐시 행을 지우면 cache_owners 도 트리거로 함께 지워진다.
    # 테스트 안의 캐시 동작(같은 테스트 안에서 두 번 부르면 한 번만 호출 등)은 그대로 시험된다.
    with store.connect() as db:
        db.execute('DELETE FROM cache')


# 같은 업체 확인(app/place_identity.py)은 공공 API 를 배경 스레드에서 부른다. 테스트에서는 스레드를 띄우지 않는다
# (TOUR_API_KEY 를 넣은 테스트가 /media 를 불러도 실제 공공 API 로 나가지 않게). 조회 자체를 보는 테스트는 lookup·_work 를 직접 부른다.
@pytest.fixture(autouse=True)
def no_public_identity_worker(monkeypatch):
    from app import place_identity
    monkeypatch.setattr(place_identity, '_start_worker', lambda: None)
    place_identity._queue.clear()
    yield
    place_identity._queue.clear()


# 착한가격업소 자료(app/good_price.py)도 배경 스레드에서 서울 API 를 부른다. 테스트에서는 띄우지 않는다(받기는 refresh 를 직접 부른다).
@pytest.fixture(autouse=True)
def no_good_price_worker(monkeypatch):
    from app import good_price
    monkeypatch.setattr(good_price, '_start_refresh', lambda: None)


# 추천 작업 목록(app/plan_jobs._jobs)은 프로세스 메모리에 있고, 끝난 작업도 600초 동안 남아 '작업 100개'(start 의 429 '검색 요청이 많아요')에 센다.
# 테스트 실행 전체가 한 프로세스라 10분 안에 코스를 100번 넘게 만들면 그 뒤 테스트의 추천이 429 로 막혀 generate() 가 45초를 기다리다 실패했다
# (2026-11-21 확인: CI test (sqlite) 의 간헐 실패 test_readability_stage1_ui·test_print_ui 가 로컬 Docker 전체 실행에서 재현됐고, 실패 순간 POST /api/plan-jobs 가 429).
# 테스트마다 앞 테스트들이 남긴 끝난 작업을 지워 다른 테스트가 만든 작업이 세어지지 않게 한다(tests/test_readability_stage6_ui.py 의
# release_finished_plan_jobs 를 모든 테스트로 넓힘). 아직 도는 작업은 그대로 둔다(그 작업이 끝나면 다음 테스트 시작 때 지워짐).
@pytest.fixture(autouse=True)
def fresh_plan_jobs():
    from app import plan_jobs
    with plan_jobs._lock:
        for key in [k for k, job in plan_jobs._jobs.items() if job.get('status') != 'running']:
            del plan_jobs._jobs[key]
    yield


# 네이버 검색 결과는 사용자별로만 보관한다(app/naver_cache.py). HTTP 를 거치지 않고 함수를 직접 부르는 테스트는
# 한 사용자(소유자)의 요청 안에서 부른 것으로 본다. TestClient 요청은 미들웨어가 그 요청의 소유자로 다시 건다.
# 테스트마다 새 소유자다(다른 테스트가 남긴 보관분을 읽지 않게). 요청 안 메모는 쓰지 않는다(직접 부르기 한 번 = 요청 하나).
@pytest.fixture(autouse=True)
def naver_owner():
    import uuid
    from app import naver_cache
    owner = store.owner_of('pytest-naver-' + uuid.uuid4().hex)
    tokens = naver_cache.bind(owner, memo=False)
    try:
        yield owner
    finally:
        naver_cache.unbind(tokens)


@pytest.fixture
def naver_dict_cache(monkeypatch):
    """네이버 결과 보관(app/naver_cache)을 원래 키 그대로의 dict 로 바꾼다. 테스트가 무엇을 보관했는지 키로 본다.
    (예전에는 store.cached·cache 를 dict 로 바꿨다. 네이버 결과는 이제 store 가 아니라 naver_cache 를 거친다.)"""
    from app import naver_cache
    box = {}
    monkeypatch.setattr(naver_cache, 'cached', lambda key: box.get(key))
    monkeypatch.setattr(naver_cache, 'cache', lambda key, value, ttl=86400: box.__setitem__(key, value))
    monkeypatch.setattr(naver_cache, 'cached_many', lambda keys: {k: box[k] for k in keys if k in box})
    monkeypatch.setattr(naver_cache, 'cache_many', lambda entries: [box.__setitem__(k, v) for k, v, _ in entries])
    monkeypatch.setattr(naver_cache, 'owned_values', lambda prefix: {k: v for k, v in box.items() if k.startswith(prefix)})
    return box


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
