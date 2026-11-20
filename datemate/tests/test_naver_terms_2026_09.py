"""네이버 검색 API 특약 개정(2026-09) 1단계: AI 차단, 보관 기간, 표시.

app/naver_cache.py(사용자별 24시간·새 질의 시까지), app/naver_terms.py(AI 근거 정리·21일 이력 보관),
static/naver-attribution.js(네이버 검색결과 표시)를 확인한다.
"""

import json
import time
from pathlib import Path

import pytest

from app import naver_cache, naver_terms, store

ROOT = Path(__file__).resolve().parents[1]
OTHER = store.owner_of('pytest-naver-other')

NAVER_PLACE = dict(
    id='discovered:abc123', name='비밀정원카페', address='서울특별시 마포구 비밀로 7', lat=37.55, lon=126.92,
    region='서울', category='카페·미식', themes=['카페·미식'], tags=['cafe', '카페,디저트>카페'], meal=False,
    description='카페,디저트>카페', source='https://map.naver.com/p/search/x', source_type='네이버 지역 검색 · 요청 활동 유형 연결',
    license='검색 결과', naver_result=True, price=None, price_unit='person', stay=60, demo=False,
)  # fmt: skip
OWN_PLACE = dict(id='Q1', name='공공미술관', address='서울 종로구 공공로 1', lat=37.57, lon=126.98, region='서울',
                 category='문화·예술', source='https://www.wikidata.org/wiki/Q1', source_type='Wikidata CC0', stay=60)  # fmt: skip


def plan_with_naver():
    return dict(
        id='plan-naver', conditions=dict(mode='real', transport='walk', region='서울', request='카페 가고 싶어요'),
        places=[NAVER_PLACE, OWN_PLACE],
        legs=[dict(origin='출발지', destination='비밀정원카페'), dict(origin='비밀정원카페', destination='공공미술관')],
        timeline=[dict(place_id='discovered:abc123', arrival='12:00', departure='13:00', stay=60),
                  dict(place_id='Q1', arrival='13:20', departure='14:20', stay=60)],
        costs=[dict(name='비밀정원카페', unit=[6000, 6000], amount=[12000, 12000], price_kind='web_reference',
                    source='https://blog.naver.com/someone/1', price_basis='블로그 글에 나온 가격',
                    price_evidence=[dict(amount=6000, item='라떼', source='https://blog.naver.com/someone/1',
                                         evidence='비밀정원카페 라떼 6,000원 맛있어요')]),
               dict(name='공공미술관', unit=[0, 0], amount=[0, 0], status='confirmed', source='https://example.org')],
        reasons=['네이버 코스 검색 1위 글에 등장 · 카페·미식 · 체류 60분', '문화·예술 · 체류 60분'],
        course_search=dict(query='연남동 데이트 코스', posts=[dict(rank=1, title='연남동 비밀정원카페 후기', description='요약 본문',
                                                              url='https://blog.naver.com/someone/1', author='someone')]),
        blog_score=5,
    )  # fmt: skip


# ---------------------------------------------------------------- 보관(2.3·2.4)


def shared_rows():
    with store.connect() as db:
        return [r[0] for r in db.execute("SELECT key FROM cache WHERE key NOT LIKE 'nv:%'").fetchall()]


def test_naver_results_are_kept_per_owner_for_at_most_a_day():
    naver_cache.cache('place-blogs-v1:x', {'posts': [1]}, 7 * 86400)
    assert naver_cache.cached('place-blogs-v1:x') == {'posts': [1]}
    assert not any(k.startswith('place-blogs-') for k in shared_rows())
    with store.connect() as db:
        row = db.execute("SELECT key,expires FROM cache WHERE key LIKE 'nv:place:%place-blogs-v1:x'").fetchone()
    key, expires = row[0], row[1]  # PostgreSQL 행(Record)은 풀어 쓰면 열 이름이 나온다
    assert key.startswith('nv:place:') and expires <= time.time() + naver_cache.PERSONAL_MAX_SECONDS + 5
    # 다른 사용자는 읽지 못한다.
    with naver_cache.scope(OTHER):
        assert naver_cache.cached('place-blogs-v1:x') is None
    # 소유자가 없는 문맥(유지보수·색인)은 DB 에 남기지 않는다.
    with naver_cache.scope(None):
        naver_cache.cache('place-blogs-v1:anon', {'posts': []}, 60)
    with store.connect() as db:
        assert not db.execute("SELECT 1 FROM cache WHERE key LIKE '%place-blogs-v1:anon'").fetchone()


