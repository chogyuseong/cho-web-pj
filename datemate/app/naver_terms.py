"""네이버 검색 API 특약(2026-09 개정) 1단계 조치: AI 입력 차단과 저장 코스의 이력 보관 기한.

- 특약 2.3: 검색 결과와 그 가공물·파생물을 AI 입력·학습·평가·노출에 쓸 수 없다.
  → ai_safe_plan()/redact_text() 로 LLM 근거(app/rag.py)에서 네이버 유래 필드와 문자열을 뺀다.
  → is_naver_place() 로 색인(app/indexing.py)에서 네이버 유래 장소를 뺀다.
- 특약 2.4: 서버 보관은 이력 조회 목적이면 최대 21일.
  → strip_plan() 으로 저장 코스(plans) 안의 네이버 유래 필드를 지운다(코스 자체는 남김). maintenance 가 매시간 부른다.
- 사용자 공용 캐시를 쓰지 않는 개인화 보관(24시간·새 질의 시까지)은 app/naver_cache.py.

네이버 유래로 보는 것:
  · 장소: id 가 discovered:·food:naver- 로 시작하거나, source_type 에 '네이버'가 있거나, license 가 '검색 결과…' 인 장소
    (네이버 지역 검색으로 찾은 장소 전체 — 이름·주소·좌표·업종이 모두 검색 결과다).
  · 코스: course_search(블로그 검색 글·선정 근거·발견 진단), blog_score, 이유 문장의 '네이버 코스 검색 n위 글' 부분.
  · 비용: price_evidence(블로그 요약 조각), 블로그 가격(web_reference·naver_menu)의 출처 링크·근거 문장.
"""

import copy
import json
import re
import time

HISTORY_MAX_SECONDS = 21 * 86400
NAVER_ID_PREFIXES = ("discovered:", "food:naver-")
NAVER_LICENSES = ("검색 결과", "검색 결과와 원문 인용")
NAVER_PRICE_KINDS = ("web_reference", "naver_menu")
EXPIRED_NAME = "보관 기간이 지난 검색 장소"
AI_PLACEHOLDER = "네이버 검색 장소"
EXPIRED_PRICE_BASIS = "블로그 검색에서 읽은 가격은 보관 기간(21일)이 지나 지웠어요. 가격은 확인 필요예요."
# 21일이 지나도 남기는 장소 필드(우리가 계산했거나 일정 계산에 필요한 값). 이름·주소·업종·설명·링크·좌표는 지운다.
# 좌표(lat·lon)는 지역 검색 결과라 21일 뒤 None 으로 둔다(2026-11-20 후속 조치). 일정 시간·이동 시간은 이미 계산한 값이 남는다.
KEEP_PLACE_FIELDS = (
    "id", "region", "category", "themes", "meal", "demo", "stay", "stay_basis",
    "price", "price_unit", "price_status", "setting", "hours", "closed_days", "breaks", "last_entry",
    "reservation", "rating", "photos", "videos",
)  # fmt: skip
# AI 근거로 보낼 때는 가격도 뺀다(검색 결과의 파생물).
AI_DROP_PLACE_FIELDS = ("lat", "lon", "price", "price_status")
REASON_PREFIX = re.compile(r"^네이버 코스 검색 [^·]*?에 등장 · ")

# 출발지·귀가지 이름. 지역 검색(장소 이름으로 찾기)으로 고른 출발지는 이름이 그 결과의 도로명·지번 주소다(app/geocoding.search_places).
# 저장 코스에는 어디서 왔는지 남지 않아(주소 검색의 지오코딩 결과와 모양이 같음) 화면이 만든 이름 모양이 아니면 모두 바꾼다.
# 화면이 만든 이름: 동네 칩('… 지역 중심'), 동네 중심('성수동 중심'), 현재 위치('… · 현재 위치'), 지도에서 고르기('… · 지도에서 선택',
# '지도에서 선택한 …'), 축제·팝업 거점('… 주변'), 구 대표 위치('… 대표 위치 · 주소', 지오코딩), 데모 출발점.
EXPIRED_ORIGIN_NAME = "보관 기간이 지난 출발지 주소"
EXPIRED_HOME_NAME = "보관 기간이 지난 귀가지 주소"
AI_ORIGIN_NAME = "출발지"
AI_HOME_NAME = "귀가지"
SAFE_POINT_NAMES = ("데모 출발점",)
SAFE_POINT_SUFFIXES = (" · 현재 위치", " · 지도에서 선택", " 중심", " 주변")
SAFE_POINT_PREFIXES = ("지도에서 선택한 ",)


