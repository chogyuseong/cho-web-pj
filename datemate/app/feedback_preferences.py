"""Small, explainable preferences from the current owner's explicit feedback."""

import json
from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from . import store

_current = ContextVar("feedback_preferences", default=None)


def build(owner, mode="real"):
    with store.connect() as db:
        rows = db.execute(
            "SELECT e.kind,e.payload,p.payload AS plan FROM experience_events e JOIN plans p ON p.id=e.plan_id WHERE e.owner=? AND p.owner=? AND e.kind IN ('visit','replace_reason') ORDER BY e.created DESC LIMIT 50",
            (owner, owner),
        ).fetchall()
    categories = Counter()
    issues = Counter()
    visited = set()
    used = 0
    for row in rows:
        feedback = json.loads(row["payload"])
        plan = json.loads(row["plan"])
        if plan.get("conditions", {}).get("mode") != mode:
            continue
        used += 1
        if row["kind"] == "replace_reason":
            if feedback.get("reason") in ("budget", "distance"):
                issues[feedback["reason"]] += 1
        elif feedback.get("visited") == "yes":
            key = plan.get("aggregate_key") or tuple(p["id"] for p in plan["places"])
            if key in visited:
                continue
            visited.add(key)
            if feedback.get("reuse") == "yes" and feedback.get("obstacle") == "none":
                categories.update(set(p["category"] for p in plan["places"]))
            elif feedback.get("obstacle") in ("distance", "price"):
                issues["budget" if feedback["obstacle"] == "price" else "distance"] += 1
    return dict(
        categories={key: min(1, count / 3) for key, count in categories.items()},
        prefer_shorter=issues["distance"] >= 2,
        prefer_lower_cost=issues["budget"] >= 2,
        samples=used,
        visit_samples=len(visited),
        mode=mode,
    )


@contextmanager
def personalizing(owner, enabled, mode="real"):
    profile = build(owner, mode) if enabled else None
    token = _current.set(profile)
    try:
        yield profile
    finally:
        _current.reset(token)


def bonus(plan):
    profile = _current.get()
    if not profile:
        return 0
    values = profile["categories"]
    score = sum(values.get(p["category"], 0) for p in plan["places"]) / max(1, len(plan["places"]))
    if profile["prefer_shorter"]:
        score -= min(0.5, sum(r.get("minutes") or 0 for r in plan["legs"]) / 120)
    if profile["prefer_lower_cost"]:
        score -= min(0.5, plan["total"][1] / 400000)
    return score


def explanation(profile):
    if not profile:
        return None
    messages = []
    if profile["categories"]:
        messages.append(
            "이용 후 좋았다고 답한 코스의 "
            + ", ".join(profile["categories"])
            + " 유형을 약하게 우선했어요."
        )
    if profile["prefer_shorter"]:
        messages.append("이동 불편 피드백이 반복되어 짧은 이동 조합을 우선 비교했어요.")
    if profile["prefer_lower_cost"]:
        messages.append("비용 불편 피드백이 반복되어 낮은 비용 조합을 우선 비교했어요.")
    return dict(
        messages=messages or ["아직 순위에 반영할 방문·교체 피드백이 부족해요."],
        samples=profile["samples"],
        scope=(
            "시연 모드 피드백만 반영 · "
            if profile["mode"] == "demo"
            else "현재 브라우저의 실제 장소 모드 자기 신고 기반 · "
        )
        + "입력한 조건과 제외 요청을 우선합니다.",
    )
