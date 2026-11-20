"""비용 계산(app/pricing.py): 등록 단가와 계획용 가정 범위만 쓴다. 블로그 요약에서 금액을 읽지 않고, 가격을 찾는 외부 호출이 없다."""
from datetime import date

import httpx

from app import pricing
from app.catalog import places
from app.models import Conditions
from app.planner import evaluate
from app.pricing import ASSUMPTIONS, apply_prices, price_plans


def sample(**changes):
    venue = next(p for p in places('real') if p['price'] is None)
    c = Conditions(mode='real', allow_estimates=True, visit_date=date.today(), count=2,
                   origin=dict(name=venue['name'], lat=venue['lat'], lon=venue['lon']), **changes)
    plan, error = evaluate([venue], c, partial=True)
    assert not error
    return plan, venue


def test_blog_price_reading_is_gone():
    for name in ('extract_quote', 'lookup_price', 'search_client', 'price_parallel', 'collecting_stats', 'BLOG_SEARCH_URL'):
        assert not hasattr(pricing, name), name


def test_pricing_makes_no_external_call_even_with_a_search_key(monkeypatch):
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID', 'test')
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET', 'secret')
    calls = []

    def blocked(*args, **kwargs):
        calls.append(args)
        raise AssertionError('가격 계산은 외부를 부르지 않는다')

    monkeypatch.setattr(httpx, 'get', blocked)
    monkeypatch.setattr(httpx.Client, 'get', blocked)
    monkeypatch.setattr(httpx.Client, 'request', blocked)
    plan, venue = sample(people=3)
    row = price_plans([plan])[0]['costs'][0]
    assert not calls
    low, high = ASSUMPTIONS[venue['category']]
    assert row['unit'] == [low, high] and row['amount'] == [low * 3, high * 3] and row['quantity'] == 3
    assert row['price_kind'] == 'planning_assumption' and row['status'] == 'estimated'
    assert '실제 단가 아님' in row['price_basis'] and '등록된 단가가 없어' in row['price_basis']
    assert 'price_evidence' not in row and 'price_lookup_status' not in row
    assert plan['costs'][0]['amount'] is None, '원본은 바꾸지 않는다'


def test_absent_price_is_left_unpriced_when_assumptions_are_not_allowed():
    plan, venue = sample()
    plan['conditions']['allow_price_estimates'] = False
    updated = apply_prices(plan)
    row = updated['costs'][0]
    assert row['amount'] is None and row['status'] == 'unknown' and 'price_kind' not in row
    assert '등록된 단가가 없어요' in row['price_basis']
    assert venue['name'] + ' 가격' in updated['unknown']


def test_total_is_registered_prices_plus_assumption_ranges():
    venues = [p for p in places('real') if p['price'] is None][:2]
    registered = dict(venues[0], price=[7000, 9000], price_unit='person', price_status='confirmed')
    c = Conditions(mode='real', allow_estimates=True, visit_date=date.today(), count=2, people=2, max_leg=180, budget=1000000,
                   origin=dict(name=registered['name'], lat=registered['lat'], lon=registered['lon']))
    plan, error = evaluate([registered, venues[1]], c, soft=True)
    assert not error
    priced = apply_prices(plan)
    first, second = priced['costs'][0], priced['costs'][1]
    assert first['amount'] == [14000, 18000] and first['status'] == 'confirmed' and not first.get('price_kind')
    low, high = ASSUMPTIONS[venues[1]['category']]
    assert second['amount'] == [low * 2, high * 2] and second['price_kind'] == 'planning_assumption'
    others = [r['amount'] for r in priced['costs'][2:] if r['amount'] is not None]
    assert priced['total'] == [14000 + low * 2 + sum(a[0] for a in others), 18000 + high * 2 + sum(a[1] for a in others)]
    assert priced['confirmed'][0] >= 14000 and priced['estimated'][1] >= high * 2


def test_operator_menu_price_is_kept_and_blog_price_kinds_are_never_created():
    plan, venue = sample()
    plan['costs'][0].update(unit=[9000, 9000], amount=[18000, 18000], status='estimated', price_kind='operator_menu', price_basis='메뉴 1개/인 가정')
    row = apply_prices(plan)['costs'][0]
    assert row['unit'] == [9000, 9000] and row['price_kind'] == 'operator_menu'
    assert 'web_reference' not in str(price_plans([sample()[0]]))
