import copy
import json
import os
import secrets
import time
import mimetypes
import logging
import uuid
import re
import asyncio
from contextlib import suppress
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import FastAPI, HTTPException, Request, Response, Query
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from . import store
from .catalog import places, get_place
from .config import ROOT, REGION, production, public_origin, validate_runtime
from . import web_security
from .models import Conditions, ReviewInput, ChatInput, THEMES, TransportMode
from .planner import replacements
from .indexing import collections, embedding_mode, search_places
from .rag import ask
from .geocoding import search_address
from .taxonomy import DATE_CATEGORIES
from .media import media_info
from .blog_search import place_blogs
from .request_usage import bind_client, unbind_client
from .static_pages import versioned_page

# Provider keys (e.g. the tourism API key) travel in URL queries; httpx logs request
# URLs at INFO, so keep its loggers quiet even if INFO logging is enabled later.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Largest legitimate body is a recommendation request (~30 KB worst case).
MAX_BODY_BYTES = 64 * 1024

# Windows 레지스트리의 .js=text/plain 매핑에서도 nosniff와 호환되도록 고정한다.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("font/woff2", ".woff2")


@asynccontextmanager
async def lifespan(app):
    validate_runtime()
    await run_in_threadpool(store.init)
    from .maintenance import loop
    from .plan_jobs import heartbeat_loop

    task = asyncio.create_task(loop())
    heartbeat_task = asyncio.create_task(heartbeat_loop())
    try:
        yield
    finally:
        task.cancel()
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        with suppress(asyncio.CancelledError):
            await heartbeat_task


app = FastAPI(
    title="데이트메이트 · 전국 데이트 코스 추천",
    version="0.2.0",
    lifespan=lifespan,
    docs_url=None if production() else "/docs",
    redoc_url=None if production() else "/redoc",
    openapi_url=None if production() else "/openapi.json",
)
from .experience_api import router as experience_router

app.include_router(experience_router)
from .plan_jobs import router as jobs_router

app.include_router(jobs_router)
from .explore import router as explore_router

app.include_router(explore_router)
from .sharing import router as sharing_router

app.include_router(sharing_router)
from .planning_outcomes import router as outcomes_router

app.include_router(outcomes_router)
from .festivals import router as festivals_router

app.include_router(festivals_router)


@app.get("/healthz", include_in_schema=False)
def health():
    return {"status": "ok"}


@app.get("/readyz", include_in_schema=False)
def readiness():
    try:
        with store.connect() as db:
            db.execute("SELECT 1 FROM sessions LIMIT 1").fetchone()
        return {"status": "ready", "scope": "database_only", "external_services_verified": False}
    except Exception:
        return JSONResponse({"status": "not_ready"}, status_code=503)


