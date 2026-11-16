"""서울시 공영주차장 실시간 주차 대수(서울 열린데이터광장 GetParkingInfo).

서울시가 운영하는 '(시)' 공영주차장 약 120곳만 실시간 정보가 있다(2026-11-16 응답 list_total_count 122).
한 번 호출로 전부 받아 3분 캐시하고, 주차장 코드(PKLT_CD)로 data/public_parking.json 의 서울 행(id 'seoul-<코드>')과 맞춘다.
PRK_STTS_YN 이 '1'(20분 안에 받은 자료)인 곳만 쓴다. 키(SEOUL_OPEN_API_KEY)가 없거나 호출이 실패하면 빈 자료로 동작한다.
개발에 쓴 컴퓨터의 네트워크에서는 openapi.seoul.go.kr 에 연결되지 않아, 응답 모양은 사용자가 휴대폰으로 받은 실제 응답으로 확인했다.
"""

import os
from datetime import datetime

import httpx

from . import store
from .telemetry import observed_http

URL = "http://openapi.seoul.go.kr:8088/{key}/json/GetParkingInfo/1/1000/"
CACHE_KEY = "seoul-parking-live-v1"
CACHE_SECONDS = 180
FAILED_SECONDS = 60
TIMEOUT = 4


def enabled():
    return bool(os.environ.get("SEOUL_OPEN_API_KEY", "").strip())


def number(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def parse(data):
    """응답 → {주차장 코드: dict(now, total, updated)}. 오래됐거나 숫자가 이상한 행은 뺀다."""
    rows = ((data or {}).get("GetParkingInfo") or {}).get("row") or []
    live = {}
    for row in rows:
        if not isinstance(row, dict) or str(row.get("PRK_STTS_YN")) != "1":
            continue
        code, now, total = str(row.get("PKLT_CD") or "").strip(), number(row.get("NOW_PRK_VHCL_CNT")), number(row.get("TPKCT"))
        if not code or now is None or not total or now < 0:
            continue
        updated = str(row.get("NOW_PRK_VHCL_UPDT_TM") or "").strip()
        try:
            datetime.strptime(updated, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            updated = None
        live[code] = dict(now=min(now, total), total=total, updated=updated)
    return live


def live_counts():
    """{주차장 코드: dict(now, total, updated)}. 실패하면 빈 dict(1분 동안 다시 부르지 않음)."""
    if not enabled():
        return {}
    cached = store.cached(CACHE_KEY)
    if cached is not None:
        return cached
    try:
        url = URL.format(key=os.environ["SEOUL_OPEN_API_KEY"].strip())
        with httpx.Client(timeout=TIMEOUT) as client:
            response = observed_http(client.get, url)
            response.raise_for_status()
            live = parse(response.json())
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        store.cache(CACHE_KEY, {}, FAILED_SECONDS)
        return {}
    store.cache(CACHE_KEY, live, CACHE_SECONDS if live else FAILED_SECONDS)
    return live
