"""3안 단계별 채우기(exp-v2) 검증: 구성·이동 차이 → 장소 기준 완화 → 같은 구성 · 다른 장소. 외부 호출 없음.

경주 황리단길 자료는 2026-11-13 실제 키 측정 때 캐시된 장소(tests/fixtures/regional_places.json)다. 식당을 하나만 남기면
실제 측정에서 본 경주 유형(한 식당을 모든 조합이 공유해 exp-v1 규칙으로는 'places' 탈락이 많고 2안만 나옴)이 재현된다.
"""
import copy
import json
from pathlib import Path

import pytest

from app import catalog, option_diversity as od, planner
from app.models import Conditions
from app.quality import is_meal
from app.request_intent import normalize
from tests.test_option_diversity_experience import plan, conditions as unit_conditions, ids

FIXTURE = json.loads((Path(__file__).parent / 'fixtures' / 'regional_places.json').read_text('utf-8'))['regions']
SEONGSU = dict(name='서울 성수역 지역 중심', lat=37.5446, lon=127.0559)
OTHER_MEALS = [p['id'] for p in FIXTURE['경북']['places'] if is_meal(p)][1:]


@pytest.fixture
def regional(monkeypatch):
    original = catalog.places
    rows = [p for region in FIXTURE.values() for p in region['places']]

    def places(mode='demo', visit_date=None):
        found = original(mode, visit_date)
        if mode != 'real':
            return found
        return [p for p in found if p.get('region') not in FIXTURE] + copy.deepcopy(rows)

    monkeypatch.setattr(catalog, 'places', places)


def regional_conditions(region='경북', **patch):
    origin = FIXTURE[region]['origin'] if region in FIXTURE else SEONGSU
    data = dict(mode='real', region=region, origin=origin, area_center=origin, allow_estimates=True, include_meal=True,
                start='13:00', end='19:00', visit_date='2026-11-13')
    return normalize(Conditions(**(data | patch)))


def strict(c, selector='experience'):
    """recommend_strict 결과와 선택기에 들어간 최종 후보 풀."""
    captured = {}
    original = od.select_options

    def spy(plans, cond, *args, **kwargs):
        captured['pool'] = copy.deepcopy(list(plans))
        return original(plans, cond, *args, **kwargs)

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv('DATEMATE_OPTION_SELECTOR', selector)
        mp.setattr(od, 'select_options', spy)
        result = planner.recommend_strict(c)
    return result, captured.get('pool', [])


def kinds(plans):
    return len({od.composition_label(p) for p in plans})


def worse(plans, c):
    base = od.fit_key(plans[0], c)
    return sum(any(x > y for x, y in zip(od.fit_key(p, c), base)) for p in plans[1:])


# --- 실제 장소 재현 ---

def test_gyeongju_shared_restaurant_returns_three_with_at_least_legacy_compositions(regional):
    c = regional_conditions(excluded_place_ids=OTHER_MEALS)
    result, pool = strict(c)
    legacy = od.legacy_select_options(copy.deepcopy(pool), c)
    record = result['diagnostics']['option_selection']
    # 한 식당을 모든 조합이 공유한다.
    shared = set.intersection(*({p['id'] for p in plan['places']} for plan in pool))
    assert len(shared) == 1
    assert len(result['plans']) == 3 >= len(legacy)
    assert kinds(result['plans']) >= kinds(legacy) and kinds(result['plans']) == 3
    assert ids(result['plans'])[0] == ids(legacy)[0]
    assert worse(result['plans'], c) == 0
    # exp-v1 규칙(1단계)만으로는 2안이고, 2단계(장소 1곳 이상 다름)로 셋째 안을 채운다.
    assert record['picked_by_stage'] == {'1': 1, '2': 1, '3': 0}
    assert record['rejected'].get('places')


def test_seongsu_small_pool_returns_same_count_as_legacy():
    # 서울 성수 유형: 완료 후보 4개(저장소 자료만 사용). exp-v1은 1안만 냈다.
    c = regional_conditions('서울')
    result, pool = strict(c)
    legacy = od.legacy_select_options(copy.deepcopy(pool), c)
    assert len(od._unique(pool)) == 4
    assert len(result['plans']) == len(legacy) == 3
    assert kinds(result['plans']) >= kinds(legacy)
    assert ids(result['plans'])[0] == ids(legacy)[0]
    assert worse(result['plans'], c) == 0
    stages = [p['difference']['selection_stage'] for p in result['plans'][1:]]
    assert stages == [2, 3]
    filled = result['plans'][2]
    assert filled['option_purpose'] == '같은 구성 · 다른 장소'
    number = next(i + 1 for i, q in enumerate(result['plans'][:2]) if od.dcomp(filled, q) == 0)
    changed = od.changed_places(filled, result['plans'][number - 1])
    assert filled['option_description'] == f"코스 {number}{'와' if number == 2 else '과'} 같은 구성에서 장소 {changed}곳이 달라요"


def test_locked_place_is_kept_in_every_filled_option(regional):
    meal = next(p for p in FIXTURE['경북']['places'] if is_meal(p))
    c = regional_conditions(locked={0: meal['id']})
    result, _ = strict(c)
    assert len(result['plans']) == 3
    assert all(plan['places'][0]['id'] == meal['id'] for plan in result['plans'])
    assert '고정한 장소 1곳은 모든 코스에서 유지해요.' in result['plans'][0]['diversity_note']


