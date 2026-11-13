"""한 코스에 식당이 연달아 들어가지 않게 하는 규칙(식사 시간대마다 식당 1곳) 검증. 외부 호출 없음.

운영 재현(2026-11-13): 홈의 '부산 해운대' 카드(데이트 분류 '활동적인')로 기본 추천을 받으면 3안이 모두 식당 3곳이었다.
닿는 후보는 식당 8 · 카페 2 · 전시 5곳. '활동적인'(레저·산책·체험)에 맞지 않는 카페·전시는 후보에서 빠지고
식사만 분류와 무관하게 남아, 탐색 후보 34개가 모두 '식사+식사+식사'였다.
"""
import copy
import json
from pathlib import Path

import pytest

from app import catalog, planner
from app.models import Conditions
from app.quality import extra_meals, is_meal

FIXTURE = json.loads((Path(__file__).parent / 'fixtures' / 'regional_places.json').read_text('utf-8'))['regions']
BUSAN = FIXTURE['부산']['places']
# 운영 요청 본문 그대로(홈 '부산 해운대' 카드 + 기본 조건).
BODY = {"course_query": "", "mode": "real", "allow_price_estimates": True, "allow_estimates": True, "stay_minutes": 60,
        "region": "부산", "origin": {"name": "부산 해운대역 지역 중심", "lat": 35.1631, "lon": 129.1636},
        "visit_date": "2026-11-14", "start": "11:00", "end": "19:00", "people": 2, "budget": 100000, "transport": "walk",
        "count": 3, "themes": [], "date_category": "타입별", "date_subcategory": "활동적인", "theme_mode": "mix",
        "setting": "any", "avoid": [], "reservation": False, "max_leg": 30, "max_walk": None, "return_home": False,
        "home": None, "mbti": "", "use_mbti": False, "request": "", "locked": {}, "include_meal": True,
        "transition_buffer_minutes": 0, "neighborhood_radius_km": 2.5, "meeting_type": "regular", "priority": "balanced",
        "trust_mode": "balanced", "hard_constraints": [], "use_feedback": False, "festival": None, "explicit_fields": []}


def use_places(monkeypatch, rows):
    original = catalog.places

    def places(mode='demo', visit_date=None):
        found = original(mode, visit_date)
        if mode != 'real':
            return found
        return [p for p in found if p.get('region') != '부산'] + copy.deepcopy(rows)

    monkeypatch.setattr(catalog, 'places', places)


def production_supply():
    """운영 진단의 공급과 같은 구성: 식당 8 · 카페 2 · 전시 5(산책·체험·레저 없음)."""
    meals = [p for p in BUSAN if p.get('meal')]
    cafes = [p for p in BUSAN if 'cafe' in p['tags']][:2]
    culture = [p for p in BUSAN if 'culture' in p['tags']][:5]
    assert (len(meals), len(cafes), len(culture)) == (8, 2, 5)
    return meals + cafes + culture


def meal_counts(result):
    return [sum(is_meal(p) for p in plan['places']) for plan in result['plans']]


def test_haeundae_default_is_not_three_meals(monkeypatch):
    use_places(monkeypatch, production_supply())
    result = planner.recommend(Conditions(**BODY))
    assert len(result['plans']) == 3
    assert meal_counts(result) == [1, 1, 1]
    labels = {tuple(sorted('식사' if is_meal(p) else p['category'] for p in plan['places'])) for plan in result['plans']}
    assert len(labels) >= 2
    # 카드가 넣은 '활동적인'은 우선순위일 뿐이라(explicit_fields 비어 있음) 엄격 탐색에서 카페·전시로 채운다.
    assert result['status'] == 'ok' and not any(p.get('search_adjustments') for p in result['plans'])
    selection = result['diagnostics']['option_selection']
    assert selection['stage'] == 'planner'
    assert all(name.count('식사') == 1 for name in selection['pool_compositions'])
    assert result['diagnostics']['classification']['applied'] == 'preference'
    assert result['diagnostics']['classification']['shortfall'] is True


def test_strict_search_rejects_meal_only_pool_and_says_why(monkeypatch):
    # 사용자가 '활동적인'을 직접 고르면 분류를 지키고, 식당만 남으면 식사 중복으로 거른 뒤 기존 완화로 넘긴다.
    use_places(monkeypatch, production_supply())
    from app.request_intent import normalize
    chosen = BODY | {'explicit_fields': ['date_subcategory']}
    result = planner.recommend_strict(normalize(Conditions(**chosen)))
    assert result['plans'] == []
    assert '식사 장소 중복 (식사 시간대마다 식당 1곳)' in result['reasons']
    relaxed = planner.recommend(Conditions(**chosen))
    assert relaxed['status'] == 'best_effort' and meal_counts(relaxed) == [1, 1, 1]
    assert any('데이트 분류' in m for m in relaxed['plans'][0]['search_adjustments']['messages'])


def test_walks_available_keep_one_meal(monkeypatch):
    use_places(monkeypatch, BUSAN)
    result = planner.recommend(Conditions(**BODY))
    assert result['plans'] and all(n <= 1 for n in meal_counts(result))


@pytest.mark.parametrize('patch', [{'priority': 'food'}, {'request': '해운대 맛집 탐방'}, {'request': '맛집 위주로'}])
def test_food_requests_may_stack_meals(monkeypatch, patch):
    use_places(monkeypatch, production_supply())
    from app.request_intent import normalize
    c = normalize(Conditions(**(BODY | {'date_category': '', 'date_subcategory': ''} | patch)))
    plan = dict(places=[dict(id='a', meal=True), dict(id='b', meal=True)],
                timeline=[dict(arrival='12:00', departure='13:00'), dict(arrival='13:10', departure='14:10')])
    assert extra_meals(plan, c) == 0


def plan_at(*slots):
    return dict(places=[dict(id=f'p{i}', meal=meal) for i, (meal, _, _) in enumerate(slots)],
                timeline=[dict(arrival=a, departure=d) for _, a, d in slots])


def test_meal_window_rule():
    c = Conditions(**BODY)
    # 점심 1곳 + 저녁 1곳은 허용, 같은 점심 시간대 2곳은 1곳 초과.
    assert extra_meals(plan_at((True, '12:00', '13:00'), (False, '14:00', '15:00'), (True, '18:00', '19:00')), c) == 0
    assert extra_meals(plan_at((True, '11:03', '12:03'), (True, '12:10', '13:10')), c) == 1
    assert extra_meals(plan_at((True, '11:03', '12:03'), (True, '12:10', '13:10'), (True, '13:20', '14:20')), c) == 2
    # 식사 시간대 밖 식당은 1곳까지(시간대 식사가 있으면 추가 식당은 모두 초과).
    assert extra_meals(plan_at((True, '15:00', '16:00')), c) == 0
    assert extra_meals(plan_at((True, '12:00', '13:00'), (True, '15:00', '16:00')), c) == 1
    # 사용자가 식당 두 곳을 고정했으면 그대로 둔다.
    locked = Conditions(**(BODY | {'locked': {0: 'p0', 1: 'p1'}}))
    assert extra_meals(plan_at((True, '12:00', '13:00'), (True, '13:10', '14:10')), locked) == 0
