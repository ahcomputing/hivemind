import logging
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import Settings, get_settings
from .models import OpportunitySummaryInput, ReportInput
from .repository import ElasticsearchRepository
from .security import digest, token, verify

logger = logging.getLogger(__name__)
MOUNTAIN = ZoneInfo("America/Denver")
COOKIE_NAME = "hivemind_session"
CSRF_COOKIE_NAME = "hivemind_csrf"


def public_report(report: dict) -> dict:
    return {
        key: report[key]
        for key in (
            "id",
            "content",
            "location",
            "category",
            "expires_at",
            "created_at",
            "starts_at",
            "avatar_seed",
        )
        if key in report
    }


def as_utc(value: datetime, default_timezone: ZoneInfo = MOUNTAIN) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=default_timezone).astimezone(UTC)


def start_for(payload: ReportInput, now: datetime) -> datetime:
    return as_utc(payload.starts_at) if payload.starts_at else now


def expiry_for(payload: ReportInput, now: datetime) -> datetime:
    start = start_for(payload, now)
    duration_minutes = {"15m": 15, "30m": 30, "45m": 45, "1h": 60, "75m": 75, "90m": 90, "105m": 105, "120m": 120}
    if payload.expiration in duration_minutes:
        return start + timedelta(minutes=duration_minutes[payload.expiration])
    if payload.expiration == "end_of_day":
        return datetime.combine(start.astimezone(MOUNTAIN).date(), time.max, MOUNTAIN).astimezone(UTC)
    if payload.custom_expires_at is None:
        raise HTTPException(422, "custom expiration requires custom_expires_at")
    result = as_utc(payload.custom_expires_at)
    if result <= start:
        raise HTTPException(422, "expiration must be after the report start")
    if result <= now:
        raise HTTPException(422, "expiration must be in the future")
    return result


def get_repository(request: Request) -> ElasticsearchRepository:
    return request.app.state.repository


async def database_or_503(request: Request) -> ElasticsearchRepository:
    repository = get_repository(request)
    if not await repository.ready():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "database unavailable")
    return repository


