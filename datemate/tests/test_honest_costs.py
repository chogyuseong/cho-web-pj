"""모르는 값을 정직하게 보이기: 가정 가격·예산 판정(개선안 22·신규), 코스 비교(2·27), 출발 전 하나만 확인(21).

2026-11-19 측정(docs/info-enrichment-measure-2026-11-19.md)에서 가격을 못 찾은 공방이 계획용 가정(0~2만 원/인)으로 채워져
예산 5만 원 필수 조건을 '이내'로 통과했다(실제 3만 2천 원/인). 막지는 않되 '이내'라고 단정하지 않고 가정한 곳을 밝힌다.
"""
import copy
from datetime import date

from fastapi.testclient import TestClient

from app.catalog import places
from app.condition_audit import audit_plan
from app.main import app
from app.models import Conditions
from app.planner import evaluate
from app.pricing import price_plans
from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401 (fixture)


def priced_plan(hard):
    with TestClient(app) as client:
        client.get('/api/places?mode=demo')
    rows = copy.deepcopy(places('demo')[:2])
    for p in rows:
        p.update(demo=False, hours=[0, 1440], closed_days=[], last_entry=None, breaks=None, price=[1000, 1000], price_unit='person', stay=30)
    rows[1].update(price=None, category='체험')
    c = Conditions(mode='real', visit_date=date(2026, 10, 24), allow_estimates=True, count=2, budget=200000, max_leg=180, end='23:00',
                   hard_constraints=hard)
    plan, error = evaluate(rows, c)
    assert not error
    return audit_plan(price_plans([plan])[0], c), rows[1]['name']


def test_assumed_price_is_named_instead_of_calling_the_budget_met():
    plan, name = priced_plan(['budget'])
    assert any(r.get('price_kind') == 'planning_assumption' for r in plan['costs'])
    budget = next(r for r in plan['condition_checks'] if r['condition'] == 'budget')
    assert budget['state'] == 'estimated', '막지는 않는다(실제 장소 대부분이 가격 자료가 없다)'
    assert name in budget['message'] and '가정' in budget['message'] and '보장할 수 없어요' in budget['message']
    soft, _ = priced_plan([])
    message = next(r for r in soft['condition_checks'] if r['condition'] == 'budget')['message']
    assert name in message and '보장할 수 없어요' not in message, '꼭 지킬 조건이 아니면 보장 문장은 붙이지 않는다'


def test_comparison_says_only_certain_differences_and_never_shows_unknown_as_zero(audit_page):
    page, _, _ = audit_page
    notes = page.evaluate("""()=>{
      const p=(total,walking,extra={})=>Object.assign({total,walking,unknown:[],conditions:{budget:50000},costs:[],condition_checks:[]},extra);
      return {
        one: courseComparisonNotes([p([1,2],5)]),
        overlap: courseComparisonNotes([p([30000,60000],10),p([40000,50000],18)]),
        cheaper: courseComparisonNotes([p([40000,50000],20),p([10000,20000],12)]),
        tie: courseComparisonNotes([p([1000,2000],7),p([1000,2000],7)]),
        three: courseComparisonNotes([p([1000,2000],7),p([1000,2000],null),p([5000,6000],7,{unknown:['어느 공방 가격']})]),
      };
    }""")
    assert notes['one'] == []
    assert notes['overlap'] == ['코스 2: 비용 범위가 코스 1과 겹쳐 어느 쪽이 싼지 단정할 수 없어요 · 도보 8분 많아요']
    assert notes['cheaper'] == ['코스 2: 비용이 확실히 적어요(최대 20,000원 < 코스 1 최소 40,000원) · 도보 8분 적어요']
    assert notes['tie'] == ['코스 2: 비용 범위가 같아요 · 도보 시간이 같아요']
    assert notes['three'][0] == '코스 2: 비용 범위가 같아요 · 도보 시간을 모르는 코스가 있어 도보는 비교하지 않았어요'
    assert '미확인 비용이 있어 빠진 금액이 있어요' in notes['three'][1] and '0분' not in ' '.join(notes['three'])
    labels = page.evaluate("""()=>[
      costStatusLabel({amount:null,status:'unknown'}),
      costStatusLabel({amount:[0,40000],status:'estimated',price_kind:'planning_assumption'}),
      costStatusLabel({amount:[2000,2000],status:'confirmed'}),
      budgetFitLabel({conditions:{budget:50000},total:[0,40000],costs:[{price_kind:'planning_assumption'}],condition_checks:[{condition:'budget',state:'estimated'}]}),
      budgetFitLabel({conditions:{budget:50000},total:[0,64000],costs:[],condition_checks:[{condition:'budget',state:'unmet'}]}),
      budgetFitLabel({conditions:{budget:50000},total:[0,40000],costs:[],condition_checks:[{condition:'budget',state:'unknown'}]}),
      budgetFitLabel({conditions:{budget:50000,budget_unlimited:true},total:[0,1],costs:[],condition_checks:[]}),
    ]""")
    assert labels == ['미확인 · 합계에서 빠짐', '가정 · 실제 단가 아님 · 합계에 포함', '확정', '예산 안 · 가정 가격 포함',
                      '예산 14,000원 초과', '예산 안인지 모름(미확인 비용)', '']
    first = page.evaluate("""()=>[
      topPendingCheck([{state:'unknown',condition:'weather_forecast',message:'날씨'},{state:'unknown',condition:'visit_date',message:'첫 장소 영업시간'},{state:'unknown',condition:'budget',message:'예산'}])?.message,
      topPendingCheck([{state:'unknown',condition:'budget',message:'예산'}]),
    ]""")
    assert first == ['첫 장소 영업시간', None]


def test_real_results_show_walking_and_notes_on_a_phone(audit_page):
    page, _, _ = audit_page
    generate(page)
    wait_for_selected_detail(page)
    page.set_viewport_size({'width': 390, 'height': 844})
    if page.evaluate('plans.length') >= 2:
        page.locator('#results .comparison-details > summary').click()
        assert page.locator('#results .comparison-notes li').count() == page.evaluate('plans.length') - 1
    walks = page.locator('#results .comparison-walk').all_text_contents()
    assert walks and all(w.startswith('도보 ') for w in walks)
    statuses = page.evaluate("[...document.querySelectorAll('#plan-detail .cost-table tbody tr td:nth-child(6)')].map(td=>td.textContent)")
    assert statuses and all(s in ('확정', '추정', '미확인 · 합계에서 빠짐', '가정 · 실제 단가 아님 · 합계에 포함') for s in statuses)
    assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth')
