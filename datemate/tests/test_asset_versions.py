import hashlib
from fastapi.testclient import TestClient
from app.config import ROOT
from app.main import app


# 2026-11-27 JS 묶기(QA-14): 첫 화면·공유 화면의 스크립트는 묶음(static/bundles/<페이지>.js) 하나로 받는다.
# 묶음 주소의 ?v= 는 묶음 파일의 해시라 원본 JS 가 바뀌면(묶음을 다시 만들면) 주소가 바뀐다. 원본 순서(maps.js 가 app.js 보다 앞)는
# 묶음 안의 순서로 지켜진다(tests/test_js_bundle.py). CSS 는 묶지 않으므로 예전처럼 파일별 ?v= 다.
def test_home_revalidates_script_dependencies_after_changes():
    with TestClient(app) as client:
        response=client.get('/')
        assert response.headers['cache-control']=='no-store'
        for name in ('bundles/index.js','plan-map.css'):
            version=hashlib.sha256((ROOT/'static'/name).read_bytes()).hexdigest()[:12]
            url=f'/static/{name}?v={version}'
            assert url in response.text
            assert client.get(url).status_code==200
        bundle=(ROOT/'static'/'bundles'/'index.js').read_text(encoding='utf-8')
        assert bundle.index('/* ---- maps.js ---- */')<bundle.index('/* ---- app.js ---- */')


def test_shared_page_revalidates_script_dependencies_after_changes():
    with TestClient(app) as client:
        response=client.get('/shared')
        assert response.headers['cache-control']=='no-store'
        assert response.headers['referrer-policy']=='no-referrer'
        for name in ('bundles/shared.js','style.css'):
            version=hashlib.sha256((ROOT/'static'/name).read_bytes()).hexdigest()[:12]
            url=f'/static/{name}?v={version}'
            assert url in response.text
            assert client.get(url).status_code==200
