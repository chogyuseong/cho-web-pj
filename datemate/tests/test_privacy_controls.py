from fastapi.testclient import TestClient
from app.main import app
from app import store


def test_delete_only_current_browser_data():
    with TestClient(app) as client:
        client.get('/')
        owner=client.cookies.get('dm_session')
        with store.connect() as db:
            db.execute('INSERT INTO chats VALUES(?,?,?,?,?)',(owner,'private','user','private text',1))
            db.execute('INSERT INTO chats VALUES(?,?,?,?,?)',('other-owner','private','user','keep',1))
        response=client.delete('/api/me/data')
        assert response.status_code==200
        assert response.headers['cache-control']=='no-store'
        with store.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM chats WHERE owner=?',(owner,)).fetchone()[0]==0
            assert db.execute('SELECT COUNT(*) FROM chats WHERE owner=?',('other-owner',)).fetchone()[0]>0
            assert db.execute('SELECT COUNT(*) FROM sessions WHERE token=?',(owner,)).fetchone()[0]==0


def test_readiness_does_not_create_session():
    with TestClient(app) as client:
        response=client.get('/readyz')
        assert response.status_code==200
        assert response.json()['external_services_verified'] is False
        assert 'dm_session' not in client.cookies
