import asyncio
import hashlib
import json
import logging
import re
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, time, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request as UrlRequest
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import Settings, get_settings
from .models import OpportunitySummaryInput, ReportInput
from .repository import ElasticsearchRepository
from .security import digest, token, verify
from .summaries import (
    OpenAISummarizer,
    OpportunitySummary,
    SummaryUnavailable,
    estimate_microusd,
    evidence_payload,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
MOUNTAIN = ZoneInfo("America/Denver")
COOKIE_NAME = "hivemind_session"
CSRF_COOKIE_NAME = "hivemind_csrf"
START_PAST_TOLERANCE = timedelta(minutes=5)
START_FUTURE_LIMIT = timedelta(days=7)
AVATAR_SEED = re.compile(r"[A-Za-z0-9_-]{1,128}")
MAX_AVATAR_BYTES = 1_000_000


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
    start = as_utc(payload.starts_at) if payload.starts_at else now
    if start < now - START_PAST_TOLERANCE:
        raise HTTPException(422, "report start cannot be more than five minutes in the past")
    if start > now + START_FUTURE_LIMIT:
        raise HTTPException(422, "report start cannot be more than seven days in the future")
    return start


def expiry_for(payload: ReportInput, now: datetime) -> datetime:
    start = start_for(payload, now)
    duration_minutes = {"15m": 15, "30m": 30, "45m": 45, "1h": 60, "75m": 75, "90m": 90, "105m": 105, "120m": 120}
    if payload.expiration in duration_minutes:
        result = start + timedelta(minutes=duration_minutes[payload.expiration])
    elif payload.expiration == "end_of_day":
        result = datetime.combine(start.astimezone(MOUNTAIN).date(), time.max, MOUNTAIN).astimezone(UTC)
    else:
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


def evidence_key(official: list[dict], reports: list[dict], window_minutes: int) -> tuple[str, str]:
    # A content address makes a cache entry invalid as soon as an active report,
    # source snapshot, or time-window evidence set changes.
    material = json.dumps(
        {"window_minutes": window_minutes, "official": official, "reports": reports},
        default=str, sort_keys=True, separators=(",", ":"),
    ).encode()
    digest_value = hashlib.sha256(material).hexdigest()
    return f"summary:{digest_value}", digest_value


def validate_summary_sources(summary: OpportunitySummary, official: list[dict], reports: list[dict]) -> None:
    _, eligible = evidence_payload(official, reports)
    for bullet in summary.bullets:
        if not bullet.text.strip() or not bullet.source_ids or not set(bullet.source_ids).issubset(eligible):
            raise SummaryUnavailable("summary had an unsupported citation")


async def current_opportunity_evidence(
    repository: ElasticsearchRepository, now: datetime, window_minutes: int
) -> tuple[list[dict], list[dict], dict | None]:
    window_end = now + timedelta(minutes=window_minutes)
    official, freshness = await repository.list_official_events_overlapping(now, window_end)
    reports = await repository.list_reports_for_opportunities(window_end)
    return official, reports, freshness


async def database_or_503(request: Request) -> ElasticsearchRepository:
    repository = get_repository(request)
    if not await repository.ready():
        logger.warning(
            "report request rejected: database unavailable",
            extra={"event.name": "hivemind.report.rejected", "hivemind.rejection.reason": "database"},
        )
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "database unavailable")
    return repository


def load_avatar_png(seed: str, avatar_service_url: str) -> bytes:
    """Fetch a bounded PNG from the fixed cluster-local RoboHash Service."""
    avatar_url = (
        f"{avatar_service_url.rstrip('/')}/robot/{quote(seed, safe='')}.png?set=set1&size=80x80"
    )
    request = UrlRequest(avatar_url, headers={"Accept": "image/png"})
    with urlopen(request, timeout=3) as response:
        if response.status != 200 or response.headers.get_content_type() != "image/png":
            raise ValueError("RoboHash returned an unexpected response")
        image = response.read(MAX_AVATAR_BYTES + 1)
    if len(image) > MAX_AVATAR_BYTES:
        raise ValueError("RoboHash avatar exceeds the maximum size")
    return image


async def fetch_avatar_png(seed: str, avatar_service_url: str) -> bytes:
    try:
        return await asyncio.to_thread(load_avatar_png, seed, avatar_service_url)
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        logger.info("Avatar proxy unavailable: %s", type(error).__name__)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "avatar unavailable") from error


