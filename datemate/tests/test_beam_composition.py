"""빔 구성 할당(composition_beam) 검증. 외부 호출 없음.

부산 해운대역·경주 황리단길 자료는 2026-11-13 실제 키 측정 때 캐시된 장소(tests/fixtures/regional_places.json)다.
변경 전에는 빔이 한 구성(부산: 식사+카페+보기, 경주: 식사+카페+하기)으로 모였다.
"""
import copy
import json
from pathlib import Path

import pytest

from app import catalog, option_diversity as od, planner
from app.models import Conditions
from app.request_intent import normalize, plan_penalty

FIXTURE = json.loads((Path(__file__).parent / 'fixtures' / 'regional_places.json').read_text('utf-8'))['regions']
SEONGSU = dict(name='서울 성수역 지역 중심', lat=37.5446, lon=127.0559)


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


def conditions(region='부산', **patch):
    origin = FIXTURE[region]['origin'] if region in FIXTURE else SEONGSU
    data = dict(mode='real', region=region, origin=origin, area_center=origin, allow_estimates=True, include_meal=True,
                start='13:00', end='19:00', visit_date='2026-11-13')
    return normalize(Conditions(**(data | patch)))


def old_beam(plans, limit, **_):
    return od.diverse_beam(plans, limit)


def strict(c, monkeypatch=None, before=False, selector='shadow'):
    """recommend_strict 결과와 선택기에 들어간 최종 후보 풀."""
    captured = {}
    original = od.select_options

    def spy(plans, cond, *args, **kwargs):
        captured['pool'] = copy.deepcopy(list(plans))
        return original(plans, cond, *args, **kwargs)

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv('DATEMATE_OPTION_SELECTOR', selector)
        mp.setattr(od, 'select_options', spy)
        if before:
            mp.setattr(od, 'composition_beam', old_beam)
        result = planner.recommend_strict(c)
    return result, captured.get('pool', [])


def ids(plans):
    return [[p['id'] for p in plan['places']] for plan in plans]


def kinds(plans):
    return {od.composition_label(p) for p in plans}


@pytest.mark.parametrize('region,dominant', [('부산', '식사+카페+보기'), ('경북', '식사+카페+하기')])
def test_regional_pool_keeps_three_or_more_compositions(regional, region, dominant):
    c = conditions(region)
    _, before = strict(c, before=True)
    assert kinds(before) == {dominant}  # 변경 전 수렴 재현
    result, after = strict(c)
    assert len(kinds(after)) >= 3
    assert result['diagnostics']['option_selection']['distinct_compositions'] >= 3
    assert all('식사' in label for label in kinds(after))


@pytest.mark.parametrize('region', ['부산', '경북'])
def test_first_option_is_unchanged(regional, region):
    c = conditions(region)
    before, before_pool = strict(c, before=True)
    after, after_pool = strict(c)
    assert ids(after['plans'])[0] == ids(before['plans'])[0]
    assert ids(after_pool)[0] == ids(before_pool)[0]
    # 할당은 평가를 늘리지 않는다: 빔 크기 60을 넘는 완료 후보는 없다.
    assert len(after_pool) <= 60


def test_focus_request_is_not_diluted(regional):
    c = conditions(themes=['카페·미식'], theme_mode='focus', include_meal=False)
    before, before_pool = strict(c, before=True)
    after, after_pool = strict(c)
    assert after_pool and ids(after_pool) == ids(before_pool) and ids(after['plans']) == ids(before['plans'])
    assert all(len({p['category'] for p in plan['places']}) == 1 for plan in after_pool)


def test_requested_activities_stay_in_every_plan(regional):
    c = conditions(request='전시 보고 산책하기')
    before, before_pool = strict(c, before=True)
    after, after_pool = strict(c)
    assert after['plans'] and ids(after['plans'])[0] == ids(before['plans'])[0]
    assert all(plan_penalty(p, c) == 0 for p in after_pool)
    assert all(plan_penalty(p, c) == 0 for p in after['plans'])


def test_locked_place_is_kept(regional):
    meal = next(p for p in FIXTURE['부산']['places'] if p.get('meal'))
    c = conditions(locked={0: meal['id']})
    before, _ = strict(c, before=True)
    after, after_pool = strict(c)
    assert after_pool and all(plan['places'][0]['id'] == meal['id'] for plan in after_pool)
    assert ids(after['plans'])[0] == ids(before['plans'])[0]


def test_small_pool_is_unchanged():
    # 서울 성수 유형: 완료 후보가 4개뿐이라 할당할 자리가 없다(저장소 자료만 사용).
    c = conditions('서울')
    before, before_pool = strict(c, before=True)
    after, after_pool = strict(c)
    assert len(after_pool) <= 6
    assert ids(after_pool) == ids(before_pool) and ids(after['plans']) == ids(before['plans'])


def test_same_input_gives_same_result(regional):
    c = conditions()
    first, _ = strict(c)
    second, _ = strict(c)
    assert json.dumps(first['plans'], ensure_ascii=False, sort_keys=True) == json.dumps(second['plans'], ensure_ascii=False, sort_keys=True)


def test_experience_mode_returns_three_compositions(regional):
    for region in ('부산', '경북'):
        result, _ = strict(conditions(region), selector='experience')
        assert len(result['plans']) == 3
        assert len(kinds(result['plans'])) == 3


# --- composition_beam 단위 검증 ---

def fake(pid, groups, tier=0):
    kinds_ = {'식사': ('카페·미식', True), '카페': ('카페·미식', False), '보기': ('문화·예술', False), '걷기': ('산책·풍경', False)}
    places = [dict(id=f'{pid}-{i}', category=kinds_[g][0], meal=kinds_[g][1]) for i, g in enumerate(groups)]
    return dict(places=places, tier=tier)


def test_beam_protects_top_ranks_and_admits_other_compositions():
    plans = [fake(f'a{i}', ['식사', '카페']) for i in range(10)] + [fake('b', ['식사', '보기']), fake('c', ['카페', '걷기'])]
    chosen = od.composition_beam(plans, 6)
    assert [p['places'][0]['id'] for p in chosen] == ['a0-0', 'a1-0', 'a2-0', 'a3-0', 'b-0', 'c-0']
    # 끄면 기존 diverse_beam과 같다.
    assert od.composition_beam(plans, 6, enabled=False) == od.diverse_beam(plans, 6)


def test_beam_never_moves_seats_across_tiers():
    plans = [fake(f'a{i}', ['식사', '카페']) for i in range(10)] + [fake('worse', ['식사', '보기'], tier=1)]
    chosen = od.composition_beam(plans, 6, tier=lambda p: p['tier'])
    assert all(p['tier'] == 0 for p in chosen) and len(chosen) == 6
