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
