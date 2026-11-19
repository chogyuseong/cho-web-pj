"""네이버 검색 API 특약(2026-09) 1단계 후속(2026-11-20).

- 21일 이력 보관 뒤에도 남던 파생값: 지역 검색 장소의 좌표, 그 장소에 닿는 구간의 길찾기 링크·도로 경로,
  블로그 가격에서 온 금액(→ '확인 필요'), 지역 검색 주소에서 온 출발지·귀가지 이름(app/naver_terms.strip_plan).
- 바꾼 코스(자식)는 부모와 함께 정리한다(created 만 보면 고칠 때마다 21일이 늘어남).
- 좌표를 지운 코스는 열리지만 다시 계산하는 요청은 409(app/naver_terms.ensure_changeable), 화면은 그 기능을 그리지 않는다.
브라우저 저장소(기기 24시간)는 tests/test_naver_device_retention.py.
"""

import json
import time

from fastapi.testclient import TestClient

from app import naver_cache, naver_terms, store
from app.main import app
from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401 (fixture)

ROAD = '서울특별시 마포구 비밀로 7'
NAVER_PLACE = dict(
    id='discovered:abc123', name='비밀정원카페', address=ROAD, lat=37.55, lon=126.92, region='서울',
    category='카페·미식', source='https://map.naver.com/p/search/x', source_type='네이버 지역 검색', license='검색 결과',
    naver_result=True, price=None, price_unit='person', stay=60,
)  # fmt: skip
OWN_PLACE = dict(id='Q1', name='공공미술관', address='서울 종로구 공공로 1', lat=37.57, lon=126.98, region='서울',
                 category='문화·예술', source='https://www.wikidata.org/wiki/Q1', stay=60)  # fmt: skip
LOCAL_ORIGIN = '서울 마포구 양화로 160'  # 지역 검색 결과(장소 이름으로 찾기)의 도로명 주소로 만든 출발지 이름


def naver_link(a, b):
    from app.routes import app_link

    return app_link(a, b, 'walk')


def plan_with_naver(origin_name=LOCAL_ORIGIN, home_name='서울 종로구 귀가로 9'):
    origin = dict(name=origin_name, lat=37.556, lon=126.923)
    home = dict(name=home_name, lat=37.58, lon=126.99)
    return dict(
        conditions=dict(mode='real', transport='walk', region='서울', budget=100000, origin=origin, area_center=dict(origin),
                        return_home=True, home=home, visit_date='2026-10-24', start='11:00', end='19:00'),
        places=[dict(NAVER_PLACE), dict(OWN_PLACE)],
        legs=[dict(origin=origin_name, destination='비밀정원카페', mode='walk', link=naver_link(origin, NAVER_PLACE), path=[[126.92, 37.55]]),
              dict(origin='비밀정원카페', destination='공공미술관', mode='walk', link=naver_link(NAVER_PLACE, OWN_PLACE), path=[]),
              dict(origin='공공미술관', destination=home_name, mode='walk', link=naver_link(OWN_PLACE, home), path=[])],
        timeline=[dict(place_id='discovered:abc123', arrival='12:00', departure='13:00', stay=60),
                  dict(place_id='Q1', arrival='13:20', departure='14:20', stay=60)],
        costs=[dict(name='비밀정원카페', unit=[6000, 6000], quantity=2, amount=[12000, 12000], status='estimated',
                    price_kind='web_reference', source='https://blog.naver.com/someone/1', price_basis='블로그 글에 나온 가격',
                    price_evidence=[dict(amount=6000, item='라떼', source='https://blog.naver.com/someone/1', evidence='라떼 6,000원')]),
               dict(name='공공미술관', unit=[5000, 5000], quantity=2, amount=[10000, 10000], status='confirmed', source='https://example.org'),
               dict(name='공공미술관 → ' + home_name, unit=[0, 0], quantity=1, amount=[0, 0], status='estimated', source='추정')],
        total=[22000, 22000], confirmed=[10000, 10000], estimated=[12000, 12000], remaining=[78000, 78000], unknown=[],
        reasons=['카페·미식 · 체류 60분', '문화·예술 · 체류 60분'],
    )  # fmt: skip


# ---------------------------------------------------------------- 21일 정리(서버)


