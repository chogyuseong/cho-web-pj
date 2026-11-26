"""2026-11-25 운영 QA 보고서(docs/QA_REPORT-2026-11-25.ko.md)의 '낮음' 항목 회귀 테스트(QA-14 파일 묶기는 보류).

QA-06 둘러보기 검색어의 기호('<script>' 등): 관광공사가 400(사유 10)으로 거절하던 것을 장애로 읽었다 → 검색어 정리 + 거절은 결과 없음·입력 안내.
QA-07 없는 주소를 브라우저 화면으로 열면 한국어 404 화면(처음 화면 링크). API·JSON 요청은 지금처럼 JSON. Worker 엣지도 같은 화면.
QA-08 첫 화면 head 의 description·Open Graph·canonical. 절대 주소는 공개 주소 설정에서만, 엣지 페이지와 앱 페이지가 같다.
QA-09 장소 정보 창의 '확인 시점'은 한국 시각 'YYYY-MM-DD HH:MM'.
QA-10 사진 단추 이름이 '… 장소 사진 사진 크게 보기'로 겹치지 않는다.
QA-11 머리글 메뉴의 현재 위치는 aria-current 하나(aria-pressed 없음).
QA-12 방문 날짜 칸 min = 오늘(한국 날짜, 서버의 지난 날짜 검사와 같은 시계 — /api/status today).
QA-13 첫 화면에 12px 보다 작은 글자가 없다('반드시 지킬 조건' 칩이 11px 이었다).
QA-15 공유 링크를 만드는 복사 단추 이름에 '링크'(일정·링크 복사), 마우스 설명. 동작은 그대로.
QA-16 공개 /api/status 에 내부 설정 문구(llm 'GMS 키 없음'·embedding 'demo')가 없고 화면이 읽는 값은 그대로다.
덧붙임: 공유 화면(shared.js)의 자체 fetch 도 연결 실패 때 'Failed to fetch' 대신 한국어 안내.
"""
import json
import os
import shutil
import subprocess

import httpx
import pytest
from fastapi.testclient import TestClient

from app import explore, public_places, static_pages
from app.config import ROOT
from app.main import app
from app.static_pages import versioned_page
from public_fakes import calls, fake_public_api, tour_item
from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401 (fixture)

ORIGIN = 'https://datemate.guseong-family.workers.dev'
NETWORK_TEXT = '연결이 끊겨 서버에 닿지 못했어요. 인터넷 연결을 확인하고 다시 시도해 주세요.'
# 2026-11-25 실제 응답(searchKeyword2 keyword='<script>'): HTTP 400 + 이 본문.
REJECTED = httpx.Response(400, json=dict(OpenAPI_ServiceResponse=dict(cmmMsgHeader=dict(
    errMsg='INVALID_REQUEST_PARAMETER_ERROR', returnAuthMsg='잘못된 요청 파라미터 에러', returnReasonCode='10'))))
UNAVAILABLE_TEXT = '공공 자료를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.'


# ---------------------------------------------------------------- QA-06 둘러보기 검색어


def test_search_words_are_cleaned_before_the_tourism_api():
    clean = public_places.keyword_text
    assert clean('<script>') == 'script'
    assert clean('<script>alert(1)</script>') == 'script alert(1) /script'
    assert clean('javascript:') == 'javascript' and clean('onerror=') == 'onerror'
    assert clean('"성수"') == '성수' and clean('성수;') == '성수'
    # 장소 이름에 쓰이는 글자는 그대로다.
    for text in ('서울숲', '성수 카페', 'D·P 성수-역 (1)', "O'Briens", '성수/서울숲', '롯데월드 & 아쿠아리움'):
        assert clean(text) == text, text
    assert clean('  a\t\nb  ') == 'a b' and clean('가' * 80) == '가' * 60


@pytest.fixture
def tour(monkeypatch):
    box = fake_public_api(monkeypatch)
    box['tour'].append(tour_item(1, '서울숲', 37.5444, 127.0374, cat3='A02020700', type_id='12', address='서울특별시 성동구 뚝섬로 273'))
    return box


