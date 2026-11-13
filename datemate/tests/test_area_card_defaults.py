"""홈 인기 동네 카드 6곳의 기본 추천. 외부 호출 없음.

카드(static/theme-cards.js)는 data-mood로 데이트 분류를 넣지만 사용자가 고른 것이 아니라서 explicit_fields 가 비어 있다.
이 분류는 후보를 거르지 않고 우선순위로만 쓴다(app/taxonomy.py classification_strict). 그래서 엄격 추천이 status ok 로
3안을 내고, '분류 확대' 완화 안내나 미충족 표시가 붙지 않아야 한다.
부산·경주는 2026-11-13 실제 키 측정 때 캐시된 장소(tests/fixtures/regional_places.json), 서울 성수는 저장소 자료,
제주·전주·강릉은 재현 자료가 없어 종류별 후보 수를 흉내 낸 자료를 쓴다.
"""
import copy
import json
from pathlib import Path

import pytest

from app import catalog, planner, option_diversity as od
from app.models import Conditions
from app.quality import is_meal
from app.request_intent import normalize

FIXTURE = json.loads((Path(__file__).parent / 'fixtures' / 'regional_places.json').read_text('utf-8'))['regions']
TEMPLATE = FIXTURE['부산']['places'][1]
KINDS = {'meal': ('카페·미식', True, '음식점>한식'), 'cafe': ('카페·미식', False, '음식점>카페,디저트'),
         'culture': ('문화·예술', False, '문화,예술>갤러리,화랑'), 'walk': ('산책·풍경', False, '여행,명소>공원'),
         'workshop': ('체험·제작', False, '생활,편의>공방')}


