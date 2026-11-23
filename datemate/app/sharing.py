"""Revocable capability links expose only an explicit, non-private projection."""
import hashlib
import json
import secrets
import time
from datetime import date
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import Literal
from . import store
from .config import ROOT
from .models import PlaceId
from .regions import normalize_region
from .static_pages import versioned_page

router = APIRouter()


def owned(plan_id, owner):
    row = store.get_plan(plan_id)
    if not row or row['owner'] != owner:
        raise HTTPException(404, '일정을 찾을 수 없습니다.')
    return row


def resolve(authorization):
    token = (authorization or '').removeprefix('Bearer ')
    if not token or len(token) > 128:
        raise HTTPException(404, '공유 링크가 만료되었거나 취소됐어요.')
    digest = hashlib.sha256(token.encode()).hexdigest()
    with store.connect() as db:
        row = db.execute('SELECT p.*,s.expires,s.token_hash FROM plan_shares s JOIN plans p ON p.id=s.plan_id WHERE s.token_hash=? AND s.expires>?', (digest, time.time())).fetchone()
    if not row:
        raise HTTPException(404, '공유 링크가 만료되었거나 취소됐어요.')
    return dict(row)


def festival_search(conditions):
    """Only the region and visit day, so the shared page can list that day's festivals."""
    region = normalize_region(str(conditions.get('region') or '서울'))
    try:
        day = date.fromisoformat(str(conditions.get('visit_date') or '')).isoformat()
    except ValueError:
        return None
    return dict(region=region, visit_date=day) if region else None


def public_plan(plan):
    # Never copy the original payload and remove fields: new private fields must
    # remain private by default. No origin/home/requests/routes/free text/images.
    # 네이버 검색으로 찾은 장소는 '네이버 검색결과' 표시와 원본(지도 검색) 링크를 함께 보낸다(특약 2.1·2.2).
    from .naver_terms import is_naver_place
    def naver_fields(p):
        if not is_naver_place(p):return {}
        source=next((u for u in (p.get('place_source'),p.get('source')) if str(u or '').startswith('https://')),None)
        return dict(naver_result=True,source=source,naver_expired=bool(p.get('naver_expired')))
    shared = {'places': [dict(id=p['id'], name=p['name'], category=p.get('category',''),
                              # 주소 키가 있어도 값이 None 인 장소가 있다(주소 없는 공공데이터 장소). null 대신 빈 글로 보낸다 —
                              # 화면(static/shared.js)은 빈 주소면 ' · 주소' 를 적지 않는다. 2026-11-23 운영 확인에서 '… · null' 로 보이던 것.
                              address=p.get('address') or '',
                              arrival=plan['timeline'][i]['arrival'],
                              departure=plan['timeline'][i]['departure'],
                              **naver_fields(p))
                         for i,p in enumerate(plan['places'])],
              'festival_search': festival_search(plan.get('conditions') or {}),
              'notice': '공유용 코스예요. 영업·예약·이동 시간은 방문 전 확인해 주세요.'}
    visit = festival_visit(plan)
    if visit:
        shared['festival_visit'] = visit
    return shared


def festival_visit(plan):
    """운영 시간에 맞춰 고정한 축제 방문(plan['festival_visit'], app/festival_time.visit_record)의 이름과 시각만.
    행사장 = 출발지라 좌표·주소·출발지 이름은 싣지 않고, 운영 시간 원문(hours)·축제 id·기다림·돌아오는 구간도 싣지 않는다.
    고정하지 않은 코스는 None(공유 응답에 키가 없다 — 예전 모양 그대로)."""
    visit = plan.get('festival_visit')
    if not isinstance(visit, dict):
        return None
    fields = {key: visit.get(key) for key in ('title', 'arrival', 'departure')}
    if not all(isinstance(value, str) and value for value in fields.values()):
        return None
    # 코스 맨 앞('first')인지, 장소를 돈 뒤 행사장으로 돌아와 마무리하는지('last'), 장소 사이에 들르는지('middle' + 앞 장소 번호 after).
    # 행사장으로 가는 구간(leg)은 싣지 않는다. 자리가 장소 사이가 아닌 중간 기록은 예전처럼 맨 앞으로 본다.
    from .leg_modes import middle_after
    after = middle_after(plan)
    if after is not None:
        fields.update(position='middle', after=after)
    else:
        fields['position'] = 'last' if visit.get('position') == 'last' else 'first'
    return fields


@router.post('/api/plans/{plan_id}/shares')
def create_share(plan_id: str, request: Request):
    owned(plan_id, request.state.owner)
    token = secrets.token_urlsafe(32)
    expires = time.time() + 86400
    with store.connect() as db:
        db.execute('DELETE FROM plan_shares WHERE expires<=?', (time.time(),))
        count = db.execute('SELECT COUNT(*) FROM plan_shares WHERE plan_id=?', (plan_id,)).fetchone()[0]
        if count >= 10:
            raise HTTPException(429, '기존 공유를 취소한 뒤 새 링크를 만들어 주세요.')
        db.execute('INSERT INTO plan_shares VALUES(?,?,?,?)',
                   (hashlib.sha256(token.encode()).hexdigest(),plan_id,request.state.owner,expires))
    return {'url': '/shared#'+token, 'expires': expires}


@router.delete('/api/plans/{plan_id}/shares')
def revoke_shares(plan_id: str, request: Request):
    owned(plan_id, request.state.owner)
    with store.connect() as db:
        db.execute('DELETE FROM plan_shares WHERE plan_id=?', (plan_id,))
    return {'revoked': True}