def explore_get(**params):
    with TestClient(app) as client:
        response = client.get('/api/explore', params=dict(region='서울', **params))
    assert response.status_code == 200
    return response.json()


def test_tag_like_search_is_no_result_not_an_outage(tour):
    data = explore_get(q='<script>')
    assert data['status'] == 'empty' and data['places'] == []
    assert data['message'] != UNAVAILABLE_TEXT
    assert calls(tour, 'tour_keyword')[0]['keyword'] == 'script', '기호를 뺀 검색어를 보낸다'
    # 기호를 떼면 이름 검색이 맞는다('"서울숲"' 은 예전에 0건).
    found = explore_get(q='"서울숲"')
    assert [p['name'] for p in found['places']] == ['서울숲']


def test_rejected_search_word_reads_as_an_input_hint_and_is_kept(tour):
    tour['answer']['tour_keyword'] = REJECTED
    data = explore_get(q='onerror')
    assert data['status'] == 'empty' and data['message'] == explore.KEYWORD_HINT
    assert public_places.tour_keyword('서울', 'onerror')['status'] == 'rejected'
    # 같은 검색어는 늘 같은 답이라 다시 부르지 않는다(장애처럼 60초 뒤 다시 묻지 않음).
    assert len(calls(tour, 'tour_keyword')) == 1
    # 기호만이거나 한 글자면 부르지 않고 안내한다(예전에는 'unavailable' 로 '불러오지 못했어요'였다).
    for q in ('<>', '가', '!!'):
        data = explore_get(q=q)
        assert data['status'] == 'empty' and data['message'] == explore.KEYWORD_HINT, q
    assert len(calls(tour, 'tour_keyword')) == 1


def test_real_outage_still_says_unavailable(tour):
    tour['fail'] |= {'tour_keyword'}
    data = explore_get(q='서울숲')
    assert data['status'] == 'unavailable' and data['message'] == UNAVAILABLE_TEXT
    # 키·권한 오류(403)는 거절된 검색어가 아니다.
    tour['fail'].clear()
    tour['answer']['tour_keyword'] = httpx.Response(403, json=dict(OpenAPI_ServiceResponse=dict(cmmMsgHeader=dict(
        errMsg='SERVICE_KEY_IS_NOT_REGISTERED_ERROR', returnReasonCode='30'))))
    assert public_places.tour_keyword('서울', '서울숲 공원')['status'] == 'unavailable'


def test_explore_screen_shows_the_hint_for_a_script_search(audit_page, monkeypatch):
    page, _, _ = audit_page
    box = fake_public_api(monkeypatch)
    box['answer']['tour_keyword'] = REJECTED
    page.get_by_role('button', name='장소 둘러보기', exact=True).click()
    page.wait_for_function("!document.querySelector('#catalog').textContent.includes('찾고 있어요')")
    page.locator('#search').fill('<script>alert(1)</script>')
    page.locator('#search-button').click()
    page.wait_for_function(f"document.querySelector('#catalog').textContent.includes({json.dumps(explore.KEYWORD_HINT)})")
    assert UNAVAILABLE_TEXT not in page.locator('#catalog').inner_text()
    assert page.get_by_role('button', name='다시 불러오기').count() == 0


# ---------------------------------------------------------------- QA-07 404


def test_browser_gets_a_korean_not_found_page_and_api_keeps_json():
    html = {'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'}
    with TestClient(app) as client:
        for path in ('/no-such-page', '/static/nope.js', '/shared/extra'):
            page = client.get(path, headers=html)
            assert page.status_code == 404, path
            assert page.headers['content-type'] == 'text/html; charset=utf-8'
            assert '찾는 페이지가 없어요' in page.text and '<a class="home" href="/">' in page.text
            assert page.text == versioned_page(static_pages.NOT_FOUND_PAGE)
            assert page.headers['cache-control'] == 'no-store' and page.headers['x-content-type-options'] == 'nosniff'
            assert 'set-cookie' not in page.headers
        # API 는 브라우저로 열어도, 그 밖의 주소는 fetch·JSON 요청이면 예전 그대로 JSON.
        for path, headers in (('/api/nope', html), ('/no-such-page', {}), ('/no-such-page', {'Accept': 'application/json'}),
                              ('/static/nope.js', {'Accept': '*/*'})):
            response = client.get(path, headers=headers)
            assert response.status_code == 404 and response.json() == {'detail': 'Not Found'}, path
        # 처리 함수가 낸 한국어 404(API)는 그대로다.
        assert client.get('/api/places/none', headers=html).json() == {'detail': '장소를 찾을 수 없습니다.'}
        assert client.head('/no-such-page', headers=html).status_code == 404