def test_strip_removes_coordinates_links_and_blog_prices():
    stripped = naver_terms.strip_plan(plan_with_naver())
    text = json.dumps(stripped, ensure_ascii=False)
    place = stripped['places'][0]
    assert place['naver_expired'] and place['lat'] is None and place['lon'] is None
    assert stripped['places'][1] == OWN_PLACE
    # 지운 장소에 닿는 두 구간: 링크·도로 경로가 없다. 귀가 구간은 귀가지 이름을 바꿔 링크를 다시 만든다(좌표는 남음).
    first, second, home = stripped['legs']
    assert first['link'] is None and first['path'] == [] and second['link'] is None
    assert home['link'].startswith('nmap://route/walk?') and '37.58' in home['link']
    # 블로그 가격 → 금액 없음('확인 필요'), 합계에서 빠짐. 확정 가격(공공미술관)은 그대로.
    cost = stripped['costs'][0]
    assert cost['amount'] is None and cost['unit'] is None and cost['status'] == 'unknown' and 'price_kind' not in cost
    assert cost['price_evidence'] == [] and cost['source'] is None and '확인 필요' in cost['price_basis']
    assert stripped['total'] == [10000, 10000] and stripped['confirmed'] == [10000, 10000] and stripped['estimated'] == [0, 0]
    assert stripped['remaining'] == [90000, 90000]
    assert naver_terms.EXPIRED_NAME + ' 가격' in stripped['unknown']
    # 검색 결과일 수 있는 출발지·귀가지 주소: 조건·구간·비용 이름 어디에도 남지 않는다. 출발지 이름은 시·도로 시작한다(조건 검증).
    for word in ('비밀정원카페', '비밀로 7', LOCAL_ORIGIN, '귀가로 9', 'blog.naver.com', '%EB%B9%84%EB%B0%80'):
        assert word not in text, word
    c = stripped['conditions']
    assert c['origin']['name'] == '서울 · ' + naver_terms.EXPIRED_ORIGIN_NAME and c['origin']['lat'] == 37.556
    assert c['area_center']['name'] == c['origin']['name'] and c['home']['name'] == naver_terms.EXPIRED_HOME_NAME
    assert first['origin'] == c['origin']['name'] and home['destination'] == naver_terms.EXPIRED_HOME_NAME
    from app.models import Conditions

    assert Conditions.model_validate(c).origin.name.startswith('서울')
    # 다시 정리해도 같다(자식 코스는 이미 정리한 장소를 옮겨 온다).
    assert naver_terms.strip_plan(stripped) == stripped


def test_screen_made_origin_names_are_kept():
    for name in ('서울 성수역 지역 중심', '서울특별시 성동구 성수동1가 · 현재 위치', '부산광역시 수영구 광안동 · 지도에서 선택',
                 '서울 영등포구 · 더현대 서울 주변', '강남구 대표 위치 · 서울특별시 강남구 학동로 426'):
        stripped = naver_terms.strip_plan(plan_with_naver(origin_name=name, home_name='지도에서 선택한 귀가지'))
        assert stripped['conditions']['origin']['name'] == name
        assert stripped['conditions']['home']['name'] == '지도에서 선택한 귀가지'
        assert stripped['legs'][0]['origin'] == name


def test_ai_evidence_hides_a_search_origin():
    safe = naver_terms.ai_safe_plan(plan_with_naver())
    text = json.dumps(safe, ensure_ascii=False)
    assert LOCAL_ORIGIN not in text and '귀가로 9' not in text
    assert safe['conditions']['origin'] == dict(name=naver_terms.AI_ORIGIN_NAME, lat=None, lon=None)
    assert safe['costs'][0]['amount'] is None and safe['total'] == [10000, 10000]
    history = naver_terms.redact_history([dict(role='assistant', content=f'{LOCAL_ORIGIN}에서 출발해요')], plan_with_naver())
    assert LOCAL_ORIGIN not in history[0]['content']


def save(plan, days, parent=None):
    saved = store.save_plan(plan, naver_cache.current_owner(), parent=parent)
    with store.connect() as db:
        db.execute('UPDATE plans SET created=? WHERE id=?', (time.time() - days * 86400, saved['id']))
    return saved['id']


