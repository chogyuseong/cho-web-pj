"""네이버 검색 API 특약 2.2(2단계, docs/naver-terms-stage2-design.ko.md 3.1(a)·3.2(a)).

1) 블로그 검색 결과는 추천 계산에 들어가지 않는다: 결과가 달라도(다른 글·0건·검색 실패) 3안의 장소·순서·이름·이유 문장·비용이 같다.
2) 화면에 보낼 글 목록은 받은 순서·건수·원문 그대로다(자세한 것은 tests/test_course_search.py, tests/test_blog_search.py).
3) 배포 전에 저장된 예전 형식 코스는 마이그레이션 v0006 이 한 번 정리한다(SQLite·PostgreSQL 같은 코드).
외부 호출 없음(고정 자료)."""
import copy
import json
import time
import uuid

import httpx
import pytest

from app import store
from app.database import postgres_enabled
from app.migrations import MIGRATIONS, v0006_naver_terms_stage2_blog_price as migration
from test_recommendation_speed import POSTDATE, SCENARIOS, blog_items, clean_region, naver, run  # noqa: F401 (naver: fixture)


def shape(result):
    """추천 계산의 결과물: 안마다 이름·장소 순서·이유 문장·비용·조건 확인."""
    return [dict(purpose=p.get('option_purpose'), places=[x['id'] for x in p['places']], reasons=p['reasons'], total=p['total'],
                 costs=[(r['name'], r['amount'], r.get('price_kind'), r['status']) for r in p['costs']],
                 checks=[(r['condition'], r['state']) for r in p['condition_checks']],
                 evidence=[(f['place_id'], f['reason'], f['price_kind']) for f in p['place_evidence']],
                 adjustments=p.get('search_adjustments')) for p in result['plans']]


def praising(query):
    """추천 후보로 나올 장소 이름을 대놓고 칭찬·비추천하는 글들. 예전 규칙(이름 일치 가산·'비추천' 제외·협찬 감점)이라면 순위가 바뀐다."""
    names = ['한지 공방', '남문 피순대', '골목 갤러리', '천변 산책로', '초코 디저트', '도자기 체험', '전주 백반', '오목대 공원']
    return [dict(title=f'{name} 강력 추천 데이트 코스', description=f'{name} 최고예요. 한옥 비빔밥은 비추천이에요. 한옥 찻집 쌍화차 7,000원. 협찬 아님',
                 link=f'https://blog.naver.com/fan{i}/9{i}', postdate=POSTDATE, bloggername=f'팬{i}') for i, name in enumerate(names * 2)]


def failing(query):
    raise httpx.ConnectError('blog search down')


@pytest.mark.parametrize('name', sorted(SCENARIOS))
def test_recommendation_is_the_same_whatever_the_blog_search_returns(name, naver):
    results = {}
    for label, blog in (('default', blog_items), ('praising', praising), ('empty', lambda query: []), ('failing', failing)):
        clean_region(SCENARIOS[name]['region'])
        naver.blog = blog
        results[label] = run(name, naver, store.owner_of('blog-independent-' + uuid.uuid4().hex))
    base = shape(results['default'])
    assert base and all(plan['places'] for plan in base)
    for label, result in results.items():
        assert shape(result) == base, label
    for result in results.values():
        for plan in result['plans']:
            assert 'blog_score' not in plan and 'recommendation_method' not in plan
            assert not any('네이버 코스 검색' in reason or '위 글' in reason for reason in plan['reasons'])
            assert not any('blog_match' in fact or 'price_sources' in fact for fact in plan['place_evidence'])
            assert not any(row.get('price_kind') == 'web_reference' or 'price_evidence' in row for row in plan['costs'])
    # 화면용 글 목록은 결과마다 다르고(받은 그대로), 추천에는 영향이 없었다.
    posts = {label: [p['title'] for p in result['plans'][0]['course_search']['posts']] for label, result in results.items()}
    assert len(posts['praising']) == 16 and posts['praising'][0] == '한지 공방 강력 추천 데이트 코스'
    assert len(posts['default']) == 6 and posts['empty'] == [] and posts['failing'] == []
    assert results['failing']['course_search']['status'] == 'unavailable' and results['empty']['course_search']['status'] == 'not_found'
    assert 'unexpected-blog' not in naver.calls, '가격을 찾는 블로그 검색은 나가지 않는다'


# ---------------------------------------------------------------- 이미 저장된 코스(마이그레이션 v0006)


