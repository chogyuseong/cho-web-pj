"""경험 기준 코스 선택기(exp-v2: 구성·이동 차이 → 장소 기준 완화 → 같은 구성 채우기)와 선택 모드(place/shadow/experience) 검증."""
import copy
import json
import logging
from datetime import datetime, timezone

import pytest

from app import option_diversity as od
from app.models import Conditions

TODAY = datetime.now(timezone.utc).date().isoformat()
CATEGORY = {'cafe': '카페·미식', 'meal': '카페·미식', 'see': '문화·예술', 'walk': '산책·풍경',
            'do': '체험·제작', 'play': '오락·놀이', 'rest': '휴식·힐링'}


def place(pid, kind, known=True, name=None):
    row = dict(id=pid, name=name or '장소 ' + pid, lat=37.5 + len(pid) * 1e-4, lon=127.0,
               category=CATEGORY[kind], tags=[], meal=kind == 'meal', price=[10000, 10000])
    if known:
        row.update(hours=[600, 1260], closed_days=[], operations_source='등록 자료', operations_checked_at=TODAY)
    else:
        row.update(hours=None, closed_days=None)
    return row


def plan(spec, minutes=20, known=True, penalty=0):
    """spec: 'a:cafe b:see c:walk' 형식."""
    places = [place(pid, kind, known) for pid, kind in (item.split(':') for item in spec.split())]
    costs = [dict(category=p['category'], name=p['name'], amount=[10000, 10000] if known else None, status='confirmed')
             for p in places]
    return dict(places=places, legs=[dict(minutes=minutes, status='estimated')], costs=costs, total=[30000, 30000],
                penalty=penalty, conditions=dict(mode='demo', transport='walk'))


def conditions(**patch):
    return Conditions(**(dict(visit_date='2026-10-24', include_meal=False) | patch))


@pytest.fixture
def experience(monkeypatch):
    monkeypatch.setenv('DATEMATE_OPTION_SELECTOR', 'experience')


def ids(plans):
    return [[p['id'] for p in plan['places']] for plan in plans]


# ① 장소 ID만 다르고 구성이 같은 후보 → 3단계(같은 구성 · 다른 장소)로 채우고 사실대로 이름 붙임
def test_same_composition_with_other_places_is_filled_with_factual_label(experience):
    plans = [plan('a:cafe b:see c:walk'), plan('d:cafe e:see f:walk'), plan('g:cafe h:see i:walk', minutes=22)]
    diagnostics = {}
    result = od.select_options(plans, conditions(), diagnostics)
    assert ids(result) == [['a', 'b', 'c'], ['d', 'e', 'f'], ['g', 'h', 'i']]
    assert result[0]['option_purpose'] == '기준 코스'
    assert result[0]['difference'] is None
    assert [p['option_purpose'] for p in result[1:]] == ['같은 구성 · 다른 장소'] * 2
    assert [p['option_description'] for p in result[1:]] == ['코스 1과 같은 구성에서 장소 3곳이 달라요'] * 2
    assert all(p['difference']['selection_stage'] == 3 and p['difference']['composition_changed'] == 0 for p in result[1:])
    assert '같은 구성에서 장소만 다른 코스를 함께 보여요.' in result[0]['diversity_note']
    record = diagnostics['option_selection']
    assert record['selector'] == 'experience' and record['picked_by_stage'] == {'1': 0, '2': 0, '3': 2}
    assert record['returned'] == 3 and record['shortfall'] == 0 and record['distinct_compositions'] == 1


def test_composition_or_travel_difference_names_the_actual_change(experience):
    base = plan('a:cafe b:see c:walk', minutes=40)
    swapped = plan('d:cafe e:do f:walk', minutes=40)
    shorter = plan('g:cafe h:see i:walk', minutes=15)
    result = od.select_options([base, swapped, shorter], conditions())
    assert [p['option_purpose'] for p in result] == ['기준 코스', '체험·놀이 넣은 코스', '이동이 짧은 안']
    assert result[1]['option_description'] == '코스 1의 전시·관람 1곳 대신 체험·놀이 1곳이 들어가요'
    assert result[1]['difference']['composition_changed'] == 1 and 'composition' in result[1]['difference']['kinds']
    assert result[2]['option_description'] == '약 25분 짧아요(추정 기준)'
    assert 'travel_shorter' in result[2]['difference']['kinds']
    assert result[0]['experience']['version'] == od.EXPERIENCE_VERSION
    assert result[0]['experience']['composition'] == {'카페': 1, '보기': 1, '걷기': 1}


