"""네이버 검색 API 특약 2단계(블로그 글·가격, docs/naver-terms-stage2-design.ko.md 3.1(a)·3.2(a)): 이미 저장된 코스를 새 형식으로 한 번 정리한다.

배포 전에 저장된 코스(아직 21일 정리 전, plans.naver_cleared IS NULL)에는 예전 형식이 남아 있다.
  · course_search: 우리가 점수로 고르고 다시 줄 세운 글 5건·글에 나온 장소(matches)·선정 이유. 원래 순서·건수를 되살릴 수 없으므로 통째로 지운다.
    (새 형식은 format=2: 네이버가 준 순서·건수·원문 그대로. 그 코스는 건드리지 않는다.)
  · blog_score·recommendation_method, 이유 문장 머리말 '네이버 코스 검색 n위 글에 등장 · ', 장소별 blog_match·price_sources.
  · 블로그 요약에서 읽은 금액(web_reference, 블로그에서 온 naver_menu, price_evidence): 금액을 지워 '확인 필요'로 돌리고 합계를 다시 낸다.
    운영자가 확인한 제공 메뉴로 넣은 식당 가격은 금액을 남기고 종류 이름만 operator_menu 로 바꾼다.
조건 확인(condition_checks)은 코스를 열 때마다 다시 계산하므로(app/main.plan_row) 여기서 고치지 않는다.

마이그레이션은 바뀌면 안 되므로 정리 규칙을 app/naver_terms.py 에서 가져오지 않고 여기에 고정한다.
되돌리기: 이 정리는 되돌릴 수 없다(지운 값은 약관상 다시 만들 수 없다). 코드를 되돌려도 예전 화면은 정리된 코스를 그대로 연다
(course_search 가 없으면 조사 패널을 그리지 않고, 금액 없는 비용은 '미확인'으로 보인다).
"""

import json
import re

VERSION = "0006-naver-terms-stage2-blog-price"

NEW_FORMAT = 2
REASON_PREFIX = re.compile(r"^네이버 코스 검색 [^·]*?에 등장 · ")
BLOG_PRICE_BASIS = "블로그 글에서 읽은 가격은 더 이상 쓰지 않아 지웠어요(네이버 검색 API 약관). 가격은 확인 필요예요."
OPERATOR_MENU_MARK = "운영자가 확인한 제공 메뉴"
# 예전 형식이 들어 있을 수 있는 코스만 고른다(가상 장소 코스 등은 읽지 않음).
MARKERS = (
    '"course_search"',
    '"blog_score"',
    '"web_reference"',
    '"naver_menu"',
    '"price_evidence"',
    '"blog_match"',
)


def _strip_reason(value):
    return REASON_PREFIX.sub("", value) if isinstance(value, str) else value


def _blog_price(row):
    kind = row.get("price_kind")
    if kind == "naver_menu" and OPERATOR_MENU_MARK in str(row.get("price_basis") or ""):
        return False
    return kind in ("web_reference", "naver_menu") or bool(row.get("price_evidence"))


def clean_plan(plan):
    """예전 형식 코스(dict)를 제자리에서 새 형식으로 고친다. 바꾼 것이 있으면 True."""
    before = json.dumps(plan, ensure_ascii=False, sort_keys=True)
    search = plan.get("course_search")
    if search is not None and not (isinstance(search, dict) and search.get("format") == NEW_FORMAT):
        plan.pop("course_search")
    plan.pop("blog_score", None)
    plan.pop("recommendation_method", None)
    if isinstance(plan.get("reasons"), list):
        plan["reasons"] = [_strip_reason(r) for r in plan["reasons"]]
    for fact in plan.get("place_evidence") or []:
        if isinstance(fact, dict):
            fact.pop("blog_match", None)
            fact.pop("price_sources", None)
            if "reason" in fact:
                fact["reason"] = _strip_reason(fact["reason"])
    summary = plan.get("decision_summary")
    if isinstance(summary, dict):
        summary.pop("source_matched_places", None)
    places = plan.get("places") if isinstance(plan.get("places"), list) else []
    costs = plan.get("costs") if isinstance(plan.get("costs"), list) else []
    repriced = False
    for index, row in enumerate(costs):
        if not isinstance(row, dict):
            continue
        place = places[index] if index < len(places) and isinstance(places[index], dict) else None
        if row.get("price_kind") == "naver_menu" and not _blog_price(row):
            row["price_kind"] = "operator_menu"
            if place and isinstance(place.get("menu_pricing"), dict):
                place["menu_pricing"]["price_kind"] = "operator_menu"
            continue
        if not _blog_price(row):
            row.pop("price_lookup_status", None)
            if row.get("price_evidence") == []:
                row.pop("price_evidence")
            continue
        repriced = True
        row.update(
            source=None,
            price_basis=BLOG_PRICE_BASIS,
            unit=None,
            amount=None,
            status="unknown",
            formula="가격 확인 필요",
        )
        for key in ("price_kind", "price_evidence", "price_lookup_status", "checked_at"):
            row.pop(key, None)
        if isinstance(plan.get("unknown"), list) and row.get("name"):
            plan["unknown"] = sorted(set(plan["unknown"]) | {row["name"] + " 가격"})
        if place and isinstance(place.get("menu_pricing"), dict):
            place.pop("menu_pricing")
            place.update(price=None, price_status="unknown")
        for fact in plan.get("place_evidence") or []:
            if place and isinstance(fact, dict) and fact.get("place_id") == place.get("id"):
                fact["price_kind"] = "unknown"
                fact.pop("price_checked_at", None)
    if repriced and all(isinstance(row, dict) and "amount" in row for row in costs):
        priced = [row for row in costs if row["amount"] is not None]
        total = [sum(row["amount"][i] for row in priced) for i in (0, 1)]
        known = [
            sum(row["amount"][i] for row in priced if row.get("status") == "confirmed")
            for i in (0, 1)
        ]
        if "total" in plan:
            plan.update(
                total=total, confirmed=known, estimated=[total[i] - known[i] for i in (0, 1)]
            )
            c = plan.get("conditions") if isinstance(plan.get("conditions"), dict) else {}
            if (
                "remaining" in plan
                and not c.get("budget_unlimited")
                and isinstance(c.get("budget"), int)
            ):
                plan["remaining"] = [c["budget"] - total[1], c["budget"] - total[0]]
        if isinstance(summary, dict) and "unknown_prices" in summary:
            summary["unknown_prices"] = sum(row["amount"] is None for row in costs)
    return json.dumps(plan, ensure_ascii=False, sort_keys=True) != before


def upgrade(db, backend):
    if backend == "postgres":
        # 요청용 20초 제한 대신, 한 번뿐인 정리에 넉넉한 제한을 이 트랜잭션에만 건다(v0003 과 같은 방식).
        db.execute("SET LOCAL statement_timeout = '300s'")
    where = " OR ".join("payload LIKE ?" for _ in MARKERS)
    rows = db.execute(
        f"SELECT id FROM plans WHERE naver_cleared IS NULL AND ({where})",
        tuple("%" + marker + "%" for marker in MARKERS),
    ).fetchall()
    for plan_id in [row[0] for row in rows]:
        row = db.execute("SELECT payload FROM plans WHERE id=?", (plan_id,)).fetchone()
        try:
            plan = json.loads(row[0])
        except (TypeError, ValueError):
            continue
        if isinstance(plan, dict) and clean_plan(plan):
            db.execute(
                "UPDATE plans SET payload=? WHERE id=?",
                (json.dumps(plan, ensure_ascii=False), plan_id),
            )
