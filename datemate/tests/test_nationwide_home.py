"""Home theme cards cover nationwide regions, not only Seoul."""
import re
from html import unescape

from fastapi.testclient import TestClient

from app.config import ROOT
from app.main import app
from app.models import Conditions, Point
from app.taxonomy import DATE_CATEGORIES
from test_functional_audit import audit_page  # noqa: F401  (pytest fixture)

AREAS = {
    '서울 성수': ('서울', '서울 성수역 지역 중심', 37.5446, 127.0559),
    '부산 해운대': ('부산', '부산 해운대역 지역 중심', 35.1631, 129.1636),
    '제주 애월': ('제주', '제주 애월 한담해변 지역 중심', 33.4621, 126.3104),
    '경주 황리단길': ('경북', '경북 경주 황리단길 지역 중심', 35.8375, 129.2097),
    '전주 한옥마을': ('전북', '전북 전주 한옥마을 지역 중심', 35.8150, 127.1530),
    '강릉 안목해변': ('강원', '강원 강릉 안목해변 지역 중심', 37.7716, 128.9477),
}


def attrs(tag):
    return {k: unescape(v) for k, v in re.findall(r'([\w-]+)="([^"]*)"', tag)}


def markup():
    return (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')


def preset_cards(html):
    return [attrs(tag) for tag in re.findall(r'<button[^>]*\bdata-preset="[^>]*>', html)]


def test_home_has_no_inspiration_section_and_six_nationwide_areas():
    with TestClient(app) as client:
        html = client.get('/').text
    assert 'id="inspiration"' not in html and '취향을 발견하는 작은 시작' not in html
    assert 'href="#inspiration"' not in html and 'inspiration.js' not in html
    # The hidden quick builder was removed; theme cards carry their own area values.
    assert 'quick-builder' not in html and 'id="quick-start"' not in html
    assert 'data-region=' not in html
    cards = preset_cards(html)
    assert [c['data-preset'] for c in cards] == list(AREAS)
    for c in cards:
        state, name, lat, lon = AREAS[c['data-preset']]
        assert (c['data-state'], c['data-origin'], float(c['data-lat']), float(c['data-lon'])) == (state, name, lat, lon)
    with TestClient(app) as client:
        assert client.get('/api/inspirations').status_code == 404


def test_every_preset_passes_backend_condition_validation():
    html = markup()
    for b in preset_cards(html):
        mood = b['data-mood']
        category = '타입별' if mood in ('사교적인', '활동적인') else '콘셉트별'
        assert mood in DATE_CATEGORIES[category]
        origin = Point(name=b['data-origin'], lat=float(b['data-lat']), lon=float(b['data-lon']))
        assert origin.name.split(' ', 1)[0] == b['data-state']
        c = Conditions(mode='real', region=b['data-state'], origin=origin, visit_date='2026-11-20',
                       date_category=category, date_subcategory=mood, allow_estimates=True)
        assert c.region == AREAS[b['data-preset']][0]


def intercept_plan_jobs(page):
    bodies = []

    def create(route):
        if route.request.method != 'POST':
            return route.continue_()
        bodies.append(route.request.post_data_json)
        return route.fulfill(json={'id': 'audit-nationwide-job'})

    page.route('**/api/plan-jobs', create)
    page.route('**/api/plan-jobs/audit-nationwide-job',
               lambda route: route.fulfill(json={'status': 'failed', 'message': '점검용 검색 중단'}))
    return bodies


def wait_for_job(page, bodies):
    page.wait_for_function('document.querySelector("#progress").textContent.includes("점검용 검색 중단")')
    assert len(bodies) == 1
    return bodies.pop()


def test_theme_card_fills_planner_with_its_region(audit_page):  # noqa: F811
    page, base, errors = audit_page
    bodies = intercept_plan_jobs(page)
    for width in (320, 390):
        page.set_viewport_size({'width': width, 'height': 900})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), width
    page.set_viewport_size({'width': 1440, 'height': 1000})
    page.locator('[data-preset="제주 애월"]').click()
    page.wait_for_function('location.hash==="#planner-section"')
    assert page.locator('[name=region]').input_value() == '제주'
    assert page.locator('[name=origin_name]').input_value() == '제주 애월 한담해변 지역 중심'
    page.locator('#submit-plan').click()
    body = wait_for_job(page, bodies)
    assert body['region'] == '제주' and body['origin']['name'].startswith('제주')
    assert body['date_subcategory'] == '편안한 데이트'
    assert Conditions.model_validate(body).region == '제주'
    for width in (320, 390):
        page.set_viewport_size({'width': width, 'height': 900})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), width