def test_meal_and_cafe_are_separate_groups():
    assert od.composition(plan('a:meal b:cafe c:see')) == {'식사': 1, '카페': 1, '보기': 1}
    assert od.dcomp(plan('a:meal b:see c:walk'), plan('d:cafe e:see f:walk')) == 1


# ② 구성은 다르지만 금지 활동을 포함한 후보 → 선택되지 않음
def test_forbidden_activity_is_never_selected(experience):
    base = plan('a:cafe b:see c:walk')
    banned = plan('d:cafe e:play f:walk')
    banned['places'][1]['name'] = '방탈출 카페'
    diagnostics = {}
    result = od.select_options([base, banned], conditions(avoid=['방탈출']), diagnostics)
    assert ids(result) == [['a', 'b', 'c']]
    assert diagnostics['option_selection']['rejected'] == {'forbidden': 1}


def test_worse_fit_is_rejected_even_when_composition_differs(experience):
    diagnostics = {}
    result = od.select_options([plan('a:cafe b:see c:walk'), plan('d:cafe e:do f:walk', penalty=3)], conditions(), diagnostics)
    assert len(result) == 1
    assert diagnostics['option_selection']['rejected'] == {'fit': 1}
    assert '다른 구성의 조합은 요청 조건과 덜 맞아 제외했어요.' in result[0]['diversity_note']


# ③ 고정 장소가 대부분이라 다양성이 불가능한 요청
def test_mostly_locked_request_explains_limited_seats(experience):
    c = conditions(locked={0: 'a', 1: 'b'})
    result = od.select_options([plan('a:cafe b:see c:walk'), plan('a:cafe b:see d:walk')], c)
    # 활동이 같으면 3단계로 채우되, 고정 장소는 그대로이고 이름·설명은 실제 차이(장소 1곳)만 말한다.
    assert ids(result) == [['a', 'b', 'c'], ['a', 'b', 'd']]
    assert result[1]['option_purpose'] == '같은 구성 · 다른 장소'
    assert result[1]['option_description'] == '코스 1과 같은 구성에서 장소 1곳이 달라요'
    assert '고정한 장소 2곳은 모든 코스에서 유지해요.' in result[0]['diversity_note']
    assert '바꿀 수 있는 자리가 1곳뿐이에요.' in result[0]['diversity_note']
    # 바꿀 수 있는 자리가 하나라도 활동이 다르면 고른다.
    result = od.select_options([plan('a:cafe b:see c:walk'), plan('a:cafe b:see d:rest')], c)
    assert ids(result) == [['a', 'b', 'c'], ['a', 'b', 'd']]
    assert result[1]['option_purpose'] == '휴식 넣은 코스'


def test_fully_locked_or_focus_keeps_same_composition_label(experience):
    c = conditions(theme_mode='focus', themes=['카페·미식'])
    result = od.select_options([plan('a:cafe b:cafe c:cafe'), plan('d:cafe e:cafe f:cafe')], c)
    assert [p['option_purpose'] for p in result] == ['기준 코스', '같은 구성 · 다른 장소']
    c = conditions(locked={0: 'a', 1: 'b', 2: 'c'})
    result = od.select_options([plan('a:cafe b:see c:walk')], c)
    assert len(result) == 1 and '바꿀 수 있는 자리가 0곳뿐이에요.' in result[0]['diversity_note']


# ④ 운영정보가 부족한 새 장소 → U가 높고 "확인 적은" 문구를 받지 않음
def test_unknown_operating_data_raises_confirm_items_without_easy_claims(experience):
    base = plan('a:cafe b:see c:walk')
    unknown = plan('d:cafe e:do f:walk', known=False)
    result = od.select_options([base, unknown], conditions())
    assert result[0]['experience']['confirm_items'] == 0
    assert result[1]['experience']['confirm_items'] == 6
    assert result[1]['difference']['confirm_delta'] == 6
    assert '확인할 정보' not in result[1]['option_description']
    assert 'confirm_fewer' not in result[1]['difference']['kinds']
    # 반대로 기준 코스보다 확인할 것이 2개 이상 적으면 그 사실만 덧붙인다.
    result = od.select_options([plan('a:cafe b:see c:walk', known=False), plan('d:cafe e:do f:walk')], conditions())
    assert result[1]['option_description'].endswith('확인할 정보도 6개 적어요')
    for word in ('쉬움', '무료', '조용'):
        assert word not in result[1]['option_description']


