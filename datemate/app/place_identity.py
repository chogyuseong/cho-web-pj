"""같은 업체 확인을 공공 자료로 한다(2026-11-20, docs/naver-terms-stage2-design.ko.md 3.6(b)).

카드의 '위치' 줄(static/plan-evidence.js identityEvidence)이 이 결과를 보여 준다. 예전에는 네이버 지역 검색 결과로
'같은 이름·400m·하나뿐'을 계산해 '위치 확인됨'으로 표시했는데, 검색 결과에서 만든 판정을 우리 표시로 쓰는 것이
네이버 검색 API 특약 2.2·2.3 과 맞지 않아 공공데이터포털 자료 둘로 바꿨다(이용허락범위 제한 없음, 저장·가공 가능).

자료와 판정
  1) 소상공인시장진흥공단 상가(상권)정보 storeListInRadius — 우리 좌표 반경 STORE_RADIUS_M(200m) 안의 업소 목록.
     이름이 같은 업소(띄어쓰기·기호 무시, 지점 낱말을 뗀 이름도 봄)가 서로 다른 주소로 정확히 한 곳이면 located(위치 확인).
     응답 머리의 stdrYm(자료 기준 연월)을 함께 보여 준다.
  2) 행정안전부 지방행정 인허가 일반음식점·휴게음식점 — 음식점·카페(카페·미식, meal)만. 도로명 주소가 같은 인허가를
     서버 쪽 조건(cond[ROAD_NM_ADDR::LIKE])으로 찾고, 그중 이름이 맞는 것의 영업상태를 본다.
     '영업/정상'이 하나라도 있으면 open(영업 중), 맞는 인허가가 모두 폐업이면 closed(폐업으로 등록됨), 그 밖은 판정 없음.
     전국 목록을 훑지 않는다(한 번에 주소 하나, 최대 100건). 좌표(CRD_INFO_X·Y)는 EPSG:5174 라 app/korea_tm.py 로 바꿔
     우리 좌표에서 MAX_KM(0.4km) 넘게 떨어진 인허가는 뺀다(같은 도로명·번호가 다른 시·군·구에도 있기 때문).
  인허가 판정이 있으면 그것을, 없으면 상가정보 판정을 보여 준다. 둘 다 없으면 판정 없이 '네이버 지도에서 확인' 링크만 나온다.

응답이 느리다
  인허가 API 는 2026-11-20 측정에서 한 번에 10~54초가 걸리고 60초에서 게이트웨이 시간 초과(504)가 자주 났다.
  그래서 사용자 요청은 공공 API 를 부르지 않는다. verify_identity 는 저장해 둔 판정(store 캐시)만 읽고, 없으면 배경 일꾼에
  맡긴 뒤 pending=True 로 답한다. 화면은 링크만 먼저 그리고 /api/places/{id}/identity 를 몇 번 다시 물어 판정이 생기면 바꾼다.
  배경 일꾼은 한 번에 한 곳만 조회하고(가장 최근에 본 장소부터, 대기 QUEUE_MAX 곳까지), 실패하면 RETRY_SECONDS 동안 다시 시도하지 않는다.
  키가 없거나, 실패하거나, 자료에 없으면 판정 없음으로 남고 화면은 막히지 않는다.

네이버 검색 장소에는 쓰지 않는다
  지역 검색으로 찾은 장소(naver_terms.is_naver_place)의 이름·좌표를 다른 계산의 입력으로 쓰지 않으려고(특약 2.1 의 엄격한 읽기)
  그런 장소는 조회하지 않고 판정 없음으로 둔다.

키: 공공데이터포털 계정 키 하나(TOUR_API_KEY)로 TourAPI·상가정보·인허가를 모두 부른다. 로그·캐시에 키를 남기지 않는다.
캐시: 판정과 기준 시점만 store 캐시에 둔다(업소 목록은 저장하지 않음). 찾음 FOUND_SECONDS, 없음 MISS_SECONDS.
함께 바꿀 값: STORE_RADIUS_M 을 바꾸면 static/plan-evidence.js 의 '200m' 문구도 고친다.
"""

