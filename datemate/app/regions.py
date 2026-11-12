"""Canonical Korean first-level administrative regions for national searches."""

REGIONS = {
    '서울': ('서울', '서울시', '서울특별시'),
    '부산': ('부산', '부산시', '부산광역시'),
    '대구': ('대구', '대구시', '대구광역시'),
    '인천': ('인천', '인천시', '인천광역시'),
    '광주': ('광주', '광주시', '광주광역시'),
    '대전': ('대전', '대전시', '대전광역시'),
    '울산': ('울산', '울산시', '울산광역시'),
    '세종': ('세종', '세종시', '세종특별자치시'),
    '경기': ('경기', '경기도'),
    '강원': ('강원', '강원도', '강원특별자치도'),
    '충북': ('충북', '충청북도'),
    '충남': ('충남', '충청남도'),
    '전북': ('전북', '전라북도', '전북특별자치도'),
    '전남': ('전남', '전라남도'),
    '경북': ('경북', '경상북도'),
    '경남': ('경남', '경상남도'),
    '제주': ('제주', '제주도', '제주특별자치도'),
}

ALIASES = {alias: region for region, names in REGIONS.items() for alias in names}


def normalize_region(value):
    return ALIASES.get(str(value or '').strip())


def region_from_address(value):
    first = str(value or '').strip().split(' ', 1)[0]
    return normalize_region(first)


def same_region(place, region):
    found = normalize_region(place.get('region')) or region_from_address(place.get('address'))
    return found == normalize_region(region)


def korean_coordinates(lat, lon):
    return 33 <= lat <= 39 and 124 <= lon <= 132
