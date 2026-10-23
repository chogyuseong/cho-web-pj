import pytest
from app.search_address_text import street_address,place_query

@pytest.mark.parametrize('raw,expected',[
 ('서울특별시 강서구 양천로 401 2층 코델','서울특별시 강서구 양천로 401'),
 ('서울특별시 강서구 양천로 401-2 A동 201호','서울특별시 강서구 양천로 401-2'),
 ('서울 강남구 강남대로 94길 12 지하1층','서울 강남구 강남대로94길 12'),
 ('서울 중구 충무로4길 3 1층','서울 중구 충무로4길 3'),
 ('서울 종로구 익선동 166-78 2층','서울 종로구 익선동 166-78'),
 (None,''),
])
def test_remove_only_address_details(raw,expected):assert street_address(raw)==expected

def test_name_kept_and_original_data_unchanged():
 p={'name':'코델','address':'서울특별시 강서구 양천로 401 2층 201호'}
 assert place_query(p)=='코델 서울특별시 강서구 양천로 401'
 assert p['address'].endswith('201호')


def test_sports_club_building_floor_removed():
    assert place_query({'name':'박흥권 탁구 클럽','address':'서울특별시 강남구 선릉로 664 건설빌딩 지하1층'})=='박흥권 탁구 클럽 서울특별시 강남구 선릉로 664'
