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


def run(who, *options, mode='demo'):
    """추천 한 번(같은 recommendation_group_id)에 저장되는 안들. 첫 안이 그 추천의 대표다."""
    group = uuid.uuid4().hex
    for groups in options:
        store.save_plan(dict(course(*groups, mode=mode), recommendation_group_id=group), who)


def test_familiar_groups_count_recent_runs():
    with TestClient(app):
        who = owner()
        # 가장 오래된 추천에만 '하기'. 최근 5번(RECENT): 첫 안이 모두 카페, 2번에 보기(≥2), 1번에 걷기(<2).
        run(who, ('카페', '하기', '하기'))
        for i in range(5):
            run(who, ('카페', '보기' if i < 2 else '쉬기' if i < 4 else '걷기'), ('하기', '하기'))
        # 바꾼 코스(parent 있음)와 다른 모드 코스는 세지 않는다.
        store.save_plan(course('하기', '하기'), who, parent='x')
        run(who, ('하기', '하기'), mode='real')
        groups, basis = familiar_groups(who, 'demo')
        assert basis == 'history'
        assert groups == ['카페', '보기', '쉬기']


def test_one_run_counts_its_first_option_not_every_option():
    """한 번 추천에 일부러 서로 다르게 고른 3안이 저장된다. 그 셋을 다 세면 거의 모든 종류가 익숙해진다(검토 지적)."""
    with TestClient(app):
        who = owner()
        run(who, ('걷기', '카페', '보기'), ('쉬기', '하기', '하기'), ('카페', '걷기', '쉬기'))
        assert familiar_groups(who, 'demo') == (['카페', '보기', '걷기'], 'history')


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


# --- 정렬·선택·조건 확인 ---
from app.catalog import places  # noqa: E402
from app.condition_audit import audit_plan  # noqa: E402
from app.fresh_place import fresh_indexes, fresh_penalty  # noqa: E402
from app.option_diversity import place_group  # noqa: E402
from app.planner import evaluate, recommend  # noqa: E402


def on(familiar, basis='history', **extra):
    return conditions(fresh_one=True, fresh_familiar=familiar, fresh_basis=basis, **extra)


def demo(*groups):
    """데모 장소에서 묶음 순서대로 한 곳씩. 같은 묶음이 또 나오면 그 묶음의 다음 장소."""
    pool, used = places('demo'), []
    for g in groups:
        used.append(next(p for p in pool if place_group(p) == g and p not in used))
    return used


def audited(c, *groups):
    plan, error = evaluate(demo(*groups), c)
    assert not error
    return audit_plan(plan, c)


def fresh_check(plan):
    found = [r for r in plan['condition_checks'] if r['condition'] == 'fresh_place']
    assert len(found) == 1
    return found[0]


def test_penalty_prefers_exactly_one_fresh():
    c = on(['식사', '카페'])
    assert fresh_penalty(course('카페', '식사', '보기'), c) == 0
    assert fresh_penalty(course('카페', '보기', '걷기'), c) == 1
    assert fresh_penalty(course('카페', '식사', '카페'), c) == 2
    assert fresh_indexes(course('카페', '식사', '보기'), c) == [2]
    off = conditions()
    assert all(fresh_penalty(course(*g), off) == 0 for g in (('카페', '보기', '걷기'), ('카페', '카페')))


def test_audit_marks_the_fresh_place():
    plan = audited(on(['카페', '하기']), '카페', '보기', '하기')
    assert plan['fresh_place'] == dict(index=1, group='보기', label='전시·관람')
    check = fresh_check(plan)
    assert check['state'] == 'met' and check['label'] == '새로운 곳 한 곳'
    assert check['message'] == f"{plan['places'][1]['name']}(전시·관람) — 최근 코스에 드물던 종류예요."


def test_audit_counts_more_than_one_fresh_place():
    check = fresh_check(audited(on(['카페']), '카페', '보기', '하기'))
    assert check['state'] == 'met' and '새로운 종류가 2곳 들어갔어요.' in check['message']


def test_audit_without_fresh_kind_is_unknown_and_course_kept():
    plan = audited(on(['카페', '보기', '하기']), '카페', '보기', '하기')
    assert 'fresh_place' not in plan
    check = fresh_check(plan)
    assert check['state'] == 'unknown' and '다른 종류를 찾지 못했어요' in check['message']


def test_default_basis_explains():
    check = fresh_check(audited(on(['식사', '카페'], basis='default'), '카페', '보기', '하기'))
    assert check['message'].endswith('최근 코스 기록이 적어 식사·카페를 익숙한 종류로 봤어요.')


