"""한국관광공사 '쉬는 날' 안내를 휴무일 계산에 넣는다 (2026-11-24 사용자 결정: 관광공사 쉬는 날 반영, '(관광공사 안내 기준)' 표시).

- 읽는 글: TourAPI detailIntro2 의 쉬는 날 필드(app/tour_places.HOURS_FIELDS) — 카드를 열 때 받아 보관해 둔 것만 쓴다(추천 계산에서 새로 부르지 않음).
- 매주 쉬는 요일이 분명할 때만 쓴다('매주 월요일', '월·화요일 휴무'). '연중무휴'는 휴무 없음.
  '둘째·넷째 주', '격주', '마지막 주'처럼 매주가 아닌 글은 쓰지 않는다(예전처럼 '확인 필요').
- 운영자가 확인한 휴무일(closed_days)이 있으면 그것이 먼저다.
"""
from datetime import date

import pytest

from app import store, tour_places
from app.models import Conditions
from app.planner import evaluate


@pytest.mark.parametrize('text,days', [
    ('매주 월요일', [0]),
    ('월요일', [0]),
    ('매주 월, 화요일 휴무', [0, 1]),
    ('월·화요일 정기휴무', [0, 1]),
    ('매주 일요일 (공휴일 제외)', [6]),
    ('매주 월요일, 1월 1일, 설날 및 추석 당일', [0]),
    ('연중무휴', []),
    ('연중 무휴', []),
    ('매월 둘째, 넷째 주 월요일', None),
    ('격주 화요일', None),
    ('매월 마지막 주 수요일', None),
    ('부정기 휴무', None),
    ('', None),
    (None, None),
])
def test_rest_weekdays(text, days):
    assert tour_places.rest_weekdays(text) == days


def place(**kw):
    base = dict(id='fixture:t1', name='월요일에 쉬는 전시', category='전시', region='서울', lat=37.5446, lon=127.0557,
                address='서울 성동구 성수이로 1', hours=[600, 1200], stay=60, last_entry=None, breaks=None, closed_days=None,
                price=[0, 0], price_unit='person', source='https://example.org/t1', checked_at='2026-11-01', reservation=False)
    base.update(kw)
    return base


def remember(p, rest):
    """카드를 열 때 tour_info 가 보관하는 것과 같은 자리에 안내를 둔다."""
    store.cache(tour_places.info_cache_key(p), dict(status='available', content_id='1', hours=None, rest=rest,
                                                    source_url='https://korean.visitkorea.or.kr/detail/ms_detail.do?cotid=1'), 3600)


def conditions(day):
    return Conditions(mode='real', region='서울', visit_date=day, allow_estimates=True, count=2, max_leg=180,
                      start='11:00', end='18:00', origin=dict(name='성수역', lat=37.5446, lon=127.0557))


MONDAY, TUESDAY = date(2026, 12, 7), date(2026, 12, 8)


def rows(*places):
    """추천 후보를 모을 때(quality.pool) 하는 것과 같이 보관된 관광공사 안내로 휴무 요일을 채운다."""
    return tour_places.apply_rest_days([dict(p) for p in places])


def test_planner_uses_the_tour_rest_day():
    p, other = place(), place(id='fixture:t2', name='늘 여는 카페', closed_days=[])
    remember(p, '매주 월요일')
    filled = rows(p, other)
    assert filled[0]['closed_days'] == [0] and filled[0]['closed_days_basis'] == '관광공사 안내 기준'
    plan, error = evaluate(filled, conditions(MONDAY))
    assert plan is None and '휴무' in str(error), (plan, error)
    plan, error = evaluate(filled, conditions(TUESDAY))
    assert not error
    # 휴무를 관광공사 안내로 알았으므로 '휴무 확인 필요'로 세지 않는다.
    assert '월요일에 쉬는 전시 휴무' not in plan['unknown'], plan['unknown']


def test_unclear_or_missing_text_keeps_the_old_assumption():
    p, other = place(), place(id='fixture:t2', name='늘 여는 카페', closed_days=[])
    remember(p, '매월 둘째, 넷째 주 월요일')
    filled = rows(p, other)
    assert filled[0]['closed_days'] is None and 'closed_days_basis' not in filled[0]
    plan, error = evaluate(filled, conditions(MONDAY))
    assert not error, '애매한 글은 쓰지 않고 예전처럼 연다고 가정한다'


def test_operator_closed_days_come_first():
    p, other = place(closed_days=[2]), place(id='fixture:t2', name='늘 여는 카페', closed_days=[])
    remember(p, '매주 월요일')
    filled = rows(p, other)
    assert filled[0]['closed_days'] == [2] and 'closed_days_basis' not in filled[0]
    plan, error = evaluate(filled, conditions(MONDAY))
    assert not error, '운영자가 확인한 휴무일(수요일)이 관광공사 안내보다 먼저다'


def test_pool_fills_rest_days(monkeypatch):
    from app import catalog
    from app.quality import pool
    p = place()
    remember(p, '매주 월요일')
    monkeypatch.setattr(catalog, 'places', lambda mode, visit_date=None: [dict(p)])
    got = {row['id']: row for row in pool(conditions(MONDAY))}
    assert got['fixture:t1']['closed_days'] == [0]


def test_tour_hours_carries_the_parsed_days(monkeypatch):
    p = place()
    monkeypatch.setattr(tour_places, 'tour_info', lambda place, force=False: dict(status='available', hours='10:00~20:00', rest='매주 월요일', source_url='u'))
    assert tour_places.tour_hours(p)['closed_days'] == [0]
    monkeypatch.setattr(tour_places, 'tour_info', lambda place, force=False: dict(status='available', hours='10:00~20:00', rest='격주 월요일', source_url='u'))
    assert tour_places.tour_hours(p)['closed_days'] is None