def old_plan():
    """2단계 전 형식으로 저장된 코스: 고른 5건·matches·blog_score·이유 문장 머리말·블로그 가격·블로그 메뉴 가격·운영자 메뉴 가격."""
    cafe = dict(id='discovered:abc', name='비밀정원카페', category='카페·미식', price=None)
    food = dict(id='food:naver-1', name='연남 식당', category='카페·미식', meal=True, price=[9000, 9000], price_status='estimated',
                menu_pricing=dict(price_kind='naver_menu', price_basis='백반 1개/인 가정 · 블로그 글에 나온 가격 참고가', source='https://map.naver.com/p/search/x'))
    owned = dict(id='food:own', name='등록 식당', category='카페·미식', meal=True, price=[12000, 12000], price_status='estimated',
                 menu_pricing=dict(price_kind='naver_menu', price_basis='정식 1개/인 가정 · 운영자가 확인한 제공 메뉴 참고가', source='https://example.org/menu'))
    walk = dict(id='Q1', name='공원', category='산책·풍경', price=None)
    museum = dict(id='Q2', name='미술관', category='문화·예술', price=[3000, 3000])
    return dict(
        conditions=dict(mode='real', people=2, budget=100000, allow_price_estimates=True),
        places=[cafe, food, owned, walk, museum],
        costs=[
            dict(name='비밀정원카페', category='카페·미식', unit=[6000, 7000], quantity=2, formula='1인 기준 × 2', amount=[12000, 14000], status='estimated',
                 price_kind='web_reference', source='https://blog.naver.com/a/1', checked_at='2026-11-10T00:00:00+00:00', price_lookup_status='available',
                 price_basis='블로그 글에 나온 가격 · 라떼 1인 기준 · 지금 가격인지는 확인하지 못했어요',
                 price_evidence=[dict(amount=6000, item='라떼', source='https://blog.naver.com/a/1', evidence='라떼 6,000원')]),
            dict(name='연남 식당', category='카페·미식', unit=[9000, 9000], quantity=2, formula='단가 × 2', amount=[18000, 18000], status='estimated',
                 price_kind='naver_menu', price_basis='백반 1개/인 가정 · 블로그 글에 나온 가격 참고가', source='https://map.naver.com/p/search/x'),
            dict(name='등록 식당', category='카페·미식', unit=[12000, 12000], quantity=2, formula='단가 × 2', amount=[24000, 24000], status='estimated',
                 price_kind='naver_menu', price_basis='정식 1개/인 가정 · 운영자가 확인한 제공 메뉴 참고가', source='https://example.org/menu'),
            dict(name='공원', category='산책·풍경', unit=[0, 5000], quantity=2, formula='1인 기준 × 2', amount=[0, 10000], status='estimated',
                 price_kind='planning_assumption', source='서비스 예산 계획용 가정', price_evidence=[], price_lookup_status='not_found',
                 price_basis='계획용 1인 범위 · 검색에서 가격을 확보하지 못해 사용한 가정 (실제 단가 아님)'),
            dict(name='미술관', category='문화·예술', unit=[3000, 3000], quantity=2, formula='단가 × 2', amount=[6000, 6000], status='confirmed', source='https://example.org'),
        ],
        total=[60000, 72000], confirmed=[6000, 6000], estimated=[54000, 66000], remaining=[28000, 40000], unknown=['공원 주차비'],
        reasons=['네이버 코스 검색 1위 글, 3위 글에 등장 · 카페·미식 · 체류 60분', '카페·미식 · 체류 60분', '카페·미식', '산책·풍경', '문화·예술'],
        course_search=dict(query='연남동 데이트 코스', provider='네이버 검색 후보에서 지역·최근성·작성자 중복을 고려한 후기 최대 5개',
                           posts=[dict(rank=1, search_rank=4, title='연남동 후기', description='요약', url='https://blog.naver.com/a/1', author='a',
                                       selection_reason='검색 순위 4 · 지역명 일치', mentioned_places=['비밀정원카페'])],
                           matches={'discovered:abc': dict(ranks=[1, 3], score=7)}),
        blog_score=7, recommendation_method='naver_blog_selected5',
        place_evidence=[dict(place_id='discovered:abc', reason='네이버 코스 검색 1위 글, 3위 글에 등장 · 카페·미식 · 체류 60분', blog_match=True,
                             price_kind='web_reference', price_sources=[dict(source='https://blog.naver.com/a/1', evidence='라떼 6,000원')])],
        decision_summary=dict(title='카페 2곳', source_matched_places=1, unknown_prices=0, assumed_prices=1),
    )  # fmt: skip


def stored(plan_id):
    return json.loads(store.get_plan(plan_id)['payload'])


def migrate():
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        migration.upgrade(db, 'postgres' if postgres_enabled() else 'sqlite')


