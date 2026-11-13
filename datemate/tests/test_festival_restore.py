"""이어받은 결과(저장된 코스 링크·새로고침 복원·공유 링크)에서도 그 코스의 지역·방문일 축제를 보여 주는지."""
import copy
import json
from datetime import date
from urllib.parse import parse_qs, urlsplit
from fastapi.testclient import TestClient
from app import store
from app.catalog import places
from app.main import app
from app.models import Conditions
from app.planner import evaluate
from test_feedback_ui import FESTIVALS, route_festivals
from test_functional_audit import audit_page, generate

ANCHOR = dict(id='201', title='점검 등불축제', lat=37.5762, lon=126.9850)


def saved_plan(client, festival=False):
    client.get('/api/places?mode=demo')
    rows = copy.deepcopy(places('demo')[:2])
    for p in rows:
        p.update(demo=False, hours=[0, 1440], closed_days=[], last_entry=None, breaks=None, price=[1000, 1000], price_unit='person', stay=30)
    extra = dict(origin=dict(name='서울 종로구 · 점검 등불축제 행사장 주변', lat=ANCHOR['lat'], lon=ANCHOR['lon']), festival=ANCHOR) if festival else {}
    c = Conditions(mode='real', region='서울', visit_date=date(2026, 10, 24), allow_estimates=True, count=2, budget=200000, max_leg=180, end='23:00',
                   request='SECRET_REQUEST', **extra)
    plan, error = evaluate(rows, c)
    assert not error
    return store.save_plan(plan, store.owner_of(client.cookies['dm_session']))


def festival_queries(page):
    seen = []
    page.on('request', lambda request: seen.append(parse_qs(urlsplit(request.url).query)) if '/api/festivals?' in request.url else None)
    return seen


def test_shared_plan_exposes_only_region_and_visit_day_for_festivals():
    with TestClient(app) as owner, TestClient(app) as guest:
        plan = saved_plan(owner, festival=True)
        token = owner.post('/api/plans/' + plan['id'] + '/shares').json()['url'].split('#')[1]
        shared = guest.get('/api/shared-plan', headers={'Authorization': 'Bearer ' + token})
        assert shared.status_code == 200
        body = shared.json()
        assert body['festival_search'] == {'region': '서울', 'visit_date': '2026-10-24'}
        # 고른 축제·출발지·요청 문구는 공유 응답에 새로 실리지 않는다.
        assert 'conditions' not in body and 'SECRET' not in shared.text
        assert '점검 등불축제' not in shared.text and str(ANCHOR['lat']) not in shared.text


def test_opening_a_saved_course_link_shows_its_festivals(audit_page):
    page, base, errors = audit_page
    with TestClient(app) as client:
        plan = saved_plan(client)
        owner = client.cookies['dm_session']
    route_festivals(page)
    queries = festival_queries(page)
    page.context.add_cookies([{'name': 'dm_session', 'value': owner, 'url': base}])
    page.goto(base + '/?plan=' + plan['id'])
    page.wait_for_function('(id)=>selected?.id===id', arg=plan['id'])
    page.wait_for_function('document.querySelectorAll("#festival-results .festival-card").length===3')
    assert queries[-1] == {'start': ['2026-10-24'], 'end': ['2026-10-24'], 'region': ['서울']}
    assert page.locator('#festival-section').is_visible()
    assert page.locator('#festival-title').inner_text() == '2026-10-24 서울에서 열리는 축제·행사'
    jump = page.locator('#festival-jump')
    assert jump.is_visible() and jump.inner_text() == '서울 축제 3건 보기 ↓'
    # 지도 표시용 축제와 축제 기준 코스 버튼도 새 추천 때와 같다.
    assert page.evaluate('FestivalPanel.mapItems.map(f=>f.id)') == ['201', '202']
    assert page.locator('#festival-results').get_by_role('button', name='이 축제 주변 코스 추천받기', exact=True).count() == 2
    assert page.locator('#festival-origin-note').is_hidden()


