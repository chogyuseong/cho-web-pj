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
EXPIRED_PRICE_BASIS = "블로그 검색에서 읽은 가격의 근거는 보관 기간(21일)이 지나 지웠어요."
# 21일이 지나도 남기는 장소 필드(우리가 계산했거나 일정 계산에 필요한 값). 이름·주소·업종·설명·링크는 지운다.
KEEP_PLACE_FIELDS = (
    "id", "lat", "lon", "region", "category", "themes", "meal", "demo", "stay", "stay_basis",
    "price", "price_unit", "price_status", "setting", "hours", "closed_days", "breaks", "last_entry",
    "reservation", "rating", "photos", "videos",
)  # fmt: skip
# AI 근거로 보낼 때는 좌표·가격도 뺀다(검색 결과의 파생물).
AI_DROP_PLACE_FIELDS = ("lat", "lon", "price", "price_status")
REASON_PREFIX = re.compile(r"^네이버 코스 검색 [^·]*?에 등장 · ")


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


def naver_strings(plan):
    """plan 안의 네이버 유래 문자열(장소 이름·주소·업종, 블로그 제목·요약·작성자, 가격 근거 조각). 긴 것부터."""
    found = set()
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
    if not isinstance(text, str) or not strings:
        return text
    for value in strings:
        if value in text:
            text = text.replace(value, placeholder)
    return text


def _redact(value, strings, placeholder):
    if isinstance(value, str):
        return redact_text(value, strings, placeholder)
    if isinstance(value, list):
        return [_redact(v, strings, placeholder) for v in value]
    if isinstance(value, dict):
        # 조건(conditions)은 사용자가 입력한 값이라 가리지 않는다(이동 수단·지역 값이 바뀌면 코스를 열 수 없다).
        return {k: v if k in ("conditions", "id", "place_id") else _redact(v, strings, placeholder) for k, v in value.items()}
    return value


def strip_plan(plan, for_ai=False):
    """네이버 유래 필드를 뺀 코스 사본. for_ai 면 LLM 근거용으로 좌표·블로그 가격 금액까지 뺀다.

    화면은 course_search·price_evidence 가 없어도, 장소 이름이 EXPIRED_NAME 이어도 그대로 그린다.
    """
    plan = copy.deepcopy(plan)
    placeholder = AI_PLACEHOLDER if for_ai else EXPIRED_NAME
    strings = naver_strings(plan)
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
            kept.update(name=placeholder, naver_expired=True, source=None, source_type="네이버 검색 결과(보관 기간 지남)",
                        photos=[], videos=[])  # fmt: skip
            places.append(kept)
        else:
            places.append(place)
    if "places" in plan:
        plan["places"] = places
    for row in plan.get("costs") or []:
        if row.get("price_evidence") or row.get("price_kind") in NAVER_PRICE_KINDS:
            row["price_evidence"] = []
            row["source"] = None
            row["price_basis"] = EXPIRED_PRICE_BASIS
            if for_ai:
                row.update(unit=None, amount=None)
    return _redact(plan, strings, placeholder)


def ai_safe_plan(plan):
    return strip_plan(plan, for_ai=True)


def redact_history(history, plan):
    """LLM 에 넘기는 대화 기록에서 코스의 네이버 유래 문자열을 가린다(예전 답변에 장소 이름이 들어 있을 수 있음)."""
    strings = naver_strings(plan) if plan else []
    return [dict(row, content=redact_text(row.get("content", ""), strings)) for row in history or []]


# ---------------------------------------------------------------- 이력 보관 기한(21일)


CLEANUP_BATCH = 200


def cleanup_expired_plans(now=None, batch=CLEANUP_BATCH):
    """만든 지 21일이 지난 코스에서 네이버 유래 필드를 지운다(코스는 남김). 이번에 확인한 코스 수를 돌려준다."""
    from . import store

    now = time.time() if now is None else now
    cutoff = now - HISTORY_MAX_SECONDS
    with store.connect() as db:
        rows = db.execute(
            "SELECT id,payload FROM plans WHERE created<? AND naver_cleared IS NULL LIMIT ?",
            (cutoff, batch),
        ).fetchall()
    cleaned = 0
    for row in rows:
        try:
            plan = json.loads(row[1])
        except (TypeError, ValueError):
            plan = None
        payload = row[1]
        if isinstance(plan, dict):
            stripped = strip_plan(plan)
            if stripped != plan:
                payload = json.dumps(stripped, ensure_ascii=False)
                cleaned += 1
        with store.connect() as db:
            db.execute("UPDATE plans SET payload=?,naver_cleared=? WHERE id=?", (payload, now, row[0]))
    # 대화 기록(chats)의 실제 장소 질문·답변에는 장소 이름 같은 검색 결과가 들어갈 수 있어 같은 기한에 지운다.
    with store.connect() as db:
        db.execute("DELETE FROM chats WHERE created<? AND scope LIKE 'real:%'", (cutoff,))
    if cleaned:
        import logging

        logging.getLogger(__name__).info("naver_history_cleared plans=%s", cleaned)
    return len(rows)


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
