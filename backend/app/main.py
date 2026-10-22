import asyncio
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import (
    auth, business_units, fleet, health, identity, ingest, ingestion_tokens, integrations, monitoring, platform, site,
    site_tribot, sso, tribot, users, usv,
)
from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.core.tenancy import iter_database_sessionmakers
from app.core.logging import configure_logging, get_logger
from app.core.security import decode_access_token
from app.services.audit_service import AuditService
from app.services.ingestion_worker import DEFAULT_BATCH_SIZE, process_pending_events, purge_processed_events
from app.services.monitoring.checks import api_errors
from app.services.monitoring.rules import run_monitoring

configure_logging()
logger = get_logger("app")

# How often the ingestion worker polls ingested_event when it is idle.
# Deliberately short: the table is the async-receive staging area (T-2), not
# a slow queue -- a real Tribot push should show up in fleet_* within
# seconds, not minutes. While a backlog exists the worker does not sleep
# between batches at all (see below).
_INGESTION_WORKER_INTERVAL_SECONDS = 5
_PURGE_INTERVAL_SECONDS = 3600


def _ingest_tick(purge: bool) -> bool:
    """One pass of the ingestion worker over every database (each customer's
    own database in pool mode). Returns True if any database had a full
    batch, i.e. probably more waiting. One failing database never stops the
    others."""
    more_waiting = False
    for label, factory in iter_database_sessionmakers():
        db = factory()
        try:
            counts = process_pending_events(db)
            handled = counts["processed"] + counts["failed"] + counts["skipped"]
            if handled:
                logger.info("ingestion worker [%s]: %s", label, counts)
            more_waiting = more_waiting or handled >= DEFAULT_BATCH_SIZE
            if purge:
                purged = purge_processed_events(db, settings.ingested_event_retention_days)
                if purged:
                    logger.info("ingestion worker [%s]: purged %d staged events older than %d days",
                                label, purged, settings.ingested_event_retention_days)
        except Exception:
            logger.exception("ingestion worker failed for database %s", label)
        finally:
            db.close()
    return more_waiting


async def _ingestion_worker_loop():
    last_purge = 0.0
    while True:
        more_waiting = False
        try:
            if settings.ingestion_worker_enabled:
                purge = time.monotonic() - last_purge >= _PURGE_INTERVAL_SECONDS
                if purge:
                    last_purge = time.monotonic()
                more_waiting = await asyncio.to_thread(_ingest_tick, purge)
        except Exception:
            logger.exception("ingestion worker tick failed")
        # A full batch somewhere means more is probably waiting: go again now.
        await asyncio.sleep(0 if more_waiting else _INGESTION_WORKER_INTERVAL_SECONDS)


# USV's own alert rules (O&M Manual section 7): site silent/disconnected,
# token problems, ingestion backlog, database/certificate/backup health,
# security -- evaluated once a minute.
_MONITORING_INTERVAL_SECONDS = 60


def _run_monitoring_everywhere() -> None:
    for label, factory in iter_database_sessionmakers():
        db = factory()
        try:
            run_monitoring(db)
        except Exception:
            logger.exception("monitoring failed for database %s", label)
        finally:
            db.close()


async def _monitoring_loop():
    while True:
        try:
            if settings.monitor_loop_enabled:
                await asyncio.to_thread(_run_monitoring_everywhere)
        except Exception:
            logger.exception("monitoring tick failed")
        await asyncio.sleep(_MONITORING_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("USV backend starting up (app_env=%s)", settings.app_env)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("database connection verified")
    except Exception:
        logger.exception("database connection failed at startup")

    worker_task = asyncio.create_task(_ingestion_worker_loop())
    monitoring_task = asyncio.create_task(_monitoring_loop())
    yield
    worker_task.cancel()
    monitoring_task.cancel()
    logger.info("USV backend shutting down")


app = FastAPI(title="Tribastion Site USV", lifespan=lifespan)


def _record_rbac_denied(request: Request) -> None:
    actor_user_id = None
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        try:
            payload = decode_access_token(auth_header[7:])
            actor_user_id = uuid.UUID(str(payload.get("user_id")))
        except Exception:
            actor_user_id = None

    db = SessionLocal()
    try:
        AuditService(db).record(
            event_type="rbac_denied",
            actor_user_id=actor_user_id,
            result="denied",
            source_ip=request.client.host if request.client else None,
        )
    finally:
        db.close()


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 403 and request.url.path.startswith("/api/v1/users"):
        _record_rbac_denied(request)

    if isinstance(exc.detail, dict) and "error" in exc.detail:
        content = exc.detail
    else:
        content = {"error": {"code": "HTTP_ERROR", "message": str(exc.detail)}}
    return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": {"code": "VALIDATION_ERROR", "message": str(exc)}},
    )


# Deliberately a middleware, not @app.exception_handler(Exception): FastAPI/
# Starlette special-case a handler registered for the bare `Exception` type
# by attaching it to ServerErrorMiddleware, the outermost layer, added
# outside of every add_middleware()-registered middleware regardless of
# ordering. A response built there never passes back through CORSMiddleware,
# so the browser sees a bare CORS failure instead of the actual error body
# (confirmed via a duplicate-username POST during Story Point 7 validation:
# the resulting 500 had no Access-Control-Allow-Origin header at all).
#
# Registered as a plain HTTP middleware instead, and registered BEFORE
# CORSMiddleware below: Starlette wraps add_middleware() calls so the one
# added LAST ends up OUTERMOST (closest to the client). Putting this
# try/except middleware first and CORSMiddleware second means CORS is the
# outermost layer and gets a chance to stamp headers on every response this
# middleware produces, including ones built from a caught exception.
@app.middleware("http")
async def catch_unhandled_exceptions(request: Request, call_next):
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.exception("unhandled exception while processing request")
        message = str(exc) if settings.app_env == "development" else "An unexpected error occurred"
        response = JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": {"code": "INTERNAL_ERROR", "message": message}},
        )
    api_errors.record(response.status_code)  # API error-rate alert (PL-07)
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(site.router)
app.include_router(usv.router)
app.include_router(integrations.router)
app.include_router(tribot.router)
app.include_router(users.router)
app.include_router(business_units.router)
app.include_router(ingestion_tokens.router)
app.include_router(ingest.router)
app.include_router(fleet.router)
app.include_router(monitoring.router)
app.include_router(platform.router)
app.include_router(identity.router)
app.include_router(sso.router)
app.include_router(site_tribot.router)