def test_changed_plans_are_cleaned_with_their_parent():
    parent = save(plan_with_naver(), 22)
    child = save(plan_with_naver(), 2, parent=parent)
    grandchild = save(plan_with_naver(), 1, parent=child)
    unrelated = save(plan_with_naver(), 2)
    store.chat_save(naver_cache.current_owner(), 'real:plan:' + child, '주소?', '비밀정원카페: ' + ROAD)
    while naver_terms.cleanup_expired_plans() >= naver_terms.CLEANUP_BATCH:
        pass
    for pid in (parent, child, grandchild):
        assert '비밀정원카페' not in store.get_plan(pid)['payload'], pid
    assert '비밀정원카페' in store.get_plan(unrelated)['payload']
    assert store.history(naver_cache.current_owner(), 'real:plan:' + child) == []


def test_expired_plan_opens_but_recalculation_is_refused():
    with TestClient(app) as client:
        plan = client.post('/api/plans', json={'visit_date': '2026-10-24', 'max_leg': 180, 'budget': 1000000}).json()['plans'][0]
        pid = plan['id']
        stored = json.loads(store.get_plan(pid)['payload'])
        stored['conditions']['area_center'] = dict(stored['conditions']['origin'])
        stored['places'][0].update(id='discovered:expired1', lat=None, lon=None, naver_expired=True, name=naver_terms.EXPIRED_NAME)
        stored['legs'][0].update(link=None, path=[])
        with store.connect() as db:
            db.execute('UPDATE plans SET payload=? WHERE id=?', (json.dumps(stored, ensure_ascii=False), pid))
        opened = client.get('/api/plans/' + pid)
        assert opened.status_code == 200, opened.text
        assert opened.json()['places'][0]['naver_expired']
        assert client.get(f'/api/plans/{pid}/delay-check').status_code == 200
        assert client.get(f'/api/plans/{pid}/reviews').status_code == 200
        refused = [
            ('POST', 'prices', None), ('GET', 'restaurant-matches', None), ('GET', 'restaurants', None),
            ('GET', 'parking', None), ('GET', 'meal-rescue', None), ('POST', 'alternatives', {'index': 1}),
            ('POST', 'replace', {'index': 1, 'replacement_id': 'x'}), ('POST', 'transport', {'default': 'car'}),
            ('POST', 'leisure-options', {'index': 1}), ('POST', 'leisure-select', {'index': 1, 'replacement_id': 'x'}),
            ('POST', 'meal-preview', {'restaurant_id': 'x'}), ('POST', 'agreement-preview', {}),
        ]  # fmt: skip
        for method, path, body in refused:
            response = client.request(method, f'/api/plans/{pid}/{path}', **({} if body is None else {'json': body}))
            assert response.status_code == 409, (path, response.status_code, response.text)
            assert '21일' in response.json()['detail']
        # 고정·의견·피드백처럼 다시 계산하지 않는 요청은 그대로 된다.
        assert client.post(f'/api/plans/{pid}/locks', json={'locked': [1]}).status_code == 200


# ---------------------------------------------------------------- 화면


def test_expired_plan_screen_hides_recalculation(audit_page):
    page, _, errors = audit_page
    generate(page)
    wait_for_selected_detail(page)
    page.evaluate("""()=>{
      selected.conditions.mode='real';
      Object.assign(selected.places[0],{id:'discovered:expired1',name:'보관 기간이 지난 검색 장소',lat:null,lon:null,naver_expired:true});
      selected.legs[0].link=null;selected.legs[0].path=[];selected.legs[1].link=null;
      renderDetail();renderPlanMapCard();
    }""")
    detail = page.locator('#plan-detail')
    assert detail.locator('.naver-expired-plan').count() == 1
    assert detail.locator('.naver-expired').count() == 1
    changes = detail.get_by_role('button', name='↻ 다른 장소로 변경')
    assert changes.count() == page.evaluate('selected.places.length')
    assert all(changes.nth(i).is_disabled() for i in range(changes.count()))
    assert detail.locator('.route-mode-toggle, .transport-bulk, .parking-panel, .meal-suggestions').count() == 0
    assert detail.get_by_role('button', name='현재 단가 다시 검색').count() == 0
    # 이름을 지운 장소는 '네이버 지도에서 찾기' 목록에 넣지 않는다.
    assert '보관 기간이 지난 검색 장소' not in detail.locator('.map-link-list').inner_text()
    page.wait_for_timeout(500)
    assert not errors, errors