import hashlib
import logging
import os
import re
import threading
from collections import OrderedDict
from datetime import date, datetime, timezone

import httpx

from . import store
from .routes import distance
from .telemetry import observed_http

STORE_URL = "https://apis.data.go.kr/B553077/api/open/sdsc2/storeListInRadius"
LICENSE_URLS = {
    "일반음식점": "https://apis.data.go.kr/1741000/general_restaurants/info",
    "휴게음식점": "https://apis.data.go.kr/1741000/rest_cafes/info",
}
STORE_RADIUS_M = 200
STORE_PAGE_ROWS = 1000
STORE_MAX_PAGES = 3
STORE_TIMEOUT = 10
MAX_KM = 0.4
LICENSE_ROWS = 100
# 게이트웨이가 60초에 끊는다. 그보다 조금 짧게 기다린다.
LICENSE_TIMEOUT = 58
FOUND_SECONDS = 7 * 86400
MISS_SECONDS = 3 * 86400
RETRY_SECONDS = 1800
QUEUE_MAX = 40
CACHE_PREFIX = "public-identity-v1:"
OPEN_CODE, CLOSED_CODE = "01", "03"
_CORPORATE = re.compile(r"주식회사|유한회사|\(주\)|㈜|\(유\)")
_ROAD = re.compile(r"([가-힣A-Za-z0-9·.]+(?:대로|로|길))\s*(\d+(?:-\d+)?)(?![\d-])")

log = logging.getLogger(__name__)


def _key():
    """공공데이터포털 계정 키. .env 에 작은따옴표로 감싸 둔 경우도 받는다."""
    return os.getenv("TOUR_API_KEY", "").strip().strip("'\"")


def _compact(text):
    return re.sub(r"[\W_]+", "", _CORPORATE.sub(" ", str(text or ""))).casefold()


def _names(place):
    from .course_search import without_branch

    names = {_compact(place.get("name")), _compact(without_branch(place.get("name") or ""))}
    return {n for n in names if len(n) >= 2}


def applies(place):
    """공공 자료로 확인해 볼 장소인지: 실제 장소이고 이름·좌표가 있으며 네이버 검색 장소가 아니다."""
    from .naver_terms import is_naver_place

    return bool(
        isinstance(place, dict)
        and not place.get("demo")
        and place.get("name")
        and place.get("lat") is not None
        and place.get("lon") is not None
        and not is_naver_place(place)
    )


def license_kinds(place):
    """인허가 자료를 볼 순서. 음식점·카페가 아니면 빈 목록(인허가 자료를 보지 않음)."""
    if not (place.get("category") == "카페·미식" or place.get("meal")):
        return []
    return ["일반음식점", "휴게음식점"] if place.get("meal") else ["휴게음식점", "일반음식점"]


def road_key(address):
    """주소에서 (도로명, 건물번호). '서울 중구 명동10길 29 (명동2가)' → ('명동10길', '29'). 도로명 주소가 아니면 None."""
    import unicodedata

    text = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(address or ""))).strip()
    text = re.sub(r"((?:대로|로))\s+(\d+(?:번)?길)", r"\1\2", text)
    match = _ROAD.search(text)
    return (match[1], match[2]) if match else None


def road_query(address):
    """인허가 API 의 도로명 주소 조건에 넣을 조각. 앞의 시·군·구가 있으면 함께 넣어 다른 도시의 같은 도로명을 줄인다."""
    import unicodedata

    text = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(address or ""))).strip()
    text = re.sub(r"((?:대로|로))\s+(\d+(?:번)?길)", r"\1\2", text)
    match = _ROAD.search(text)
    if not match:
        return None
    before = text[: match.start()].split()
    district = before[-1] if before and re.fullmatch(r"[가-힣]{1,8}(?:구|군|시)", before[-1]) else ""
    return " ".join(part for part in (district, match[1], match[2]) if part)