def test_course_without_the_option_has_no_check():
    plan = audited(conditions(), '카페', '보기', '하기')
    assert 'fresh_place' not in plan
    assert not [r for r in plan['condition_checks'] if r['condition'] == 'fresh_place']


def test_reopen_keeps_the_same_judgement():
    plan = audited(on(['카페', '하기']), '카페', '보기', '하기')
    again = audit_plan(dict(plan), Conditions.model_validate(plan['conditions']))
    assert again['fresh_place'] == plan['fresh_place']


def test_selection_keeps_three_options_when_on():
    """3안 선택의 '요청 조건과 덜 맞음' 거르기에 새로운 곳 점수를 넣으면, 첫 안만 새로운 곳이 1곳일 때 나머지가 모두 빠졌다(검토 지적).
    새로운 곳은 정렬만 바꾸고 안을 버리지 않는다."""
    from app.option_diversity import select_options
    familiar = ['카페', '걷기']
    built = lambda c: [audited(c, *g) for g in (('카페', '걷기', '보기'), ('카페', '걷기', '카페'), ('걷기', '카페', '걷기'), ('카페', '보기', '하기'))]
    off = select_options(built(conditions()), conditions())
    fresh = select_options(built(on(familiar)), on(familiar))
    assert len(off) == 3 and len(fresh) == len(off)


def test_demo_recommendation_puts_one_fresh_place():
    familiar = ['카페', '보기', '걷기', '하기']
    result = recommend(on(familiar))
    assert result['plans']
    for plan in result['plans']:
        assert [place_group(p) for p in plan['places']].count('쉬기') == 1
        assert fresh_check(plan)['state'] == 'met'


def test_off_recommendation_unchanged():
    first = recommend(conditions())
    again = recommend(conditions())
    assert [[p['id'] for p in plan['places']] for plan in first['plans']] == [[p['id'] for p in plan['places']] for plan in again['plans']]
    assert all('fresh_place' not in plan for plan in first['plans'])
    assert not [r for plan in first['plans'] for r in plan['condition_checks'] if r['condition'] == 'fresh_place']


# --- 화면 ---
from test_functional_audit import audit_page  # noqa: E402,F401  (브라우저 고정 장치)


def test_form_sends_fresh_one(audit_page):  # noqa: F811
    page, base, errors = audit_page
    page.goto(base + '/')
    page.wait_for_function('typeof updateExperienceValues==="function" && !!document.querySelector("[name=fresh_one]")')
    # values()(app.js)가 조건을 모을 때 쓰는 부분. 지역을 고르지 않아도 이 칸의 값만 본다.
    sent = '(()=>{const box=document.querySelector("[name=fresh_one]"),d={};updateExperienceValues(d,new FormData(box.form));return d.fresh_one;})()'
    box = page.locator('[name=fresh_one]')
    assert box.count() == 1 and not box.is_checked()
    assert page.evaluate(sent) is False
    label = box.locator('xpath=ancestor::label')
    assert '한 곳은 평소와 다른 새로운 곳으로' in label.text_content()
    # 세부 설정(선택) 접기 안, 피드백 반영 체크 바로 뒤.
    assert page.evaluate('document.querySelector("[name=fresh_one]").closest("details.simple-extra-options") !== null')
    page.evaluate('document.querySelector("[name=fresh_one]").checked=true')
    assert page.evaluate(sent) is True
    assert not errors


def test_course_screen_tags_the_fresh_place(audit_page):  # noqa: F811
    page, base, errors = audit_page
    with TestClient(app) as client:
        client.get('/api/places?mode=demo')
        plan = audited(on(['카페', '하기']), '카페', '보기', '하기')
        saved = store.save_plan(plan, store.owner_of(client.cookies['dm_session']))
        owner = client.cookies['dm_session']
    page.route('**/api/festivals?*', lambda route: route.fulfill(json=dict(status='available', festivals=[], message='')))
    page.context.add_cookies([{'name': 'dm_session', 'value': owner, 'url': base}])
    page.goto(base + '/?plan=' + saved['id'])
    page.wait_for_function('(id)=>selected?.id===id', arg=saved['id'])
    tag = page.locator('#plan-detail .fresh-place-tag')
    assert tag.count() == 1 and tag.inner_text() == '새로운 곳 · 전시·관람'
    stop = tag.locator('xpath=ancestor::article[contains(@class,"stop")]')
    assert stop.locator('.stop-number').inner_text() == '2'
    assert page.locator('.plan-card', has_text='새로운 곳: ' + plan['places'][1]['name'] + '(전시·관람)').count() >= 1
    assert not errors
