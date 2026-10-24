"""Revocable capability links expose only an explicit, non-private projection."""
import hashlib
import json
import secrets
import time
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Literal
from . import store
from .config import ROOT

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


def public_plan(plan):
    # Never copy the original payload and remove fields: new private fields must
    # remain private by default. No origin/home/requests/routes/free text/images.
    return {'places': [dict(id=p['id'], name=p['name'], category=p.get('category',''),
                            address=p.get('address',''),
                            arrival=plan['timeline'][i]['arrival'],
                            departure=plan['timeline'][i]['departure'])
                       for i,p in enumerate(plan['places'])],
            'notice': '공유용 코스예요. 영업·예약·이동 시간은 방문 전 확인해 주세요.'}


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
def read_shared(authorization: str | None = Header(default=None)):
    row = resolve(authorization)
    return dict(public_plan(json.loads(row['payload'])), expires=row['expires'])


class SharedVote(BaseModel):
    choices: dict[str, Literal['yes','no','neutral']] = Field(max_length=5)


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
    return FileResponse(ROOT/'static'/'shared.html', headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