def is_naver_place(place):
    if not isinstance(place, dict):
        return False
    pid = str(place.get("id") or "")
    return (
        pid.startswith(NAVER_ID_PREFIXES)
        or "네이버" in str(place.get("source_type") or "")
        or place.get("license") in NAVER_LICENSES
        or bool(place.get("naver_expired"))
        or bool(place.get("naver_result"))
    )


def _strings(place):
    out = []
    for key in ("name", "address", "lot_address", "description", "cuisine", "recognition"):
        value = place.get(key)
        if isinstance(value, str) and len(value.strip()) >= 2:
            out.append(value.strip())
    for value in place.get("search_aliases") or []:
        if isinstance(value, str) and len(value.strip()) >= 2:
            out.append(value.strip())
    # 태그 중 네이버 업종 분류('음식점>한식')만. 'cafe'·'walk' 같은 우리 태그는 조건 값과 겹치므로 넣지 않는다.
    for value in place.get("tags") or []:
        if isinstance(value, str) and ">" in value:
            out.append(value.strip())
    return out


def safe_point_name(name):
    """화면이 만든 출발지·귀가지 이름(네이버 검색 결과가 아님)이면 True."""
    name = str(name or "").strip()
    return (
        name in SAFE_POINT_NAMES
        or name in (EXPIRED_HOME_NAME, AI_ORIGIN_NAME, AI_HOME_NAME)
        or name.endswith(EXPIRED_ORIGIN_NAME)
        or name.endswith(SAFE_POINT_SUFFIXES)
        or name.startswith(SAFE_POINT_PREFIXES)
        or " 대표 위치 · " in name
    )


def point_renames(plan, for_ai=False):
    """실제 장소 코스의 출발지·귀가지(·동네 기준점) 이름 중 검색 결과일 수 있는 것 → 바꿀 이름. {예전 이름: 새 이름}."""
    c = plan.get("conditions")
    if not isinstance(c, dict) or c.get("mode") != "real":
        return {}
    region = str(c.get("region") or "").strip()
    origin_name = AI_ORIGIN_NAME if for_ai else (f"{region} · {EXPIRED_ORIGIN_NAME}" if region else EXPIRED_ORIGIN_NAME)
    home_name = AI_HOME_NAME if for_ai else EXPIRED_HOME_NAME
    renames = {}
    for key, new in (("origin", origin_name), ("home", home_name), ("area_center", origin_name)):
        point = c.get(key)
        name = point.get("name") if isinstance(point, dict) else None
        if isinstance(name, str) and name.strip() and not safe_point_name(name) and name not in renames:
            renames[name] = new
    return renames


def naver_strings(plan):
    """plan 안의 네이버 유래 문자열(장소 이름·주소·업종, 블로그 제목·요약·작성자, 가격 근거 조각,
    검색 결과일 수 있는 출발지·귀가지 주소). 긴 것부터."""
    found = {name for name in point_renames(plan) if len(name.strip()) >= 2}
    for place in plan.get("places") or []:
        if is_naver_place(place) and not place.get("naver_expired"):
            found.update(_strings(place))
    evidence = plan.get("course_search") or {}
    for post in evidence.get("posts") or []:
        if isinstance(post, dict):
            for key in ("title", "description", "summary", "blogger", "author", "url"):
                if isinstance(post.get(key), str) and len(post[key].strip()) >= 2:
                    found.add(post[key].strip())
    for row in plan.get("costs") or []:
        for quote in row.get("price_evidence") or []:
            if isinstance(quote, dict):
                for key in ("evidence", "source"):
                    if isinstance(quote.get(key), str) and len(quote[key].strip()) >= 2:
                        found.add(quote[key].strip())
    return sorted(found, key=len, reverse=True)