# ---------------------------------------------------------------- QA-08 head


def with_origin(monkeypatch):
    monkeypatch.setenv('DATEMATE_PUBLIC_ORIGIN', ORIGIN)
    monkeypatch.setenv('DATEMATE_ALLOWED_HOSTS', 'testserver')


def test_home_head_has_description_open_graph_and_canonical(monkeypatch):
    with_origin(monkeypatch)
    with TestClient(app) as client:
        html = client.get('/').text
        shared = client.get('/shared').text
    assert f'<link rel="canonical" href="{ORIGIN}/">' in html
    assert f'<meta property="og:url" content="{ORIGIN}/">' in html
    assert f'<meta property="og:image" content="{ORIGIN}/static/images/seoul-evening.jpg">' in html
    assert '<meta name="description" content="' in html and '<meta property="og:title" content="데이트메이트' in html
    assert '<meta property="og:description" content="' in html and '{{PUBLIC_ORIGIN}}' not in html
    assert (ROOT / 'static' / 'images' / 'seoul-evening.jpg').is_file()
    # 공유 화면은 그대로 noindex 이고 canonical·og:url 을 넣지 않는다(일반 문구 미리보기는 2026-11-27 추가 — tests/test_share_og_tour_photo_400.py).
    assert '<meta name="robots" content="noindex, nofollow">' in shared and 'canonical' not in shared and 'og:url' not in shared


def test_without_a_public_origin_absolute_tags_are_left_out(monkeypatch):
    monkeypatch.delenv('DATEMATE_PUBLIC_ORIGIN', raising=False)
    with TestClient(app) as client:
        html = client.get('/').text
    assert 'rel="canonical"' not in html and 'property="og:url"' not in html and 'property="og:image"' not in html
    assert '{{PUBLIC_ORIGIN}}' not in html
    assert '<meta name="description"' in html and 'og:title' in html, '주소가 필요 없는 설명은 남는다'


NODE_SCRIPT = """
const [build, edge] = await Promise.all([import(process.env.BUILD_URL), import(process.env.EDGE_URL)]);
const pages = build.buildEdgePages();
const env = { PUBLIC_ORIGIN: process.env.EDGE_ORIGIN, DATEMATE_FEEDBACK_ENABLED: process.env.EDGE_FEEDBACK || undefined,
  ASSETS: { fetch: async () => new Response(null, { status: 404 }) } };
const home = edge.pageResponse('/', 'GET', env, pages);
const missing = await edge.edgeResponse({ kind: 'static' }, new Request('https://x.example/static/nope.js', { headers: { accept: 'text/html' } }), env, pages);
process.stdout.write(JSON.stringify({ home: await home.text(), missing: await missing.text(), type: missing.headers.get('content-type') }));
"""