@router.get('/api/shared-plan')
def read_shared(request: Request,authorization: str | None = Header(default=None)):
    row = resolve(authorization)
    from .experience import vote_status
    status=vote_status(json.loads(row['payload']),request.state.owner)
    return dict(public_plan(json.loads(row['payload'])),expires=row['expires'],my_choices=status['mine'])


class SharedVote(BaseModel):
    choices: dict[PlaceId, Literal['yes','no','neutral','must']] = Field(max_length=5)


@router.post('/api/shared-plan/vote')
def vote_shared(data: SharedVote, request: Request, authorization: str | None = Header(default=None)):
    row = resolve(authorization)
    from .experience import save_votes
    try:
        save_votes(json.loads(row['payload']), request.state.owner, row['owner'], data.choices,share_token=row['token_hash'])
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return {'saved': True}


@router.get('/shared', include_in_schema=False)
def shared_page():
    # 홈과 같이 js·css 주소에 내용 해시를 붙여, 배포 직후 이전 festivals.js 가 캐시에서 섞여 쓰이지 않게 한다.
    # 개인 공유 링크 화면은 검색에 나오지 않게 한다. robots.txt 로 막으면 로봇이 이 noindex 를 읽지 못하므로 막지 않는다.
    return HTMLResponse(versioned_page('shared.html'), headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer',
                                                               'X-Robots-Tag':'noindex, nofollow'})


SHARE_FAMILY_DEPTH = 20


def owned_ancestors(db, plan_id, owner):
    """plan_id 부터 부모를 따라 올라간 코스 id 목록(자기 자신 포함). 다른 브라우저의 코스를 만나면 거기서 멈춘다."""
    path, current = [], plan_id
    while current and current not in path and len(path) < SHARE_FAMILY_DEPTH:
        row = db.execute('SELECT owner,parent FROM plans WHERE id=?', (current,)).fetchone()
        if not row or row['owner'] != owner:
            break
        path.append(current)
        current = row['parent']
    return path


def partner_opinions(db, plan_id, owner):
    """그 코스에 남은 상대 의견 수(만든 브라우저 자신의 의견은 빼고). 의견은 코스 id 마다 따로 저장된다(experience.save_votes)."""
    return db.execute('SELECT COUNT(*) FROM partner_votes WHERE plan_id=? AND owner!=?', (plan_id, owner)).fetchone()[0]


@router.get('/api/plans/{plan_id}/shares')
def share_status(plan_id: str, request: Request):
    """만든 브라우저만: 같은 변경 계열의 열려 있는 공유 링크 수와 가장 늦은 만료 시각(개선안 31·32, 2026-11-24 점검 F1).
    링크는 코스 하나에 묶여 있어, 장소를 바꿔 새 버전(자식 코스)이 생겨도 예전 링크를 받은 사람은 바뀌기 전 코스를 보고
    의견도 그 코스 id 에 남는다(지금 코스의 합의에는 잡히지 않는다).
    - current: 이 코스. earlier: 이 코스의 이전 버전(부모 코스)들.
    - other: 같은 처음 코스(부모를 끝까지 따라간 코스)에서 나온 나머지 버전 — 되돌리기 전 코스(relation='later', 이 코스의 자손)와
      되돌린 뒤 따로 바꾼 코스(relation='branch'). 되돌리기는 부모 코스 자체로 돌아가므로(main.undo) 자식 쪽 링크를 여기서 알린다.
      자손만 보지 않고 형제까지 보는 까닭: '바꿔 공유 → 되돌림 → 다른 것으로 바꿈'은 흔한 흐름인데, 자손만 보면 그 링크가 다시 안 보인다.
    범위는 이 브라우저(소유자)의 코스만이고 토큰 값은 돌려주지 않는다(저장소에도 해시만 있다). 처음 코스를 찾는 깊이는 20단계까지."""
    owner = request.state.owner
    owned(plan_id, owner)
    now = time.time()
    with store.connect() as db:
        def active(pid):
            shares = db.execute('SELECT COUNT(*) AS n, MAX(expires) AS until FROM plan_shares WHERE plan_id=? AND expires>?', (pid, now)).fetchone()
            return dict(plan_id=pid, active=shares['n'], expires=shares['until'])
        chain = owned_ancestors(db, plan_id, owner)
        current = active(plan_id)
        earlier = [dict(row, opinions=partner_opinions(db, row['plan_id'], owner)) for row in map(active, chain[1:]) if row['active']]
        root, other = chain[-1], []
        # 이 브라우저의 열린 링크가 걸린 코스 가운데 같은 처음 코스로 올라가는 것. 열린 링크는 24시간이면 닫혀 몇 개 되지 않는다.
        # payload 는 GROUP BY 에 넣지 않고(PostgreSQL 은 묶지 않은 열을 받지 않는다) 계열에 든 코스만 따로 읽는다.
        rows = db.execute('SELECT s.plan_id AS plan_id, COUNT(*) AS n, MAX(s.expires) AS until FROM plan_shares s JOIN plans p ON p.id=s.plan_id '
                          'WHERE p.owner=? AND s.expires>? GROUP BY s.plan_id ORDER BY MAX(s.expires) DESC', (owner, now)).fetchall()
        for row in rows:
            if row['plan_id'] in chain:
                continue
            path = owned_ancestors(db, row['plan_id'], owner)
            if root not in path:
                continue
            payload = db.execute('SELECT payload FROM plans WHERE id=?', (row['plan_id'],)).fetchone()['payload']
            places = [str(p.get('name') or '') for p in (json.loads(payload).get('places') or [])]
            other.append(dict(plan_id=row['plan_id'], active=row['n'], expires=row['until'],
                              relation='later' if plan_id in path else 'branch', places=places,
                              opinions=partner_opinions(db, row['plan_id'], owner)))
    return {'current': current, 'earlier': earlier, 'other': other}
