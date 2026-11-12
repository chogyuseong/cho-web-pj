"""'어떤 하루를 원하세요' 자유 입력의 규칙 기반 기준 데이터: 동의어·날씨·계절·동행·예산 감각·제외 조건."""
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from app.catalog import places
from app.main import app
from app.models import Conditions
from app.request_intent import interpret, normalize


@pytest.mark.parametrize('text,wanted', [
    ('브런치 먹고 전시회', {'cafe', 'culture'}),
    ('원데이클래스 체험하고 싶어', {'workshop'}),
    ('바닷가 걷기', {'walk'}),
    ('벚꽃 보러 가자', {'walk'}),
    ('노래방 가자', {'game'}),
    ('서핑 하고 싶어', {'activity'}),
    ('루프탑에서 경치 보기', {'view'}),
    ('백화점 쇼핑', {'shopping'}),
    ('찜질방에서 쉬고 싶어', {'rest'}),
    ('오페라 보러 갈래', {'performance'}),
    ('과학관 구경', {'museum'}),
    ('맛있는 거 먹으러 가자', {'meal'}),
])
def test_common_expressions_become_activities(text, wanted):
    assert set(interpret(text)['intents']) == wanted


@pytest.mark.parametrize('text,key', [
    ('걷는 건 싫어', 'walk'),
    ('걷기 싫어요', 'walk'),
    ('오래 안 걷고 싶어', 'walk'),
    ('걷고 싶지 않아', 'walk'),
    ('노래방은 별로', 'game'),
    ('등산은 힘들어', 'activity'),
    ('찜질방은 관심 없어', 'rest'),
])
def test_negative_expressions_are_never_positive(text, key):
    result = interpret(text)
    assert key in result['excluded'] and key not in result['intents']


def test_walking_dislike_changes_transport_only_without_another_choice():
    parsed = interpret('걷는 건 싫어')
    assert parsed['patch']['transport'] == 'transit' and parsed['warnings']
    assert interpret('걷는 건 싫어, 차로 갈게')['patch']['transport'] == 'car'
    assert 'transport' not in interpret('산책하고 싶어')['patch']
    assert interpret('산책하고 싶어')['intents'] == ['walk']


@pytest.mark.parametrize('text,label,word', [
    ('매운 건 빼고', '매운 음식', '매운'),
    ('안 매운 음식으로', '매운 음식', '마라'),
    ('맵찔이라 순한 맛집', '매운 음식', '불닭'),
    ('술은 빼고', '술', '술집'),
    ('해산물 알레르기가 있어요', '해산물', '횟집'),
])
def test_food_exclusions_become_avoid_words(text, label, word):
    parsed = interpret(text)
    assert word in parsed['patch']['avoid']
    assert any(label in warning and '메뉴까지 확인한 것은 아니에요' in warning for warning in parsed['warnings'])


@pytest.mark.parametrize('text', ['매운 거 좋아', '미술관 가고 싶어', '술 한잔 하자', '해산물 맛집'])
def test_positive_food_words_do_not_exclude(text):
    assert 'avoid' not in interpret(text)['patch']


def test_food_exclusion_does_not_hide_the_requested_meal():
    parsed = interpret('매운 건 빼고 맛집')
    assert parsed['intents'] == ['meal'] and '매운' in parsed['patch']['avoid']


def test_avoid_words_merge_with_user_avoid_and_filter_candidates(monkeypatch):
    template = places()[0]
    rows = []
    for i, name in enumerate(['매운 떡볶이 식당', '순한 한식당', '마라탕 집']):
        p = deepcopy(template)
        p.update(id=f'spicy-{i}', name=name, category='카페·미식', themes=['카페·미식'], tags=['meal'], meal=True,
                 lat=37.575 + i * .0003, lon=126.985, setting='indoor', price=[1000, 1000], reservation=False)
        rows.append(p)
    monkeypatch.setattr('app.quality.pool', lambda c: rows)
    from app.planner import candidates
    c = normalize(Conditions(visit_date='2026-10-24', request='매운 건 빼고 맛집', avoid=['클라이밍']))
    assert c.avoid[0] == '클라이밍' and '매운' in c.avoid and '마라' in c.avoid
    assert [p['name'] for p in candidates(c)] == ['순한 한식당']


@pytest.mark.parametrize('text,category,sub', [
    ('비 오는 날 데이트', '날씨별', '비 오는 날'),
    ('눈 오는 날 어디 가지', '날씨별', '눈 오는 날'),
    ('화창한 날 데이트', '날씨별', '맑은 날'),
    ('가을 데이트 추천', '계절별', '가을'),
    ('봄에 데이트하고 싶어', '계절별', '봄'),
    ('크리스마스 데이트', '계절별', '겨울'),
    ('여유로운 데이트', '콘셉트별', '편안한 데이트'),
    ('신나는 데이트', '콘셉트별', '즐거운 데이트'),
    ('활동적인 하루', '타입별', '활동적인'),
])
def test_weather_season_and_mood_become_date_classification(text, category, sub):
    patch = interpret(text)['patch']
    assert (patch['date_category'], patch['date_subcategory']) == (category, sub)


