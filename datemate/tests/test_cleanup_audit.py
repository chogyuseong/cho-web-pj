"""Related-record cleanup, checked on SQLite and PostgreSQL."""
import time
from fastapi.testclient import TestClient
from app import store
from app.main import app


def test_personal_deletion_removes_chat_budget_and_preserves_other_user():
    with TestClient(app) as client:
        client.get('/')
        owner=client.cookies['dm_session']
        bucket=int(time.time()//60)
        store.reserve_budget([('chat:'+owner,10),('chat:other-cleanup-user',10)],bucket)
        assert client.delete('/api/me/data').status_code==200
        with store.connect() as db:
            assert db.execute('SELECT 1 FROM request_budgets WHERE scope=?',('chat:'+owner,)).fetchone() is None
            assert db.execute('SELECT 1 FROM request_budgets WHERE scope=?',('chat:other-cleanup-user',)).fetchone()


def test_review_deletion_removes_associated_reports():
    with TestClient(app) as author,TestClient(app) as reporter:
        plan=author.post('/api/plans',json={'visit_date':'2026-10-31','max_leg':180,'budget':1000000}).json()['plans'][0]
        response=author.put('/api/plans/'+plan['id']+'/review',json={
            'nickname':'점검','rating':4,'visited':'2026-01-01','body':'삭제 점검용 후기'})
        assert response.status_code==200
        review=next(row for row in response.json()['rows'] if row['mine'])
        assert reporter.post('/api/reviews/'+review['id']+'/report',json={'reason':'점검용 신고'}).status_code==200
        assert author.delete('/api/reviews/'+review['id']).status_code==200
        with store.connect() as db:
            assert db.execute('SELECT 1 FROM reports WHERE review_id=?',(review['id'],)).fetchone() is None
