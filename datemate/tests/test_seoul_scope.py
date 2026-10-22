import json
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from app import catalog
from app.main import app
from app.models import Conditions


@pytest.mark.parametrize('region', ['서울', '서울시', '서울특별시'])
def test_seoul_aliases_are_normalized(region):
    assert Conditions(visit_date='2026-10-24', region=region).region == '서울'


@pytest.mark.parametrize('region', ['부산', '인천', '경기도', '', '전국'])
def test_other_regions_are_rejected(region):
    with pytest.raises(ValidationError, match='서울특별시 내 장소만'):
        Conditions(visit_date='2026-10-24', region=region)


def test_catalog_search_and_detail_exclude_other_regions(tmp_path, monkeypatch):
    data = tmp_path / 'data'
    data.mkdir()
    rows = [dict(id='seoul', region='서울', name='서울공원', category='산책', tags=[]),
            dict(id='busan', region='부산', name='부산공원', category='산책', tags=[]),
            dict(id='unknown', name='지역미상공원', category='산책', tags=[])]
    (data / 'real_places.json').write_text(json.dumps(rows), encoding='utf-8')
    monkeypatch.setattr(catalog, 'ROOT', tmp_path)
    assert [p['id'] for p in catalog.places('real')] == ['seoul']
    assert catalog.get_place('busan', 'real') is None
    with TestClient(app) as client:
        assert [p['id'] for p in client.get('/api/places?mode=real').json()['places']] == ['seoul']
        assert client.get('/api/places/busan?mode=real').status_code == 404
        response = client.post('/api/plans', json={'region':'부산','visit_date':'2026-10-24'})
        assert response.status_code == 422


def test_ui_and_natural_language_keep_seoul_scope():
    with TestClient(app) as client:
        html = client.get('/').text
        assert '<title>서울 데이트메이트 · 서울 데이트 코스 추천</title>' in html
        assert '서울은 임시 서비스 지역' not in html
        response = client.post('/api/conditions/parse', json={'text':'부산에서 전시 보고 싶어'})
        assert response.json()['patch']['region'] == '서울'
        assert any('서울 밖 장소는 추천하지 않습니다' in s for s in response.json()['warnings'])