@pytest.mark.skipif(not shutil.which('node') or not (ROOT.parent / 'cloudflare' / 'edge.mjs').is_file(), reason='needs node and cloudflare/')
def test_edge_pages_equal_the_app_pages(monkeypatch):
    """잠든 컨테이너 대신 Worker 가 주는 첫 화면·404 화면이 앱이 주는 것과 글자까지 같다(cloudflare/edge.mjs)."""
    with_origin(monkeypatch)
    with TestClient(app) as client:
        home = client.get('/').text
        missing = client.get('/static/nope.js', headers={'Accept': 'text/html'})
    cloudflare = ROOT.parent / 'cloudflare'
    env = dict(os.environ, BUILD_URL=(cloudflare / 'build-edge-pages.mjs').as_uri(), EDGE_URL=(cloudflare / 'edge.mjs').as_uri(),
               EDGE_ORIGIN=ORIGIN, EDGE_FEEDBACK=os.getenv('DATEMATE_FEEDBACK_ENABLED', ''))
    done = subprocess.run(['node', '--input-type=module', '-e', NODE_SCRIPT], capture_output=True, encoding='utf-8', env=env, timeout=60)
    assert done.returncode == 0, done.stderr
    edge = json.loads(done.stdout)
    assert edge['home'] == home and f'href="{ORIGIN}/"' in edge['home']
    assert edge['missing'] == missing.text and edge['type'] == missing.headers['content-type']


# ---------------------------------------------------------------- QA-09 확인 시점


def test_place_dialog_checked_time_reads_in_korea_time(audit_page):
    page, _, _ = audit_page
    assert page.evaluate("""[koreaTimeText('2026-11-25T11:48:00.010032+00:00'),koreaTimeText('2026-11-25T15:30:00Z'),
      koreaTimeText('2026-11-25'),koreaTimeText(''),koreaTimeText('시점 미확인'),photoCheckedAt('2026-11-24T23:05:00+00:00')]""") == [
        '2026-11-25 20:48', '2026-11-26 00:30', '2026-11-25', '', '시점 미확인', '2026-11-25 08:05']
    place_id = page.evaluate("api('/places?mode=demo').then(d=>d.places[0].id)")

    def checked_now(route):
        data = route.fetch().json()
        data['checked_at'] = '2026-11-25T11:48:00.010032+00:00'
        route.fulfill(json=data)
    page.route(f'**/api/places/{place_id}?mode=demo', checked_now)
    page.evaluate(f"showPlace({json.dumps(place_id)},'demo')")
    page.wait_for_function("[...document.querySelectorAll('#dialog dt')].some(dt=>dt.textContent==='확인 시점')")
    shown = page.evaluate("[...document.querySelectorAll('#dialog dt')].find(dt=>dt.textContent==='확인 시점').nextElementSibling.textContent")
    assert shown == '2026-11-25 20:48'


# ---------------------------------------------------------------- QA-10 사진 단추 이름


def test_photo_button_names_do_not_repeat_the_word_photo(audit_page):
    page, base, _ = audit_page
    assert page.evaluate("""[photoOpenLabel('성수노루 장소 사진','성수노루'),photoOpenLabel('성수노루 장소 사진 2','성수노루'),
      photoOpenLabel('외관','성수노루'),photoOpenLabel('','성수노루'),photoOpenLabel('사진 1','성수노루')]""") == [
        '성수노루 사진 크게 보기', '성수노루 사진 2 크게 보기', '외관 사진 크게 보기', '성수노루 사진 크게 보기', '성수노루 사진 1 크게 보기']
    photos = [{'kind': 'place_public', 'source_label': '업체 등록 사진', 'title': '성수노루 장소 사진' + (f' {i + 1}' if i else ''), 'source': base,
               'image_url': f'{base}/qa10-{i}.png', 'url': f'{base}/qa10-{i}.png', 'search_url': base, 'checked_at': '2026-11-25'} for i in range(2)]
    from test_results_extras_ui import wide_png
    png = wide_png()
    page.route('**/qa10-*.png', lambda route: route.fulfill(body=png, content_type='image/png'))
    page.route('**/api/places/*/media?*', lambda route: route.fulfill(json={'status': 'available', 'photos': photos}))
    page.route('**/api/explore?*', lambda route: route.fulfill(json={
        'places': [{'id': 'qa10', 'name': '성수노루', 'category': '카페·미식', 'address': '서울 성동구 성수동', 'region': '서울'}],
        'total': 1, 'has_more': False, 'region': '서울', 'activity': '', 'message': ''}))
    page.get_by_role('button', name='장소 둘러보기', exact=True).click()
    opener = page.locator('#catalog .place-card .photo-open').first
    opener.wait_for()
    assert opener.get_attribute('aria-label') == '성수노루 사진 크게 보기'
    page.get_by_role('button', name='다음 사진').first.click()
    page.wait_for_function("document.querySelector('#catalog .photo-open').getAttribute('aria-label')==='성수노루 사진 2 크게 보기'")
    labels = page.evaluate("[...document.querySelectorAll('[aria-label]')].map(e=>e.getAttribute('aria-label'))")
    assert not [label for label in labels if '사진 사진' in label], labels