def redact_text(text, strings, placeholder=AI_PLACEHOLDER):
    """strings 를 placeholder 로 바꾼다. strings 가 {문자열: 바꿀 말} 이면 문자열마다 그 말로 바꾼다(긴 것부터)."""
    if not isinstance(text, str) or not strings:
        return text
    pairs = strings.items() if isinstance(strings, dict) else ((value, placeholder) for value in strings)
    for value, replacement in sorted(pairs, key=lambda pair: len(pair[0]), reverse=True):
        if value in text:
            text = text.replace(value, replacement)
    return text


def _redact(value, strings, placeholder):
    if isinstance(value, str):
        return redact_text(value, strings, placeholder)
    if isinstance(value, list):
        return [_redact(v, strings, placeholder) for v in value]
    if isinstance(value, dict):
        # 조건(conditions)은 통째로 가리지 않는다(이동 수단·지역 값이 바뀌면 코스를 열 수 없다). 출발지·귀가지 이름만 point_renames 로 바꾼다.
        return {k: v if k in ("conditions", "id", "place_id") else _redact(v, strings, placeholder) for k, v in value.items()}
    return value


def _has_point(point):
    return isinstance(point, dict) and all(isinstance(point.get(k), (int, float)) for k in ("lat", "lon"))


def _expire_prices(plan, places):
    """블로그 검색에서 읽은 가격(web_reference·naver_menu)을 '확인 필요'(금액 없음, 합계에서 빠짐)로 돌리고 합계를 다시 낸다."""
    changed = False
    costs = plan.get("costs") or []
    for index, row in enumerate(costs):
        if not isinstance(row, dict) or not (row.get("price_evidence") or row.get("price_kind") in NAVER_PRICE_KINDS):
            continue
        changed = True
        row.update(price_evidence=[], source=None, price_basis=EXPIRED_PRICE_BASIS, unit=None, amount=None, status="unknown",
                   formula="가격 확인 필요")  # fmt: skip
        for key in ("price_kind", "price_lookup_status", "checked_at"):
            row.pop(key, None)
        if isinstance(plan.get("unknown"), list) and row.get("name"):
            plan["unknown"] = sorted(set(plan["unknown"]) | {row["name"] + " 가격"})
        # 식당 메뉴 가격(meal_draft 의 naver_menu)은 장소의 price·menu_pricing 에도 들어 있다.
        if index < len(places) and isinstance(places[index], dict):
            place = places[index]
            if (place.get("menu_pricing") or {}).get("price_kind") in NAVER_PRICE_KINDS:
                place.pop("menu_pricing", None)
                place.update(price=None, price_status="unknown")
    for place in places:
        if isinstance(place, dict) and (place.get("menu_pricing") or {}).get("price_kind") in NAVER_PRICE_KINDS:
            place.pop("menu_pricing", None)
            place.update(price=None, price_status="unknown")
            changed = True
    if not changed or not all(isinstance(row, dict) and "amount" in row for row in costs):
        return
    # 합계·확정·추정·예산 차액을 남은 금액으로 다시 낸다(app/planner.evaluate·pricing.apply_prices 와 같은 식).
    total = [sum(row["amount"][i] for row in costs if row["amount"] is not None) for i in (0, 1)]
    known = [sum(row["amount"][i] for row in costs if row["amount"] is not None and row.get("status") == "confirmed") for i in (0, 1)]
    if "total" in plan:
        plan.update(total=total, confirmed=known, estimated=[total[i] - known[i] for i in (0, 1)])
        c = plan.get("conditions") or {}
        if "remaining" in plan and not c.get("budget_unlimited") and isinstance(c.get("budget"), int):
            plan["remaining"] = [c["budget"] - total[1], c["budget"] - total[0]]


