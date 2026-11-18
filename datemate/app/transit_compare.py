"""대중교통 구간의 지하철·버스 비교(TMAP 대중교통 API). 결과 화면에서 사용자가 단추를 눌렀을 때만 부른다.

왜: 대중교통 구간은 지하철·버스 구분 없는 추정이다(app/routes.py TRANSIT_*). 사용자가 '지하철이 편한지 버스가 편한지
시간·지도로 보고 골라 보고 싶다'고 했고(2026-11-18), 공급자는 TMAP 대중교통 API 로 정했다.

무엇: 코스의 대중교통 구간마다 TMAP 에 한 번 묻고, 받은 경로를 pathType 으로 지하철·버스·버스+지하철로 묶어
묶음마다 가장 빠른 경로 하나를 돌려준다. 코스(DB)·공유·인쇄에는 아무것도 쓰지 않는다(화면 미리보기 전용, 사용자 결정).

약관(2026-11-18 확인, https://transit.tmapmobility.com/terms · https://tmapapi.tmapmobility.com/terms.html):
  · "TMAP 대중교통 API 서비스를 이용하여 얻어진 데이터는 저장 후 24시간 이상 사용할 수 없습니다."
      → 캐시 CACHE_SECONDS(6시간) < 24시간. store.cache 의 기본 TTL 이 정확히 24시간이라 반드시 값을 넘긴다.
        결과를 코스·공유 자료에 넣지 않는다. 화면(static/transit-compare.js)도 23시간 지난 응답은 버린다.
  · "동일한 서비스를 위하여 다수의 프로젝트를 생성하여 사용하는 경우에는 불법 사용으로 간주" → 앱 키는 TMAP_TRANSIT_APP_KEY 하나.
  · 무료 하루 10건, 종량제 건당 0.88원(후불). 하루 상한 DAILY_LIMIT_ENV(기본 300건 ≈ 264원)로 비용을 막는다.
  · 출처 표시·다른 지도 위 표시·상업 이용에 관한 조항은 없었다. 그래도 화면에 'TMAP 대중교통 · 조회 시점 기준'을 밝힌다.

응답 형식(https://transit.tmapmobility.com/docs/routes): metaData.plan.itineraries[] 에
  totalTime·totalWalkTime(초), transferCount, pathType(1 지하철, 2 버스, 3 버스+지하철, 4~7 시외버스·기차·항공·해운),
  fare.regular.totalFare·currency.currencyCode, legs[].mode(WALK·BUS·SUBWAY…)·route(노선 이름)·sectionTime,
  legs[].passShape.linestring(대중교통 구간 좌표 "경도,위도 경도,위도"), legs[].steps[].linestring(도보 좌표).
  검증·파싱은 2026-10-29 에 키가 없어 뺐던 예전 어댑터(git 689176e^ app/route_providers.py)의 것을 다시 썼다.
  실제 응답으로는 아직 확인하지 못했다(키 발급 전). 키를 넣은 뒤 첫 조회에서 필드 이름을 확인할 것(문서 표 'lane'/예제 'Lane' 차이 등).
"""

import hashlib
import json
import math
import os
import time
from datetime import datetime, timedelta, timezone

import httpx

from . import store
from .leg_modes import endpoints, leg_mode
from .request_usage import cache_hit, measure
from .service_time import today
from .telemetry import observed_http

URL = "https://apis.openapi.sk.com/transit/routes"
KEY_ENV = "TMAP_TRANSIT_APP_KEY"
DAILY_LIMIT_ENV = "DATEMATE_TMAP_TRANSIT_CALLS_PER_DAY"
DAILY_LIMIT_DEFAULT = 300
# 약관 24시간보다 넉넉히 짧게. 같은 구간을 여러 사람이 비교해도 6시간 안에는 다시 부르지 않는다.
CACHE_SECONDS = 6 * 3600
# 화면이 응답을 버리는 시간(초). 서버 캐시에서 막 꺼낸 응답(최대 6시간 묵음)도 합쳐 24시간을 넘지 않게 17시간.
CLIENT_KEEP_SECONDS = 17 * 3600
# 한 번 비교에서 부르는 최대 구간 수(코스 최대 5곳 + 귀가 1 = 6).
MAX_LEGS = 6
MAX_PATH_POINTS = 2000
SOURCE = "TMAP 대중교통 · 조회 시점 기준이며 방문일 시간표·배차 대기·좌석은 보장하지 않아요."
# pathType → 화면 묶음. 4~7(시외버스·기차·항공·해운)은 데이트 코스 구간에 맞지 않아 뺀다.
KINDS = {1: "subway", 2: "bus", 3: "mixed"}
KIND_NAMES = {"subway": "지하철", "bus": "버스", "mixed": "버스+지하철"}
LEG_MODES = {"WALK": "walk", "BUS": "bus", "SUBWAY": "subway"}


