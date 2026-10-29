"""Explicit decisions and opt-in planning outcomes, without free-text analytics."""

import json
import time
import uuid
from typing import Literal
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from . import store

router = APIRouter(prefix="/api")
SESSION_TTL = 86400


class Consent(BaseModel):
    consented: Literal[True]


class Decision(BaseModel):
    extra_search: Literal["unknown", "none", "some", "many"] = "unknown"
    manual_planning_minutes: int | None = Field(default=None, ge=0, le=240)


def session_for(session_id, owner):
    session = store.cached("planning-study:" + session_id)
    if not session or session.get("owner") != owner:
        raise HTTPException(
            409, "계획 경험 측정이 만료됐어요. 측정 참여를 해제하거나 새 검색을 시작해 주세요."
        )
    return session


@router.post("/planning-sessions")
def start(data: Consent, request: Request):
    sid = uuid.uuid4().hex
    now = time.time()
    record = dict(
        owner=request.state.owner, session_id=sid, started_at=now, consent_version="2026-10-29"
    )
    # One transaction so enrollment and its owner-bound state cannot diverge.
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "INSERT INTO cache VALUES(?,?,?)",
            ("planning-study:" + sid, json.dumps(record), now + SESSION_TTL),
        )
        db.execute(
            "INSERT INTO experience_events VALUES(?,?,?,?,?,?)",
            (
                uuid.uuid4().hex,
                request.state.owner,
                "",
                "planning_started",
                json.dumps(dict(session_id=sid, consent_version=record["consent_version"])),
                now,
            ),
        )
    return dict(session_id=sid, expires=now + SESSION_TTL)


def owned_plan(pid, owner):
    row = store.get_plan(pid)
    if not row or row["owner"] != owner:
        raise HTTPException(404, "이 브라우저에서 만든 일정만 결정할 수 있어요.")
    return json.loads(row["payload"])


def existing(db, pid, owner):
    row = db.execute(
        "SELECT payload FROM experience_events WHERE owner=? AND plan_id=? AND kind='course_decision'",
        (owner, pid),
    ).fetchone()
    return json.loads(row["payload"]) if row else None


@router.get("/plans/{pid}/decision")
def read(pid: str, request: Request):
    owned_plan(pid, request.state.owner)
    with store.connect() as db:
        value = existing(db, pid, request.state.owner)
    return dict(decision=value)


@router.get("/my/decisions")
def decisions(request: Request):
    with store.connect() as db:
        rows = db.execute(
            "SELECT p.id,p.payload,e.payload AS decision FROM plans p JOIN experience_events e ON e.plan_id=p.id WHERE p.owner=? AND e.owner=? AND e.kind='course_decision' ORDER BY e.created DESC LIMIT 10",
            (request.state.owner, request.state.owner),
        ).fetchall()
    items = []
    for row in rows:
        plan = json.loads(row["payload"])
        decision = json.loads(row["decision"])
        items.append(
            dict(
                id=row["id"],
                title=plan.get("decision_summary", {}).get("title") or "결정한 데이트 코스",
                places=[p["name"] for p in plan["places"]],
                visit_date=plan["conditions"].get("visit_date"),
                confirmed_at=decision["confirmed_at"],
            )
        )
    return dict(items=items, scope="현재 브라우저에서 결정한 최근 코스 최대 10개")


@router.post("/plans/{pid}/decision")
def decide(pid: str, data: Decision, request: Request):
    plan = owned_plan(pid, request.state.owner)
    sid = plan["conditions"].get("planning_session_id", "")
    session = store.cached("planning-study:" + sid) if sid else None
    if session and session.get("owner") != request.state.owner:
        raise HTTPException(404, "측정 기록을 찾을 수 없어요.")
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        # Plan deletion and consent state must still be valid at the write boundary.
        if not db.execute(
            "SELECT 1 FROM plans WHERE id=? AND owner=?", (pid, request.state.owner)
        ).fetchone():
            raise HTTPException(404, "일정을 찾을 수 없어요.")
        if (
            session
            and not db.execute(
                "SELECT 1 FROM cache WHERE key=? AND expires>?",
                ("planning-study:" + sid, time.time()),
            ).fetchone()
        ):
            raise HTTPException(409, "측정이 만료됐어요. 새 검색에서 다시 참여해 주세요.")
        previous = existing(db, pid, request.state.owner)
        now = time.time()
        group_id = plan.get("recommendation_group_id", pid)
        value = dict(confirmed_at=(previous or {}).get("confirmed_at", now), group_id=group_id)
        if previous and not session:
            value = dict(previous)
        if session:
            value.update(
                data.model_dump(),
                session_id=sid,
                elapsed_seconds=max(0, round(value["confirmed_at"] - session["started_at"])),
                timing_scope="추천 요청부터 코스 결정까지 · 검색 대기와 자리 비움 포함",
                evidence="추가 검색·평소 계획 시간은 자기 신고 · 실제 방문 인증 아님",
            )
        # Answers without consent are not retained or included in study metrics.
        if previous == value:
            return dict(decision=previous, saved=True)
        # A new choice replaces the previous choice from the same search batch.
        for row in db.execute(
            "SELECT id,payload FROM experience_events WHERE owner=? AND kind='course_decision'",
            (request.state.owner,),
        ).fetchall():
            if json.loads(row["payload"]).get("group_id") == group_id:
                db.execute("DELETE FROM experience_events WHERE id=?", (row["id"],))
        db.execute(
            "DELETE FROM experience_events WHERE owner=? AND plan_id=? AND kind='course_decision'",
            (request.state.owner, pid),
        )
        db.execute(
            "INSERT INTO experience_events VALUES(?,?,?,?,?,?)",
            (
                uuid.uuid4().hex,
                request.state.owner,
                pid,
                "course_decision",
                json.dumps(value, ensure_ascii=False),
                now,
            ),
        )
    return dict(decision=value, saved=True)


def study_summary(actions):
    """Cohort: sessions started in the report window; one decision per session."""
    started = {
        (r["owner"], json.loads(r["payload"]).get("session_id"))
        for r in actions
        if r["kind"] == "planning_started"
    }
    latest = {}
    for row in sorted(actions, key=lambda r: r.get("created", 0)):
        if row["kind"] != "course_decision":
            continue
        value = json.loads(row["payload"])
        key = (row["owner"], value.get("session_id"))
        if key in started:
            latest[key] = value
    decisions = list(latest.values())
    answers = [v for v in decisions if v.get("extra_search") in ("none", "some", "many")]
    times = sorted(v["elapsed_seconds"] for v in decisions if "elapsed_seconds" in v)
    middle = len(times) // 2
    median = (
        (times[middle] if len(times) % 2 else (times[middle - 1] + times[middle]) / 2)
        if times
        else None
    )
    return dict(
        enrolled_sessions=len(started),
        decided_sessions=len(decisions),
        decision_rate=len(decisions) / len(started) if started else None,
        median_request_to_decision_seconds=median,
        timing_samples=len(times),
        extra_search_answered=len(answers),
        no_extra_search=sum(v["extra_search"] == "none" for v in answers),
        no_extra_search_rate=sum(v["extra_search"] == "none" for v in answers) / len(answers)
        if answers
        else None,
        manual_baseline_samples=sum(
            v.get("manual_planning_minutes") is not None for v in decisions
        ),
        scope="Opt-in browser sessions started in the report window, including unfinished/failed searches; latest course decision per session. Timing includes idle time. Baselines and extra search are self-reported; no causal comparison or verified visits.",
    )
