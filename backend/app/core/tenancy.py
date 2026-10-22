"""DEPLOYMENT_MODE-aware connection routing (ECC_USV_PLATFORM_SPEC.md
Section 3.5/6.3, T-1).

Scope note: this module is consulted by the new T-2/T-3 fleet/ingestion
surfaces and by tenant provisioning. The pre-existing routes (site, usv,
integrations, tribot, users, auth) still depend on app.core.rbac.get_db,
i.e. the single configured database -- correct and sufficient for
SINGLE_TENANT (this deployment's actual mode today), but NOT yet re-pointed
at a per-tenant database in MULTI_TENANT_POOL mode. Retrofitting those to
route through get_tenant_db is flagged as follow-up work, not done here, to
avoid touching working, already-tested endpoints as part of this pass.
"""
import uuid
from contextlib import contextmanager

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import decode_access_token
from app.core.tenant_engines import get_platform_sessionmaker, get_sessionmaker_for_database
from app.models.tenant_registry import TenantRegistry

SINGLE_TENANT = "SINGLE_TENANT"
MULTI_TENANT_POOL = "MULTI_TENANT_POOL"

_bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={"error": {"code": "UNAUTHORIZED", "message": "Authentication required"}},
    )


@contextmanager
def platform_session():
    """A session against the platform database (where TenantRegistry lives
    in MULTI_TENANT_POOL mode). In SINGLE_TENANT mode this is the same
    single configured database, since platform_database_url defaults to
    settings.database_url when not overridden."""
    factory = get_platform_sessionmaker()
    session = factory()
    try:
        yield session
    finally:
        session.close()


def resolve_tenant_database_name(tenant_id: uuid.UUID) -> str:
    with platform_session() as db:
        entry = db.get(TenantRegistry, tenant_id)
        if entry is None:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "TENANT_NOT_FOUND", "message": "Unknown tenant"}},
            )
        return entry.database_name


def resolve_tenant_database_name_by_code(tenant_code: str) -> tuple[uuid.UUID, str]:
    """Used only at login time in MULTI_TENANT_POOL mode, before a JWT (and
    therefore a tenant_id claim) exists yet."""
    with platform_session() as db:
        entry = db.query(TenantRegistry).filter_by(tenant_code=tenant_code).one_or_none()
        if entry is None:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "TENANT_NOT_FOUND", "message": "Unknown tenant_code"}},
            )
        return entry.tenant_id, entry.database_name


def session_for_tenant(tenant_id: uuid.UUID) -> Session:
    if settings.deployment_mode != MULTI_TENANT_POOL:
        return SessionLocal()
    database_name = resolve_tenant_database_name(tenant_id)
    return get_sessionmaker_for_database(database_name)()


def tenant_id_from_authorization(authorization: str | None) -> uuid.UUID | None:
    """The customer a request belongs to, if its token says it lives in a
    customer database (claim tenant_db). None for platform users, for
    SINGLE_TENANT mode, and for missing/invalid tokens (the route's own
    authentication then rejects those)."""
    if settings.deployment_mode != MULTI_TENANT_POOL or not authorization:
        return None
    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() != "bearer" or not credentials:
        return None
    try:
        payload = decode_access_token(credentials)
        if not payload.get("tenant_db") or not payload.get("tenant_id"):
            return None
        return uuid.UUID(str(payload["tenant_id"]))
    except (jwt.InvalidTokenError, ValueError, TypeError):
        return None


def session_for_request(authorization: str | None) -> Session:
    tenant_id = tenant_id_from_authorization(authorization)
    return session_for_tenant(tenant_id) if tenant_id is not None else SessionLocal()


# ── ingestion routing: a Tribot's ingestion token -> its customer's database ──

_token_route_cache: dict[uuid.UUID, uuid.UUID] = {}


def register_token_route(token_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    """Pool mode: remember which customer database holds this ingestion
    token, in the platform database, so a Tribot's push (which carries only
    the token) can be routed there."""
    if settings.deployment_mode != MULTI_TENANT_POOL:
        return
    from app.models.ingestion_token_route import IngestionTokenRoute

    with platform_session() as db:
        if db.get(IngestionTokenRoute, token_id) is None:
            db.add(IngestionTokenRoute(token_id=token_id, tenant_id=tenant_id))
            db.commit()
    _token_route_cache[token_id] = tenant_id


def session_for_ingestion_token(presented: str | None) -> Session:
    """The database to authenticate an ingest request against. Unknown or
    malformed tokens fall back to the platform database, where
    authentication then fails as it should."""
    if settings.deployment_mode != MULTI_TENANT_POOL or not presented:
        return SessionLocal()
    try:
        token_id = uuid.UUID(presented.split(".", 1)[0])
    except (ValueError, AttributeError):
        return SessionLocal()
    tenant_id = _token_route_cache.get(token_id)
    if tenant_id is None:
        from app.models.ingestion_token_route import IngestionTokenRoute

        with platform_session() as db:
            route = db.get(IngestionTokenRoute, token_id)
        if route is None:
            return SessionLocal()
        tenant_id = _token_route_cache[token_id] = route.tenant_id
    return session_for_tenant(tenant_id)


def iter_database_sessionmakers():
    """Every database the background workers must serve: the one database
    in SINGLE_TENANT mode; in pool mode the platform database plus each
    ready customer database. Yields (label, sessionmaker)."""
    if settings.deployment_mode != MULTI_TENANT_POOL:
        yield "default", SessionLocal
        return
    yield "platform", get_platform_sessionmaker()
    with platform_session() as db:
        tenants = db.query(TenantRegistry).filter(TenantRegistry.status == "ready").all()
    for tenant in tenants:
        yield tenant.tenant_code, get_sessionmaker_for_database(tenant.database_name)


def get_tenant_db(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme)):
    """FastAPI dependency: yields a Session bound to the caller's tenant
    database. SINGLE_TENANT mode: identical to app.core.rbac.get_db (a
    no-op routing decision, per Section 3.5). MULTI_TENANT_POOL mode:
    decodes the JWT's `tenant_id` claim, resolves it via TenantRegistry,
    and binds to that tenant's own engine/session -- without first needing
    a database session on any *other* database to do so."""
    if settings.deployment_mode != MULTI_TENANT_POOL:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()
        return

    if credentials is None or not credentials.credentials:
        raise _unauthorized()
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.InvalidTokenError:
        raise _unauthorized()

    tenant_id_raw = payload.get("tenant_id") if payload.get("tenant_db") else None
    if not tenant_id_raw:
        raise _unauthorized()
    try:
        tenant_id = uuid.UUID(str(tenant_id_raw))
    except (ValueError, TypeError):
        raise _unauthorized()

    db = session_for_tenant(tenant_id)
    try:
        yield db
    finally:
        db.close()


def get_current_user_scoped(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_tenant_db),
):
    """Like app.core.rbac.get_current_user, but resolves the user against
    the tenant-routed session from get_tenant_db rather than the single
    default database -- required for the new T-2/T-3 fleet/ingestion
    routes to work correctly in MULTI_TENANT_POOL mode, where a user's row
    lives in their own tenant's database, not a shared default one."""
    from app.models.usv_user import UsvUser  # local import: avoids a tenancy<->usv_user import cycle at module load

    if credentials is None or not credentials.credentials:
        raise _unauthorized()
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.InvalidTokenError:
        raise _unauthorized()
    try:
        user_id = uuid.UUID(str(payload.get("user_id")))
    except (ValueError, TypeError):
        raise _unauthorized()

    user = db.get(UsvUser, user_id)
    if user is None or user.status != "active":
        raise _unauthorized()
    return user
