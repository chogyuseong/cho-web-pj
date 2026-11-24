"""P2 '이 장소 포함해서 코스 짜기' (2026-11-24 사용자 요구 'UX 개선 P2').

서버: 고정한 장소(conditions.locked)가 추천 후보에 없으면(둘러보기에서 찾은 공공 장소는 새 추천 때 후보에서 비워진다)
     catalog.get_place 로 찾아 후보에 넣는다 — 고정이 '찾을 수 없음'으로 끝나지 않게.
화면: 둘러보기 카드의 「이 장소 포함해서 코스 짜기」 → 코스 만들기로 가고, 그 장소를 고정 슬롯으로 보내며, 폼 맨 위에 '포함할 장소' 태그.
"""
from datetime import date

from app import catalog
from app.models import Conditions
from app.quality import pool
from test_functional_audit import audit_page  # noqa: F401  (fixture)

EXPLORED = dict(id='public:tour-777', name='둘러보기 미술관', category='전시', region='서울', lat=37.5446, lon=127.0557,
                address='서울 성동구 성수이로 7', hours=None, closed_days=None, stay=None, reservation=None, price=[0, 0],
                price_unit='person', source='https://korean.visitkorea.or.kr/x', tags=[], setting='indoor')


def conditions(**kw):
    base = dict(mode='real', region='서울', visit_date=date(2026, 12, 5), allow_estimates=True, max_leg=60,
                origin=dict(name='서울 둘러보기 미술관 주변', lat=37.5446, lon=127.0557))
    base.update(kw)
    return Conditions(**base)


def test_locked_place_outside_the_candidates_is_added(monkeypatch):
    real_places = catalog.places
    monkeypatch.setattr(catalog, 'places', lambda mode, visit_date=None: [p for p in real_places(mode, visit_date) if p['id'] != EXPLORED['id']])
    monkeypatch.setattr(catalog, 'get_place', lambda place_id, mode: dict(EXPLORED) if place_id == EXPLORED['id'] else None)
    ids = {p['id'] for p in pool(conditions(locked={0: EXPLORED['id']}))}
    assert EXPLORED['id'] in ids
    # 고정하지 않으면 넣지 않는다.
    assert EXPLORED['id'] not in {p['id'] for p in pool(conditions())}


def test_explore_card_sends_the_place_as_a_fixed_slot(audit_page):  # noqa: F811
    page, _, _ = audit_page
    page.wait_for_function('!!statusData')
    page.route('**/api/explore?*', lambda route: route.fulfill(json={'places': [EXPLORED], 'total': 1, 'has_more': False, 'region': '서울', 'activity': '', 'message': ''}))
    page.route('**/api/places/*/media?*', lambda route: route.fulfill(json={'status': 'not_found', 'photos': []}))
    page.get_by_role('button', name='장소 둘러보기', exact=True).click()
    card = page.locator('#catalog .place-card').first
    card.get_by_role('button', name='이 장소 포함해서 코스 짜기', exact=True).click()
    page.wait_for_function("location.hash==='#planner-section'")
    tags = page.locator('#preset-tags')
    assert tags.is_visible() and '둘러보기 미술관' in tags.inner_text()
    sent = page.evaluate('values().locked')
    assert list(sent.values()) == [EXPLORED['id']]
    assert page.evaluate('[form.elements.region.value, locationState.origin.name]') == ['서울', '서울 둘러보기 미술관 주변']
    # 빼기를 누르면 고정에서도 뺀다.
    tags.get_by_role('button', name='이 장소 빼기', exact=True).click()
    assert page.evaluate('Object.keys(values().locked).length') == 0