@app.middleware("http")
async def safety(request: Request, call_next):
    started = time.perf_counter()
    request_id = uuid.uuid4().hex

    def finish(response):
        response.headers["Server-Timing"] = (
            f"total;dur={(time.perf_counter() - started) * 1000:.2f}"
        )
        return web_security.headers(response, request, request_id)

    token = None
    session_state = "current"
    client_token = None
    try:
        if not web_security.allowed_host(request):
            return finish(
                JSONResponse({"detail": "허용되지 않은 사이트 주소입니다."}, status_code=400)
            )
        if request.url.path in ("/healthz", "/readyz") or request.url.path.startswith("/static/"):
            return finish(await call_next(request))
        client = web_security.client_key(request)
        # Limits and provider budgets below the HTTP layer read the caller's IP range.
        client_token = bind_client(client)
        api = request.url.path.startswith("/api/")
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("origin")
            expected = public_origin() or str(request.base_url).rstrip("/")
            fetch_site = request.headers.get("sec-fetch-site")
            if (
                (origin and origin.rstrip("/") != expected)
                or fetch_site == "cross-site"
                or (production() and not origin and fetch_site != "same-origin")
            ):
                return finish(
                    JSONResponse(
                        {"detail": "다른 사이트에서 보낸 변경 요청은 허용하지 않습니다."},
                        status_code=403,
                    )
                )
            body = bytearray()
            try:
                async with asyncio.timeout(15):
                    async for chunk in request.stream():
                        body.extend(chunk)
                        if len(body) > MAX_BODY_BYTES:
                            return finish(
                                JSONResponse(
                                    {"detail": "요청은 64 KiB 이하로 보내주세요."}, status_code=413
                                )
                            )
            except TimeoutError:
                return finish(
                    JSONResponse({"detail": "요청 전송 시간이 초과됐어요."}, status_code=408)
                )
            request._body = bytes(body)

        def admitted():
            return web_security.api_budget(request, client) and web_security.expensive_budget(
                request, client
            )

        if not await run_in_threadpool(admitted):
            return finish(
                JSONResponse(
                    {"detail": "요청이 많아요. 잠시 후 다시 시도해 주세요."},
                    status_code=429,
                    headers={"Retry-After": "60"},
                )
            )

        def identify():
            """(cookie token, owner digest, state); state says which cookie to send.

            "current": nothing to send; "refresh": renew the sliding expiry;
            "legacy": move a pre-__Host- cookie to the new name; "new": first visit.
            """
            token = request.cookies.get(web_security.session_cookie(request), "")
            legacy = False
            if not token and web_security.secure_cookies(request):
                token = request.cookies.get(web_security.SESSION_COOKIE, "")
                legacy = bool(token)
            token = token[:128]
            now = time.time()
            if token:
                owner = store.owner_of(token)
                with store.connect() as db:
                    row = db.execute(
                        "SELECT last_used,created FROM sessions WHERE token=?", (owner,)
                    ).fetchone()
                    if row:
                        # One write per day at most; it also renews the cookie.
                        stale = (row[0] if row[0] is not None else row[1] or 0) < (
                            now - SESSION_TOUCH_SECONDS
                        )
                        if stale:
                            db.execute(
                                "UPDATE sessions SET last_used=? WHERE token=?", (now, owner)
                            )
                        return (
                            token,
                            owner,
                            "legacy" if legacy else ("refresh" if stale else "current"),
                        )
            # New sessions only for API calls, and a bounded number per IP range, so
            # page views and bots cannot grow the sessions table without limit.
            if not web_security.ip_allow(
                "session", "DATEMATE_IP_SESSIONS_PER_MINUTE", 30, key=client
            ):
                return None, None, None
            token = secrets.token_urlsafe(32)
            owner = store.owner_of(token)
            with store.connect() as db:
                db.execute(
                    "INSERT INTO sessions(token,created,last_used) VALUES(?,?,?)",
                    (owner, now, now),
                )
            return token, owner, "new"

        if not api:
            # HTML, shared page and 404s do not need an owner; no session is created.
            request.state.owner = None
            response = await call_next(request)
            return finish(response)
        token, owner, session_state = await run_in_threadpool(identify)
        if token is None:
            return finish(
                JSONResponse(
                    {"detail": "새 연결 요청이 많아요. 잠시 후 다시 시도해 주세요."},
                    status_code=429,
                    headers={"Retry-After": "60"},
                )
            )
        request.state.owner = owner
        match = re.match(r"^/api/(?:plans/|chat/plan/)([^/]+)", request.url.path)
        if match:
            row = await run_in_threadpool(store.get_plan, match.group(1))
            if not row or not secrets.compare_digest(
                str(row["owner"] or "").encode(), owner.encode()
            ):
                response = JSONResponse(
                    {"detail": "일정을 찾을 수 없습니다. 공유 링크로 접속해 주세요."},
                    status_code=404,
                )
            else:
                response = await call_next(request)
        else:
            response = await call_next(request)
    except Exception:
        logging.getLogger(__name__).exception(
            "request_failed id=%s method=%s path=%s", request_id, request.method, request.url.path
        )
        response = JSONResponse(
            {"detail": "요청 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."},
            status_code=500,
        )
    finally:
        if client_token is not None:
            unbind_client(client_token)
    if token and request.url.path != "/api/me/data":
        if session_state != "current":
            # Lax keeps the session when arriving from another site's link; state
            # changes are still refused above by the Origin/Sec-Fetch-Site check.
            response.set_cookie(
                web_security.session_cookie(request),
                token,
                httponly=True,
                samesite="lax",
                secure=web_security.secure_cookies(request),
                max_age=web_security.SESSION_MAX_AGE,
                path="/",
            )
        if web_security.secure_cookies(request) and web_security.SESSION_COOKIE in request.cookies:
            # The pre-__Host- cookie was carried over (or is stale); retire it.
            expire_cookie(response, web_security.SESSION_COOKIE, secure=True)
    return finish(response)