def test_same_input_gives_same_result(regional):
    c = regional_conditions(excluded_place_ids=OTHER_MEALS)
    first, _ = strict(c)
    second, _ = strict(c)
    dump = lambda r: json.dumps([r['plans'], r['diagnostics']], ensure_ascii=False, sort_keys=True)
    assert dump(first) == dump(second)


def test_place_mode_is_unchanged_legacy(regional):
    c = regional_conditions(excluded_place_ids=OTHER_MEALS)
    result, pool = strict(c, selector='place')
    legacy = od.legacy_select_options(copy.deepcopy(pool), c)
    assert json.dumps(result['plans'], ensure_ascii=False, sort_keys=True) == json.dumps(legacy, ensure_ascii=False, sort_keys=True)
    assert [p['option_purpose'] for p in result['plans']] == ['취향 우선', '다른 매력', '편안한 동선']
    assert all('experience' not in p and 'difference' not in p for p in result['plans'])
    assert 'reserve' not in result


# --- 단위 검증: 이름·설명이 실제 차이와 맞는다 ---

def test_stage_two_and_three_labels_are_factual(monkeypatch):
    monkeypatch.setenv('DATEMATE_OPTION_SELECTOR', 'experience')
    # 식당 r을 모두 공유: 바꿀 수 있는 자리가 사실상 2곳.
    base = plan('r:meal a:cafe b:do')
    see = plan('r:meal a:cafe c:see')       # 구성 다름, 장소 1곳 다름 → 2단계
    same = plan('r:meal d:cafe e:do')       # 구성 같음, 장소 2곳 다름 → 3단계
    diagnostics = {}
    result = od.select_options([base, same, see], unit_conditions(), diagnostics)
    assert ids(result) == [['r', 'a', 'b'], ['r', 'a', 'c'], ['r', 'd', 'e']]
    assert result[1]['option_purpose'] == '전시·관람 넣은 코스'
    assert result[1]['option_description'] == '코스 1의 체험·놀이 1곳 대신 전시·관람 1곳이 들어가요'
    assert result[1]['difference']['selection_stage'] == 2 and result[1]['difference']['places_changed'] == 1
    assert result[2]['option_purpose'] == '같은 구성 · 다른 장소'
    assert result[2]['option_description'] == '코스 1과 같은 구성에서 장소 2곳이 달라요'
    assert result[2]['difference']['composition_changed'] == 0
    assert diagnostics['option_selection']['picked_by_stage'] == {'1': 0, '2': 1, '3': 1}
    for p in result[1:]:
        assert '다른 매력' not in p['option_purpose'] and '취향' not in p['option_purpose']


def test_filled_option_names_the_course_it_shares_composition_with(monkeypatch):
    monkeypatch.setenv('DATEMATE_OPTION_SELECTOR', 'experience')
    base = plan('a:cafe b:see c:walk')
    other = plan('d:cafe e:do f:walk')        # 1단계: 체험 넣은 코스
    twin = plan('g:cafe h:do i:walk')         # 코스 2와 구성 같음 → 3단계
    result = od.select_options([base, other, twin], unit_conditions())
    assert [p['option_purpose'] for p in result] == ['기준 코스', '체험·놀이 넣은 코스', '같은 구성 · 다른 장소']
    assert result[2]['option_description'] == '코스 2와 같은 구성에서 장소 3곳이 달라요'
    # 비교 표가 쓰는 기준 코스 대비 차이는 그대로 코스 1 기준이다.
    assert result[2]['difference']['base_option'] == 1 and result[2]['difference']['composition_changed'] == 1


def test_fit_guard_and_forbidden_hold_in_fill_stages(monkeypatch):
    monkeypatch.setenv('DATEMATE_OPTION_SELECTOR', 'experience')
    base = plan('a:cafe b:see c:walk')
    worse_same = plan('d:cafe e:see f:walk', penalty=2)
    banned = plan('g:cafe h:see i:walk')
    banned['places'][1]['name'] = '방탈출 카페'
    diagnostics = {}
    result = od.select_options([base, worse_same, banned], unit_conditions(avoid=['방탈출']), diagnostics)
    assert ids(result) == [['a', 'b', 'c']]
    assert diagnostics['option_selection']['rejected'] == {'forbidden': 1, 'fit': 1}
    assert '다른 구성의 조합은 요청 조건과 덜 맞아 제외했어요.' in result[0]['diversity_note']


def test_refill_after_pricing_uses_the_same_stages():
    c = unit_conditions()
    kept = [plan('a:cafe b:see c:walk'), plan('d:cafe e:do f:walk')]
    reserve = [plan('a:cafe b:see g:walk'), plan('h:cafe i:see j:walk', penalty=1), plan('k:cafe l:see m:walk')]
    # 구성이 다른 예비 후보가 없으면 같은 구성 · 다른 장소(적합도 유지) 후보로 채운다.
    refilled = od.refill_candidates(kept, reserve, c, limit=2)
    assert ids(refilled) == [['k', 'l', 'm']]


def test_reserve_keeps_every_composition():
    c = unit_conditions()
    chosen = [plan('a:cafe b:see c:walk')]
    pool = chosen + [plan(f'{x}1:cafe {x}2:do {x}3:walk') for x in 'defghijklmnop'] + [plan('q1:cafe q2:rest q3:walk'),
                                                                                      plan('r1:cafe r2:see r3:walk')]
    reserve = od.reserve_candidates(pool, chosen, c, limit=6)
    labels = [od.composition_label(p) for p in reserve]
    assert len(reserve) == 6
    assert {'카페+걷기+하기', '카페+걷기+쉬기', '카페+보기+걷기'} <= set(labels)
    assert od.reserve_candidates(pool, chosen, c, limit=6) == reserve
