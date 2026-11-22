"""코스(plan id) 경로는 만든 브라우저만 쓴다. 공유받은 사람은 공유 토큰 경로(/api/shared-plan…)만 쓴다.

두 겹으로 막는다: safety 미들웨어(app/main.py)가 /api/plans/{id}… 와 /api/chat/plan/{id} 를 먼저 거르고,
각 처리 함수도 plan_row/load 에서 소유자를 다시 확인한다. 아래 '미들웨어 없이' 시험은 두 번째 겹만 따로 본다.
"""
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app import store
from app.main import app

CONDITIONS = {'visit_date': '2026-10-24', 'max_leg': 180, 'budget': 1000000}

# 코스 id 를 받는 모든 경로와, 처리 함수까지 닿도록 형식이 맞는 요청 본문. 새 경로를 만들면 여기에도 넣는다
# (아래 test_every_plan_route_is_listed 가 빠진 경로를 알려 준다).
REVIEW = {'rating': 5, 'body': '좋았어요', 'nickname': '방문자', 'visited': '2026-01-01'}
PLAN_ROUTES = {
    ('GET', '/api/plans/{id}'): None,
    ('GET', '/api/plans/{id}/restaurant-matches'): None,
    ('GET', '/api/plans/{id}/restaurants'): None,
    ('GET', '/api/plans/{id}/parking'): None,
    ('GET', '/api/plans/{id}/meal-rescue'): None,
    ('POST', '/api/plans/{id}/alternatives'): {'index': 0},
    ('POST', '/api/plans/{id}/replace'): {'index': 0, 'replacement_id': 'x'},
    ('POST', '/api/plans/{id}/transport'): {'default': 'walk'},
    ('POST', '/api/plans/{id}/undo'): None,
    ('GET', '/api/plans/{id}/reviews'): None,
    ('PUT', '/api/plans/{id}/review'): REVIEW,
    ('POST', '/api/plans/{id}/leisure-options'): {'index': 0},
    ('POST', '/api/plans/{id}/leisure-select'): {'index': 0, 'replacement_id': 'x'},
    ('POST', '/api/plans/{pid}/locks'): {'locked': []},
    ('POST', '/api/plans/{pid}/meal-preview'): {'restaurant_id': 'x'},
    ('POST', '/api/plans/{pid}/draft-apply'): {'token': '0' * 32},
    ('POST', '/api/plans/{pid}/feedback'): {'kind': 'selection'},
    ('GET', '/api/plans/{pid}/feedback'): None,
    ('DELETE', '/api/plans/{pid}/feedback'): None,
    ('POST', '/api/plans/{pid}/place-report'): {'place_id': 'x', 'reason': 'closed'},
    ('GET', '/api/plans/{pid}/agreement'): None,
    ('POST', '/api/plans/{pid}/agreement'): {'choices': {}},
    ('POST', '/api/plans/{pid}/agreement-preview'): {},
    ('GET', '/api/plans/{pid}/delay-check'): None,
    ('POST', '/api/plans/{pid}/delay-recovery'): {'index': 0, 'minutes': 10, 'target': 0},
    ('GET', '/api/plans/{pid}/decision'): None,
    ('POST', '/api/plans/{pid}/decision'): {},
    ('POST', '/api/plans/{plan_id}/shares'): None,
    ('DELETE', '/api/plans/{plan_id}/shares'): None,
    ('GET', '/api/plans/{plan_id}/shares'): None,
    ('GET', '/api/chat/{kind}/{id}'): None,
    ('POST', '/api/chat/{kind}/{id}'): {'question': '이 코스 어때요?', 'mode': 'demo'},
}


def endpoints(routes):
    """앱의 모든 (메서드, 주소). include_router 로 붙인 경로는 FastAPI 가 감싸 두므로(_IncludedRouter) 안까지 펼친다."""
    for route in routes:
        inner = getattr(route, 'original_router', None)
        if inner is not None:
            yield from endpoints(inner.routes)
        else:
            for method in getattr(route, 'methods', None) or ():
                yield method, route.path


def plan_routes():
    return {(method, path) for method, path in endpoints(app.routes)
            if method != 'HEAD' and path.startswith(('/api/plans/{', '/api/chat/{'))}


def url(path, plan_id):
    for name in ('{id}', '{pid}', '{plan_id}'):
        path = path.replace(name, plan_id)
    return path.replace('{kind}', 'plan')


def call(client, method, path, plan_id, body):
    kwargs = {} if body is None else {'json': body}
    return client.request(method, url(path, plan_id), **kwargs)


def make_plan(client):
    response = client.post('/api/plans', json=CONDITIONS)
    assert response.status_code == 200, response.text
    return response.json()['plans'][0]


def snapshot(plan_id):
    """다른 브라우저의 요청 뒤에도 코스와 딸린 기록이 그대로인지 본다."""
    with store.connect() as db:
        counts = {table: db.execute(f'SELECT COUNT(*) FROM {table} WHERE plan_id=?', (plan_id,)).fetchone()[0]
                  for table in ('plan_shares', 'partner_votes', 'experience_events')}
        children = db.execute('SELECT COUNT(*) FROM plans WHERE parent=?', (plan_id,)).fetchone()[0]
    return store.get_plan(plan_id)['payload'], counts, children


def test_every_plan_route_is_listed():
    assert plan_routes() == set(PLAN_ROUTES), '코스 id 를 받는 새 경로는 소유자 검사 후 PLAN_ROUTES 에 넣어 주세요.'