def test_new_query_replaces_previous_results_of_the_same_purpose():
    naver_cache.cache('explore-result-v2:old', {'places': []}, 3600)
    naver_cache.cache('discovered-place:keep', dict(NAVER_PLACE), 3600)
    with naver_cache.scope(naver_cache.current_owner()):
        naver_cache.new_query('explore')
        assert naver_cache.cached('explore-result-v2:old') is None
        assert naver_cache.cached('discovered-place:keep')  # 다른 목적(코스)은 그대로
        naver_cache.new_query('plan')
        assert naver_cache.cached('discovered-place:keep') is None


def test_derived_places_are_not_shared_with_other_users():
    from app.catalog import places

    naver_cache.cache('discovered-place:' + NAVER_PLACE['id'], dict(NAVER_PLACE), 3600)
    assert NAVER_PLACE['id'] in {p['id'] for p in places('real')}
    with naver_cache.scope(OTHER):
        assert NAVER_PLACE['id'] not in {p['id'] for p in places('real')}
    with naver_cache.scope(None):
        assert NAVER_PLACE['id'] not in {p['id'] for p in places('real')}


def test_old_shared_rows_are_removed_by_migration_cleanup():
    store.cache('discovered-place:legacy', dict(NAVER_PLACE), 3600)
    store.cache('popups-raw:legacy', {'posts': []}, 3600)
    store.cache('festival-detail:v1:1', {'ok': True}, 3600)  # 관광공사 자료는 그대로
    naver_cache.cleanup_shared()
    keys = shared_rows()
    assert 'discovered-place:legacy' not in keys and 'popups-raw:legacy' not in keys
    assert 'festival-detail:v1:1' in keys
    from app.migrations import v0005_naver_terms_2026_09 as migration

    assert set(migration.SHARED_PREFIXES) == set(naver_cache.SHARED_PREFIXES)


def test_purge_owner_removes_personal_naver_rows():
    naver_cache.cache('price-search-v2:x', {'status': 'available', 'quotes': []}, 3600)
    owner = naver_cache.current_owner()
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        store.purge_owner(db, owner)
    with store.connect() as db:
        assert not db.execute('SELECT 1 FROM cache WHERE key LIKE ?', (f'nv:%:{owner}:%',)).fetchone()
        db.execute('DELETE FROM revoked_sessions WHERE token=?', (owner,))


# ---------------------------------------------------------------- 이력 보관(21일)


def save_old_plan(days):
    plan = store.save_plan(plan_with_naver(), naver_cache.current_owner())
    with store.connect() as db:
        db.execute('UPDATE plans SET created=? WHERE id=?', (time.time() - days * 86400, plan['id']))
    return plan['id']


def test_plans_older_than_21_days_lose_naver_fields_but_stay():
    fresh, old = save_old_plan(3), save_old_plan(22)
    while naver_terms.cleanup_expired_plans() >= naver_terms.CLEANUP_BATCH:
        pass
    stored = json.loads(store.get_plan(old)['payload'])
    text = json.dumps(stored, ensure_ascii=False)
    assert 'course_search' not in stored and 'blog_score' not in stored
    assert '비밀정원카페' not in text and '비밀로 7' not in text and 'blog.naver.com' not in text
    assert stored['places'][0]['naver_expired'] and stored['places'][0]['name'] == naver_terms.EXPIRED_NAME
    assert stored['places'][1] == OWN_PLACE and stored['conditions']['transport'] == 'walk'
    # 블로그 가격의 금액도 지운다('확인 필요', 2026-11-20 후속 — tests/test_naver_terms_followups.py).
    assert stored['costs'][0]['price_evidence'] == [] and stored['costs'][0]['amount'] is None
    assert stored['places'][0]['lat'] is None and stored['places'][0]['lon'] is None
    assert not stored['reasons'][0].startswith('네이버 코스 검색')
    assert '비밀정원카페' in store.get_plan(fresh)['payload']


