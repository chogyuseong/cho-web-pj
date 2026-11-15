"""평소 말 요청 해석 평가 세트(tests/fixtures/plain_requests.json, 합성 문장)의 정답률 하한.

- 문장 정답: 기대 해석(e)의 모든 항목이 실제 해석과 같고, 기대하지 않은 항목이 없을 때.
- 조건 단위: (항목, 값) 짝의 정밀도·재현율.
- 미지원 알림: u=true 문장에서 '반영하지 못함' 조각을 하나 이상 내는지(재현율), u 가 없는 문장에서 내지 않는지(정밀도).
하한은 이 규칙으로 실제로 잰 값에서 몇 문장 여유를 둔 값이다(측정값은 docs 가 아니라 작업 보고에 적었다).
"""
import json
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / 'fixtures' / 'plain_requests.json'
FIELDS = ('setting', 'people', 'count', 'meeting_type', 'budget', 'transport', 'reservation', 'priority', 'max_walk', 'theme_mode')


def rows(kind=None):
    data = json.loads(FIXTURE.read_text('utf-8'))['rows']
    return [r for r in data if kind is None or r['set'] == kind]


def observed(parsed, resolved_patch, food_avoid):
    """해석 결과를 평가 형식(e)으로. 예산은 인원 2명 기준 전체 예산."""
    label_of = {word: label for _, label, words, *_ in food_avoid for word in words}
    patch = resolved_patch(parsed, 2, False)
    out = {}
    if parsed['intents']:
        out['intents'] = sorted(set(parsed['intents']))
    if parsed['excluded']:
        out['excluded'] = sorted(set(parsed['excluded']))
    for key in FIELDS:
        if key in patch:
            out[key] = patch[key]
    if patch.get('date_subcategory'):
        out['date'] = patch['date_subcategory']
    if patch.get('avoid'):
        out['avoid'] = sorted({label_of[w] for w in patch['avoid'] if w in label_of})
    if parsed.get('budget_style'):
        out['budget_style'] = parsed['budget_style']
    return out


def expected(row):
    return {k: sorted(v) if isinstance(v, list) else v for k, v in row['e'].items()}


def pairs(view):
    return {(k, x) for k, v in view.items() for x in (v if isinstance(v, list) else [v])}


def score(interpret, resolved_patch, food_avoid, data, unparsed_of=None):
    exact = 0
    tp = fp = fn = 0
    misses = []
    flag = dict(tp=0, fp=0, fn=0)
    for row in data:
        parsed = interpret(row['t'])
        got, want = observed(parsed, resolved_patch, food_avoid), expected(row)
        if got == want:
            exact += 1
        else:
            misses.append((row['t'], want, got))
        g, w = pairs(got), pairs(want)
        tp += len(g & w); fp += len(g - w); fn += len(w - g)
        if unparsed_of:
            said = bool([u for u in unparsed_of(parsed) if u['reason'] == 'unknown'])
            if said and row.get('u'): flag['tp'] += 1
            elif said: flag['fp'] += 1
            elif row.get('u'): flag['fn'] += 1
    return dict(n=len(data), exact=exact, accuracy=exact / len(data), precision=tp / max(1, tp + fp), recall=tp / max(1, tp + fn),
                misses=misses, flag=flag)


def current(data):
    from app.request_intent import FOOD_AVOID, interpret, resolved_patch
    return score(interpret, resolved_patch, FOOD_AVOID, data, lambda parsed: parsed['unparsed'])


def test_fixture_is_large_varied_and_well_formed():
    data = rows()
    assert len(data) >= 150 and len(rows('dev')) >= 120 and len(rows('fresh')) >= 30 and len(rows('fresh2')) >= 20
    assert {r['set'] for r in data} == {'dev', 'fresh', 'fresh2'}
    assert len({r['t'] for r in data}) == len(data)
    tags = {t for r in data for t in r['g']}
    assert {'반말', '줄임말', '오타', '부정', '복합', '미지원'} <= tags
    allowed = {'intents', 'excluded', 'date', 'avoid', 'budget_style', *FIELDS}
    for r in data:
        assert set(r['e']) <= allowed, r['t']


# 2026-11-15 측정(문장 정답): dev 125/125, fresh 27/30, fresh2 17/20. 처음 볼 때(규칙을 고치기 전) fresh 19/30, fresh2 10/20.
# 하한은 측정값보다 몇 문장 낮게 잡아 표현을 조금 바꾸는 수정은 허용하고, 크게 나빠지면 잡는다.
@pytest.mark.parametrize('kind,floor', [('dev', 0.95), ('fresh', 0.80), ('fresh2', 0.75)])
def test_plain_request_accuracy_floor(kind, floor):
    result = current(rows(kind))
    assert result['accuracy'] >= floor, (result['accuracy'], result['misses'])


def test_unsupported_requests_are_reported_not_silently_dropped():
    # 측정: u 문장 26/26 을 알렸고, 알린 33문장 중 26문장이 u 문장이었다.
    result = current(rows())
    flag = result['flag']
    recall = flag['tp'] / max(1, flag['tp'] + flag['fn'])
    precision = flag['tp'] / max(1, flag['tp'] + flag['fp'])
    assert recall >= 0.90 and precision >= 0.65, flag