def test_confirm_items_is_null_without_cost_rows():
    row = plan('a:cafe b:see c:walk')
    del row['costs']
    assert od.confirm_items(row) is None


# ⑤ 후보가 1개뿐
def test_single_candidate(experience):
    result = od.select_options([plan('a:cafe b:see c:walk')], conditions())
    assert len(result) == 1
    assert '조건에 맞는 장소 조합이 1개뿐이에요.' in result[0]['diversity_note']
    assert od.select_options([], conditions()) == []


# ⑦ 같은 입력을 두 번 실행하면 결과가 같음
def test_selection_is_deterministic(experience):
    pool = [plan('a:cafe b:see c:walk'), plan('d:cafe e:do f:walk'), plan('g:rest h:see i:walk', minutes=50),
            plan('j:meal k:see l:walk'), plan('m:cafe n:play o:rest', minutes=5)]
    first = od.select_options(copy.deepcopy(pool), conditions())
    second = od.select_options(copy.deepcopy(pool), conditions())
    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(second, ensure_ascii=False, sort_keys=True)
    assert len(first) == 3


def demo_conditions(**patch):
    return Conditions(**(dict(visit_date='2026-11-21', request='보드게임 하고 전시 보기') | patch))


def recommended(monkeypatch, selector, c=None):
    from app import planner
    monkeypatch.setenv('DATEMATE_OPTION_SELECTOR', selector)
    return planner.recommend(c or demo_conditions())


def plans_json(result):
    return json.dumps(result['plans'], ensure_ascii=False, sort_keys=True)


# ⑧ shadow 모드는 기존 결과를 그대로 반환하고 진단·로그를 남김
def test_shadow_returns_legacy_result_and_records_diagnostics(monkeypatch, caplog):
    place_mode = recommended(monkeypatch, 'place')
    with caplog.at_level(logging.INFO, logger='app.option_diversity'):
        shadow = recommended(monkeypatch, 'shadow')
    assert plans_json(shadow) == plans_json(place_mode)
    assert all('experience' not in p and 'difference' not in p for p in shadow['plans'])
    assert 'reserve' not in shadow
    record = shadow['diagnostics']['option_selection']
    assert record['selector'] == 'shadow' and record['error'] is None
    assert record['legacy_ids'] == ids(shadow['plans'])
    assert record['experience_ids'] and record['unique_sets'] >= record['experience_returned']
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith('option_selection_shadow')]
    assert lines
    assert '보드게임' not in lines[0] and '37.5' not in lines[0] and '데모 출발점' not in lines[0]


def test_default_selector_is_experience(monkeypatch):
    from app.config import option_selector
    monkeypatch.delenv('DATEMATE_OPTION_SELECTOR', raising=False)
    assert option_selector() == 'experience'
    monkeypatch.setenv('DATEMATE_OPTION_SELECTOR', 'unknown')
    assert option_selector() == 'experience'
    for value in ('place', 'shadow', 'experience'):
        monkeypatch.setenv('DATEMATE_OPTION_SELECTOR', value)
        assert option_selector() == value


# ⑨ 새 선택기가 예외를 내도 shadow 모드 추천이 성공함
def test_shadow_survives_experience_selector_error(monkeypatch):
    expected = plans_json(recommended(monkeypatch, 'place'))

    def broken(*args, **kwargs):
        raise RuntimeError('boom')

    monkeypatch.setattr(od, 'experience_select', broken)
    shadow = recommended(monkeypatch, 'shadow')
    assert plans_json(shadow) == expected
    assert shadow['diagnostics']['option_selection']['error'] == 'RuntimeError'