def cache_key(place, part):
    digest = hashlib.sha256(
        repr([place.get("id"), place.get("name"), place.get("address"), place.get("lat"), place.get("lon")]).encode()
    ).hexdigest()
    return f"{CACHE_PREFIX}{part}:{digest}"


def _now():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------- 상가정보


def store_matches(place, rows):
    """상가정보 업소 목록에서 이름이 같고 MAX_KM 안인 업소의 서로 다른 주소 수."""
    from .course_search import without_branch

    names = _names(place)
    addresses = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        name, branch = str(row.get("bizesNm") or ""), str(row.get("brchNm") or "")
        found = {_compact(name), _compact(name + branch), _compact(without_branch(name))}
        if not (found & names):
            continue
        try:
            point = dict(lat=float(row["lat"]), lon=float(row["lon"]))
        except (KeyError, TypeError, ValueError):
            continue
        if distance(place, point) <= MAX_KM:
            addresses.add(str(row.get("rdnmAdr") or row.get("lnoAdr") or (round(point["lat"], 5), round(point["lon"], 5))))
    return len(addresses)


def store_lookup(place, client):
    """dict(status=located·not_found, data_month, checked_at) 또는 실패하면 None."""
    rows, month = [], None
    for page in range(1, STORE_MAX_PAGES + 1):
        response = observed_http(
            client.get,
            STORE_URL,
            params=dict(
                serviceKey=_key(),
                radius=STORE_RADIUS_M,
                cx=place["lon"],
                cy=place["lat"],
                type="json",
                numOfRows=STORE_PAGE_ROWS,
                pageNo=page,
            ),
            timeout=STORE_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        header = data.get("header") or {}
        code = str(header.get("resultCode") or "")
        if code == "03":  # NODATA_ERROR: 반경 안에 업소가 없다.
            break
        if code != "00":
            raise ValueError("provider_error")
        body = data.get("body") or {}
        items = body.get("items") or []
        if not isinstance(items, list):
            raise ValueError("invalid_response")
        rows.extend(items)
        month = month or str(header.get("stdrYm") or "") or None
        if len(rows) >= int(body.get("totalCount") or 0) or not items:
            break
    else:
        # 반경 안 업소가 너무 많아 다 보지 못했다. 하나뿐인지 알 수 없으므로 판정하지 않는다.
        return dict(status="not_found", data_month=month, checked_at=_now())
    located = store_matches(place, rows) == 1
    return dict(status="located" if located else "not_found", data_month=month, checked_at=_now())


# ---------------------------------------------------------------- 인허가


def _license_rows(data):
    body = (data.get("response") or {}).get("body") or {}
    header = (data.get("response") or {}).get("header") or {}
    if str(header.get("resultCode") or "") not in ("0", "00"):
        raise ValueError("provider_error")
    items = (body.get("items") or {}).get("item") if isinstance(body.get("items"), dict) else body.get("items")
    rows = items if isinstance(items, list) else [items] if isinstance(items, dict) else []
    return [row for row in rows if isinstance(row, dict)], int(body.get("totalCount") or 0)


def _day(value):
    """'2026-03-02', '20260302', '2026-06-02 18:02:54' → '2026-03-02'. 읽을 수 없으면 None."""
    digits = re.sub(r"\D", "", str(value or ""))[:8]
    try:
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8])).isoformat() if len(digits) == 8 else None
    except ValueError:
        return None


def license_matches(place, rows):
    """인허가 행 중 우리 장소와 같은 업소: 도로명·건물번호가 같고, 이름이 같거나(지점 낱말·법인 표기 무시) 한쪽이 다른 쪽을 품고(3자 이상),
    좌표가 있으면 MAX_KM 안."""
    from .korea_tm import to_wgs84

    ours = road_key(place.get("address"))
    names = _names(place)
    found = []
    for row in rows:
        if not ours or road_key(row.get("ROAD_NM_ADDR")) != ours:
            continue
        name = _compact(row.get("BPLC_NM"))
        if not name or not any(name == n or (min(len(name), len(n)) >= 3 and (n in name or name in n)) for n in names):
            continue
        point = to_wgs84(row.get("CRD_INFO_X"), row.get("CRD_INFO_Y"))
        if point and distance(place, dict(lat=point[0], lon=point[1])) > MAX_KM:
            continue
        found.append(row)
    return found


