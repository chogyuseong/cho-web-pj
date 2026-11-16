"""공공데이터 '전국주차장정보표준데이터'(data/public_parking.json)의 요금·운영시간.

scripts/build_public_parking.py 가 만든 파일을 처음 쓸 때 한 번 읽고, 0.01도 격자로 묶어 가까운 주차장을 찾는다.
외부 호출은 없다. 파일이 없으면 빈 자료로 동작한다(주차장 칸은 네이버 지역 검색 결과만 보여 준다).
자료는 지자체가 올린 값이고 데이터기준일자 이후 바뀌었을 수 있어, 화면에는 기준일을 함께 보인다.
"""

import json
import math
import re
import threading
from datetime import date

from .config import ROOT

PATH = ROOT / "data" / "public_parking.json"
SOURCE = "공공데이터포털 전국주차장정보표준데이터"
CELL = 0.01
_lock = threading.Lock()
_data = None


def load(path=None):
    """(행 목록, 격자). 행은 열 이름 dict. 테스트는 path 로 다른 파일을 넣는다."""
    global _data
    if path is None and _data is not None:
        return _data
    with _lock:
        if path is None and _data is not None:
            return _data
        target = path or PATH
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
            columns = payload["columns"]
            lots = [dict(zip(columns, row)) for row in payload["rows"]]
        except (OSError, ValueError, KeyError, TypeError):
            lots = []
        grid = {}
        for lot in lots:
            grid.setdefault(cell(lot["lat"], lot["lon"]), []).append(lot)
        result = (lots, grid)
        if path is None:
            _data = result
        return result


def reset(path=None):
    """다른 파일(테스트)로 바꾸거나 다시 읽게 한다."""
    global _data
    with _lock:
        _data = None
    if path is not None:
        _data = load(path)


def cell(lat, lon):
    return (math.floor(lat / CELL), math.floor(lon / CELL))


def metres(lat1, lon1, lat2, lon2):
    """짧은 거리용 근사(평면). 800m 안의 비교에는 충분하다."""
    dy = (lat2 - lat1) * 111_320
    dx = (lon2 - lon1) * 111_320 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy)


def nearby(lat, lon, radius_m):
    """(거리 m, 주차장) 가까운 순."""
    _, grid = load()
    span = int(radius_m / (CELL * 111_320 * 0.7)) + 1
    base = cell(lat, lon)
    found = []
    for i in range(base[0] - span, base[0] + span + 1):
        for j in range(base[1] - span, base[1] + span + 1):
            for lot in grid.get((i, j), ()):
                d = metres(lat, lon, lot["lat"], lot["lon"])
                if d <= radius_m:
                    found.append((d, lot))
    return sorted(found, key=lambda pair: pair[0])


def won(amount):
    return f"{amount:,}원"


def fee_text(lot):
    """'무료' / '기본 30분 500원 · 추가 10분당 200원 · 1일 10,000원' / None(요금을 알 수 없음)."""
    kind = lot.get("fee_kind") or ""
    if kind == "무료":
        return "무료"
    parts = []
    if lot.get("base_minutes") and lot.get("base_fee") is not None:
        fee = "무료" if lot["base_fee"] == 0 else won(lot["base_fee"])
        parts.append(f"기본 {lot['base_minutes']}분 {fee}")
    if lot.get("extra_minutes") and lot.get("extra_fee"):
        parts.append(f"추가 {lot['extra_minutes']}분당 {won(lot['extra_fee'])}")
    if lot.get("day_fee"):
        parts.append(f"1일 {won(lot['day_fee'])}")
    if not parts:
        return None
    return ("유료·무료 혼합 · " if kind == "혼합" else "") + " · ".join(parts)


DAY_KEYS = (("weekday", "평일"), ("saturday", "토요일"), ("holiday", "공휴일"))


def day_type(visit):
    """방문일의 운영시간 구분. 일요일은 이 자료에서 공휴일 칸으로 본다(공휴일 달력은 쓰지 않음)."""
    weekday = visit.weekday()
    if weekday == 5:
        return "saturday", "토"
    if weekday == 6:
        return "holiday", "일"
    return "weekday", "월화수목금"[weekday]


def hours_text(lot, visit):
    """'방문일(토) 09:00~18:00' / '방문일(토) 24시간' / '방문일(일) 운영하지 않아요' / None."""
    if not isinstance(visit, date):
        return None
    key, label = day_type(visit)
    days = lot.get("days") or ""
    word = dict(DAY_KEYS)[key]
    if days and word not in days:
        return f"방문일({label}) 운영하지 않아요(운영요일: {days})"
    span = lot.get(key)
    if not span:
        return None
    start, end = span
    if start == "00:00" and end in ("23:59", "24:00"):
        return f"방문일({label}) 24시간"
    return f"방문일({label}) {start}~{end}"


def squeeze(text):
    return re.sub(r"[\s()·\-]|주차장|공영|노상|노외", "", str(text or "")).casefold()


def same_lot(naver_name, lot, distance_m):
    """네이버 결과와 공공데이터 행이 같은 주차장인지: 60m 안이면서 이름이 겹치거나, 20m 안."""
    if distance_m <= 20:
        return True
    if distance_m > 60:
        return False
    a, b = squeeze(naver_name), squeeze(lot["name"])
    return bool(a and b and (a in b or b in a))


def details(lot, visit):
    """주차장 칸에 붙일 공공데이터 정보."""
    return dict(
        fee=fee_text(lot),
        hours=hours_text(lot, visit),
        kind=lot.get("kind") or None,
        as_of=lot.get("as_of") or None,
        source=SOURCE,
    )