def test_other_browser_gets_404_without_plan_content():
    with TestClient(app) as owner, TestClient(app) as other:
        plan = make_plan(owner)
        before = snapshot(plan['id'])
        names = [p['name'] for p in plan['places']]
        for (method, path), body in PLAN_ROUTES.items():
            response = call(other, method, path, plan['id'], body)
            assert response.status_code == 404, (method, path, response.status_code, response.text)
            assert not any(name in response.text for name in names), (method, path)
        # 없는 코스와 남의 코스는 같은 답이다(존재 여부를 드러내지 않는다).
        missing = other.get('/api/plans/no-such-plan')
        assert missing.status_code == 404
        assert other.get('/api/plans/' + plan['id']).json() == missing.json()
        assert snapshot(plan['id']) == before


def test_handlers_check_the_owner_even_without_the_middleware():
    """미들웨어의 주소 규칙이 바뀌거나 빠져도 처리 함수가 남의 코스를 내주지 않는다."""
    bare = FastAPI()
    bare.router.routes.extend(app.router.routes)  # 같은 경로·처리 함수, safety 미들웨어만 없다

    @bare.middleware('http')
    async def owner_header(request: Request, call_next):
        request.state.owner = request.headers.get('x-test-owner', '')
        return await call_next(request)

    with TestClient(app) as browser:
        plan = make_plan(browser)
    owner = store.get_plan(plan['id'])['owner']
    before = snapshot(plan['id'])
    names = [p['name'] for p in plan['places']]
    with TestClient(bare) as client:
        for stranger in ('someone-else', ''):
            client.headers['x-test-owner'] = stranger
            for (method, path), body in PLAN_ROUTES.items():
                response = call(client, method, path, plan['id'], body)
                assert response.status_code == 404, (stranger, method, path, response.status_code, response.text)
                # 경로를 못 찾은 404('Not Found')가 아니라 처리 함수가 소유자를 보고 낸 404 여야 한다.
                assert response.json()['detail'] != 'Not Found', (method, path)
                assert not any(name in response.text for name in names), (method, path)
        assert snapshot(plan['id']) == before
        client.headers['x-test-owner'] = owner
        mine = client.get('/api/plans/' + plan['id'])
        assert mine.status_code == 200 and mine.json()['id'] == plan['id'] and mine.json()['can_edit'] is True


def test_owner_routes_keep_working():
    with TestClient(app) as owner:
        plan = make_plan(owner)
        pid = plan['id']
        opened = owner.get('/api/plans/' + pid)
        assert opened.status_code == 200 and opened.json()['can_edit'] is True
        assert owner.get(f'/api/plans/{pid}/restaurant-matches').status_code == 200
        assert owner.get(f'/api/plans/{pid}/meal-rescue').status_code == 200
        assert owner.get(f'/api/plans/{pid}/reviews').status_code == 200
        assert owner.get(f'/api/plans/{pid}/feedback').json() == {'visit': None}
        saved = owner.post(f'/api/plans/{pid}/feedback', json={'kind': 'visit', 'visited': 'yes', 'obstacle': 'none', 'reuse': 'yes'})
        assert saved.status_code == 200 and owner.get(f'/api/plans/{pid}/feedback').json()['visit']['visited'] == 'yes'
        place_id = plan['places'][0]['id']
        assert owner.post(f'/api/plans/{pid}/place-report', json={'place_id': place_id, 'reason': 'hours'}).status_code == 200
        assert owner.get(f'/api/plans/{pid}/agreement').json()['can_replan'] is True
        assert owner.get(f'/api/chat/plan/{pid}', params={'mode': 'demo'}).status_code == 200


def test_partner_uses_the_share_token_and_owner_sees_the_votes():
    with TestClient(app) as owner, TestClient(app) as partner:
        plan = make_plan(owner)
        pid = plan['id']
        token = owner.post(f'/api/plans/{pid}/shares').json()['url'].split('#', 1)[1]
        auth = {'Authorization': 'Bearer ' + token}
        # 공유받은 사람은 코스 id 로는 열 수 없고, 토큰으로 공개용 요약만 본다.
        assert partner.get('/api/plans/' + pid).status_code == 404
        shared = partner.get('/api/shared-plan', headers=auth)
        assert shared.status_code == 200
        assert [p['id'] for p in shared.json()['places']] == [p['id'] for p in plan['places']]
        first = plan['places'][0]['id']
        assert partner.post('/api/shared-plan/vote', headers=auth, json={'choices': {first: 'must'}}).json() == {'saved': True}
        assert partner.get('/api/shared-plan', headers=auth).json()['my_choices'] == {first: 'must'}
        # 코스 id 경로로 의견을 넣으려 하면 막힌다(공유 토큰 경로만 받는다).
        assert partner.post(f'/api/plans/{pid}/agreement', json={'choices': {first: 'no'}}).status_code == 404
        # 만든 브라우저는 상대 의견을 본다.
        status = owner.get(f'/api/plans/{pid}/agreement').json()
        assert status['participants'] == 1 and status['places'][first]['must'] == 1 and status['answered']['others'] == [1]
        assert owner.post(f'/api/plans/{pid}/agreement', json={'choices': {first: 'yes'}}).status_code == 200
        assert owner.get(f'/api/plans/{pid}/agreement').json()['participants'] == 2
        # 공유를 취소하면 토큰도 더는 열리지 않는다.
        assert owner.delete(f'/api/plans/{pid}/shares').status_code == 200
        assert partner.get('/api/shared-plan', headers=auth).status_code == 404
