import hashlib
from fastapi.testclient import TestClient
from app.config import ROOT
from app.main import app


def test_home_revalidates_script_dependencies_after_changes():
    with TestClient(app) as client:
        response=client.get('/')
        assert response.headers['cache-control']=='no-store'
        for name in ('maps.js','app.js','plan-map.css'):
            version=hashlib.sha256((ROOT/'static'/name).read_bytes()).hexdigest()[:12]
            url=f'/static/{name}?v={version}'
            assert url in response.text
            assert client.get(url).status_code==200
        assert response.text.index('/static/maps.js?')<response.text.index('/static/app.js?')