def license_verdict(place, rows, kind):
    """dict(status=open·closed, …) 또는 맞는 인허가가 없거나 영업·폐업이 아니면 None."""
    matched = license_matches(place, rows)
    if not matched:
        return None
    current = [row for row in matched if str(row.get("SALS_STTS_CD") or "") == OPEN_CODE]
    if current:
        changed = max((_day(row.get("LAST_MDFCN_PNT")) or "" for row in current), default="") or None
        return dict(status="open", kind=kind, modified_on=changed, checked_at=_now())
    if all(str(row.get("SALS_STTS_CD") or "") == CLOSED_CODE for row in matched):
        closed = max((_day(row.get("CLSBIZ_YMD")) or "" for row in matched), default="") or None
        return dict(status="closed", kind=kind, closed_on=closed, checked_at=_now())
    return None


def license_lookup(place, client):
    """dict(status=open·closed·not_found·not_applicable, …) 또는 한 곳이라도 조회에 실패해 결론을 못 내면 None."""
    kinds = license_kinds(place)
    query = road_query(place.get("address"))
    if not kinds or not query:
        return dict(status="not_applicable", checked_at=_now())
    from .course_search import without_branch

    failed = False
    for kind in kinds:
        try:
            params = {
                "serviceKey": _key(),
                "pageNo": 1,
                "numOfRows": LICENSE_ROWS,
                "returnType": "json",
                "cond[ROAD_NM_ADDR::LIKE]": query,
            }
            response = observed_http(client.get, LICENSE_URLS[kind], hold_slot=False, params=params, timeout=LICENSE_TIMEOUT)
            response.raise_for_status()
            rows, total = _license_rows(response.json())
            if total > len(rows):
                # 큰 건물은 인허가가 100건을 넘는다. 이름 조건을 더해 한 번 더 찾는다.
                params["cond[BPLC_NM::LIKE]"] = without_branch(place["name"])
                response = observed_http(client.get, LICENSE_URLS[kind], hold_slot=False, params=params, timeout=LICENSE_TIMEOUT)
                response.raise_for_status()
                rows, _ = _license_rows(response.json())
        except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
            failed = True
            continue
        verdict = license_verdict(place, rows, kind)
        if verdict:
            return verdict
    return None if failed else dict(status="not_found", checked_at=_now())


# ---------------------------------------------------------------- 배경 조회

_queue = OrderedDict()
_queue_lock = threading.Lock()
_worker = None


def _ttl(result):
    return FOUND_SECONDS if result["status"] in ("located", "open", "closed") else MISS_SECONDS


def lookup(place):
    """공공 API 를 불러 판정을 캐시에 넣는다. 배경 일꾼이 부른다(사용자 요청 안에서 부르지 않는다)."""
    wanted = {
        part: fn
        for part, fn in (("store", store_lookup), ("license", license_lookup))
        if not store.cached(cache_key(place, part)) and not store.cached(cache_key(place, part + "-retry"))
    }
    if not wanted:
        return
    with httpx.Client() as client:
        for part, fn in wanted.items():
            try:
                result = fn(place, client)
            except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
                result = None
            if result is None:
                # 실패는 판정으로 남기지 않는다. 잠시 뒤 다시 볼 수 있게 표시만 둔다.
                store.cache(cache_key(place, part + "-retry"), True, RETRY_SECONDS)
            else:
                store.cache(cache_key(place, part), result, _ttl(result))


def _work():
    global _worker
    while True:
        with _queue_lock:
            if not _queue:
                _worker = None
                return
            _, place = _queue.popitem(last=True)
        try:
            lookup(place)
        except Exception:  # 배경 조회 실패가 일꾼을 멈추지 않게 한다(판정 없음으로 남음).
            log.warning("public_identity_lookup_failed")


