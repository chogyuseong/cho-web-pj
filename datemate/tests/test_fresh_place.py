"""한 곳만 새로운 곳으로(app/fresh_place.py): 켠 사람의 코스에서 장소 한 곳을 최근 코스에 드물던 종류로 채우고 알리는지.
익숙한 종류는 이 브라우저(owner)의 최근 저장 코스로 서버가 정하고, 켜지 않은 코스는 예전과 같은지."""
import uuid
from datetime import date

from fastapi.testclient import TestClient

from app import store
from app.fresh_place import familiar_groups, with_familiar
from app.main import app  # noqa: F401  (DB 초기화)
from app.models import Conditions

CATEGORY = {'카페': '카페·미식', '보기': '문화·예술', '걷기': '산책·풍경', '하기': '체험·제작', '쉬기': '휴식·힐링'}


def place(group, n=0):
    if group == '식사':
        return dict(id=f'food:{n}', name=f'점검 식당 {n}', category='카페·미식', meal=True)
    return dict(id=f'{group}-{n}', name=f'점검 {group} {n}', category=CATEGORY[group])


def course(*groups, mode='demo'):
    return dict(places=[place(g, i) for i, g in enumerate(groups)], conditions=dict(mode=mode))


def owner():
    return 'fresh-' + uuid.uuid4().hex


def conditions(**extra):
    return Conditions(visit_date=date(2026, 10, 24), **extra)


def test_familiar_groups_default_without_history():
    with TestClient(app):
        assert familiar_groups(owner(), 'demo') == (['식사', '카페'], 'default')


def test_familiar_groups_count_recent_fifteen():
    with TestClient(app):
        who = owner()
        # 가장 오래된 코스에만 '하기'. 최근 15개: 모두 카페, 6개에 보기(≥5), 4개에 걷기(<5).
        store.save_plan(course('카페', '하기', '하기'), who)
        for i in range(15):
            store.save_plan(course('카페', '보기' if i < 6 else '쉬기' if i < 11 else '걷기'), who)
        # 바꾼 코스(parent 있음)와 다른 모드 코스는 세지 않는다.
        store.save_plan(course('하기', '하기'), who, parent='x')
        store.save_plan(course('하기', '하기', mode='real'), who)
        groups, basis = familiar_groups(who, 'demo')
        assert basis == 'history'
        assert '카페' in groups and '보기' in groups and '쉬기' in groups
        assert '걷기' not in groups and '하기' not in groups


def test_screen_value_is_replaced():
    with TestClient(app):
        c = with_familiar(conditions(fresh_one=True, fresh_familiar=['하기'], fresh_basis='history'), owner())
        assert c.fresh_familiar == ['식사', '카페'] and c.fresh_basis == 'default'
        off = with_familiar(conditions(fresh_familiar=['하기'], fresh_basis='history'), owner())
        assert off.fresh_familiar == [] and off.fresh_basis == ''


def test_off_keeps_condition_shape():
    data = conditions().model_dump(mode='json')
    assert not {'fresh_one', 'fresh_familiar', 'fresh_basis'} & set(data)
    on = conditions(fresh_one=True, fresh_familiar=['카페'], fresh_basis='history').model_dump(mode='json')
    assert on['fresh_one'] is True and on['fresh_familiar'] == ['카페'] and on['fresh_basis'] == 'history'
