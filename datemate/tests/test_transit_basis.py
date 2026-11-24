"""대중교통 구간이 지하철·버스 구분 없는 추정임을 분명히 표시한다(2026-11-18 사용자 요청).

실제 대중교통 길찾기는 연결돼 있지 않다(app/routes.py TRANSIT_* 머리 주석). 그래서
1) 서버는 대중교통 추정 구간에 transit_basis(가정값을 담은 문장)를 넣고, 시간·요금은 그 상수로 계산한다.
2) 화면은 구간 줄에 '(지하철·버스 구분 없음)'을 덧붙이고, 일정 위에 transit_basis 를 한 번 보여 준다."""
import math

from app import routes
from app.models import Conditions
from test_functional_audit import audit_page, generate  # noqa: F401  (audit_page 는 fixture)

A = dict(name='출발', lat=37.5665, lon=126.9780)
B = dict(name='도착', lat=37.5765, lon=126.9780)  # 북쪽 약 1.1km


def conditions(**patch):
    return Conditions(visit_date='2026-10-24', origin=dict(name='출발', lat=A['lat'], lon=A['lon']), **patch)


def test_transit_estimate_uses_the_named_assumptions_and_says_it_does_not_tell_subway_from_bus():
    for mode in ('demo', 'real'):
        leg = routes.leg(A, B, conditions(transport='transit', people=2, mode=mode, allow_estimates=True))
        km = routes.distance(A, B) * (1 if mode == 'demo' else 1.35)
        assert leg['status'] == 'estimated'
        assert leg['minutes'] == max(1, math.ceil(km / routes.TRANSIT_SPEED_KMH * 60)) + routes.TRANSIT_WAIT_MINUTES
        assert leg['walking'] == routes.TRANSIT_WALK_MINUTES and leg['cost'] == routes.TRANSIT_FARE_PER_PERSON * 2
        # 화면에 그대로 보여 줄 문장: 구분 없음과 가정값(상수에서 만든 숫자)이 모두 들어 있다.
        basis = leg['transit_basis']
        assert basis == routes.TRANSIT_BASIS and '지하철·버스를 구분하지 않은 추정' in basis
        for value in (f'{routes.TRANSIT_SPEED_KMH}km', f'대기 {routes.TRANSIT_WAIT_MINUTES}분',
                      f'도보 {routes.TRANSIT_WALK_MINUTES}분', f'{routes.TRANSIT_FARE_PER_PERSON:,}원'):
            assert value in basis, value
    # 다른 수단 구간에는 이 키가 없다.
    for transport in ('walk', 'bicycle', 'car'):
        assert 'transit_basis' not in routes.leg(A, B, conditions(transport=transport, mode='demo')), transport


def test_label_and_note_for_saved_plans_with_and_without_basis(audit_page):
    """legModeLabel·transitBasisNote 를 직접 부른다. 예전에 저장한 코스(transit_basis 없음)는 숫자 없이 구분 없음만 말한다."""
    page, base, errors = audit_page
    page.wait_for_function("typeof transitBasisNote==='function'")
    result = page.evaluate("""()=>{
      const plan=(legs,mode='real')=>({conditions:{transport:'transit',mode},legs});
      const old=transitBasisNote(plan([{status:'estimated',minutes:12}]));
      const walkOnly=transitBasisNote({conditions:{transport:'walk',mode:'real'},legs:[{status:'estimated'}]});
      const api=transitBasisNote(plan([{status:'api',minutes:12}]));
      return {label:legModeLabel(plan([]),{status:'estimated',minutes:12}),demo:legModeLabel(plan([],'demo'),{status:'estimated',minutes:12}),
        apiLabel:legModeLabel(plan([]),{status:'api',minutes:12}),walk:legModeLabel({conditions:{transport:'walk',mode:'real'}},{status:'estimated',minutes:17}),
        old:old&&old.textContent,walkOnly,api};}""")
    assert result['label'] == '대중교통 12분 · 추정 (지하철·버스 구분 없음)'
    assert result['demo'] == '대중교통 12분 · 가상 추정 (지하철·버스 구분 없음)'
    # 실제 노선 조회(status api)가 붙으면 덧붙임과 안내가 저절로 빠진다.
    assert result['apiLabel'] == '대중교통 12분 · 네이버 길찾기' and result['api'] is None
    assert result['walk'] == '도보 17분 · 추정' and result['walkOnly'] is None
    assert result['old'].startswith('대중교통: 지하철·버스를 구분하지 않은 추정이에요. 실제 지하철·버스 노선과 요금은')
    assert not errors, errors


def test_switching_all_legs_to_transit_shows_the_basis_once_above_the_schedule(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 900})
    generate(page)
    original = page.evaluate('selected.id')
    # 도보 코스에는 안내가 없다.
    assert page.locator('#plan-detail .transit-basis-note').count() == 0
    bulk = page.locator('#plan-detail .transport-bulk')
    bulk.locator('summary').click()
    bulk.get_by_role('button', name='대중교통', exact=True).click()
    page.wait_for_function('(id)=>selected.id!==id', arg=original)
    lines = page.locator('#plan-detail .route-line-text').all_inner_texts()
    assert lines and all(line.endswith('· 가상 추정 (지하철·버스 구분 없음)') and '· 대중교통 ' in line for line in lines), lines
    note = page.locator('#plan-detail .transit-basis-note')
    assert note.count() == 1
    text = note.inner_text()
    assert text.startswith('대중교통: ' + routes.TRANSIT_BASIS) and '지도 앱' in text, text
    # 안내는 첫 장소의 구간 줄보다 위(일정 위)에 있다.
    assert note.bounding_box()['y'] < page.locator('#plan-detail .route-line').first.bounding_box()['y']
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert not errors, errors