def _start_worker():
    """대기열을 비울 일꾼 스레드를 띄운다(이미 돌고 있으면 그대로). 테스트는 이 함수를 막고 _work 를 직접 부른다(tests/conftest.py)."""
    global _worker
    with _queue_lock:
        if _worker is None and _queue:
            _worker = threading.Thread(target=_work, name="public-identity", daemon=True)
            _worker.start()


def enqueue(place):
    """배경 조회 대기열에 넣는다(같은 장소는 한 번만, 가장 최근 것부터 처리, 넘치면 가장 오래된 것을 버림)."""
    fields = ("id", "name", "address", "lat", "lon", "category", "meal")
    with _queue_lock:
        key = cache_key(place, "queue")
        _queue.pop(key, None)
        _queue[key] = {field: place.get(field) for field in fields}
        while len(_queue) > QUEUE_MAX:
            _queue.popitem(last=False)
    _start_worker()


# ---------------------------------------------------------------- 화면용 판정


def _age_days(checked_at):
    try:
        then = datetime.fromisoformat(str(checked_at))
    except ValueError:
        return None
    return max(0, (datetime.now(timezone.utc) - then).days)


def verify_identity(place):
    """화면에 줄 판정. 저장된 판정만 읽는다(공공 API 를 부르지 않음). 판정이 아직 없으면 배경 조회를 맡기고 pending=True.

    status: open(영업 중, 인허가) · closed(폐업으로 등록됨, 인허가) · located(위치 확인, 상가정보) · unknown(판정 없음 — 링크만).
    unknown 의 reason: checking(조회 중) · not_found(자료에서 찾지 못함 — 조회가 끝까지 성공했을 때만) · unavailable(조회 실패,
    RETRY_SECONDS 뒤 다시 조회) · key_missing · not_applicable.
    """
    unknown = dict(status="unknown", pending=False, source=None)
    if not applies(place):
        return dict(unknown, reason="not_applicable")
    if not _key():
        return dict(unknown, reason="key_missing")
    found = store.cached_many([cache_key(place, part) for part in ("store", "license", "store-retry", "license-retry")])
    shop, permit = found.get(cache_key(place, "store")), found.get(cache_key(place, "license"))
    waiting = [
        part
        for part, hit in (("store", shop), ("license", permit))
        if hit is None and cache_key(place, part + "-retry") not in found
    ]
    if waiting:
        enqueue(place)
    pending = bool(waiting)
    if permit and permit.get("status") in ("open", "closed"):
        return dict(
            status=permit["status"],
            pending=False,
            source="license",
            source_label="행정안전부 지방행정 인허가 자료",
            license_kind=permit.get("kind"),
            closed_on=permit.get("closed_on"),
            modified_on=permit.get("modified_on"),
            checked_at=permit.get("checked_at"),
            age_days=_age_days(permit.get("checked_at")),
        )
    if shop and shop.get("status") == "located":
        return dict(
            status="located",
            pending=pending,
            source="store_info",
            source_label="소상공인시장진흥공단 상가(상권)정보",
            data_month=shop.get("data_month"),
            radius_m=STORE_RADIUS_M,
            checked_at=shop.get("checked_at"),
            age_days=_age_days(shop.get("checked_at")),
        )
    # 조회가 실패해 다시 시도를 기다리는 자료가 있으면 '없음'이 아니라 '연결 실패'(unavailable)로 답한다. 2026-11-20 운영 키가 어긋났던 동안
    # 실패한 조회가 not_found 로 보였다(금호미술관·국립현대미술관 서울). 판정 저장은 그때도 하지 않았다(실패는 RETRY_SECONDS 표시만).
    failed = [part for part, hit in (("store", shop), ("license", permit)) if hit is None and cache_key(place, part + "-retry") in found]
    return dict(unknown, pending=pending, reason="checking" if pending else "unavailable" if failed else "not_found")
