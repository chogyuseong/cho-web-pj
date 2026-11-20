"""중부원점 TM(EPSG:5174) 좌표를 위도·경도(WGS84)로 바꾼다.

행정안전부 지방행정 인허가 자료(일반음식점·휴게음식점)의 CRD_INFO_X·CRD_INFO_Y 가 이 좌표계다
(공공데이터포털 서비스 설명: '보정계수 안들어간 Bessel 중부원점TM(EPSG:5174)').

2026-11-20 검증: 인허가 자료의 실제 업소 두 곳을 이 변환으로 바꾼 값과, 같은 도로명 주소를 소상공인 상가정보 API 가
WGS84 로 준 좌표를 비교했다.
  · 서울 중구 명동10길 29   X=198672.005950725 Y=451143.699280519 → 37.562571, 126.985757 (상가정보 37.562573, 126.985761 · 0.4m 차이)
  · 서울 중구 을지로12길 5  X=199170.677028258 Y=451519.369414946 → 37.565957, 126.991401 (상가정보 37.565952, 126.991398 · 0.6m 차이)
  · 제주 서귀포시 대정읍 하모리 694-7  X=130194.06 Y=-30956.18 → 33.215062, 126.252051 (대정읍 하모리 안. Y 가 음수인 것은 원점(북위 38도)에서
    남쪽으로 53만 m 떨어져 가산값 50만 m 를 넘기 때문이다)
tests/test_korea_tm.py 가 위 값을 고정한다.

계산: Bessel 1841 타원체의 횡축 메르카토르 역변환 → 3차원 직교 좌표 → 7매개변수 변환(국토지리정보원이 쓰는 값,
proj 의 +towgs84=-115.80,474.99,674.11,1.16,-2.31,-1.63,6.43) → WGS84 위도·경도. 외부 라이브러리를 쓰지 않는다.
"""

import math

_A_BESSEL, _F_BESSEL = 6377397.155, 1 / 299.1528128
_A_WGS, _F_WGS = 6378137.0, 1 / 298.257223563
_LAT0, _LON0 = math.radians(38.0), math.radians(127.0028902777778)
_FALSE_EASTING, _FALSE_NORTHING = 200000.0, 500000.0
_DX, _DY, _DZ = -115.80, 474.99, 674.11
_RX, _RY, _RZ = (math.radians(seconds / 3600) for seconds in (1.16, -2.31, -1.63))
_SCALE = 1 + 6.43e-6


def _meridian_arc(lat, a, e2):
    e4, e6 = e2 * e2, e2 * e2 * e2
    return a * (
        (1 - e2 / 4 - 3 * e4 / 64 - 5 * e6 / 256) * lat
        - (3 * e2 / 8 + 3 * e4 / 32 + 45 * e6 / 1024) * math.sin(2 * lat)
        + (15 * e4 / 256 + 45 * e6 / 1024) * math.sin(4 * lat)
        - (35 * e6 / 3072) * math.sin(6 * lat)
    )


def _tm_to_bessel(x, y):
    e2 = 2 * _F_BESSEL - _F_BESSEL * _F_BESSEL
    ep2 = e2 / (1 - e2)
    arc = _meridian_arc(_LAT0, _A_BESSEL, e2) + (y - _FALSE_NORTHING)
    mu = arc / (_A_BESSEL * (1 - e2 / 4 - 3 * e2 * e2 / 64 - 5 * e2**3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    foot = (
        mu
        + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
        + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
        + (151 * e1**3 / 96) * math.sin(6 * mu)
        + (1097 * e1**4 / 512) * math.sin(8 * mu)
    )
    c1 = ep2 * math.cos(foot) ** 2
    t1 = math.tan(foot) ** 2
    n1 = _A_BESSEL / math.sqrt(1 - e2 * math.sin(foot) ** 2)
    r1 = _A_BESSEL * (1 - e2) / (1 - e2 * math.sin(foot) ** 2) ** 1.5
    d = (x - _FALSE_EASTING) / n1
    lat = foot - (n1 * math.tan(foot) / r1) * (
        d * d / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1 * c1 - 9 * ep2) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 * t1 - 252 * ep2 - 3 * c1 * c1) * d**6 / 720
    )
    lon = _LON0 + (
        d
        - (1 + 2 * t1 + c1) * d**3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1 * c1 + 8 * ep2 + 24 * t1 * t1) * d**5 / 120
    ) / math.cos(foot)
    return lat, lon


def _bessel_to_wgs84(lat, lon):
    e2 = 2 * _F_BESSEL - _F_BESSEL * _F_BESSEL
    n = _A_BESSEL / math.sqrt(1 - e2 * math.sin(lat) ** 2)
    x = n * math.cos(lat) * math.cos(lon)
    y = n * math.cos(lat) * math.sin(lon)
    z = n * (1 - e2) * math.sin(lat)
    x2 = _DX + _SCALE * (x - _RZ * y + _RY * z)
    y2 = _DY + _SCALE * (_RZ * x + y - _RX * z)
    z2 = _DZ + _SCALE * (-_RY * x + _RX * y + z)
    e2w = 2 * _F_WGS - _F_WGS * _F_WGS
    p = math.hypot(x2, y2)
    lat2 = math.atan2(z2, p * (1 - e2w))
    for _ in range(6):
        nw = _A_WGS / math.sqrt(1 - e2w * math.sin(lat2) ** 2)
        lat2 = math.atan2(z2 + e2w * nw * math.sin(lat2), p)
    return math.degrees(lat2), math.degrees(math.atan2(y2, x2))


def to_wgs84(x, y):
    """(위도, 경도). 숫자로 읽을 수 없거나 우리나라 범위를 벗어나면 None."""
    try:
        x, y = float(x), float(y)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(x) and math.isfinite(y)) or not (-200000 <= x <= 700000 and -200000 <= y <= 800000):
        return None
    lat, lon = _bessel_to_wgs84(*_tm_to_bessel(x, y))
    return (lat, lon) if 32 <= lat <= 39.5 and 124 <= lon <= 132 else None
