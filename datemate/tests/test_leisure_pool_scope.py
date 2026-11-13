"""레저 후보 조회로 찾아 둔 운동 시설은 운동을 원한 요청에서만 추천 후보가 된다.

누군가 레저 패널을 열면 탁구장·볼링장이 장소 목록에 저장된다. 그 뒤 같은 동네의 기본 추천에
'탁구장 → 식사 → 볼링장' 같은 코스가 섞이면 안 된다."""
import pytest

from app import quality
from app.models import Conditions

LEISURE = '네이버 지역 검색 · 레저 종목 분류'


def _conditions(**update):
    base = dict(mode='real', allow_estimates=True, include_meal=False, visit_date='2026-11-12', region='부산',
                origin={'name': '부산광역시 부산진구 부전동', 'lat': 35.1578, 'lon': 129.0600}, count=3)
    return Conditions(**(base | update))


def _place(pid, category, dlat=0.0, **extra):
    return dict(id=pid, name=pid, region='부산', lat=35.1578 + dlat, lon=129.0600, category=category,
                meal=False) | {'tags': []} | extra


@pytest.fixture
def catalog(monkeypatch):
    rows = [_place('cafe', '카페·미식'), _place('park', '산책·풍경', .001),
            _place('pingpong', '레저·활동', .002, source_type=LEISURE, tags=['table_tennis']),
            _place('curated-leisure', '레저·활동', .003, source_type='운영자 확인')]
    monkeypatch.setattr('app.catalog.places', lambda *a, **k: [dict(row) for row in rows])


def _ids(c):
    return {p['id'] for p in quality.pool(c)}


def test_default_request_leaves_out_venues_found_by_leisure_search(catalog):
    ids = _ids(_conditions())
    assert 'pingpong' not in ids
    # 레저 조회에서 온 것만 뺀다. 원래 있던 레저 장소와 다른 종류는 그대로 후보다.
    assert {'cafe', 'park', 'curated-leisure'} <= ids


@pytest.mark.parametrize('update', [
    dict(request='탁구 치고 싶어'),
    dict(request='운동하고 싶어'),
    dict(themes=['레저·활동']),
    # 조건 화면에서 소분류를 직접 고른 경우(화면이 explicit_fields 에 넣는다).
    dict(date_category='타입별', date_subcategory='활동적인', explicit_fields=['date_subcategory']),
])
def test_requests_that_want_leisure_keep_them(catalog, update):
    assert 'pingpong' in _ids(_conditions(**update))


def test_card_classification_does_not_bring_in_leisure_search_venues(catalog):
    # 홈 동네 카드(부산 해운대)가 넣은 '활동적인'은 사용자가 고른 것이 아니다. 기본 추천과 같으므로 운동 시설을 섞지 않는다.
    ids = _ids(_conditions(date_category='타입별', date_subcategory='활동적인'))
    assert 'pingpong' not in ids and {'cafe', 'park', 'curated-leisure'} <= ids


def test_request_that_rejects_sport_does_not_count_as_wanting_it(catalog):
    assert 'pingpong' not in _ids(_conditions(request='운동 말고 카페 가고 싶어'))


def test_place_the_user_locked_stays(catalog):
    assert 'pingpong' in _ids(_conditions(locked={1: 'pingpong'}))