async def owned_session(request: Request, repository: ElasticsearchRepository) -> tuple[str, dict]:
    value = request.cookies.get(COOKIE_NAME)
    if not value or "." not in value:
        logger.warning(
            "report request rejected: anonymous session required",
            extra={"event.name": "hivemind.report.rejected", "hivemind.rejection.reason": "session"},
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "anonymous session required")
    session_id, secret = value.split(".", 1)
    session = await repository.get_session(session_id)
    if not session or not verify(secret, session["secret_hash"]):
        logger.warning(
            "report request rejected: invalid browser session",
            extra={"event.name": "hivemind.report.rejected", "hivemind.rejection.reason": "session"},
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid browser session")
    return session_id, session


def create_app(
    settings: Settings | None = None, repository_factory=ElasticsearchRepository, summarizer_factory=OpenAISummarizer
) -> FastAPI:
    settings_override = settings

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime_settings = settings_override or get_settings()
        app.state.settings = runtime_settings
        repository = repository_factory(runtime_settings)
        app.state.repository = repository
        app.state.summarizer = summarizer_factory(runtime_settings) if runtime_settings.openai_summary_enabled else None
        try:
            await repository.initialize()
        except Exception:
            logger.warning("Elasticsearch is unavailable at startup; readiness will remain false")
        else:
            logger.info("HiveMind started", extra={"event.name": "hivemind.application.started"})
        yield
        if app.state.summarizer:
            await app.state.summarizer.close()
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

    @app.get("/avatars/{avatar_seed}.png")
    async def avatar(avatar_seed: str, request: Request):
        if not AVATAR_SEED.fullmatch(avatar_seed):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "avatar not found")
        image = await fetch_avatar_png(avatar_seed, request.app.state.settings.avatar_service_url)
        return Response(
            image,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400, stale-while-revalidate=604800"},
        )

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
                "summary_rate_window": -1,
                "summary_rate_count": 0,
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
            logger.warning(
                "report request rejected: CSRF validation failed",
                extra={"event.name": "hivemind.report.rejected", "hivemind.rejection.reason": "csrf"},
            )
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF validation failed")
        now = datetime.now(UTC)
        starts_at = start_for(payload, now)
        expires_at = expiry_for(payload, now)
        rate_window = int(now.timestamp() // runtime_settings.report_rate_limit_seconds)
        if not await repository.consume_report_slot(
            session_id, rate_window, runtime_settings.report_rate_limit_count
        ):
            logger.warning(
                "report request rejected: rate limit exceeded",
                extra={"event.name": "hivemind.report.rejected", "hivemind.rejection.reason": "rate_limit"},
            )
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
        try:
            await repository.create_report(report_id, document)
        except Exception:
            logger.error(
                "report persistence failed",
                extra={"event.name": "hivemind.report.persistence_failed"},
            )
            raise
        logger.info(
            "report created",
            extra={
                "event.name": "hivemind.report.created",
                "hivemind.report.category": payload.category,
                "hivemind.report.expiration": payload.expiration,
            },
        )
        return {"report": public_report({"id": report_id, **document})}

    @app.post("/api/opportunities/summary")
    async def opportunity_summary(payload: OpportunitySummaryInput, request: Request):
        repository = await database_or_503(request)
        session_id, session = await owned_session(request, repository)
        csrf_token = request.headers.get("X-CSRF-Token", "")
        if not csrf_token or not secrets.compare_digest(digest(csrf_token), session["csrf_hash"]):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF validation failed")
        now = datetime.now(UTC)
        official, reports, freshness = await current_opportunity_evidence(repository, now, payload.window_minutes)
        response = {
            "window_minutes": payload.window_minutes,
            "generated_at": now,
            "schedule_freshness": freshness["fetched_at"] if freshness else None,
            "official_events": official,
            "attendee_reports": [public_report(report) for report in reports],
            "selection_limited": len(official) == 40 or len(reports) == 40,
            "summary": None,
        }
        runtime_settings = request.app.state.settings
        if not runtime_settings.openai_summary_enabled:
            response["generation_status"] = "unavailable"
            response["generation_message"] = "AI summaries are not enabled. Source cards are shown instead."
            return response
        cache_id, evidence_hash = evidence_key(official, reports, payload.window_minutes)
        cached = await repository.get_opportunity_cache(cache_id, now)
        if cached:
            try:
                summary = OpportunitySummary.model_validate(cached["summary"])
                validate_summary_sources(summary, official, reports)
            except Exception:
                cached = None
            else:
                response["summary"] = summary.model_dump()
                response["generation_status"] = "cached"
                return response

        # Keep the cross-replica lock beyond the request timeout so the
        # accounting round trips and final evidence revalidation cannot open a
        # second paid request for the same evidence at the timeout boundary.
        lock_expires_at = now + timedelta(seconds=runtime_settings.openai_summary_timeout_seconds + 15)
        claimed = await repository.claim_opportunity_generation(
            cache_id, evidence_hash, payload.window_minutes, now, lock_expires_at
        )
        if not claimed:
            # Other replicas wait only for their existing single paid request;
            # this is coalescing, not an automatic paid retry.
            for _ in range(runtime_settings.openai_summary_timeout_seconds * 4):
                await asyncio.sleep(0.25)
                cached = await repository.get_opportunity_cache(cache_id, datetime.now(UTC))
                if cached:
                    try:
                        summary = OpportunitySummary.model_validate(cached["summary"])
                        validate_summary_sources(summary, official, reports)
                    except Exception:
                        break
                    response["summary"] = summary.model_dump()
                    response["generation_status"] = "coalesced"
                    return response
            response["generation_status"] = "unavailable"
            response["generation_message"] = "Summary generation is taking longer than expected. Source cards are shown instead."
            return response

        rate_window = int(now.timestamp() // runtime_settings.summary_rate_limit_seconds)
        if not await repository.consume_summary_slot(
            session_id, rate_window, runtime_settings.summary_rate_limit_count
        ):
            await repository.abandon_opportunity_generation(cache_id)
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "summary rate limit exceeded; please wait")
        reservation = estimate_microusd(
            runtime_settings.openai_summary_max_input_tokens,
            runtime_settings.openai_summary_max_output_tokens,
            runtime_settings,
        )
        month = now.strftime("%Y-%m")
        cap_microusd = int(runtime_settings.openai_monthly_cap_usd * 1_000_000)
        try:
            reserved = await repository.reserve_openai_budget(month, reservation, cap_microusd, now)
        except Exception as error:
            await repository.abandon_opportunity_generation(cache_id)
            logger.warning("OpenAI accounting unavailable: %s", type(error).__name__)
            response["generation_status"] = "unavailable"
            response["generation_message"] = "Summary accounting is unavailable. Source cards are shown instead."
            return response
        if not reserved:
            await repository.abandon_opportunity_generation(cache_id)
            response["generation_status"] = "budget_exhausted"
            response["generation_message"] = "The monthly AI summary budget is exhausted. Source cards are shown instead."
            return response

        try:
            summary, actual = await request.app.state.summarizer.generate(official, reports)
        except Exception as error:
            # Do not release an uncertain reservation: a timeout can mean the
            # provider accepted and billed the request even though we did not
            # receive a usable response.
            logger.warning("OpenAI summary unavailable: %s", type(error).__name__)
            response["generation_status"] = "unavailable"
            response["generation_message"] = "AI summary is temporarily unavailable. Source cards are shown instead."
            return response
        try:
            await repository.settle_openai_budget(month, reservation, actual, datetime.now(UTC))
            final_now = datetime.now(UTC)
            final_official, final_reports, final_freshness = await current_opportunity_evidence(
                repository, final_now, payload.window_minutes
            )
            validate_summary_sources(summary, final_official, final_reports)
            await repository.complete_opportunity_generation(
                cache_id, evidence_hash, payload.window_minutes, summary.model_dump(), final_now
            )
        except Exception as error:
            logger.warning("OpenAI summary could not be safely published: %s", type(error).__name__)
            response["generation_status"] = "unavailable"
            response["generation_message"] = "AI summary could not be safely published. Source cards are shown instead."
            return response
        response.update(
            {
                "generated_at": final_now,
                "schedule_freshness": final_freshness["fetched_at"] if final_freshness else None,
                "official_events": final_official,
                "attendee_reports": [public_report(report) for report in final_reports],
                "selection_limited": len(final_official) == 40 or len(final_reports) == 40,
                "summary": summary.model_dump(),
                "generation_status": "generated",
            }
        )
        return response

    return app


app = create_app()