def test_weather_sets_indoor_and_activities_take_precedence_over_classification():
    assert interpret('눈 오는 날')['patch']['setting'] == 'indoor'
    assert interpret('폭염이라 시원한 데 가고 싶어')['patch']['setting'] == 'indoor'
    outdoor = interpret('추운 날이지만 산책')
    assert 'setting' not in outdoor['patch'] and outdoor['warnings']
    assert 'date_category' not in interpret('겨울 카페 투어')['patch']
    assert 'date_category' not in interpret('돌봄 서비스 근처')['patch']
    conditional = interpret('날씨 좋으면 공원')
    assert 'setting' not in conditional['patch'] and conditional['warnings']


def test_classification_from_text_respects_explicit_choices():
    c = normalize(Conditions(visit_date='2026-10-24', request='가을 데이트'))
    assert (c.date_category, c.date_subcategory) == ('계절별', '가을')
    chosen = normalize(Conditions(visit_date='2026-10-24', request='가을 데이트', date_category='콘셉트별',
                                  date_subcategory='편안한 데이트', explicit_fields=['date_subcategory']))
    assert (chosen.date_category, chosen.date_subcategory) == ('콘셉트별', '편안한 데이트')
    themed = normalize(Conditions(visit_date='2026-10-24', request='가을 데이트', themes=['카페·미식'], explicit_fields=['themes']))
    assert themed.date_subcategory == '' and themed.themes == ['카페·미식']
    # 활동을 말하면서 소분류만 직접 골라도 대분류가 비어 검증 오류가 나지 않는다.
    mixed = normalize(Conditions(visit_date='2026-10-24', request='카페', date_category='계절별', date_subcategory='가을',
                                 explicit_fields=['date_subcategory']))
    assert (mixed.date_category, mixed.date_subcategory) == ('계절별', '가을')


@pytest.mark.parametrize('text,people', [('여자친구랑 전시', 2), ('남편이랑 산책', 2), ('혼자 전시 보러', 1), ('여친이랑 셋이', 3)])
def test_companions(text, people):
    assert interpret(text)['patch']['people'] == people


def test_meeting_type_from_text_and_explicit_choice_wins():
    assert interpret('첫 데이트라 긴장돼')['patch']['meeting_type'] == 'first'
    assert interpret('100일 기념 데이트')['patch']['meeting_type'] == 'anniversary'
    assert normalize(Conditions(visit_date='2026-10-24', request='소개팅')).meeting_type == 'first'
    kept = normalize(Conditions(visit_date='2026-10-24', request='소개팅', meeting_type='anniversary', explicit_fields=['meeting_type']))
    assert kept.meeting_type == 'anniversary'


@pytest.mark.parametrize('text,transport', [
    ('차로 이동할게', 'car'), ('드라이브 데이트', 'car'), ('차가 없어서 지하철로', 'transit'),
    ('따릉이 타고 다니자', 'bicycle'), ('버스킹 구경', None), ('운전 못해요', None)])
def test_transport_expressions(text, transport):
    assert interpret(text)['patch'].get('transport') == transport


def test_mood_priorities():
    assert interpret('사람 많은 곳은 싫어')['patch']['priority'] == 'talk'
    assert interpret('인스타 감성')['patch']['priority'] == 'photo'
    assert interpret('몸 쓰는 데이트')['patch']['priority'] == 'activity'


def test_low_budget_style_prefers_cheaper_plans():
    from app.preferences import fit_score
    parsed = interpret('가성비 좋은 데이트')
    assert parsed['budget_style'] == 'low' and parsed['warnings'] and 'budget' not in parsed['patch']
    c = Conditions(visit_date='2026-10-24', request='가성비 좋은 데이트')
    plan = lambda total: dict(places=[dict(id='x', category='카페·미식')], legs=[dict(minutes=5)], total=[0, total])
    assert fit_score(plan(20000), c) > fit_score(plan(80000), c)
    plain = Conditions(visit_date='2026-10-24')
    assert fit_score(plan(20000), plain) == fit_score(plan(80000), plain)


def test_parse_api_returns_new_criteria():
    with TestClient(app) as client:
        result = client.post('/api/conditions/parse', json={'text': '가을에 여자친구랑, 매운 건 빼고', 'people': 2}).json()
    assert result['patch']['date_subcategory'] == '가을' and result['patch']['people'] == 2
    assert '매운' in result['patch']['avoid']
