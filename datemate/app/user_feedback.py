"""The "피드백" page: users send what bothered them; only the administrator reads it.

- DATEMATE_FEEDBACK_ENABLED (default on) hides the menu tab and turns the page and the
  write API into 404. The admin view keeps working so collected entries stay readable.
- FEEDBACK_ADMIN_KEY enables the admin view. Without it, or with a wrong key, every
  admin route answers like an unknown path (404). The key travels only in the
  Authorization header, never in a URL, and is compared in constant time.
- Entries carry no session owner and no raw IP, so "delete my data" and the 90-day
  retention job do not touch them; they stay until the administrator deletes them.
"""

import hmac
import os
import re
import time
import unicodedata
import uuid
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from . import store, web_security
from .static_pages import versioned_page

router = APIRouter()

MESSAGE_MIN = 5
MESSAGE_MAX = 1000
CONTACT_MAX = 100
PAGE_SIZE = 20
SCREENS = {
    "home": "홈",
    "conditions": "조건 입력",
    "results": "추천 결과",
    "explore": "장소 둘러보기",
    "other": "기타",
}
# The exact menu tab in static/index.html; removed from the home page when switched off.
NAV_LINK = '<a id="nav-feedback" href="/feedback">피드백</a>'
NOT_FOUND = "Not Found"  # FastAPI's own body for unknown paths


def enabled():
    value = os.getenv("DATEMATE_FEEDBACK_ENABLED", "1").strip().lower()
    return value not in ("0", "false", "off", "no")


def admin_key():
    return os.getenv("FEEDBACK_ADMIN_KEY", "").strip()


def home_page(html):
    return html if enabled() else html.replace(NAV_LINK, "")


# Bidirectional overrides and zero-width marks can disguise text in the admin list.
_INVISIBLE = re.compile("[​-‏‪-‮⁠-⁩﻿]")


def clean_text(value, multiline):
    """Trim, normalise line breaks and drop control characters."""
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    text = _INVISIBLE.sub("", text)
    keep = "\n" if multiline else ""
    text = "".join(ch for ch in text if ch in keep or unicodedata.category(ch) not in ("Cc", "Cs"))
    if not multiline:
        text = " ".join(text.split())
    return text.strip()


def browser_family(user_agent):
    """A coarse browser name only (no version, no OS details)."""
    ua = user_agent or ""
    for marker, name in (
        ("SamsungBrowser", "삼성 인터넷"),
        ("Whale/", "웨일"),
        ("Edg", "Edge"),
        ("OPR/", "Opera"),
        ("Firefox/", "Firefox"),
        ("FxiOS", "Firefox"),
        ("CriOS", "Chrome"),
        ("Chrome/", "Chrome"),
        ("Safari/", "Safari"),
    ):
        if marker in ua:
            family = name
            break
    else:
        family = "기타"
    return family + (" · 모바일" if "Mobi" in ua else "")


