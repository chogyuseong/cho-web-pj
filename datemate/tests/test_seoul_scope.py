"""National region selection must keep venues in the chosen province."""

import json
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from app import catalog
from app.main import app
from app.models import Conditions
from app.regions import region_from_address, same_region


@pytest.mark.parametrize('alias,expected', [
    ('서울특별시', '서울'), ('부산광역시', '부산'), ('경기도', '경기'),
    ('강원특별자치도', '강원'), ('전북특별자치도', '전북'), ('제주특별자치도', '제주'),
])
def test_province_aliases_are_normalized(alias, expected):
    assert Conditions(mode='real', visit_date='2026-11-12', region=alias).region == expected
    assert region_from_address(alias + ' 시청로 1') == expected


@pytest.mark.parametrize('region', ['', '전국', '도쿄'])
def test_unsupported_regions_are_rejected(region):
    with pytest.raises(ValidationError, match='대한민국의 시·도'):
        Conditions(mode='real', visit_date='2026-11-12', region=region)


def test_origin_and_region_must_match_and_demo_remains_seoul():
    with pytest.raises(ValidationError, match='출발지 주소가 다릅니다'):
        Conditions(mode='real', visit_date='2026-11-12', region='부산',
                   origin={'name': '서울특별시 중구', 'lat': 37.56, 'lon': 126.97})
    with pytest.raises(ValidationError, match='가상 장소 데모'):
        Conditions(visit_date='2026-11-12', region='부산')


def test_catalog_keeps_known_provinces_and_rejects_unknown(tmp_path, monkeypatch):
    data = tmp_path / 'data'
    data.mkdir()
    rows = [dict(id='seoul', region='서울', name='서울공원', category='산책', tags=[]),
            dict(id='busan', region='부산', name='부산공원', category='산책', tags=[]),
            dict(id='unknown', name='지역미상공원', category='산책', tags=[])]
    (data / 'real_places.json').write_text(json.dumps(rows), encoding='utf-8')
    monkeypatch.setattr(catalog, 'ROOT', tmp_path)
    assert [p['id'] for p in catalog.places('real')] == ['seoul', 'busan']
    assert same_region(rows[1], '부산') and not same_region(rows[1], '서울')
    with TestClient(app) as client:
        assert client.get('/api/places/busan?mode=real').status_code == 200
        assert client.get('/api/places/unknown?mode=real').status_code == 404


def test_ui_and_natural_language_offer_national_regions():
    with TestClient(app) as client:
        html = client.get('/').text
        assert '전국 데이트 코스와 축제 추천' in html
        assert '<option value="부산">부산</option>' in html
        response = client.post('/api/conditions/parse', json={'text': '부산에서 전시 보고 싶어'})
        assert response.json()['patch']['region'] == '부산'


def test_busan_local_search_can_build_a_real_plan(monkeypatch):
    from app import intent_discovery
    from app.planner import recommend

    rows = [
        dict(title='해운대 카페', category='카페', roadAddress='부산광역시 해운대구 우동 1', mapx=129.163, mapy=35.163),
        dict(title='해운대 전시관', category='전시', roadAddress='부산광역시 해운대구 우동 2', mapx=129.164, mapy=35.164),
        dict(title='해운대 공원', category='공원', roadAddress='부산광역시 해운대구 우동 3', mapx=129.165, mapy=35.165),
        dict(title='서울 카페', category='카페', roadAddress='서울특별시 중구 1', mapx=126.97, mapy=37.56),
    ]
    monkeypatch.setattr(intent_discovery, 'search_enabled', lambda: True)
    monkeypatch.setattr(intent_discovery, 'local_lookup', lambda name, area: (rows, 'available'))
    c = Conditions(mode='real', allow_estimates=True, visit_date='2026-11-12', region='부산',
                   origin={'name': '부산광역시 해운대구 우동', 'lat': 35.163, 'lon': 129.163}, count=2)
    found = intent_discovery.discover_requested_places(c)
    assert found['resolved'] >= 3, found
    result = recommend(c)
    assert result['plans']
    assert all(p['region'] == '부산' for plan in result['plans'] for p in plan['places'])
