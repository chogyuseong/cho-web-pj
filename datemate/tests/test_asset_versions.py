import hashlib
from fastapi.testclient import TestClient
from app.config import ROOT
from app.main import app


# 2026-11-27 JS 묶기(QA-14): 첫 화면·공유 화면의 스크립트는 묶음(static/bundles/<페이지>.js)으로 받는다.
# 묶음 주소의 ?v= 는 묶음 파일의 해시라 원본 JS 가 바뀌면(묶음을 다시 만들면) 주소가 바뀐다. CSS 는 묶지 않으므로 예전처럼 파일별 ?v= 다.
# 2026-11-28 QA-19: 첫 화면은 묶음이 둘이다 — 바로 받는 bundles/index.js(app.js 등)와 나중에 받는 bundles/index-2.js(maps.js 등,
# template#later-scripts 안). 예전에는 한 묶음 안에서 maps.js 가 app.js 보다 앞이었다. 지금 app.js 는 나중 묶음의 이름을
# DatemateLater 를 기다린 뒤에만 쓴다(tests/test_js_split.py). 두 주소 모두 ?v= 가 붙어야 배포 뒤 예전 파일과 섞이지 않는다.
def test_home_revalidates_script_dependencies_after_changes():
    with TestClient(app) as client:
        response=client.get('/')
        assert response.headers['cache-control']=='no-store'
        for name in ('bundles/index.js','bundles/index-2.js','plan-map.css'):
            version=hashlib.sha256((ROOT/'static'/name).read_bytes()).hexdigest()[:12]
            url=f'/static/{name}?v={version}'
            assert url in response.text
            assert client.get(url).status_code==200
        first=(ROOT/'static'/'bundles'/'index.js').read_text(encoding='utf-8')
        later=(ROOT/'static'/'bundles'/'index-2.js').read_text(encoding='utf-8')
        assert '/* ---- app.js ---- */' in first and '/* ---- maps.js ---- */' not in first
        assert '/* ---- maps.js ---- */' in later and '/* ---- app.js ---- */' not in later
        # 로더(later-scripts.js)는 첫 묶음에서 app.js 보다 앞이다(app.js 가 맨 위 실행 중에 DatemateLater 를 쓴다).
        assert first.index('/* ---- later-scripts.js ---- */')<first.index('/* ---- app.js ---- */')


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