def _windows():
    now = time.time()
    return int(now // 600), int(now // 86400)


def _client(request):
    return web_security.client_key(request)


def write_allowed(request):
    """Per IP range: a few entries per 10 minutes and a daily cap.

    Scopes start with "feedback:" (not "ip:") because maintenance clears "ip:" budgets
    after two minutes; these are day buckets and are cleared after a day instead.
    """
    ten, day = _windows()
    key = _client(request)
    return store.reserve_budget(
        [
            (
                f"feedback:10m:{ten}:{key}",
                web_security.limit("DATEMATE_IP_FEEDBACK_PER_10_MINUTES", 3),
            ),
            (f"feedback:day:{key}", web_security.limit("DATEMATE_IP_FEEDBACK_PER_DAY", 20)),
        ],
        day,
    )


def _failure_scope(request):
    ten, day = _windows()
    return f"feedback:admin-fail:{ten}:{_client(request)}", day


def authorized(request, authorization):
    """True for the right key. Wrong keys count; too many lock the range for 10 minutes."""
    key = admin_key()
    if not key:
        return False
    scope, day = _failure_scope(request)
    allowed_failures = web_security.limit("DATEMATE_IP_FEEDBACK_ADMIN_FAILURES_PER_10_MINUTES", 10)
    with store.connect() as db:
        row = db.execute(
            "SELECT calls FROM request_budgets WHERE scope=? AND bucket=?", (scope, day)
        ).fetchone()
    if row and row[0] >= allowed_failures:
        return False
    supplied = ""
    if authorization and authorization[:7].lower() == "bearer ":
        supplied = authorization[7:].strip()
    if supplied and hmac.compare_digest(supplied.encode(), key.encode()):
        return True
    store.reserve_budget([(scope, 10**9)], day)
    return False


def require_admin(request, authorization):
    if not authorized(request, authorization):
        raise HTTPException(404, NOT_FOUND)


class FeedbackInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Raw bounds; the cleaned text is checked against MESSAGE_MIN/MAX and CONTACT_MAX.
    message: str = Field(max_length=4000)
    screen: Literal["", "home", "conditions", "results", "explore", "other"] = ""
    contact: str = Field(default="", max_length=400)
    viewport_width: int | None = Field(default=None, ge=1, le=10000)
    # Honeypot: hidden from people; bots that fill every field get a fake success.
    website: str = Field(default="", max_length=400)


RECEIVED = {"received": True, "message": "보내 주셔서 고마워요. 확인해서 서비스에 반영할게요."}


@router.post("/api/feedback")
def send_feedback(data: FeedbackInput, request: Request):
    if not enabled():
        raise HTTPException(404, NOT_FOUND)
    message = clean_text(data.message, multiline=True)
    contact = clean_text(data.contact, multiline=False)
    if len(message) < MESSAGE_MIN:
        raise HTTPException(422, f"내용을 {MESSAGE_MIN}자 이상 적어 주세요.")
    if len(message) > MESSAGE_MAX:
        raise HTTPException(422, f"내용은 {MESSAGE_MAX}자까지 보낼 수 있어요.")
    if len(contact) > CONTACT_MAX:
        raise HTTPException(422, f"연락처는 {CONTACT_MAX}자까지 적을 수 있어요.")
    if not write_allowed(request):
        raise HTTPException(
            429,
            "피드백을 짧은 시간에 많이 보냈어요. 잠시 후 다시 보내 주세요.",
            headers={"Retry-After": "600"},
        )
    if data.website.strip():
        return RECEIVED
    with store.connect() as db:
        db.execute(
            "INSERT INTO feedback_entries(id,created,message,screen,contact,viewport_width,browser,handled) "
            "VALUES(?,?,?,?,?,?,?,0)",
            (
                uuid.uuid4().hex,
                time.time(),
                message,
                data.screen,
                contact,
                data.viewport_width,
                browser_family(request.headers.get("user-agent")),
            ),
        )
    return RECEIVED


@router.get("/api/feedback/admin/entries")
def list_entries(
    request: Request,
    page: int = Query(default=1, ge=1, le=100000),
    authorization: str | None = Header(default=None),
):
    require_admin(request, authorization)
    with store.connect() as db:
        total = db.execute("SELECT COUNT(*) FROM feedback_entries").fetchone()[0]
        open_count = db.execute("SELECT COUNT(*) FROM feedback_entries WHERE handled=0").fetchone()[
            0
        ]
        rows = db.execute(
            "SELECT id,created,message,screen,contact,viewport_width,browser,handled "
            "FROM feedback_entries ORDER BY created DESC, id LIMIT ? OFFSET ?",
            (PAGE_SIZE, (page - 1) * PAGE_SIZE),
        ).fetchall()
    entries = []
    for row in rows:
        entry = dict(row)
        entry["handled"] = bool(entry["handled"])
        entry["screen_label"] = SCREENS.get(entry["screen"], "")
        entries.append(entry)
    return dict(
        entries=entries,
        page=page,
        pages=max(1, -(-total // PAGE_SIZE)),
        total=total,
        unhandled=open_count,
        page_size=PAGE_SIZE,
    )


class HandledInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    handled: bool


def _entry_id(entry_id):
    if not re.fullmatch(r"[0-9a-f]{32}", entry_id):
        raise HTTPException(404, "글을 찾을 수 없어요.")
    return entry_id


@router.patch("/api/feedback/admin/entries/{entry_id}")
def mark_entry(
    entry_id: str,
    data: HandledInput,
    request: Request,
    authorization: str | None = Header(default=None),
):
    require_admin(request, authorization)
    with store.connect() as db:
        cursor = db.execute(
            "UPDATE feedback_entries SET handled=? WHERE id=?",
            (1 if data.handled else 0, _entry_id(entry_id)),
        )
        if cursor.rowcount == 0:
            raise HTTPException(404, "글을 찾을 수 없어요.")
    return {"id": entry_id, "handled": data.handled}


@router.delete("/api/feedback/admin/entries/{entry_id}")
def delete_entry(entry_id: str, request: Request, authorization: str | None = Header(default=None)):
    require_admin(request, authorization)
    with store.connect() as db:
        cursor = db.execute("DELETE FROM feedback_entries WHERE id=?", (_entry_id(entry_id),))
        if cursor.rowcount == 0:
            raise HTTPException(404, "글을 찾을 수 없어요.")
    return {"id": entry_id, "deleted": True}


@router.get("/feedback", include_in_schema=False)
def feedback_page():
    if not enabled():
        raise HTTPException(404, NOT_FOUND)
    return HTMLResponse(versioned_page("feedback.html"), headers={"Cache-Control": "no-store"})


@router.get("/feedback/admin", include_in_schema=False)
def admin_page():
    if not admin_key():
        raise HTTPException(404, NOT_FOUND)
    return HTMLResponse(
        versioned_page("feedback-admin.html"),
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Robots-Tag": "noindex, nofollow",
        },
    )