# ⑩ place 모드는 기존 선택기와 같음
def test_place_mode_is_legacy_selector(monkeypatch):
    monkeypatch.setenv('DATEMATE_OPTION_SELECTOR', 'place')
    pool = [plan('a:cafe b:see c:walk'), plan('c:walk b:see a:cafe'), plan('a:cafe b:see d:walk'),
            plan('d:cafe e:see f:walk', minutes=30), plan('g:cafe h:see i:walk', minutes=5)]
    diagnostics = {}
    result = od.select_options(copy.deepcopy(pool), conditions(), diagnostics)
    legacy = od.legacy_select_options(copy.deepcopy(pool), conditions())
    assert json.dumps(result, ensure_ascii=False) == json.dumps(legacy, ensure_ascii=False)
    assert [p['option_purpose'] for p in result] == ['취향 우선', '다른 매력', '편안한 동선']
    assert diagnostics['option_selection']['experience_ids'] is None


def test_summary_title_changes_only_in_experience_mode(monkeypatch):
    from app.recommendation_summary import enrich
    legacy = enrich(dict(plan('a:meal b:cafe c:see'), option_purpose='편안한 동선'))
    assert legacy['decision_summary']['title'] == '도보 이동 약 20분 · 식사 1곳 · 카페 1곳 · 전시·문화 1곳'
    row = plan('a:meal b:cafe c:see')
    row.update(experience=od._experience(row), difference=dict(kinds=['places', 'composition']))
    assert enrich(row)['decision_summary']['title'] == '식사 1곳 · 카페 1곳 · 전시·문화 1곳'
    row['difference'] = dict(kinds=['places', 'travel_shorter'])
    assert enrich(row)['decision_summary']['title'] == '도보 이동 약 20분 · 식사 1곳 · 카페 1곳 · 전시·문화 1곳'


def test_experience_mode_recommendation_end_to_end(monkeypatch):
    result = recommended(monkeypatch, 'experience', demo_conditions(request=''))
    assert result['plans'][0]['option_purpose'] == '기준 코스'
    assert all(p['experience']['version'] == od.EXPERIENCE_VERSION for p in result['plans'])
    # 1·2단계로 고른 안은 앞선 모든 안과 구성이나 이동이 다르다(3단계 채우기는 같은 구성일 수 있다).
    assert all(od.dcomp(b, a) >= 1 or od.travel_differs(a, b)
               for i, b in enumerate(result['plans']) if i and b['difference']['selection_stage'] < 3
               for a in result['plans'][:i])
    assert len(result['reserve']) <= 12
    chosen = {frozenset(p['id'] for p in plan['places']) for plan in result['plans']}
    assert not any(frozenset(p['id'] for p in plan['places']) in chosen for plan in result['reserve'])


# ⑥ 가격 확인 후 탈락한 대안이 reserve로 대체되고 호출 상한을 지킴
def test_dropped_option_is_refilled_from_reserve_and_never_returned(monkeypatch):
    from app import preferences
    from app.recommendation_service import generate
    monkeypatch.setenv('DATEMATE_OPTION_SELECTOR', 'experience')
    c = demo_conditions(request='')
    from app import planner
    first = planner.recommend(c)['plans']
    assert len(first) == 3
    dropped = frozenset(p['id'] for p in first[1]['places'])
    original = preferences.filter_required
    monkeypatch.setattr(preferences, 'filter_required',
                        lambda plans: [p for p in original(plans) if frozenset(x['id'] for x in p['places']) != dropped])
    result = generate(c, 'refill-owner')
    assert 'reserve' not in result
    assert len(result['plans']) == 3
    assert all(frozenset(x['id'] for x in p['places']) != dropped for p in result['plans'])
    assert all('가격 확인 후 필수 조건을 넘은 코스 1개를 제외했어요.' in p['diversity_note'] for p in result['plans'])
    assert result['diagnostics']['option_selection_after_pricing']['selector'] == 'experience'
    from app import store
    saved = store.get_plan(result['plans'][0]['id'])
    assert saved and '"reserve"' not in str(saved['payload'])