# ---------------------------------------------------------------- QA-11 머리글 현재 위치


NAV = """()=>Object.fromEntries(['nav-home','nav-plan','nav-explore','nav-results'].map(id=>{const e=document.getElementById(id);
  return [id.slice(4),[e.getAttribute('aria-current'),e.hasAttribute('aria-pressed')]];}))"""


def test_header_menu_marks_the_current_place_with_aria_current_only(audit_page):
    page, _, _ = audit_page
    page.set_viewport_size({'width': 1440, 'height': 900})
    none = [None, False]
    assert page.evaluate(NAV) == {'home': ['true', False], 'plan': none, 'explore': none, 'results': none}
    page.click('#nav-explore')
    assert page.evaluate(NAV) == {'home': none, 'plan': none, 'explore': ['true', False], 'results': none}
    page.click('#nav-plan')
    assert page.evaluate(NAV) == {'home': none, 'plan': ['true', False], 'explore': none, 'results': none}
    generate(page)
    wait_for_selected_detail(page)
    page.wait_for_function("document.body.classList.contains('show-date-plan')")
    # 2026-11-26: 결과 화면에서는 '추천 결과'만 현재 위치(예전에는 '코스 만들기'도 함께 — 결과 탭이 데스크톱에도 생겨 하나로).
    assert page.evaluate(NAV) == {'home': none, 'plan': none, 'explore': none, 'results': ['true', False]}
    # 머리글 메뉴에는 aria-pressed 가 하나도 없다(데이트/여행 스위치는 메뉴가 아니라 그대로 aria-pressed).
    assert page.evaluate("document.querySelectorAll('header nav [aria-pressed]').length") == 0
    assert page.locator('#mode-switch [data-mode=date]').get_attribute('aria-pressed') == 'true'


# ---------------------------------------------------------------- QA-12 방문 날짜 min


def test_status_today_follows_the_seoul_planning_clock(monkeypatch):
    with TestClient(app) as client:
        assert client.get('/api/status').json()['today'] == '2026-01-01'  # tests/conftest.py DATEMATE_PLANNING_NOW
        monkeypatch.setenv('DATEMATE_PLANNING_NOW', '2026-11-25T15:30+00:00')  # 한국은 11-26 00:30
        assert client.get('/api/status').json()['today'] == '2026-11-26', '60초 보관 안에서도 날짜는 바로 바뀐다'


def test_visit_date_cannot_go_before_today_in_korea(audit_page):
    page, _, _ = audit_page
    field = 'form.elements.visit_date'
    assert page.evaluate(f'[{field}.min,statusData.today]') == ['2026-01-01', '2026-01-01']
    page.evaluate(f"{field}.value='2025-12-31'")
    assert page.evaluate(f'{field}.validity.rangeUnderflow') is True
    page.evaluate(f"{field}.value='2026-01-01'")
    assert page.evaluate(f'{field}.checkValidity()') is True
    # 브라우저가 한국보다 늦은 시간대라 기본값(브라우저 오늘)이 한국 오늘보다 이르면 그날로 맞춘다.
    page.evaluate(f"{field}.value='2026-01-05';applyVisitDateMin('2026-01-07')")
    assert page.evaluate(f'[{field}.min,{field}.value]') == ['2026-01-07', '2026-01-07']
    page.evaluate("applyVisitDateMin('nonsense')")
    assert page.evaluate(f'{field}.min') == '2026-01-07'


# ---------------------------------------------------------------- QA-13 작은 글자