def _expire_legs(plan, renames):
    """좌표를 지운 장소에 닿는 구간은 길찾기 링크와 도로 경로를 지운다. 이름을 바꾼 출발지·귀가지에 닿는 구간은 링크를 새 이름으로 다시 만든다.

    링크(nmap://route/…)에는 양 끝 이름이 URL 인코딩돼 들어 있어 문자열 가리기(_redact)로는 지워지지 않는다."""
    from .routes import app_link

    c = plan.get("conditions") or {}
    places = plan.get("places") or []
    points = [c.get("origin"), *places]
    if c.get("return_home") and c.get("home"):
        points.append(c["home"])
    for index, leg in enumerate(plan.get("legs") or []):
        if not isinstance(leg, dict) or index + 1 >= len(points):
            continue
        a, b = points[index], points[index + 1]
        expired = any(isinstance(p, dict) and p.get("naver_expired") for p in (a, b))
        renamed = any(isinstance(p, dict) and p.get("name") in renames.values() for p in (a, b))
        if not expired and not renamed:
            continue
        if expired:
            leg["path"] = []
        try:
            leg["link"] = app_link(a, b, leg.get("mode") or c.get("transport") or "walk") if _has_point(a) and _has_point(b) else None
        except (KeyError, TypeError):
            leg["link"] = None


def strip_plan(plan, for_ai=False):
    """네이버 유래 필드를 뺀 코스 사본. for_ai 면 LLM 근거용.

    21일 정리(for_ai=False)에서 지우는 것: 블로그 코스 검색(course_search·blog_score·이유 문장의 블로그 순위), 지역 검색 장소의 이름·주소·업종·
    설명·링크·사진·좌표, 그 장소에 닿는 구간의 길찾기 링크·도로 경로, 블로그 가격(금액은 '확인 필요'로 돌리고 합계에서 뺌), 검색 결과일 수 있는
    출발지·귀가지 이름. 출발지·귀가지 좌표는 남긴다(조건 모델이 요구하고, 지도·일정 검사의 기준점이다 — 남은 위험).
    화면은 course_search·price_evidence 가 없어도, 장소 이름이 EXPIRED_NAME 이고 좌표가 없어도 그린다(지도는 좌표 있는 곳만).
    """
    plan = copy.deepcopy(plan)
    placeholder = AI_PLACEHOLDER if for_ai else EXPIRED_NAME
    renames = point_renames(plan, for_ai)
    strings = {value: placeholder for value in naver_strings(plan)}
    strings.update(renames)
    plan.pop("course_search", None)
    plan.pop("blog_score", None)
    plan["reasons"] = [REASON_PREFIX.sub("", r) if isinstance(r, str) else r for r in plan.get("reasons") or []]
    places = []
    for place in plan.get("places") or []:
        if is_naver_place(place):
            kept = {k: place[k] for k in KEEP_PLACE_FIELDS if k in place}
            if for_ai:
                for key in AI_DROP_PLACE_FIELDS:
                    kept.pop(key, None)
            else:
                kept.update(lat=None, lon=None)
            kept.update(name=placeholder, naver_expired=True, source=None, source_type="네이버 검색 결과(보관 기간 지남)",
                        photos=[], videos=[])  # fmt: skip
            places.append(kept)
        else:
            places.append(place)
    if "places" in plan:
        plan["places"] = places
    _expire_prices(plan, places)
    c = plan.get("conditions")
    if renames and isinstance(c, dict):
        for key in ("origin", "home", "area_center"):
            point = c.get(key)
            if isinstance(point, dict) and point.get("name") in renames:
                c[key] = dict(point, name=renames[point["name"]])
                if for_ai:
                    c[key].update(lat=None, lon=None)
    if not for_ai:
        _expire_legs(plan, renames)
    return _redact(plan, strings, placeholder)


def ai_safe_plan(plan):
    return strip_plan(plan, for_ai=True)


# 21일 정리로 좌표를 지운 장소가 있는 코스는 경로·주변 검색을 다시 계산할 수 없다(좌표가 없음). 바꾸는 요청은 이 문구로 거절한다.
EXPIRED_CHANGE_MESSAGE = (
    "만든 지 21일이 지나 네이버 검색으로 찾은 장소의 정보를 지운 코스예요. 장소·이동 수단 바꾸기, 주변 식당·주차장 찾기, "
    "가격 다시 찾기는 할 수 없어요. 같은 조건으로 새로 추천받아 주세요."
)


def has_expired_places(plan):
    return any(isinstance(p, dict) and p.get("naver_expired") for p in (plan or {}).get("places") or [])


def ensure_changeable(plan):
    """보관 기간이 지나 좌표를 지운 장소가 있으면 409. 경로·주변 검색을 다시 하는 요청(app/main.py, experience_api)이 부른다."""
    if has_expired_places(plan):
        from fastapi import HTTPException

        raise HTTPException(409, EXPIRED_CHANGE_MESSAGE)