def test_place_detail_falls_back_to_the_owners_recent_plan():
    from app.catalog import get_place

    save_old_plan(3)
    with naver_cache.scope(naver_cache.current_owner()):
        assert get_place(NAVER_PLACE['id'], 'real')['name'] == '비밀정원카페'
    with naver_cache.scope(OTHER):
        assert get_place(NAVER_PLACE['id'], 'real') is None


# ---------------------------------------------------------------- AI 차단(2.3)


def test_blog_place_extraction_is_gone():
    """블로그 글에서 장소를 뽑던 경로(LLM 추출 → 지역 검색 연결)는 2단계에서 코드째 없앴다(검색 결과를 추천 계산에 쓰지 않음)."""
    from app import course_search, discovery

    for name in ('extract', 'resolve', 'discover'):
        assert not hasattr(discovery, name), name
    for name in ('select_posts', 'match_places', 'priority', 'public_body'):
        assert not hasattr(course_search, name), name


def test_rag_evidence_has_no_naver_data(monkeypatch):
    from app import rag

    sent = []

    class Fake:
        def with_structured_output(self, _):
            return self

        def invoke(self, messages):
            sent.append(json.dumps(messages, ensure_ascii=False))
            return rag.Answer(quotes=[])

    monkeypatch.setenv('GMS_KEY', 'test')
    monkeypatch.setattr(rag, 'llm', lambda: Fake())
    plan = plan_with_naver()
    history = [dict(role='assistant', content='저장된 일정의 장소: 비밀정원카페, 공공미술관')]
    rag.ask([p['id'] for p in plan['places']], '어디 가요?', 'real', history, plan=plan, owner=naver_cache.current_owner())
    assert sent, 'LLM 이 불리지 않음'
    for word in ('비밀정원카페', '비밀로 7', 'blog.naver.com', '라떼 6,000원', '연남동 비밀정원카페 후기', 'course_search', '카페,디저트>카페'):
        assert word not in sent[0], word
    assert '공공미술관' in sent[0]


def test_index_excludes_and_purges_naver_places():
    from app.indexing import collections, index_places, purge_naver_documents

    meta, _ = collections('real')
    meta.upsert(ids=[NAVER_PLACE['id']], documents=['x'], embeddings=[[0.0] * 255 + [1.0]],
                metadatas=[dict(place_id=NAVER_PLACE['id'], title='x', source='x', type='metadata', checked_at='x')])
    assert purge_naver_documents('real') >= 1
    assert NAVER_PLACE['id'] not in meta.get()['ids']
    index_places([dict(OWN_PLACE, checked_at='2026-11-20'), dict(NAVER_PLACE, checked_at='2026-11-20')], 'real')
    assert set(meta.get()['ids']) == {'Q1'}


def test_naver_photos_are_not_sent_to_a_vision_model(monkeypatch):
    from app import photo_relevance

    monkeypatch.setattr(photo_relevance, 'visual_check_configured', lambda: True)
    monkeypatch.setattr(photo_relevance, 'invoke_model', lambda *a: pytest.fail('비전 모델 호출'))
    photo = dict(image_url='https://postfiles.pstatic.net/a.jpg', url='https://postfiles.pstatic.net/a.jpg')
    assert photo_relevance.classify(OWN_PLACE, photo)['status'] == 'unverified'