def synthetic(region, origin, counts):
    """출발지 반경 약 1km 안에 종류별로 흩어 놓은 가짜 장소(이름·id만 다르고 필드는 실제 검색 결과와 같다)."""
    rows = []
    for kind, n in counts.items():
        category, meal, tag = KINDS[kind]
        for i in range(n):
            p = copy.deepcopy(TEMPLATE)
            step = len(rows)
            p.update(id=f'discovered:{region}-{kind}-{i}', name=f'{region} {kind} {i}', region=region, address=f'{region} 테스트로 {step}',
                     category=category, themes=[category], meal=meal, tags=[kind if kind != 'meal' else 'meal', tag], description=tag,
                     lat=origin['lat'] + 0.002 * ((step % 5) - 2), lon=origin['lon'] + 0.002 * ((step // 5) - 2))
            rows.append(p)
    return rows


# (카드 이름, 시·도, 출발지, data-mood, 대분류, 재현 자료). static/index.html 의 data-preset·data-mood 그대로.
JEJU = dict(name='제주 애월 한담해변 지역 중심', lat=33.4621, lon=126.3104)
JEONJU = dict(name='전북 전주 한옥마을 지역 중심', lat=35.8150, lon=127.1530)
GANGNEUNG = dict(name='강원 강릉 안목해변 지역 중심', lat=37.7716, lon=128.9477)
CARDS = [
    ('서울 성수', '서울', dict(name='서울 성수역 지역 중심', lat=37.5446, lon=127.0559), '지적인 데이트', '콘셉트별', None),
    ('부산 해운대', '부산', FIXTURE['부산']['origin'], '활동적인', '타입별', FIXTURE['부산']['places']),
    ('제주 애월', '제주', JEJU, '편안한 데이트', '콘셉트별', synthetic('제주', JEJU, dict(meal=4, cafe=8, walk=3, culture=1))),
    ('경주 황리단길', '경북', FIXTURE['경북']['origin'], '지적인 데이트', '콘셉트별', FIXTURE['경북']['places']),
    ('전주 한옥마을', '전북', JEONJU, '편안한 데이트', '콘셉트별', synthetic('전북', JEONJU, dict(meal=6, cafe=6, culture=4, workshop=2, walk=2))),
    # 강릉: 식당 1곳, 카페가 대부분, 전시·공방은 반경 밖(배포-이어가기.txt 6-1).
    ('강릉 안목해변', '강원', GANGNEUNG, '사교적인', '타입별', synthetic('강원', GANGNEUNG, dict(meal=1, cafe=10, walk=2))),
]


def card_body(region, origin, mood, category, **patch):
    # 카드를 누른 뒤 기본 조건 그대로 추천받을 때의 요청(운영 요청 본문과 같은 필드).
    return dict(course_query='', mode='real', allow_price_estimates=True, allow_estimates=True, stay_minutes=60, region=region,
                origin=origin, visit_date='2026-11-14', start='11:00', end='19:00', people=2, budget=100000, transport='walk',
                count=3, themes=[], date_category=category, date_subcategory=mood, theme_mode='mix', setting='any', avoid=[],
                reservation=False, max_leg=30, request='', locked={}, include_meal=True, neighborhood_radius_km=2.5,
                priority='balanced', trust_mode='balanced', hard_constraints=[], explicit_fields=[]) | patch


@pytest.fixture
def area(monkeypatch):
    def use(region, rows):
        if rows is None:
            return
        original = catalog.places

        def places(mode='demo', visit_date=None):
            found = original(mode, visit_date)
            if mode != 'real':
                return found
            return [p for p in found if p.get('region') != region] + copy.deepcopy(rows)

        monkeypatch.setattr(catalog, 'places', places)
    return use


def kinds(plans):
    return {od.composition_label(p) for p in plans}


@pytest.mark.parametrize('name,region,origin,mood,category,rows', CARDS, ids=[c[0] for c in CARDS])
def test_card_default_is_a_strict_ok_with_three_options(area, name, region, origin, mood, category, rows):
    area(region, rows)
    c = normalize(Conditions(**card_body(region, origin, mood, category)))
    strict = planner.recommend_strict(c)
    assert strict['status'] == 'ok' and len(strict['plans']) == 3, (name, strict.get('reasons'))
    assert len(kinds(strict['plans'])) >= 2, (name, kinds(strict['plans']))
    assert strict['diagnostics']['classification']['applied'] == 'preference'
    result = planner.recommend(Conditions(**card_body(region, origin, mood, category)))
    assert result['status'] == 'ok' and len(result['plans']) == 3
    for plan in result['plans']:
        assert not plan.get('search_adjustments') and not plan.get('best_effort')
        check = next(r for r in plan['condition_checks'] if r['condition'] == 'date_subcategory')
        assert check['state'] == 'info'
        # 식사 규칙은 그대로: 식사 시간대마다 식당 1곳.
        assert sum(is_meal(p) for p in plan['places']) <= 1


def test_card_classification_comes_first_when_it_can(area):
    # 해운대 전체 자료에는 산책(동백·송림 공원)이 있다. '활동적인'에 맞는 산책을 먼저 넣는다.
    name, region, origin, mood, category, rows = CARDS[1]
    area(region, rows)
    result = planner.recommend(Conditions(**card_body(region, origin, mood, category)))
    assert result['plans'][0]['places'] and any(p['category'] == '산책·풍경' for p in result['plans'][0]['places'])


def test_chosen_classification_still_filters(area):
    # 조건 화면에서 소분류를 직접 고르면(explicit_fields) 지금처럼 지킨다.
    name, region, origin, mood, category, rows = CARDS[1]
    area(region, rows)
    c = normalize(Conditions(**card_body(region, origin, mood, category, explicit_fields=['date_subcategory'])))
    strict = planner.recommend_strict(c)
    assert strict['diagnostics']['classification']['applied'] == 'filter'
    allowed = {'레저·활동', '산책·풍경', '체험·제작'}
    assert all(p['category'] in allowed or is_meal(p) for plan in strict['plans'] for p in plan['places'])


def test_classification_from_free_text_still_filters(area):
    name, region, origin, mood, category, rows = CARDS[1]
    area(region, rows)
    c = normalize(Conditions(**card_body(region, origin, '', '', request='활동적인 데이트 하고 싶어')))
    assert c.date_subcategory == '활동적인'
    assert planner.recommend_strict(c)['diagnostics']['classification']['applied'] == 'filter'