def test_old_saved_plans_are_cleaned_once_and_new_ones_are_left_alone():
    owner = store.owner_of('stage2-migration-' + uuid.uuid4().hex)
    old = store.save_plan(old_plan(), owner)['id']
    new_format = old_plan()
    for key in ('blog_score', 'recommendation_method', 'place_evidence', 'decision_summary'):
        new_format.pop(key)
    new_format.update(costs=[new_format['costs'][4]], places=[new_format['places'][4]], reasons=['문화·예술'], total=[6000, 6000],
                      confirmed=[6000, 6000], estimated=[0, 0], remaining=[94000, 94000],
                      course_search=dict(format=2, query='연남동 데이트 코스', posts=[dict(title='받은 그대로', description='요약', url='https://blog.naver.com/a/1',
                                                                                       blogger='a', posted_at='2026-11-01')]))
    new = store.save_plan(copy.deepcopy(new_format), owner)['id']
    demo = store.save_plan(dict(conditions=dict(mode='demo'), places=[], costs=[], reasons=['가상']), owner)['id']
    cleared = store.save_plan(old_plan(), owner)['id']
    with store.connect() as db:
        db.execute('UPDATE plans SET naver_cleared=? WHERE id=?', (time.time(), cleared))
    before_new, before_demo, before_cleared = store.get_plan(new)['payload'], store.get_plan(demo)['payload'], store.get_plan(cleared)['payload']
    migrate()
    plan = stored(old)
    text = json.dumps(plan, ensure_ascii=False)
    # 고른 5건·matches 는 원래 순서·건수를 되살릴 수 없어 통째로 지운다. 우리 점수·판정·이유 문장 머리말도 지운다.
    assert not {'course_search', 'blog_score', 'recommendation_method'} & set(plan)
    assert plan['reasons'][0] == '카페·미식 · 체류 60분' and '네이버 코스 검색' not in text
    assert plan['place_evidence'][0] == dict(place_id='discovered:abc', reason='카페·미식 · 체류 60분', price_kind='unknown')
    assert 'source_matched_places' not in plan['decision_summary']
    # 블로그에서 읽은 금액(요약 가격·블로그 메뉴 가격)은 '확인 필요'로 돌리고 합계에서 뺀다.
    blog, blog_menu, operator, assumed, registered = plan['costs']
    for row in (blog, blog_menu):
        assert row['amount'] is None and row['unit'] is None and row['status'] == 'unknown' and row['source'] is None
        assert not {'price_kind', 'price_evidence', 'price_lookup_status', 'checked_at'} & set(row)
        assert '블로그 글에서 읽은 가격은 더 이상 쓰지 않아' in row['price_basis']
    assert plan['places'][1]['price'] is None and 'menu_pricing' not in plan['places'][1]
    assert 'blog.naver.com' not in text and '라떼 6,000원' not in text and 'web_reference' not in text
    # 네이버가 아닌 출처는 그대로: 운영자 메뉴(종류 이름만 바꿈)·계획용 가정·등록 단가.
    assert operator['amount'] == [24000, 24000] and operator['price_kind'] == 'operator_menu'
    assert plan['places'][2]['menu_pricing']['price_kind'] == 'operator_menu' and plan['places'][2]['price'] == [12000, 12000]
    assert assumed['amount'] == [0, 10000] and assumed['price_kind'] == 'planning_assumption' and 'price_lookup_status' not in assumed
    assert registered == old_plan()['costs'][4]
    # 합계 = 운영자 메뉴 + 가정 범위 + 등록 단가.
    assert plan['total'] == [30000, 40000] and plan['confirmed'] == [6000, 6000] and plan['estimated'] == [24000, 34000]
    assert plan['remaining'] == [60000, 70000]
    assert plan['unknown'] == sorted(['공원 주차비', '비밀정원카페 가격', '연남 식당 가격']) and plan['decision_summary']['unknown_prices'] == 2
    # 새 형식 코스·가상 장소 코스·이미 21일 정리된 코스는 건드리지 않는다.
    assert store.get_plan(new)['payload'] == before_new and store.get_plan(demo)['payload'] == before_demo
    assert store.get_plan(cleared)['payload'] == before_cleared
    # 다시 돌려도 같다.
    once = store.get_plan(old)['payload']
    migrate()
    assert store.get_plan(old)['payload'] == once
    assert migration in MIGRATIONS


def test_cleaned_plan_opens_with_a_fresh_budget_check():
    """정리한 코스를 열면 조건 확인을 다시 계산해(app/main.plan_row) 예전 합계로 '예산 이내'라고 말하지 않는다."""
    from app.condition_audit import audit_plan
    from app.planner import recommend
    from app.models import Conditions

    plan = recommend(Conditions(visit_date='2026-10-24', budget=1000000, max_leg=180))['plans'][0]
    plan['conditions'].update(mode='real', allow_estimates=True)
    plan['costs'][0].update(price_kind='web_reference', price_evidence=[dict(source='https://blog.naver.com/a/1', evidence='1,000원')])
    assert migration.clean_plan(plan)
    budget = [r for r in audit_plan(plan)['condition_checks'] if r['condition'] == 'budget']
    assert any(r['state'] == 'unknown' for r in budget) and not any(r['state'] == 'met' for r in budget)
