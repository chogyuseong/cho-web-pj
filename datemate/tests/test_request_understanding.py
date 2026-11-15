"""자유 입력 해석 결과 구조: 이해한 항목(근거·출처·추정)과 반영하지 못한 조각, 화면에서 뺀 항목(ignore)."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Conditions
from app.request_intent import _assemble, interpret, normalize


def ids(parsed):
    return [item['id'] for item in parsed['items']]


def test_items_carry_condition_evidence_source_and_estimate():
    parsed = interpret('조용하고 비 와도 괜찮은 곳')
    items = {item['id']: item for item in parsed['items']}
    assert set(items) == {'priority:talk', 'setting:indoor', 'date:비 오는 날'}
    talk = items['priority:talk']
    assert talk['field'] == 'priority' and talk['value'] == 'talk' and talk['source'] == 'rule'
    assert talk['evidence'] == ['조용하고'] and talk['estimated'] and '소음' in talk['note']
    assert items['setting:indoor']['evidence'] == ['비 와도'] and not items['setting:indoor']['estimated']
    assert not any(key.startswith('_') for item in parsed['items'] for key in item)
    assert parsed['unparsed'] == []
    assert parsed['patch'] == dict(priority='talk', setting='indoor', date_category='날씨별', date_subcategory='비 오는 날')


@pytest.mark.parametrize('text,fragment', [
    ('분위기 좋은 곳 추천해줘', '분위기 좋은'),
    ('주차 편한 곳으로', '주차 편한'),
    ('한강 가서 치맥', '치맥'),
    ('웨이팅 없는 맛집', '웨이팅 없는'),
])
def test_unsupported_phrases_are_reported(text, fragment):
    gaps = interpret(text)['unparsed']
    assert [g['text'] for g in gaps if g['reason'] == 'unknown'] == [fragment]
    assert gaps[0]['message'].startswith('‘' + fragment + '’') and gaps[0]['message'].endswith('아직 반영하지 못했어요.')


@pytest.mark.parametrize('text', ['데이트 코스 추천해줘', '카페 가자', '그냥 아무 데나 괜찮아', '비 오는 날 실내 카페'])
def test_glue_words_are_not_reported(text):
    assert interpret(text)['unparsed'] == []


def test_negation_with_mood_food_and_activities():
    assert interpret('시끄러운 데는 싫어')['patch'] == {'priority': 'talk'}
    assert interpret('사람 많은 곳 말고 한적한 공원 산책')['patch']['priority'] == 'talk'
    # 조용한 곳을 싫다고 하면 조용함으로 보지 않는다.
    assert 'priority' not in interpret('조용한 건 싫어')['patch']
    assert interpret('술 마시는 데는 말고 카페')['intents'] == ['cafe']
    assert '술집' in interpret('술 마시는 데는 말고 카페')['patch']['avoid']
    both = interpret('매운 음식이랑 술은 빼줘')['patch']['avoid']
    assert '마라' in both and '포차' in both
    assert interpret('전시 같은 데는 별로')['excluded'] == ['culture']
    assert interpret('방탈출은 무서워서 싫어')['excluded'] == ['game']
    # 부정은 바로 앞 낱말에만: 뒤에 오는 활동까지 부정하지 않는다.
    assert interpret('카페 말고 전시')['intents'] == ['culture']
    assert interpret('실외는 너무 더워서 싫어요')['patch']['setting'] == 'indoor'


def test_walking_less_excludes_walks_and_prefers_transit():
    for text in ('걷기 적게', '힐 신고 가서 오래 못 걸어', '덜 걷는 코스'):
        parsed = interpret(text)
        assert parsed['excluded'] == ['walk'] and parsed['patch']['transport'] == 'transit', text
        assert not parsed['intents']
    assert interpret('걷기 좋은 길')['intents'] == ['walk']


def test_only_one_priority_the_rest_is_reported_as_conflict():
    parsed = interpret('조용하고 사진 잘 나오는 곳')
    assert parsed['patch']['priority'] == 'photo'
    conflict = [g for g in parsed['unparsed'] if g['reason'] == 'conflict']
    assert conflict and conflict[0]['text'] == '조용하고' and '하나만' in conflict[0]['message']


def test_conditional_weather_is_reported_not_applied():
    parsed = interpret('비 오면 실내, 맑으면 야외 산책')
    assert 'setting' not in parsed['patch']
    assert {g['reason'] for g in parsed['unparsed']} == {'conditional'}


def test_activity_first_classification_words_are_reported():
    parsed = interpret('겨울 카페 투어')
    assert 'date_category' not in parsed['patch'] and parsed['patch']['theme_mode'] == 'focus'
    assert [g['text'] for g in parsed['unparsed']] == ['겨울']


def test_focus_only_attaches_to_the_activity_word():
    assert interpret('실내 위주로 카페랑 전시')['exclusive'] is False
    assert interpret('해물 빼고 고기 위주로 먹고 싶다')['exclusive'] is False
    assert interpret('맛집 위주')['exclusive'] is True


def test_ignore_removes_only_that_item_and_its_warning():
    text = '가성비 좋게 카페 투어, 비 와도 괜찮은 곳'
    full = interpret(text)
    assert {'budget_style:low', 'activity:cafe', 'theme_mode:focus', 'setting:indoor'} <= set(ids(full))
    cheap = interpret(text, ('budget_style:low',))
    assert cheap['budget_style'] is None and not any('저렴한' in w for w in cheap['warnings'])
    assert [i['id'] for i in cheap['ignored']] == ['budget_style:low']
    no_cafe = interpret(text, ('activity:cafe',))
    # 활동을 빼면 그 활동에 붙은 집중(카페만)도 효과가 없어 보이지 않는다.
    assert not no_cafe['intents'] and 'theme_mode' not in no_cafe['patch'] and 'theme_mode:focus' not in ids(no_cafe)
    assert no_cafe['patch']['setting'] == 'indoor'


def test_server_honours_request_ignore_when_planning():
    c = Conditions(visit_date='2026-10-24', request='조용한 카페 투어, 매운 건 빼고')
    assert normalize(c).priority == 'talk' and '매운' in normalize(c).avoid
    kept = normalize(c.model_copy(update={'request_ignore': ['priority:talk', 'avoid:매운 음식']}))
    assert kept.priority == 'balanced' and '매운' not in kept.avoid and kept.themes == ['카페·미식']


def test_request_ignore_is_bounded_and_kept_out_of_old_shaped_dumps():
    assert 'request_ignore' not in Conditions(visit_date='2026-10-24').model_dump(mode='json')
    dumped = Conditions(visit_date='2026-10-24', request_ignore=['priority:talk']).model_dump(mode='json')
    assert dumped['request_ignore'] == ['priority:talk']
    assert Conditions.model_validate(dumped).request_ignore == ['priority:talk']
    with pytest.raises(ValueError):
        Conditions(visit_date='2026-10-24', request_ignore=['not an id'])
    with pytest.raises(ValueError):
        Conditions(visit_date='2026-10-24', request_ignore=[f'priority:x{i}' for i in range(41)])


def test_other_sources_can_be_assembled_with_the_same_rules():
    # 2단계에서 규칙이 못 알아들은 조각만 다른 해석기로 보내 같은 항목 구조(source 만 다름)로 더한다.
    ai = dict(id='priority:talk', field='priority', value='talk', label='조용한 곳·대화 우선', evidence=['고즈넉한'],
              source='ai', estimated=True, note='')
    rule = interpret('카페 가자')['items']
    merged = _assemble([*rule, ai], [])
    assert merged['patch']['priority'] == 'talk' and merged['intents'] == ['cafe']


def test_parse_api_returns_understanding_and_accepts_ignore():
    with TestClient(app) as client:
        body = client.post('/api/conditions/parse', json={'text': '조용하고 분위기 좋은 카페'}).json()
        assert [i['id'] for i in body['understood']] == ['activity:cafe', 'priority:talk']
        assert body['ignored'] == [] and body['unparsed'] == '조용하고 분위기 좋은 카페'
        assert [g['text'] for g in body['not_understood']] == ['분위기 좋은']
        removed = client.post('/api/conditions/parse', json={'text': '조용하고 분위기 좋은 카페', 'ignore': ['priority:talk']}).json()
        assert 'priority' not in removed['patch'] and [i['id'] for i in removed['ignored']] == ['priority:talk']
        assert client.post('/api/conditions/parse', json={'text': '카페', 'ignore': ['아무 말']}).status_code == 422
