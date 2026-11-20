"""인허가 자료 좌표(EPSG:5174) → WGS84 변환(app/korea_tm.py).

기준값은 2026-11-20 에 실제 인허가 자료의 좌표와, 같은 도로명 주소를 소상공인 상가정보 API 가 준 WGS84 좌표다(외부 호출 없이 고정값으로 비교).
"""
import math

import pytest

from app.korea_tm import to_wgs84


def meters(a, b):
    return math.hypot((a[0] - b[0]) * 111320, (a[1] - b[1]) * 111320 * math.cos(math.radians(a[0])))


@pytest.mark.parametrize('x,y,expected', [
    # 서울 중구 명동10길 29 (인허가 '명동교자 후') ↔ 상가정보 같은 주소
    (198672.005950725, 451143.699280519, (37.562573, 126.985761)),
    # 서울 중구 을지로12길 5 ↔ 상가정보 같은 주소
    (199170.677028258, 451519.369414946, (37.565952, 126.991398)),
])
def test_license_coordinates_land_on_the_same_address_as_store_info(x, y, expected):
    assert meters(to_wgs84(x, y), expected) < 2


def test_negative_northing_is_jeju_not_an_error():
    """제주 서귀포시 대정읍 하모리: 원점(북위 38도)에서 남쪽으로 50만 m 넘게 떨어져 Y 가 음수다."""
    lat, lon = to_wgs84('130194.063234931', '-30956.1782079298')
    assert 33.20 < lat < 33.23 and 126.24 < lon < 126.27


@pytest.mark.parametrize('x,y', [(None, None), ('', ''), ('abc', '1'), (float('nan'), 1), (9e9, 9e9)])
def test_unreadable_or_out_of_range_values_give_none(x, y):
    assert to_wgs84(x, y) is None