# Sessions record activity (and renew the 30-day cookie) at most once a day.
SESSION_TOUCH_SECONDS = 86400


def expire_cookie(response, name, secure):
    response.delete_cookie(name, path="/", secure=secure, httponly=True, samesite="lax")


def plan_row(id, owner=None):
    row = store.get_plan(id)
    if not row:
        raise HTTPException(404, "일정을 찾을 수 없습니다.")
    if owner is not None and row["owner"] != owner:
        raise HTTPException(403, "이 브라우저에서 만든 일정만 수정할 수 있습니다.")
    from .condition_audit import audit_plan

    plan = audit_plan(json.loads(row["payload"]))
    from .experience import verification_summary

    plan["verification"] = verification_summary(plan)
    from .recommendation_summary import enrich

    enrich(plan)
    return row, plan


@app.delete("/api/me/data")
def delete_my_data(request: Request, response: Response):
    owner = request.state.owner
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        store.purge_owner(db, owner)
    secure = web_security.secure_cookies(request)
    expire_cookie(response, web_security.session_cookie(request), secure)
    if secure:
        expire_cookie(response, web_security.SESSION_COOKIE, secure)
    from .plan_jobs import forget_owner

    forget_owner(owner)
    return {
        "deleted": True,
        "notice": "현재 브라우저에 연결된 저장 데이터를 삭제했습니다. 별도 백업과 외부 서비스 기록은 포함되지 않습니다.",
    }


STATUS_TTL_SECONDS = 60
_status_cache = {"expires": 0.0, "value": None}


@app.get("/api/status")
def status():
    # Counting index rows and reading place files on every page load is avoidable work.
    now = time.monotonic()
    if _status_cache["value"] is not None and _status_cache["expires"] > now:
        return _status_cache["value"]
    value = _status()
    _status_cache.update(value=value, expires=now + STATUS_TTL_SECONDS)
    return value


def _status():
    counts = {}
    for mode in ("demo", "real"):
        a, b = collections(mode)
        counts[mode] = dict(places=len(places(mode)), indexed=a.count(), chunks=b.count())
    return dict(
        region=REGION,
        temporary_region=False,
        counts=counts,
        llm="키 설정됨 · 실호출 결과 별도" if os.getenv("GMS_KEY") else "GMS 키 없음",
        embedding=embedding_mode(),
        themes=THEMES,
        date_categories=DATE_CATEGORIES,
        map_js_key=os.getenv("NAVER_MAPS_JS_KEY_ID", ""),
        geocoding_available=bool(os.getenv("NAVER_MAPS_KEY_ID") and os.getenv("NAVER_MAPS_KEY")),
        map_tile_url=os.getenv("MAP_TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png"),
        map_tile_attribution=os.getenv("MAP_TILE_ATTRIBUTION", "© OpenStreetMap contributors"),
    )


class AddressInput(BaseModel):
    query: str = Field(min_length=2, max_length=200)


@app.post("/api/locations/search")
def location_search(data: AddressInput, request: Request):
    if len(data.query.strip()) < 2:
        raise HTTPException(422, "주소를 두 글자 이상 입력하세요.")
    # 단일 로컬 서버의 사용자별 연속 요청 제한. 자동완성/일괄 지오코딩은 하지 않는다.
    key = "geocode-rate:" + request.state.owner
    if store.cached(key):
        raise HTTPException(429, "주소 검색은 잠시 후 다시 시도하세요.")
    web_security.require_ip(
        "geocode", "DATEMATE_IP_GEOCODE_PER_MINUTE", 20, "주소 검색은 잠시 후 다시 시도하세요."
    )
    store.cache(key, True, 1)
    return search_address(data.query.strip())