def test_saved_festival_course_restores_the_chosen_festival(audit_page):
    page, base, errors = audit_page
    with TestClient(app) as client:
        plan = saved_plan(client, festival=True)
        owner = client.cookies['dm_session']
    route_festivals(page)
    page.context.add_cookies([{'name': 'dm_session', 'value': owner, 'url': base}])
    page.goto(base + '/?plan=' + plan['id'])
    page.wait_for_function('document.querySelectorAll("#festival-results .festival-card").length===3')
    first = page.locator('#festival-results .festival-card').nth(0)
    assert '선택한 축제' in first.inner_text() and '점검 등불축제' in first.inner_text()
    assert first.get_by_role('button', name='이 축제 선택 해제', exact=True).count() == 1
    # 저장된 이름·좌표뿐인 축제 정보는 목록의 전체 자료로 바뀐다.
    assert page.evaluate('FestivalPanel.chosen.festival.address') == FESTIVALS[0]['address']
    note = page.locator('#festival-origin-note')
    assert note.is_visible() and '‘점검 등불축제’ 기준 코스' in note.inner_text()
    # 고르기 전 조건이 남아 있지 않으므로, 해제하면 조건 화면으로 돌아가 다시 고르게 한다.
    submitted = []
    page.route('**/api/plan-jobs', lambda route: (submitted.append(route.request.post_data), route.fulfill(status=503, json={'detail': '점검용 중단'})))
    note.get_by_role('button', name='축제 선택 해제 · 조건 다시 고르기', exact=True).click()
    page.wait_for_function('document.querySelector(".conditions.panel").hidden===false')
    assert submitted == [] and page.evaluate('FestivalPanel.chosen') is None and note.is_hidden()


def test_refresh_while_searching_keeps_showing_festivals(audit_page):
    page, base, errors = audit_page
    route_festivals(page)
    queries = festival_queries(page)

    def still_running(route):
        if route.request.method != 'GET':
            return route.continue_()
        route.fulfill(json=dict(id='x', status='running', stage='코스 탐색', message='찾는 중'))
    page.route('**/api/plan-jobs/*', still_running)
    page.evaluate("form.elements.mode.value='demo';form.elements.mode.dispatchEvent(new Event('change',{bubbles:true}));form.elements.visit_date.value='2026-10-24';form.elements.max_leg.value=180;form.elements.budget.value=1000000;")
    page.locator('#submit-plan').click()
    page.wait_for_function('document.querySelectorAll("#festival-results .festival-card").length===3')
    page.wait_for_function('!!sessionStorage.getItem("datemate-active-search")')
    stored = json.loads(page.evaluate('sessionStorage.getItem("datemate-active-search-festival")'))
    assert stored == {'mode': 'demo', 'region': '서울', 'visit_date': '2026-10-24', 'festival': None, 'origin': None}
    before = len(queries)
    page.reload()
    page.wait_for_function("typeof statusData!=='undefined'&&!!statusData")
    page.wait_for_function('document.querySelectorAll("#festival-results .festival-card").length===3')
    assert len(queries) > before and queries[-1]['region'] == ['서울'] and queries[-1]['start'] == ['2026-10-24']
    assert page.locator('#festival-demo-note').is_visible()
    jump = page.locator('#festival-jump')
    assert jump.is_visible() and jump.inner_text() == '서울 축제 3건 보기 ↓'
    page.evaluate('PlanSearch.generation++;PlanSearch.controller?.abort()')


def test_finished_search_forgets_festival_context(audit_page):
    page, base, errors = audit_page
    route_festivals(page)
    generate(page)
    assert page.evaluate('sessionStorage.getItem("datemate-active-search-festival")') is None


def test_shared_link_shows_festivals_without_planning_buttons(audit_page):
    page, base, errors = audit_page
    with TestClient(app) as client:
        plan = saved_plan(client)
        token = client.post('/api/plans/' + plan['id'] + '/shares').json()['url']
    route_festivals(page, hours='10:00~18:00')
    queries = festival_queries(page)
    page.goto(base + token)
    page.wait_for_function('document.querySelectorAll("#shared-places article").length===2')
    page.wait_for_function('document.querySelectorAll("#festival-results .festival-card").length===3')
    assert queries[-1] == {'start': ['2026-10-24'], 'end': ['2026-10-24'], 'region': ['서울']}
    assert page.locator('#festival-title').inner_text() == '2026-10-24 서울에서 열리는 축제·행사'
    page.wait_for_function('[...document.querySelectorAll(".festival-fee")].every(p=>p.textContent==="이용요금: 무료")')
    cards = page.locator('#festival-results .festival-card')
    assert cards.locator('button').count() == 0
    assert cards.nth(0).get_by_role('link', name='한국관광공사에서 확인 ↗').get_attribute('href').startswith('https://korean.visitkorea.or.kr/')
    # 축제 이름의 태그는 글자로만 보인다.
    assert page.locator('#xss-check').count() == 0
    jump = page.locator('#festival-jump')
    assert jump.is_visible() and jump.inner_text() == '서울 축제 3건 보기 ↓'
    jump.click()
    page.wait_for_function('document.activeElement?.id==="festival-title"')
