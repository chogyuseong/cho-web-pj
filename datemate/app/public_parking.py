"""공공데이터 '전국주차장정보표준데이터'와 서울 '공영주차장 안내 정보'(data/public_parking.json)의 요금·운영시간.

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
from .regions import region_from_address

PATH = ROOT / "data" / "public_parking.json"
SOURCE = "공공데이터포털 전국주차장정보표준데이터"
CELL = 0.01
# 승용차가 쓸 수 없는 버스 전용 주차장. '버스터미널 주차장'·'버스정류장 주차장'은 승용차도 쓰므로 낱말에 넣지 않는다.
BUS_ONLY_WORDS = ("버스전용", "버스 전용", "관광버스", "대형버스", "버스주차장")
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
        grid, names = {}, {}
        for lot in lots:
            if lot.get("lat") is not None and lot.get("lon") is not None:
                grid.setdefault(cell(lot["lat"], lot["lon"]), []).append(lot)
            core = name_core(lot["name"])
            if lot.get("district") and len(core) >= 3 and not bus_only(lot["name"]):
                # 구 이름은 시·도마다 겹친다(서울 중구·부산 중구). 시·도까지 함께 본다.
                names.setdefault(
                    (region_from_address(lot["address"]), lot["district"], core), []
                ).append(lot)
        result = (lots, grid, names)
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
    _, grid, _ = load()
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


def district(address):
    """주소의 구·군·시 낱말 하나(광역·특별시·도 이름 다음)."""
    for word in str(address or "").split():
        if word.endswith(("특별시", "광역시", "특별자치시", "특별자치도", "도")) and len(word) > 2:
            continue
        if word.endswith(("구", "군", "시")):
            return word
    return None


def name_core(name):
    """이름 핵심: 괄호·주차장·공영·임시·노상·노외·건물·평면·지하 낱말과 띄어쓰기를 뺀다('성수2가3동(건물) 공영주차장(구)' → '성수2가3동')."""
    text = re.sub(r"\([^)]*\)", "", str(name or ""))
    text = re.sub(r"공영|주차장|임시|노상|노외|건물|평면|지하|\s", "", text)
    return text.casefold()


def bus_only(name):
    """버스 전용 주차장 이름인지. '승용'이 함께 있으면(버스·승용차 겸용) 아니다."""
    text = str(name or "")
    return "승용" not in text and any(word in text for word in BUS_ONLY_WORDS)


def by_name(name, address):
    """좌표가 없는 자료(서울 노외 주차장 등)를 같은 구 + 이름 핵심으로 찾는다. 한쪽 핵심이 다른 쪽을 품으면 같은 곳으로 본다(4글자 이상)."""
    _, _, names = load()
    region, gu, core = region_from_address(address), district(address), name_core(name)
    if not region or not gu or len(core) < 3:
        return None
    exact = names.get((region, gu, core))
    if exact:
        return exact[0]
    if len(core) >= 4:
        for (other_region, other_gu, other), lots in names.items():
            if (
                (other_region, other_gu) == (region, gu)
                and len(other) >= 4
                and (core in other or other in core)
            ):
                return lots[0]
    return None


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
        if not lot.get("extra_minutes") and lot["base_minutes"] <= 10 and lot["base_fee"]:
            # 추가 단위가 없고 기본 시간이 짧으면(서울 '5분 250원') 단위 요금이다.
            parts.append(f"{lot['base_minutes']}분당 {fee}")
        else:
            parts.append(f"기본 {lot['base_minutes']}분 {fee}")
    if lot.get("extra_minutes") and lot.get("extra_fee"):
        parts.append(f"추가 {lot['extra_minutes']}분당 {won(lot['extra_fee'])}")
    if lot.get("day_fee"):
        parts.append(f"1일 {won(lot['day_fee'])}")
    if lot.get("free_days"):
        parts.append(lot["free_days"])
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
    if start == end:
        # '00:00 00:00' 등. 서울 파일에서는 휴무·24시간·자료 없음 가운데 무엇인지 알 수 없어 비운다(모름).
        return None
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
    """주차장 칸에 붙일 공공데이터 정보. 서울 파일 행은 실시간 현황을 맞출 주차장 코드(_seoul_code)를 잠시 함께 싣는다(응답 전에 뺌)."""
    info = dict(
        fee=fee_text(lot),
        hours=hours_text(lot, visit),
        kind=lot.get("kind") or None,
        as_of=lot.get("as_of") or None,
        source=SOURCE,
    )
    if str(lot.get("id") or "").startswith("seoul-"):
        info["_seoul_code"] = lot["id"][len("seoul-") :]
    return info
