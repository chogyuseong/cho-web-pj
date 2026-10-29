"""TMAP walking/transit adapters. Missing keys never produce verified routes."""

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from urllib.parse import quote
import httpx
from . import store
from .telemetry import observed_http
from .request_usage import cache_hit


def configured(mode):
    return bool(
        os.getenv(
            {"walk": "TMAP_APP_KEY", "transit": "TMAP_TRANSIT_APP_KEY"}.get(
                mode, "DATEMATE_UNUSED_ROUTE_KEY"
            ),
            "",
        )
    )


def number(value):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError("Invalid route number")
    return value


def coordinates(values):
    return [
        [float(x), float(y)]
        for x, y in values
        if isinstance(x, (int, float))
        and isinstance(y, (int, float))
        and math.isfinite(x)
        and math.isfinite(y)
        and -180 <= x <= 180
        and -90 <= y <= 90
    ]


def parse_walk(data):
    features = data["features"]
    summary = next(f["properties"] for f in features if "totalTime" in f.get("properties", {}))
    seconds = number(summary["totalTime"])
    meters = number(summary["totalDistance"])
    if seconds <= 0:
        raise ValueError("Empty route")
    path = []
    for feature in features[:2000]:
        geometry = feature.get("geometry", {})
        if geometry.get("type") == "LineString":
            rows = geometry.get("coordinates", [])
            if all(isinstance(x, list) and len(x) == 2 for x in rows):
                path.extend(coordinates(rows))
    return dict(
        minutes=math.ceil(seconds / 60),
        walking=math.ceil(seconds / 60),
        distance_km=meters / 1000,
        cost=0,
        path=path[:10000],
        transfers=0,
        source="TMAP 보행자 경로 · 조회 시점 기준, 방문일 현장 상황 미검증",
    )


def parse_transit(data):
    rows = data["metaData"]["plan"]["itineraries"]
    route = min(rows, key=lambda row: number(row["totalTime"]))
    seconds = number(route["totalTime"])
    walk = number(route["totalWalkTime"])
    if seconds <= 0 or walk > seconds:
        raise ValueError("Invalid transit time")
    fare = route.get("fare", {}).get("regular", {})
    amount = fare.get("totalFare")
    currency = fare.get("currency", {}).get("currencyCode")
    amount = number(amount) if amount is not None and currency == "KRW" else None
    return dict(
        minutes=math.ceil(seconds / 60),
        walking=math.ceil(walk / 60),
        distance_km=number(route["totalDistance"]) / 1000,
        cost=None,
        fare_per_person=amount,
        transfers=int(number(route["transferCount"])),
        path=[],
        source="TMAP 대중교통 경로 · 조회 시점 기준, 방문일 시간표·좌석·대기 보장 아님",
    )


def route(a, b, mode, people):
    if not configured(mode):
        return dict(
            status="unavailable", failure_code="key_missing", source="도보·대중교통 경로 키 미설정"
        )
    signature = json.dumps([mode, a["lat"], a["lon"], b["lat"], b["lon"]], separators=(",", ":"))
    key = "tmap-route-v1:" + hashlib.sha256(signature.encode()).hexdigest()
    result = store.cached(key)
    if result:
        cache_hit()
    if not result:
        try:
            body = dict(startX=a["lon"], startY=a["lat"], endX=b["lon"], endY=b["lat"])
            if mode == "walk":
                body.update(
                    startName=quote("출발"),
                    endName=quote("도착"),
                    reqCoordType="WGS84GEO",
                    resCoordType="WGS84GEO",
                )
                response = observed_http(
                    httpx.post,
                    "https://apis.openapi.sk.com/tmap/routes/pedestrian",
                    params={"version": "1"},
                    json=body,
                    headers={"appKey": os.environ["TMAP_APP_KEY"]},
                    timeout=8,
                    follow_redirects=False,
                )
                response.raise_for_status()
                result = parse_walk(response.json())
            else:
                body.update(count=1, lang=0, format="json")
                response = observed_http(
                    httpx.post,
                    "https://apis.openapi.sk.com/transit/routes",
                    json=body,
                    headers={"appKey": os.environ["TMAP_TRANSIT_APP_KEY"]},
                    timeout=8,
                    follow_redirects=False,
                )
                response.raise_for_status()
                result = parse_transit(response.json())
            result.update(status="api", checked_at=datetime.now(timezone.utc).isoformat())
            store.cache(key, result, 300)
        except (httpx.HTTPError, ValueError, TypeError, KeyError, StopIteration):
            return dict(
                status="unavailable",
                failure_code="provider_failed",
                source="실제 경로 조회 실패 · 추정과 구분해 확인해 주세요.",
            )
    result = dict(result)
    if mode == "transit":
        result["cost"] = (
            result["fare_per_person"] * people if result["fare_per_person"] is not None else None
        )
    return result