def configured():
    return bool(os.getenv(KEY_ENV, "").strip())


def number(value):
    """음수·무한·참거짓이 아닌 숫자. 아니면 ValueError(그 구간은 unavailable)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("Invalid route number")
    return value


def linestring(text):
    """'127.01,37.5 127.02,37.51' → [[127.01,37.5],[127.02,37.51]]. 범위 밖·숫자 아닌 점은 버린다."""
    points = []
    for pair in str(text or "").split():
        try:
            x, y = (float(v) for v in pair.split(","))
        except ValueError:
            continue
        if math.isfinite(x) and math.isfinite(y) and -180 <= x <= 180 and -90 <= y <= 90:
            points.append([x, y])
    return points


def parse_itinerary(row):
    """경로 하나 → 화면용 요약. 지도에 그릴 path 는 구간 종류별 조각([{kind, points}]), 점은 모두 [경도, 위도]."""
    seconds, walk = number(row["totalTime"]), number(row["totalWalkTime"])
    if seconds <= 0 or walk > seconds:
        raise ValueError("Invalid transit time")
    fare = (row.get("fare") or {}).get("regular") or {}
    amount = fare.get("totalFare")
    # 요금은 원화로 확인될 때만(통화가 없거나 다르면 비워 둔다).
    per_person = number(amount) if amount is not None and (fare.get("currency") or {}).get("currencyCode") == "KRW" else None
    lines, path, budget = [], [], MAX_PATH_POINTS
    for leg in row.get("legs") or []:
        kind = LEG_MODES.get(leg.get("mode"))
        if kind is None:
            continue
        if kind != "walk" and leg.get("route"):
            lines.append(dict(mode=kind, name=str(leg["route"])[:40]))
        if kind == "walk":
            points = [p for step in leg.get("steps") or [] for p in linestring(step.get("linestring"))]
        else:
            points = linestring((leg.get("passShape") or {}).get("linestring"))
        points = points[:budget]
        budget -= len(points)
        if len(points) > 1:
            path.append(dict(kind=kind, points=points))
    return dict(minutes=math.ceil(seconds / 60), walk_minutes=math.ceil(walk / 60),
                transfers=int(number(row.get("transferCount", 0))), fare_per_person=per_person, lines=lines, path=path)


def parse(data):
    """TMAP 응답 → {'subway': 요약|None, 'bus': …, 'mixed': …}. 묶음마다 totalTime 가 가장 짧은 경로.
    읽을 수 없는 경로 하나는 건너뛰고, 쓸 수 있는 경로가 하나도 없으면 ValueError."""
    rows = data["metaData"]["plan"]["itineraries"]
    options = dict.fromkeys(KINDS.values())
    for row in rows:
        kind = KINDS.get(row.get("pathType"))
        if kind is None:
            continue
        try:
            option = parse_itinerary(row)
        except (ValueError, TypeError, KeyError):
            continue
        if options[kind] is None or option["minutes"] < options[kind]["minutes"]:
            options[kind] = option
    if not any(options.values()):
        raise ValueError("No usable itinerary")
    return options


def best_of(options):
    """있는 선택지 가운데 가장 빠른 것·덜 걷는 것·환승 적은 것의 이름(같으면 앞 순서: 지하철 → 버스 → 혼합)."""
    present = [(kind, o) for kind, o in options.items() if o]
    pick = lambda key: min(present, key=lambda item: key(item[1]))[0] if present else None
    return dict(fastest=pick(lambda o: o["minutes"]), least_walk=pick(lambda o: o["walk_minutes"]),
                fewest_transfers=pick(lambda o: o["transfers"]))


def search_time(plan, index):
    """그 구간을 떠나는 방문일 시각(yyyymmddhhmi). 방문일이 오늘보다 앞이면 None(지금 기준으로 조회)."""
    c = plan["conditions"]
    try:
        day = datetime.strptime(str(c["visit_date"]), "%Y-%m-%d").date()
    except (KeyError, ValueError):
        return None
    if day < today():
        return None
    timeline = plan.get("timeline") or []
    clock = c.get("start") if index == 0 else (timeline[index - 1].get("departure") if index - 1 < len(timeline) else None)
    try:
        hour, minute = (int(v) for v in str(clock).split(":"))
    except (ValueError, AttributeError):
        return None
    minute -= minute % 10  # 캐시가 10분 단위로 같은 조회를 나눠 쓰게.
    return f"{day:%Y%m%d}{hour:02d}{minute:02d}"


def cache_key(a, b, when):
    signature = json.dumps([round(a["lat"], 5), round(a["lon"], 5), round(b["lat"], 5), round(b["lon"], 5), when],
                           separators=(",", ":"))
    return "tmap-transit-v1:" + hashlib.sha256(signature.encode()).hexdigest()


def reserve_daily_call():
    limit = max(1, int(os.getenv(DAILY_LIMIT_ENV, str(DAILY_LIMIT_DEFAULT)) or DAILY_LIMIT_DEFAULT))
    # 하루 구간(UTC 일). 지난 날의 기록은 app/maintenance.py 가 지운다('tmap-transit:%').
    return store.reserve_budget([("tmap-transit:day", limit)], int(time.time() // 86400))


def lookup(a, b, when):
    """(options, status). status: available·unavailable·limited. 성공만 캐시한다."""
    key = cache_key(a, b, when)
    hit = store.cached(key)
    if hit:
        cache_hit("transit_compare")
        return hit, "available"
    if not reserve_daily_call():
        return None, "limited"
    body = dict(startX=str(a["lon"]), startY=str(a["lat"]), endX=str(b["lon"]), endY=str(b["lat"]), count=10, lang=0, format="json")
    if when:
        body["searchDttm"] = when
    try:
        response = observed_http(httpx.post, URL, json=body, headers={"appKey": os.environ[KEY_ENV], "accept": "application/json"},
                                 timeout=8, follow_redirects=False)
        response.raise_for_status()
        options = parse(response.json())
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        return None, "unavailable"
    store.cache(key, options, CACHE_SECONDS)
    return options, "available"


def points(plan):
    """구간마다 (출발 점, 도착 점). endpoints() 와 같은 순서(출발지 → 장소들 → 귀가지)."""
    c = plan["conditions"]
    spots = {"origin": c.get("origin"), "home": c.get("home")}
    spots.update({p["id"]: p for p in plan["places"]})
    return [(spots.get(start), spots.get(end)) for start, end in endpoints(plan)]


def compare(plan):
    """GET /api/plans/{id}/transit-compare 응답. 코스는 읽기만 한다."""
    base = dict(legs=[], source=SOURCE, expires_in=CLIENT_KEEP_SECONDS, checked_at=None)
    if plan["conditions"].get("mode") != "real":
        return dict(base, status="demo", message="가상 장소 데모에서는 실제 대중교통 경로를 찾지 않아요.")
    indexes = [i for i in range(len(plan.get("legs") or [])) if leg_mode(plan, i) == "transit"][:MAX_LEGS]
    if not indexes:
        return dict(base, status="not_transit", message="대중교통 구간이 없어요.")
    if not configured():
        return dict(base, status="key_missing", message="대중교통 경로 비교가 아직 연결되지 않았어요.")
    pairs = points(plan)
    legs = []
    with measure(limit=len(indexes)):
        for i in indexes:
            a, b = pairs[i]
            leg = plan["legs"][i]
            row = dict(index=i, origin=leg.get("origin"), destination=leg.get("destination"), estimate_minutes=leg.get("minutes"),
                       options=dict.fromkeys(KINDS.values()), best={})
            if not (a and b and all(isinstance(p.get(k), (int, float)) for p in (a, b) for k in ("lat", "lon"))):
                legs.append(dict(row, status="unavailable"))
                continue
            options, status = lookup(a, b, search_time(plan, i))
            legs.append(dict(row, status=status, **(dict(options=options, best=best_of(options)) if options else {})))
    found = [leg for leg in legs if leg["status"] == "available"]
    status = "available" if found else "limited" if any(leg["status"] == "limited" for leg in legs) else "unavailable"
    messages = {"limited": "오늘 대중교통 비교 한도를 다 썼어요. 내일 다시 시도해 주세요.",
                "unavailable": "대중교통 경로를 찾지 못했어요. 잠시 후 다시 시도해 주세요."}
    return dict(base, status=status, legs=legs, message=messages.get(status, ""),
                checked_at=datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M"))