def test_refill_respects_price_route_and_budget_caps(monkeypatch):
    from app import recommendation_service as service, pricing, preferences, request_usage
    c = Conditions(visit_date='2026-11-21', mode='real', allow_estimates=True, transport='car', count=3,
                   origin=dict(name='서울 종로', lat=37.575, lon=126.985))
    kept = [plan('a:cafe b:see c:walk')]
    reserve = [plan(f'{x}1:cafe {x}2:{kind} {x}3:walk') for x, kind in
               (('d', 'do'), ('e', 'rest'), ('f', 'play'), ('g', 'see'))]
    for row in reserve:
        for p in row['places']:
            p['price'] = None
    looked_up, routed = [], []
    monkeypatch.setattr(pricing, 'price_plans', lambda plans: looked_up.extend(
        p['id'] for plan in plans for p in plan['places'] if p['price'] is None) or plans)
    monkeypatch.setattr(preferences, 'filter_required', lambda plans: plans)
    monkeypatch.setattr(service, '_verify_car_routes', lambda data, plans: routed.extend([c.count + 1] * len(plans)))
    with request_usage.measure():
        refilled = service._refill(c, kept, reserve)
    assert 1 <= len(refilled) <= service.REFILL_PLANS
    assert len(set(looked_up)) <= service.REFILL_PRICE_LOOKUPS
    assert sum(routed) <= 2 * (c.count + 1)
    # 요청별 외부 호출 예산이 모자라면 다시 검증하지 않는다.
    looked_up.clear();routed.clear()
    monkeypatch.setenv('DATEMATE_EXTERNAL_CALLS_PER_RECOMMENDATION', '3')
    with request_usage.measure():
        assert service._refill(c, kept, reserve) == []
    assert looked_up == [] and routed == []


# --- strict 실패 → 대체 경로(조건 완화·best_effort)에서도 최종 선택의 진단이 남는다 ---
# 가상 데모에는 식사 장소가 없어 include_meal=True면 엄격 추천이 식사 미충족으로 모두 빠지고
# 조건 완화 경로로 넘어간다(실제 지역에서 식당 자료가 없을 때와 같은 흐름).

GROUP_NAMES = {'식사', '카페', '보기', '걷기', '하기', '쉬기', '기타'}


def assert_pool_compositions(record):
    pool = record['pool_compositions']
    assert pool and len(pool) <= 8 and sum(pool.values()) <= record['unique_sets']
    assert all(set(key.split('+')) <= GROUP_NAMES for key in pool)
    assert record['distinct_compositions'] == len(pool) or len(pool) == 8


def test_pool_compositions_use_group_names_only():
    pool = [plan('a:meal b:cafe c:see'), plan('d:cafe e:cafe f:meal'), plan('g:cafe h:meal i:cafe')]
    stats = od.pool_stats(pool)
    assert stats['pool_compositions'] == {'식사+카페+카페': 2, '식사+카페+보기': 1}
    assert stats['unique_sets'] == 3 and stats['distinct_compositions'] == 2


def test_relaxation_path_records_final_selection_and_shadow_matches_place(monkeypatch):
    c = demo_conditions(request='', include_meal=True)
    place_mode = recommended(monkeypatch, 'place', c)
    shadow = recommended(monkeypatch, 'shadow', c)
    assert shadow['strict_failure'] and shadow['status'] == 'best_effort'
    assert plans_json(shadow) == plans_json(place_mode)
    assert 'reserve' not in shadow
    record = shadow['diagnostics']['option_selection']
    assert record['stage'] == 'relaxation' and record['selector'] == 'shadow' and record['error'] is None
    assert record['relaxation_step'] >= 1 and record['accepted_plans'] == len(shadow['plans'])
    assert record['experience_ids'] and record['legacy_ids']
    assert_pool_compositions(record)
    assert shadow['diagnostics']['option_selection_strict']['stage'] == 'planner'
    assert place_mode['diagnostics']['option_selection']['stage'] == 'relaxation'


def test_sourced_best_effort_path_records_selection(monkeypatch):
    c = demo_conditions(request='')
    used = {x['id'] for p in recommended(monkeypatch, 'place', c)['plans'] for x in p['places']}
    from app import planner
    evidence = {'matches': {'demo-04': {'ranks': [1], 'score': 5}}}
    assert 'demo-04' not in used
    monkeypatch.setenv('DATEMATE_OPTION_SELECTOR', 'place')
    place_mode = planner.recommend(c, evidence)
    monkeypatch.setenv('DATEMATE_OPTION_SELECTOR', 'shadow')
    shadow = planner.recommend(c, evidence)
    assert plans_json(shadow) == plans_json(place_mode)
    record = shadow['diagnostics']['option_selection']
    assert record['stage'] == 'best_effort_sourced' and record['experience_ids']
    assert_pool_compositions(record)


