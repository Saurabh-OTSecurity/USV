import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import auth, health, integrations, site, users, usv
from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.core.logging import configure_logging, get_logger
from app.core.security import decode_access_token
from app.services.audit_service import AuditService

configure_logging()
logger = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("USV backend starting up (app_env=%s)", settings.app_env)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("database connection verified")
    except Exception:
        logger.exception("database connection failed at startup")
    yield
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
        return await call_next(request)
    except Exception as exc:
        logger.exception("unhandled exception while processing request")
        message = str(exc) if settings.app_env == "development" else "An unexpected error occurred"
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": {"code": "INTERNAL_ERROR", "message": message}},
        )


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
app.include_router(users.router)
