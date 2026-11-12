"""결과 화면에서 고른 축제가 실제 추천 조건(출발 기준·탐색 중심)에 반영되는지."""
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app import store
from app.catalog import places
from app.main import app
from app.models import Conditions
from app.quality import configure, pool
from app.recommendation_summary import festival_context, travel_mode

FESTIVAL = dict(id='770100', title='점검 등불축제', lat=37.5796, lon=126.9770)


def festival_conditions(**fields):
    return Conditions(mode='real', visit_date='2026-10-24', region='서울',
                      origin=dict(name='서울 종로구 · 점검 등불축제 행사장 주변', lat=FESTIVAL['lat'], lon=FESTIVAL['lon']),
                      festival=FESTIVAL, **fields)


def test_festival_anchor_must_be_the_real_mode_origin():
    assert festival_conditions().festival.id == '770100'
    with pytest.raises(ValidationError):
        Conditions(mode='real', visit_date='2026-10-24', origin=dict(name='서울 강남', lat=37.49, lon=127.02), festival=FESTIVAL)
    with pytest.raises(ValidationError):
        Conditions(mode='demo', visit_date='2026-10-24', origin=dict(name='데모', lat=FESTIVAL['lat'], lon=FESTIVAL['lon']), festival=FESTIVAL)


@pytest.mark.parametrize('field,value', [('id', '1' * 241), ('title', '가' * 201), ('lat', 91), ('title', '')])
def test_festival_anchor_fields_are_bounded(field, value):
    payload = festival_conditions().model_dump(mode='json')
    payload['festival'][field] = value
    with TestClient(app) as client:
        assert client.post('/api/plans', json=payload).status_code == 422


def test_seoul_festival_keeps_search_centered_on_the_festival():
    # 동네 이름(종로)이 검색어에 있어도 축제를 고른 코스는 축제 위치를 중심으로 찾는다.
    chosen = configure(festival_conditions(), '종로구 데이트 코스')
    assert chosen.area_center.lat == FESTIVAL['lat'] and chosen.area_center.lon == FESTIVAL['lon']
    plain = configure(festival_conditions().model_copy(update={'festival': None}), '종로구 데이트 코스')
    assert plain.area_center.name == '종로 중심'


def test_choosing_a_different_festival_changes_the_candidate_pool(monkeypatch):
    template = places()[0]
    rows = []
    for i, (lat, lon) in enumerate([(37.5796, 126.9770), (37.5800, 126.9775), (37.5110, 127.0980), (37.5115, 127.0990)]):
        p = deepcopy(template)
        p.update(id=f'festival-near-{i}', name=f'점검 장소 {i}', lat=lat, lon=lon, region='서울', address='서울특별시 점검로')
        rows.append(p)
    monkeypatch.setattr('app.catalog.places', lambda *a: rows)
    first = configure(festival_conditions(), '종로구 데이트 코스')
    other = dict(FESTIVAL, id='770200', title='점검 호수축제', lat=37.5110, lon=127.0980)
    second = configure(Conditions(mode='real', visit_date='2026-10-24', region='서울', festival=other,
                                  origin=dict(name='서울 송파구 · 점검 호수축제 행사장 주변', lat=other['lat'], lon=other['lon'])), '송파구 데이트 코스')
    assert {p['id'] for p in pool(first)} == {'festival-near-0', 'festival-near-1'}
    assert {p['id'] for p in pool(second)} == {'festival-near-2', 'festival-near-3'}


def plan_with(start='11:00', finish='17:00'):
    c = festival_conditions(start=start, end='19:00').model_dump(mode='json')
    return dict(conditions=c, finish=finish, legs=[], places=[])


def test_festival_hours_are_compared_with_the_course_time_from_cache_only():
    store.cache('festival-detail:v1:770100', dict(status='available', hours='18:00~22:00'), 3600)
    after = festival_context(plan_with())
    assert after['hours'] == '18:00~22:00'
    assert any('18:00부터' in note and '17:00 뒤' in note for note in after['notes'])
    store.cache('festival-detail:v1:770100', dict(status='available', hours='10:00~18:00 (입장 마감 17:00)'), 3600)
    during = festival_context(plan_with())
    assert any('11:00~17:00' in note for note in during['notes'])
    store.cache('festival-detail:v1:770100', dict(status='available', hours='상시 개방'), 3600)
    assert any('상시 개방' in note for note in festival_context(plan_with())['notes'])
    with store.connect() as db:
        db.execute('DELETE FROM cache WHERE key=?', ('festival-detail:v1:770100',))
    unknown = festival_context(plan_with())
    assert unknown['hours'] is None and any('확인하지 못했어요' in note for note in unknown['notes'])
    assert festival_context(dict(conditions=Conditions(visit_date='2026-10-24').model_dump(mode='json'))) is None


@pytest.mark.parametrize('transport,mode,statuses,label', [
    ('walk', 'real', ['estimated', 'estimated'], '도보 · 추정'),
    ('car', 'real', ['api', 'api'], '자동차 · 네이버 길찾기'),
    ('car', 'real', ['api', 'estimated'], '자동차 · 일부 네이버 길찾기 · 일부 추정'),
    ('transit', 'real', ['estimated'], '대중교통 · 추정'),
    ('walk', 'demo', ['estimated'], '도보 · 가상 직선거리 추정'),
])
def test_travel_mode_labels_follow_leg_data(transport, mode, statuses, label):
    plan = dict(conditions=dict(transport=transport, mode=mode), legs=[dict(status=s, minutes=5) for s in statuses])
    assert travel_mode(plan)['label'] == label


def test_enriched_plan_names_the_travel_mode():
    from app.recommendation_summary import enrich
    plan = dict(conditions=dict(transport='car', mode='real'), places=[dict(id='a', name='A', category='카페·미식')],
                costs=[dict(status='unknown')], legs=[dict(status='api', minutes=12)])
    enrich(plan)
    assert plan['decision_summary']['travel_mode']['label'] == '자동차 · 네이버 길찾기'
    assert '자동차 이동 약 12분' in plan['decision_summary']['reason']
    assert any('자동차 기준 약 12분' in r and '네이버 길찾기로 조회' in r for r in plan['decision_summary']['fit_reasons'])