def test_last_resort_suggest_path_records_selection(monkeypatch):
    from app import planner
    strict = planner.recommend_strict

    def no_relaxed_plans(c, evidence=None, stage='planner'):
        result = strict(c, evidence, stage)
        if stage == 'relaxation':
            result['plans'] = []
        return result

    monkeypatch.setattr(planner, 'recommend_strict', no_relaxed_plans)
    c = demo_conditions(request='', include_meal=True)
    place_mode = recommended(monkeypatch, 'place', c)
    shadow = recommended(monkeypatch, 'shadow', c)
    assert shadow['plans'] and plans_json(shadow) == plans_json(place_mode)
    record = shadow['diagnostics']['option_selection']
    assert record['stage'] == 'relaxation_best_effort' and record['experience_ids']
    assert_pool_compositions(record)


def test_experience_mode_uses_new_selector_and_reserve_on_relaxation_path(monkeypatch):
    # 예약 가능 장소를 허용한 요청: 식사 조건만 완화되므로 원래 조건 대비 차이가 같은 후보끼리 비교한다.
    c = demo_conditions(request='', include_meal=True, reservation=True)
    result = recommended(monkeypatch, 'experience', c)
    assert result['strict_failure'] and len(result['plans']) == 3
    record = result['diagnostics']['option_selection']
    assert record['selector'] == 'experience' and record['stage'] == 'relaxation'
    assert result['plans'][0]['option_purpose'] == '기준 코스'
    assert all(p['experience']['version'] == od.EXPERIENCE_VERSION for p in result['plans'])
    assert result['reserve']
    from app.request_intent import normalize
    original = normalize(c).model_dump(mode='json')
    for p in result['reserve']:
        # 예비 후보도 선택된 코스와 같이 원래 조건·조건 차이·완화 안내를 갖는다.
        assert p['conditions'] == original and p['search_adjustments']['messages'] and 'deviations' in p


def test_experience_mode_does_not_trade_relaxed_conditions_for_variety(monkeypatch):
    # 기본 요청은 완화 단계에서 예약 필요 장소가 들어온다. 원래 조건으로 보면 차이가 더 큰 안이므로 고르지 않는다.
    c = demo_conditions(request='', include_meal=True)
    result = recommended(monkeypatch, 'experience', c)
    base = result['plans'][0]['penalty']
    assert all(p['penalty'] <= base for p in result['plans'])
    record = result['diagnostics']['option_selection']
    assert record['rejected'].get('fit') and record['shortfall'] == 3 - len(result['plans'])
    # 예비 후보를 구성별로 고르게 남겨, 원래 조건에도 맞는 다른 구성의 안으로 3안을 채운다(place 모드는 예약 차이가 있는 안을 넣는다).
    assert len(result['plans']) == 3
    place_mode = recommended(monkeypatch, 'place', c)
    assert len(place_mode['plans']) == 3 and max(p['penalty'] for p in place_mode['plans']) > base


def test_relaxation_path_refills_dropped_option_in_experience_mode(monkeypatch):
    from app import preferences, pricing
    from app.recommendation_service import generate
    monkeypatch.setenv('DATEMATE_OPTION_SELECTOR', 'experience')
    c = demo_conditions(request='', include_meal=True, reservation=True)
    from app import planner
    first = planner.recommend(c)['plans']
    assert len(first) == 3
    # 셋째 안이 가격 확인 뒤 빠지는 경우(둘째 안을 빼면 남은 두 안과 다른 예비 후보가 이 자료에는 없다).
    dropped = frozenset(p['id'] for p in first[2]['places'])
    state = {'priced': False}
    price_plans, filter_required = pricing.price_plans, preferences.filter_required

    def priced(plans, *args, **kwargs):
        state['priced'] = True
        return price_plans(plans, *args, **kwargs)

    def required(plans):
        kept = filter_required(plans)
        if not state['priced']:
            return kept
        return [p for p in kept if frozenset(x['id'] for x in p['places']) != dropped]

    monkeypatch.setattr(pricing, 'price_plans', priced)
    monkeypatch.setattr(preferences, 'filter_required', required)
    result = generate(c, 'relaxation-refill-owner')
    assert 'reserve' not in result and result['strict_failure']
    assert len(result['plans']) == 3
    assert all(frozenset(x['id'] for x in p['places']) != dropped for p in result['plans'])
    assert all(p['best_effort'] and p['search_adjustments'] for p in result['plans'])
