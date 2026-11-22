"""한 곳만 새로운 곳으로: 켠 사람(conditions.fresh_one)의 코스에서 장소 한 곳을 그 사람에게 익숙하지 않은 종류로 채운다.

- 종류: 3안 선택과 같은 묶음(option_diversity.place_group — 식사·카페·보기·걷기·하기·쉬기). '기타'는 세지 않는다.
- 익숙한 종류: 이 브라우저(owner)의 최근 새 추천 코스(parent 없음) RECENT 개 가운데 3분의 1 이상에 나온 묶음.
  저장 코스가 MIN_HISTORY 개보다 적으면 흔한 데이트 구성(DEFAULT_FAMILIAR)으로 본다. 로그인이 없어 '간 곳'이 아니라 '최근 추천받은 곳'이다.
- 추천을 시작할 때(recommendation_service.generate) 서버가 한 번 계산해 조건(fresh_familiar·fresh_basis)에 담는다.
  화면이 보낸 값은 버린다. 저장된 코스는 그 값을 그대로 가지고 있어 다시 열거나 장소를 바꿔도 같은 기준이다.
- 하지 않는 것: 후보를 거르거나 조합을 버리기(정렬 키만 더한다), 새 외부 호출, 공유 화면에 싣기.
"""

import json
import math

from . import store

RECENT = 15
MIN_HISTORY = 3
DEFAULT_FAMILIAR = ['식사', '카페']


def familiar_groups(owner, mode):
    """(익숙한 묶음 목록 — GROUP_ORDER 순, 근거 'history' 또는 'default')."""
    from .option_diversity import GROUP_ORDER, place_group

    with store.connect() as db:
        rows = db.execute(
            'SELECT payload FROM plans WHERE owner=? AND parent IS NULL ORDER BY created DESC LIMIT ?',
            (owner, RECENT * 4),
        ).fetchall()
    seen = []
    for row in rows:
        plan = json.loads(row['payload'])
        if (plan.get('conditions') or {}).get('mode') != mode:
            continue
        seen.append({place_group(p) for p in plan.get('places') or []})
        if len(seen) == RECENT:
            break
    if len(seen) < MIN_HISTORY:
        return list(DEFAULT_FAMILIAR), 'default'
    need = math.ceil(len(seen) / 3)
    return [g for g in GROUP_ORDER if sum(g in groups for groups in seen) >= need], 'history'


def with_familiar(conditions, owner):
    """조건의 익숙한 종류를 서버 값으로 채운다. 켜지 않았으면 비운다(저장되는 조건 모양이 예전과 같다)."""
    if not conditions.fresh_one:
        return conditions.model_copy(update={'fresh_familiar': [], 'fresh_basis': ''})
    groups, basis = familiar_groups(owner, conditions.mode)
    return conditions.model_copy(update={'fresh_familiar': groups, 'fresh_basis': basis})


def fresh_indexes(plan, c):
    """익숙한 종류가 아닌 장소 번호('기타' 제외). 켜지 않았으면 빈 목록."""
    if not c.fresh_one:
        return []
    from .option_diversity import place_group

    return [i for i, p in enumerate(plan['places']) if place_group(p) not in c.fresh_familiar and place_group(p) != '기타']


def fresh_penalty(plan, c):
    """정렬 키: 새로운 곳이 정확히 1곳이면 0, 2곳 이상 1, 없으면 2. 켜지 않았으면 항상 0(정렬이 예전과 같다)."""
    if not c.fresh_one:
        return 0
    count = len(fresh_indexes(plan, c))
    return 0 if count == 1 else 1 if count else 2


def audit_row(plan, c):
    """조건 확인 '새로운 곳 한 곳'의 (상태, 문장)과 plan['fresh_place']. 켜지 않았으면 None."""
    if not c.fresh_one:
        return None
    from .option_diversity import GROUP_LABELS, place_group

    found = fresh_indexes(plan, c)
    plan.pop('fresh_place', None)
    if found:
        index = found[0]
        group = place_group(plan['places'][index])
        plan['fresh_place'] = dict(index=index, group=group, label=GROUP_LABELS[group])
        state = 'met'
        message = f"{plan['places'][index]['name']}({GROUP_LABELS[group]}) — 최근 코스에 드물던 종류예요."
        if len(found) > 1:
            message += f' 새로운 종류가 {len(found)}곳 들어갔어요.'
    else:
        state = 'unknown'
        message = '이 동네 후보에서 최근 코스와 다른 종류를 찾지 못했어요. 테마나 동네를 바꿔 보세요.'
    if c.fresh_basis == 'default':
        message += ' 최근 코스 기록이 적어 식사·카페를 익숙한 종류로 봤어요.'
    return state, message