class CoordinateInput(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


@app.post("/api/locations/region")
def location_region(data: CoordinateInput, request: Request):
    """지도에서 고른 좌표의 시·도를 확인한다. 확인하지 못하면 사용자가 직접 고른다."""
    from .geocoding import district_at
    from .regions import korean_coordinates, region_from_address

    if not korean_coordinates(data.lat, data.lon):
        return dict(
            status="outside",
            region=None,
            label="",
            message="국내 좌표가 아니에요. 지도를 다시 선택하거나 시·도를 직접 골라 주세요.",
        )
    if not (os.getenv("NAVER_MAPS_KEY_ID") and os.getenv("NAVER_MAPS_KEY")):
        return dict(
            status="key_missing",
            region=None,
            label="",
            message="시·도 자동 확인에는 네이버 Maps 키가 필요해요. 시·도를 직접 골라 주세요.",
        )
    # 지도 클릭마다 한 번만 확인하도록 사용자별 연속 요청을 제한한다.
    key = "region-rate:" + request.state.owner
    if store.cached(key):
        raise HTTPException(429, "위치 확인은 잠시 후 다시 시도하세요.")
    web_security.require_ip(
        "reverse-geocode",
        "DATEMATE_IP_REVERSE_GEOCODE_PER_MINUTE",
        30,
        "위치 확인은 잠시 후 다시 시도하세요.",
    )
    store.cache(key, True, 1)
    label = district_at(data.lat, data.lon)
    region = region_from_address(label)
    if not region:
        return dict(
            status="unavailable",
            region=None,
            label="",
            message="선택한 위치의 시·도를 확인하지 못했어요. 시·도를 직접 골라 주세요.",
        )
    return dict(status="ok", region=region, label=label, message="")


@app.get("/api/places")
def catalog(mode: Literal["demo", "real"] = "demo", q: str = Query(default="", max_length=500)):
    rows = places(mode)
    if q:
        matches = [
            p
            for p in rows
            if q.lower() in (p["name"] + " " + p["category"] + " " + " ".join(p["tags"])).lower()
        ]
        if matches:
            return dict(places=matches, search="문자 일치")
        ids = search_places(q, mode)
        rows = sorted([p for p in rows if p["id"] in ids], key=lambda p: ids.index(p["id"]))
    return dict(places=rows, search="해시 데모 검색" if embedding_mode() == "demo" else "의미 검색")


@app.get("/api/places/{id}")
def place(id: str, mode: Literal["demo", "real"] = "demo"):
    p = get_place(id, mode)
    if p is None:
        raise HTTPException(404, "장소를 찾을 수 없습니다.")
    return p


class ParseInput(BaseModel):
    text: str = Field(max_length=4000)
    people: int = Field(default=2, ge=1, le=20)
    explicit_people: bool = False


def refresh_allowed(kind, owner, message):
    """Forced provider re-reads: one per 5 s per browser and a shared IP-range cap."""
    key = kind + "-refresh:" + owner
    if store.cached(key):
        raise HTTPException(429, message)
    web_security.require_ip("refresh", "DATEMATE_IP_REFRESHES_PER_MINUTE", 12, message)
    store.cache(key, True, 5)


@app.get("/api/places/{id}/media")
def place_media(
    id: str,
    request: Request,
    mode: Literal["demo", "real"] = "real",
    fallback: Literal["", "place", "reviews"] = "",
    refresh: bool = False,
):
    p = get_place(id, mode)
    if p is None:
        raise HTTPException(404, "장소를 찾을 수 없습니다.")
    if refresh:
        refresh_allowed(
            "media", request.state.owner, "사진 새로 조회는 잠시 후 다시 시도해 주세요."
        )
    return media_info(
        p, prefer_public=fallback == "place", force=refresh, review_only=fallback == "reviews"
    )


@app.get("/api/places/{id}/blogs")
def place_blog_results(id: str, mode: Literal["demo", "real"] = "real"):
    p = get_place(id, mode)
    if p is None:
        raise HTTPException(404, "장소를 찾을 수 없습니다.")
    return place_blogs(p)


@app.get("/api/places/{id}/menu")
def place_menu(
    id: str, request: Request, mode: Literal["demo", "real"] = "real", refresh: bool = False
):
    p = get_place(id, mode)
    if p is None:
        raise HTTPException(404, "장소를 찾을 수 없습니다.")
    from .menus import restaurant_menu

    if refresh:
        refresh_allowed("menu", request.state.owner, "메뉴 새로 조회는 잠시 후 다시 시도해 주세요.")
    return restaurant_menu(p, force=refresh)


@app.post("/api/conditions/parse")
def parse(data: ParseInput):
    from .request_intent import interpret, resolved_patch

    parsed = interpret(data.text)
    patch = dict(resolved_patch(parsed, data.people, data.explicit_people))
    warnings = [
        "입력 글에서 확인한 활동·인원·예산·이동수단을 적용했어요. 폼에서 확인하고 수정할 수 있어요.",
        "추천 지역과 시작 위치가 같은 시·도인지 확인해 주세요.",
    ]
    if parsed["excluded"]:
        warnings.append("제외 요청은 코스 추천 시 장소 유형과 대조해 적용해요.")
    warnings.extend(parsed["warnings"])
    return dict(patch=patch, warnings=warnings, unparsed=data.text)


@app.post("/api/plans")
def create(data: Conditions, request: Request):
    from .recommendation_service import generate

    try:
        return generate(data, request.state.owner)
    except store.PlanTooLarge as exc:
        raise HTTPException(413, str(exc))


@app.get("/api/plans/{id}")
def get_plan(id: str, request: Request):
    row, plan = plan_row(id)
    plan["can_edit"] = row["owner"] == request.state.owner
    return plan


@app.post("/api/plans/{id}/prices")
def refresh_prices(id: str, request: Request):
    _, plan = plan_row(id, request.state.owner)
    refresh_allowed("price", request.state.owner, "단가 검색은 잠시 후 다시 시도해 주세요.")
    from .pricing import price_plans

    updated = price_plans([plan], force=True)[0]
    from .preferences import hard_blocks

    if hard_blocks(updated):
        raise HTTPException(
            409,
            "재조회 가격 또는 조건이 필수 조건을 넘어요. 필수 조건을 조정한 뒤 다시 추천해 주세요.",
        )
    from .plan_changes import save_change

    try:
        return save_change(updated, plan, request.state.owner)
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.get("/api/plans/{id}/restaurant-matches")
def matched_restaurants(id: str):
    _, plan = plan_row(id)
    from .restaurants import restaurant_matches

    return restaurant_matches(plan)


@app.get("/api/plans/{id}/restaurants")
def nearby_restaurants(id: str, request: Request, after_index: int = Query(default=0, ge=0, le=4)):
    _, plan = plan_row(id)
    from .restaurants import search_nearby

    key = "local-rate:" + request.state.owner
    if store.cached(key):
        raise HTTPException(429, "주변 식당 검색은 잠시 후 다시 시도해 주세요.")
    web_security.require_ip(
        "local-search",
        "DATEMATE_IP_LOCAL_SEARCHES_PER_MINUTE",
        30,
        "주변 식당 검색은 잠시 후 다시 시도해 주세요.",
    )
    store.cache(key, True, 1)
    try:
        return search_nearby(plan, after_index)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


class ReplaceInput(BaseModel):
    index: int = Field(ge=0, le=4)
    locked: list[int] = Field(default_factory=list, max_length=5)
    replacement_id: str | None = Field(default=None, max_length=150)


@app.get("/api/plans/{id}/meal-rescue")
def recommend_meal_rescue(id: str):
    _, plan = plan_row(id)
    from .restaurants import meal_rescue

    return meal_rescue(plan)


@app.post("/api/plans/{id}/alternatives")
def alternatives(id: str, data: ReplaceInput, request: Request):
    _, plan = plan_row(id, request.state.owner)
    try:
        from .pricing import price_plans

        options = price_plans(replacements(plan, data.index, data.locked))
        from .preferences import filter_required

        options = filter_required(options)
        for option in options:
            option["delta"]["cost"] = [option["total"][i] - plan["total"][i] for i in (0, 1)]
        return {"alternatives": options}
    except ValueError as exc:
        raise HTTPException(422, str(exc))


def route_refresh_allowed(plan, kind, owner, message):
    """실제 장소 코스에 자동차 구간이 있으면 길찾기를 다시 부르므로 재요청 제한을 건다."""
    from .leg_modes import uses_car

    conditions = (
        plan if isinstance(plan, Conditions) else Conditions.model_validate(plan["conditions"])
    )
    if conditions.mode == "real" and uses_car(conditions):
        refresh_allowed(kind, owner, message)


@app.post("/api/plans/{id}/replace")
def replace(id: str, data: ReplaceInput, request: Request):
    _, plan = plan_row(id, request.state.owner)
    route_refresh_allowed(
        plan,
        "replace",
        request.state.owner,
        "자동차 길찾기를 다시 확인하는 중이에요. 잠시 후 다시 바꿔 주세요.",
    )
    try:
        options = replacements(plan, data.index, data.locked)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    chosen = next(
        (p for p in options if p["places"][data.index]["id"] == data.replacement_id), None
    )
    if not chosen:
        raise HTTPException(422, "선택 조건을 만족하는 대체 장소가 없습니다.")
    from .pricing import price_plans

    updated = price_plans([chosen])[0]
    from .preferences import hard_blocks

    if hard_blocks(updated):
        raise HTTPException(409, "필수 조건을 충족하지 않아 교체할 수 없어요.")
    from .plan_changes import save_change

    try:
        return save_change(updated, plan, request.state.owner)
    except ValueError as exc:
        raise HTTPException(409, str(exc))


class LegModeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index: int = Field(ge=0, le=5)
    mode: TransportMode


class TransportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default: TransportMode | None = None
    legs: list[LegModeInput] = Field(default_factory=list, max_length=6)


@app.post("/api/plans/{id}/transport")
def change_transport(id: str, data: TransportInput, request: Request):
    """구간별 또는 전체 이동 수단을 바꿔 새 버전으로 저장한다. 되돌리기는 /undo."""
    from .leg_modes import Blocked, NoChange, apply_change, prepare_change

    if data.default is None and not data.legs:
        raise HTTPException(422, "바꿀 구간이나 이동 수단을 골라 주세요.")
    if len({leg.index for leg in data.legs}) != len(data.legs):
        raise HTTPException(422, "같은 구간을 두 번 골랐어요.")
    _, plan = plan_row(id, request.state.owner)
    try:
        prepared = prepare_change(plan, data.default, [(leg.index, leg.mode) for leg in data.legs])
    except NoChange as exc:
        raise HTTPException(422, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    route_refresh_allowed(
        prepared["conditions"],
        "transport",
        request.state.owner,
        "자동차 길찾기를 다시 확인하는 중이에요. 잠시 후 다시 바꿔 주세요.",
    )
    try:
        updated, summary = apply_change(plan, prepared)
    except Blocked as exc:
        raise HTTPException(409, str(exc))
    from .condition_audit import audit_plan
    from .preferences import hard_blocks

    blocked = hard_blocks(audit_plan(copy.deepcopy(updated)))
    if blocked:
        labels = ", ".join(dict.fromkeys(b["label"] for b in blocked))
        raise HTTPException(409, f"필수로 고른 조건({labels})을 지키지 못해 바꾸지 않았어요.")
    from .plan_changes import save_change

    try:
        saved = save_change(updated, plan, request.state.owner)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    saved["transport_change"] = summary
    return saved


@app.post("/api/plans/{id}/undo")
def undo(id: str, request: Request):
    row, plan = plan_row(id, request.state.owner)
    if not row["parent"]:
        raise HTTPException(422, "되돌릴 변경이 없습니다.")
    return plan_row(row["parent"], request.state.owner)[1]


@app.get("/api/plans/{id}/reviews")
def reviews(id: str, request: Request):
    row, _ = plan_row(id)
    return store.reviews(row["aggregate_key"], request.state.owner)


@app.put("/api/plans/{id}/review")
def review(id: str, data: ReviewInput, request: Request):
    row, _ = plan_row(id)
    web_security.require_ip(
        "review", "DATEMATE_IP_REVIEWS_PER_MINUTE", 20, "후기 작성은 잠시 후 다시 시도해 주세요."
    )
    try:
        store.put_review(row["aggregate_key"], request.state.owner, data)
    except ValueError as exc:
        raise HTTPException(429, str(exc))
    return store.reviews(row["aggregate_key"], request.state.owner)


@app.delete("/api/reviews/{id}")
def delete_review(id: str, request: Request):
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT author FROM reviews WHERE id=?", (id,)).fetchone()
        if not row:
            raise HTTPException(404, "후기를 찾을 수 없습니다.")
        if row["author"] != request.state.owner:
            raise HTTPException(403, "본인의 후기만 삭제할 수 있습니다.")
        db.execute("DELETE FROM reports WHERE review_id=?", (id,))
        db.execute("DELETE FROM reviews WHERE id=?", (id,))
    return {"deleted": True}


class ReportInput(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


@app.post("/api/reviews/{id}/report")
def report(id: str, data: ReportInput, request: Request):
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if not db.execute("SELECT 1 FROM reviews WHERE id=?", (id,)).fetchone():
            raise HTTPException(404, "후기를 찾을 수 없습니다.")
        db.execute(
            "INSERT INTO reports VALUES(?,?,?,?) ON CONFLICT(review_id,author) DO UPDATE SET reason=excluded.reason,created=excluded.created",
            (id, request.state.owner, data.reason, time.time()),
        )
    return {
        "reported": True,
        "notice": "신고 접수됨. 자동 삭제되지 않으며 관리자 검토가 필요합니다.",
    }


def scope_ids(kind, id, mode):
    if kind == "place":
        if not get_place(id, mode):
            raise HTTPException(404, "장소를 찾을 수 없습니다.")
        return [id]
    _, plan = plan_row(id)
    if plan["conditions"]["mode"] != mode:
        raise HTTPException(422, "일정 데이터 모드가 일치하지 않습니다.")
    return [p["id"] for p in plan["places"]]


@app.get("/api/chat/{kind}/{id}")
def chat_history(
    kind: Literal["place", "plan"],
    id: str,
    request: Request,
    mode: Literal["demo", "real"] = "demo",
):
    scope_ids(kind, id, mode)
    return {"messages": store.history(request.state.owner, f"{mode}:{kind}:{id}")}


@app.post("/api/chat/{kind}/{id}")
def chat(kind: Literal["place", "plan"], id: str, data: ChatInput, request: Request):
    if not store.reserve_budget(
        [("chat:" + request.state.owner, int(os.getenv("DATEMATE_USER_CHATS_PER_MINUTE", "6")))],
        int(time.time() // 60),
    ):
        raise HTTPException(
            429, "질문이 많아요. 잠시 후 다시 시도해 주세요.", headers={"Retry-After": "60"}
        )
    web_security.require_ip(
        "chat", "DATEMATE_IP_CHATS_PER_MINUTE", 12, "질문이 많아요. 잠시 후 다시 시도해 주세요."
    )
    ids = scope_ids(kind, id, data.mode)
    scope = f"{data.mode}:{kind}:{id}"
    from .plan_chat import answer_plan

    plan = plan_row(id)[1] if kind == "plan" else None
    result = answer_plan(plan, data.question) if plan else None
    if result is None:
        result = ask(
            ids,
            data.question,
            data.mode,
            store.history(request.state.owner, scope),
            plan=plan,
            owner=request.state.owner,
        )
    store.chat_save(request.state.owner, scope, data.question, result["answer"])
    return result


@app.get("/")
def home():
    # 파일 변경 시 URL도 바꿔 이전 maps.js와 새 app.js의 혼합 로딩을 방지한다.
    return HTMLResponse(versioned_page("index.html"), headers={"Cache-Control": "no-store"})


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.post("/api/plans/{id}/leisure-options")
def leisure_options(id: str, data: ReplaceInput, request: Request):
    _, plan = plan_row(id, request.state.owner)
    from .leisure import options, message as leisure_message

    try:
        diagnostics = {}
        rows = options(plan, data.index, data.locked, discover=True, diagnostics=diagnostics)
        return {
            "options": [
                {
                    "place": r["plan"]["places"][data.index],
                    "distance_m": r["distance_m"],
                    "delta": r["plan"]["delta"],
                    "sport": r["sport"],
                }
                for r in rows
            ],
            "message": leisure_message(Conditions.model_validate(plan["conditions"])),
            "diagnostics": diagnostics,
        }
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.post("/api/plans/{id}/leisure-select")
def leisure_select(id: str, data: ReplaceInput, request: Request):
    _, plan = plan_row(id, request.state.owner)
    from .leisure import options

    try:
        rows = options(plan, data.index, data.locked)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    chosen = next(
        (r["plan"] for r in rows if r["plan"]["places"][data.index]["id"] == data.replacement_id),
        None,
    )
    if not chosen:
        raise HTTPException(
            409, "현재 조건에 맞지 않거나 후보가 바뀌었어요. 주변 레저를 다시 확인해 주세요."
        )
    from .pricing import price_plans
    from .preferences import hard_blocks

    updated = price_plans([chosen])[0]
    if hard_blocks(updated):
        raise HTTPException(409, "필수 조건에 맞지 않아 교체하지 않았어요.")
    from .recommendation_summary import enrich

    enrich(updated)
    from .plan_changes import save_change

    try:
        return save_change(updated, plan, request.state.owner)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