SMALL_TEXT = """()=>[...document.querySelectorAll('body *')].filter(e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();
  return r.width>0&&r.height>0&&s.visibility!=='hidden'&&!e.closest('.visually-hidden,.leaflet-container')
    &&[...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim())&&parseFloat(s.fontSize)<12;})
  .map(e=>[getComputedStyle(e).fontSize,e.textContent.trim().slice(0,20)])"""


def test_first_screen_has_no_text_under_12px(audit_page):
    page, _, _ = audit_page
    for width in (1440, 390):
        page.set_viewport_size({'width': width, 'height': 900})
        page.wait_for_timeout(200)
        chips = page.evaluate("[...document.querySelectorAll('#conditions .chips span')].filter(s=>s.offsetParent).map(s=>parseFloat(getComputedStyle(s).fontSize))")
        assert chips and min(chips) >= 12, (width, chips)
        assert page.evaluate(SMALL_TEXT) == [], width


# ---------------------------------------------------------------- QA-15 일정·링크 복사


def test_copy_buttons_say_they_make_a_share_link(audit_page):
    page, _, _ = audit_page
    page.set_viewport_size({'width': 1440, 'height': 900})
    generate(page)
    wait_for_selected_detail(page)
    hint = page.evaluate('LINK_COPY_HINT')
    assert '24시간' in hint and '공유 링크' in hint
    for selector, name in (('#results-bar .results-bar-copy', '일정·링크 복사'), ('.rail-kakao-copy', '카톡용 일정·링크 복사'),
                           ('#plan-detail .kakao-copy', '카톡용 일정·링크 복사')):
        button = page.locator(selector).first
        assert button.inner_text() == name, selector
        assert button.get_attribute('title') == hint, selector
    page.set_viewport_size({'width': 390, 'height': 844})
    page.wait_for_function("!!document.querySelector('#results-actionbar .results-actionbar-copy')")
    phone = page.locator('#results-actionbar .results-actionbar-copy')
    assert phone.inner_text() == '일정·링크 복사' and phone.get_attribute('title') == hint
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), '휴대폰 아래 막대가 넘치지 않는다'


# ---------------------------------------------------------------- QA-16 /api/status


def test_public_status_has_no_internal_setting_words():
    from app import main
    main._status_cache.update(value=None, expires=0)
    with TestClient(app) as client:
        data = client.get('/api/status').json()
    assert 'llm' not in data and 'embedding' not in data
    text = json.dumps(data, ensure_ascii=False)
    assert 'GMS' not in text and '키 없음' not in text and 'embedding' not in text
    # 화면이 읽는 값(app.js·location-picker.js·maps.js·place-dialog.js·popups.js)과 컨테이너 점검이 읽는 색인 수는 그대로다.
    for field in ('region', 'themes', 'date_categories', 'map_js_key', 'geocoding_available', 'map_tile_url', 'map_tile_attribution',
                  'popups_enabled', 'public_places_available', 'today', 'counts'):
        assert field in data, field
    assert set(data['counts']) == {'demo', 'real'}


# ---------------------------------------------------------------- 덧붙임: 공유 화면 연결 실패


def test_shared_page_shows_korean_text_when_the_connection_drops(audit_page):
    page, base, errors = audit_page
    generate(page)
    wait_for_selected_detail(page)
    url = page.evaluate("api('/plans/'+selected.id+'/shares',{}).then(d=>d.url)")
    page.goto(base + url, wait_until='networkidle')
    page.locator('#shared-form').wait_for()
    page.route('**/api/shared-plan/vote', lambda route: route.abort('failed'))
    page.locator('#shared-places select').first.select_option('yes')
    page.get_by_role('button', name='내 의견 전달하기').click()
    page.wait_for_function(f"document.querySelector('#shared-status').textContent==={json.dumps(NETWORK_TEXT)}")
    assert 'Failed to fetch' not in page.locator('body').inner_text()
    error = page.evaluate("""async()=>{const m=await import('/static/http-client.mjs');return [m.NETWORK_ERROR_TEXT,m.TIMEOUT_ERROR_TEXT];}""")
    assert error[0] == NETWORK_TEXT and error[1].startswith('요청 대기 시간이 끝났거나')