def test_search_photos_are_not_resized_or_cached():
    """네이버 검색 API 에서 온 사진(지금은 꺼져 있는 블로그 후기 사진 경로)은 줄이거나 서버에 담아 두지 않는다.
    이미지 검색 사진은 2026-11-20 에 아예 없앴다(tests/test_photo_source_priority.py)."""
    from app.photo_thumb import with_thumbs

    data = with_thumbs(dict(photos=[dict(kind='place_public', source_type='blog_review', image_url='https://postfiles.pstatic.net/a.jpg')]))
    assert 'thumb_url' not in data['photos'][0]


# ---------------------------------------------------------------- 호출 수(같은 사용자는 다시 부르지 않음)


def test_explore_calls_once_per_user_and_again_for_another_user(monkeypatch):
    from fastapi.testclient import TestClient
    from app import explore
    from app.main import app

    calls = []

    def lookup(client, query):
        calls.append(query)
        return query, [dict(title='호출세기카페', roadAddress='서울특별시 중구 호출로 1', mapx='1269900000', mapy='375600000', category='카페,디저트')], 'available'

    monkeypatch.setattr(explore, 'search_enabled', lambda: True)
    monkeypatch.setattr(explore, 'lookup', lookup)
    first = TestClient(app)
    params = dict(region='서울', activity='카페', q='호출세기')
    data = first.get('/api/explore', params=params).json()
    used = len(calls)
    assert data['status'] == 'ready' and 0 < used <= explore.MAX_QUERIES
    first.get('/api/explore', params=params)
    assert len(calls) == used  # 같은 사용자: 개인화 보관에서
    place = data['places'][0]
    assert first.get('/api/places/' + place['id'], params={'mode': 'real'}).status_code == 200
    second = TestClient(app)
    assert second.get('/api/places/' + place['id'], params={'mode': 'real'}).status_code == 404
    second.get('/api/explore', params=params)
    assert len(calls) == 2 * used  # 다른 사용자: 공용 캐시가 없어 다시 부른다


# ---------------------------------------------------------------- 표시(2.1·2.2)


def test_attribution_script_is_loaded_and_used():
    index = (ROOT / 'static/index.html').read_text('utf-8')
    shared = (ROOT / 'static/shared.html').read_text('utf-8')
    assert index.index('naver-attribution.js') < index.index('app.js')
    assert 'naver-attribution.js' in shared
    script = (ROOT / 'static/naver-attribution.js').read_text('utf-8')
    assert '네이버 검색결과' in script and 'NAVERAPIHUB' in script
    # 코스 조사 패널(course-search.js)은 place-blogs.js 의 블록(naverBlogBlock)으로 출처 표시를 단다.
    # 비용 표(price-controls.js)에는 더 이상 네이버 검색 자료가 없다(블로그 가격을 읽지 않음).
    assert 'naverBlogBlock(' in (ROOT / 'static/course-search.js').read_text('utf-8')
    assert 'naverAttribution(' not in (ROOT / 'static/price-controls.js').read_text('utf-8')
    for name in ('explore.js', 'plan-detail.js', 'meal-suggestions.js',
                 'place-blogs.js', 'leisure.js', 'parking.js', 'popups.js', 'place-dialog.js', 'location-picker.js', 'shared.js'):
        assert 'naverAttribution(' in (ROOT / 'static' / name).read_text('utf-8'), name


def test_restaurant_results_link_each_item_to_its_original(monkeypatch):
    from app import restaurants

    class Response:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return dict(items=[dict(title='원본식당', roadAddress='서울특별시 중구 원본로 1', category='음식점>한식', mapx='1269900000', mapy='375600000')])

    monkeypatch.setattr(restaurants, 'observed_http', lambda *a, **k: Response())
    monkeypatch.setattr('app.image_search.search_enabled', lambda: True)
    plan = dict(conditions=dict(mode='real', region='서울'), places=[dict(name='기준', lat=37.56, lon=126.99, address='서울 중구')])
    found = restaurants.search_nearby(plan, 0, radius_m=5000)['restaurants'][0]
    assert found['naver_result'] and found['source'].startswith('https://map.naver.com/p/search/') and '원본식당' not in found['search_url']