async def owned_session(request: Request, repository: ElasticsearchRepository) -> tuple[str, dict]:
    value = request.cookies.get(COOKIE_NAME)
    if not value or "." not in value:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "anonymous session required")
    session_id, secret = value.split(".", 1)
    session = await repository.get_session(session_id)
    if not session or not verify(secret, session["secret_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid browser session")
    return session_id, session


def create_app(
    settings: Settings | None = None, repository_factory=ElasticsearchRepository
) -> FastAPI:
    settings_override = settings

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime_settings = settings_override or get_settings()
        app.state.settings = runtime_settings
        repository = repository_factory(runtime_settings)
        app.state.repository = repository
        try:
            await repository.initialize()
        except Exception:
            logger.warning("Elasticsearch is unavailable at startup; readiness will remain false")
        yield
        await repository.close()

    app = FastAPI(title="HiveMind", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory="hivemind/static"), name="static")
    templates = Jinja2Templates(directory="hivemind/templates")

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        return templates.TemplateResponse(request, "index.html", {})

    @app.get("/share", response_class=HTMLResponse)
    async def share(request: Request):
        return templates.TemplateResponse(request, "share.html", {})

    @app.get("/reports", response_class=HTMLResponse)
    async def report_feed(request: Request):
        return templates.TemplateResponse(request, "reports.html", {"poll_seconds": 15})

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz(request: Request):
        if not await get_repository(request).ready():
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "database unavailable")
        return {"status": "ready"}

    @app.post("/api/session/bootstrap")
    async def bootstrap(request: Request, response: Response):
        repository = await database_or_503(request)
        runtime_settings = request.app.state.settings
        existing = request.cookies.get(COOKIE_NAME)
        if existing and "." in existing:
            session_id, session_secret = existing.split(".", 1)
            existing_session = await repository.get_session(session_id)
            if existing_session and verify(session_secret, existing_session["secret_hash"]):
                csrf_token = request.cookies.get(CSRF_COOKIE_NAME)
                if not csrf_token or not verify(csrf_token, existing_session["csrf_hash"]):
                    csrf_token = token()
                    existing_session["csrf_hash"] = digest(csrf_token)
                    await repository.update_session(session_id, existing_session)
                response.set_cookie(
                    CSRF_COOKIE_NAME,
                    csrf_token,
                    httponly=False,
                    secure=runtime_settings.cookie_secure,
                    samesite="lax",
                    max_age=60 * 60 * 24 * 30,
                    path="/",
                )
                return {
                    "csrf_token": csrf_token,
                    "avatar_seed": existing_session["avatar_seed"],
                    "avatar_base_url": runtime_settings.avatar_base_url,
                    "existing": True,
                }
        session_id, session_secret, csrf_token, avatar_seed = (
            str(uuid.uuid4()),
            token(),
            token(),
            token(),
        )
        await repository.create_session(
            session_id,
            {
                "secret_hash": digest(session_secret),
                "csrf_hash": digest(csrf_token),
                "avatar_seed": avatar_seed,
                "created_at": datetime.now(UTC),
                "rate_window": -1,
                "rate_count": 0,
            },
        )
        response.set_cookie(
            COOKIE_NAME,
            f"{session_id}.{session_secret}",
            httponly=True,
            secure=runtime_settings.cookie_secure,
            samesite="lax",
            max_age=60 * 60 * 24 * 30,
            path="/",
        )
        response.set_cookie(
            CSRF_COOKIE_NAME,
            csrf_token,
            httponly=False,
            secure=runtime_settings.cookie_secure,
            samesite="lax",
            max_age=60 * 60 * 24 * 30,
            path="/",
        )
        return {
            "csrf_token": csrf_token,
            "avatar_seed": avatar_seed,
            "avatar_base_url": runtime_settings.avatar_base_url,
            "existing": False,
        }

    @app.get("/api/reports")
    async def reports(request: Request, category: str | None = None):
        rows = await (await database_or_503(request)).list_active_reports(category)
        return {"reports": [public_report(row) for row in rows], "timezone": "America/Denver"}

    @app.post("/api/reports", status_code=status.HTTP_201_CREATED)
    async def submit_report(payload: ReportInput, request: Request):
        repository = await database_or_503(request)
        runtime_settings = request.app.state.settings
        session_id, session = await owned_session(request, repository)
        csrf_token = request.headers.get("X-CSRF-Token", "")
        if not csrf_token or not secrets.compare_digest(digest(csrf_token), session["csrf_hash"]):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF validation failed")
        now = datetime.now(UTC)
        starts_at = start_for(payload, now)
        expires_at = expiry_for(payload, now)
        rate_window = int(now.timestamp() // runtime_settings.report_rate_limit_seconds)
        if not await repository.consume_report_slot(
            session_id, rate_window, runtime_settings.report_rate_limit_count
        ):
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS, "rate limit exceeded; please wait"
            )
        report_id = str(uuid.uuid4())
        document = {
            "content": payload.content,
            "location": payload.location,
            "category": payload.category,
            "expires_at": expires_at,
            "created_at": now,
            "starts_at": starts_at,
            "status": "active",
            "session_id": session_id,
            "avatar_seed": session["avatar_seed"],
        }
        await repository.create_report(report_id, document)
        return {"report": public_report({"id": report_id, **document})}

    @app.post("/api/opportunities/summary")
    async def opportunity_summary(payload: OpportunitySummaryInput, request: Request):
        """Return source cards now; paid synthesis remains an explicit opt-in."""
        repository = await database_or_503(request)
        _, session = await owned_session(request, repository)
        csrf_token = request.headers.get("X-CSRF-Token", "")
        if not csrf_token or not secrets.compare_digest(digest(csrf_token), session["csrf_hash"]):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF validation failed")
        now = datetime.now(UTC)
        window_end = now + timedelta(minutes=payload.window_minutes)
        official, freshness = await repository.list_official_events_overlapping(now, window_end)
        reports = await repository.list_reports_for_opportunities(window_end)
        response = {
            "window_minutes": payload.window_minutes,
            "generated_at": now,
            "schedule_freshness": freshness["fetched_at"] if freshness else None,
            "official_events": official,
            "attendee_reports": [public_report(report) for report in reports],
            "selection_limited": len(official) == 40 or len(reports) == 40,
            "summary": None,
        }
        if not request.app.state.settings.openai_summary_enabled:
            response["generation_status"] = "unavailable"
            response["generation_message"] = "AI summaries are not enabled. Source cards are shown instead."
            return response
        # The enabled implementation is introduced only with a reviewed model,
        # verified current prices, and a durable shared ledger.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "AI summary service is not configured")

    return app


app = create_app()