def redact_history(history, plan):
    """LLM 에 넘기는 대화 기록에서 코스의 네이버 유래 문자열을 가린다(예전 답변에 장소 이름이 들어 있을 수 있음)."""
    strings = naver_strings(plan) if plan else []
    return [dict(row, content=redact_text(row.get("content", ""), strings)) for row in history or []]


# ---------------------------------------------------------------- 이력 보관 기한(21일)


CLEANUP_BATCH = 200


def cleanup_expired_plans(now=None, batch=CLEANUP_BATCH):
    """만든 지 21일이 지난 코스에서 네이버 유래 필드를 지운다(코스는 남김). 이번에 확인한 코스 수를 돌려준다.

    바꾼 코스(교체·수단 변경·식당 추가·합의 적용, parent 가 있음)는 부모의 장소·검색 자료를 그대로 옮겨 오고 created 만 새로 받는다.
    created 만 보면 고칠 때마다 보관 기한이 21일씩 늘어나므로, 부모를 정리했으면 자식도 함께 정리한다(같은 호출 안에서 이어서).
    교체로 새로 찾은 장소까지 조금 일찍 지워질 수 있다(짧게 두는 쪽)."""
    from . import store

    now = time.time() if now is None else now
    cutoff = now - HISTORY_MAX_SECONDS
    examined = cleaned = 0
    while examined < batch:
        with store.connect() as db:
            rows = db.execute(
                "SELECT id,payload FROM plans WHERE naver_cleared IS NULL AND (created<? OR EXISTS("
                "SELECT 1 FROM plans parent_plan WHERE parent_plan.id=plans.parent AND parent_plan.naver_cleared IS NOT NULL)) LIMIT ?",
                (cutoff, batch - examined),
            ).fetchall()
        if not rows:
            break
        examined += len(rows)
        for row in rows:
            try:
                plan = json.loads(row[1])
            except (TypeError, ValueError):
                plan = None
            payload, changed = row[1], False
            if isinstance(plan, dict):
                stripped = strip_plan(plan)
                if stripped != plan:
                    payload, changed = json.dumps(stripped, ensure_ascii=False), True
                    cleaned += 1
            with store.connect() as db:
                db.execute("UPDATE plans SET payload=?,naver_cleared=? WHERE id=?", (payload, now, row[0]))
                # 네이버 자료를 지운 코스의 질문·답변(일정 답변에 장소 이름·주소가 들어감)도 함께 지운다.
                # 바꾼 코스(자식)의 대화는 아직 21일이 안 됐을 수 있어 아래의 기한 삭제만으로는 남는다.
                if changed:
                    db.execute("DELETE FROM chats WHERE scope=?", ("real:plan:" + row[0],))
    # 대화 기록(chats)의 실제 장소 질문·답변에는 장소 이름 같은 검색 결과가 들어갈 수 있어 같은 기한에 지운다.
    with store.connect() as db:
        db.execute("DELETE FROM chats WHERE created<? AND scope LIKE 'real:%'", (cutoff,))
    if cleaned:
        import logging

        logging.getLogger(__name__).info("naver_history_cleared plans=%s", cleaned)
    return examined


def place_from_owner_plans(place_id, now=None):
    """같은 사용자의 21일 안 저장 코스에 있는 네이버 검색 장소(이력 조회). 없으면 None."""
    from . import naver_cache, store

    owner = naver_cache.current_owner()
    if not owner or not str(place_id).startswith(NAVER_ID_PREFIXES) or re.search(r"[%_\"\\]", str(place_id)):
        return None
    now = time.time() if now is None else now
    with store.connect() as db:
        rows = db.execute(
            "SELECT payload FROM plans WHERE owner=? AND created>=? AND payload LIKE ? ORDER BY created DESC LIMIT 3",
            (owner, now - HISTORY_MAX_SECONDS, '%"id": "' + place_id + '"%'),
        ).fetchall()
    for row in rows:
        try:
            plan = json.loads(row[0])
        except (TypeError, ValueError):
            continue
        for place in plan.get("places") or []:
            if place.get("id") == place_id and not place.get("naver_expired"):
                return place
    return None
