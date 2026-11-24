"""폐업한 곳을 추천하지 않는다 (2026-11-24 사용자 신고: '데이트 코스 추천을 받았는데 폐업한 곳이 나왔어').

- 행정안전부 인허가 자료로 '폐업으로 등록됨'(closed)이 저장된 식당·카페는 추천 후보(quality.pool)에서 뺀다.
  예전에는 화면의 '위치' 줄에 표시만 하고 후보에는 남겼다.
- 사용자가 고정한 장소는 남긴다(직접 고른 곳을 말없이 빼지 않는다 — 화면에 '폐업으로 등록됨'이 그대로 보인다).
- 영업 중(open)·판정 없음은 그대로 후보다(자료가 없다고 빼지 않는다).
- 추천 결과에 들어간 식당·카페 중 판정이 아직 없는 곳은 바로 배경 조회 대기열에 넣어, 다음 추천부터 걸러지게 한다(place_identity.prefetch).
"""
from datetime import date

from app import catalog, place_identity, store
from app.models import Conditions
from app.quality import pool


def cafe(pid, name):
    return dict(id='fixture:' + pid, name=name, category='카페·미식', region='서울', lat=37.5446, lon=127.0557,
                address='서울 성동구 성수이로 ' + pid[-1], hours=[600, 1320], stay=60, last_entry=None, breaks=None,
                closed_days=[], price=[5000, 9000], price_unit='person', source='https://example.org/' + pid,
                checked_at='2026-11-01', reservation=False, tags=[], setting='indoor')


PLACES = [cafe('c1', '문 닫은 카페'), cafe('c2', '영업 중 카페'), cafe('c3', '판정 없는 카페')]


def conditions(**kw):
    base = dict(mode='real', region='서울', visit_date=date(2026, 12, 5), allow_estimates=True, max_leg=180,
                origin=dict(name='성수역', lat=37.5446, lon=127.0557))
    base.update(kw)
    return Conditions(**base)


def judge(place, status):
    store.cache(place_identity.cache_key(place, 'license'), dict(status=status, kind='휴게음식점', checked_at='2026-11-24T00:00:00+00:00'), 3600)


def ids(rows):
    return {p['id'] for p in rows}


def test_closed_license_places_are_not_candidates(monkeypatch):
    monkeypatch.setattr(catalog, 'places', lambda mode, visit_date=None: [dict(p) for p in PLACES])
    judge(PLACES[0], 'closed')
    judge(PLACES[1], 'open')
    got = ids(pool(conditions()))
    assert 'fixture:c1' not in got, '폐업으로 등록된 곳은 후보가 아니다'
    assert {'fixture:c2', 'fixture:c3'} <= got, '영업 중·판정 없는 곳은 그대로'


def test_a_locked_closed_place_stays(monkeypatch):
    monkeypatch.setattr(catalog, 'places', lambda mode, visit_date=None: [dict(p) for p in PLACES])
    judge(PLACES[0], 'closed')
    assert 'fixture:c1' in ids(pool(conditions(locked={0: 'fixture:c1'})))


def test_demo_mode_is_unchanged(monkeypatch):
    # 가상 장소(데모)는 인허가 판정이 없고 거르지 않는다.
    monkeypatch.setattr(catalog, 'places', lambda mode, visit_date=None: [dict(p) for p in PLACES])
    judge(PLACES[0], 'closed')
    assert 'fixture:c1' in ids(pool(conditions(mode='demo')))


def test_prefetch_queues_only_food_places_without_a_verdict(monkeypatch):
    monkeypatch.setenv('TOUR_API_KEY', 'test-key')
    place_identity._queue.clear()
    judge(PLACES[1], 'open')
    gallery = dict(cafe('g1', '전시관'), category='전시')
    place_identity.prefetch([PLACES[1], PLACES[2], gallery, dict(PLACES[0], demo=True)])
    queued = [p['id'] for p in place_identity._queue.values()]
    assert queued == ['fixture:c3'], '판정이 있는 곳·음식점이 아닌 곳·가상 장소는 넣지 않는다'
