import uuid

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import decode_access_token
from app.models.usv_user import UsvUser

USV_PLATFORM_ADMIN = "usv_platform_admin"
# Organization levels (USV O&M Manual section 11): a customer admin manages
# one customer, a BU admin one business unit, a site admin their site(s).
USV_CUSTOMER_ADMIN = "usv_customer_admin"
USV_BU_ADMIN = "usv_bu_admin"
USV_SITE_ADMIN = "usv_site_admin"
USV_L2_ANALYST = "usv_l2_analyst"
USV_L1_OPERATOR = "usv_l1_operator"
USV_AUDITOR = "usv_auditor"
USV_VIEWER = "usv_viewer"

ALL_ROLES = (
    USV_PLATFORM_ADMIN,
    USV_CUSTOMER_ADMIN,
    USV_BU_ADMIN,
    USV_SITE_ADMIN,
    USV_L2_ANALYST,
    USV_L1_OPERATOR,
    USV_AUDITOR,
    USV_VIEWER,
)

_bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={"error": {"code": "UNAUTHORIZED", "message": "Authentication required"}},
    )


def _forbidden() -> HTTPException:
    return HTTPException(
        status_code=403,
        detail={"error": {"code": "FORBIDDEN", "message": "Insufficient role for this action"}},
    )


def get_db(request: Request):
    """The session for this request. SINGLE_TENANT: the one database.
    MULTI_TENANT_POOL (one database per customer): a token whose tenant_db
    claim is set routes to that customer's database; anything else (login,
    platform users) uses the platform database. Every route depends on this,
    so routing happens in one place."""
    from app.core.tenancy import session_for_request  # local: tenancy imports models that import rbac's siblings

    db = session_for_request(request.headers.get("authorization"))
    try:
        yield db
    finally:
        db.close()


# Reachable while a password change is required (issued or reset password).
_PASSWORD_CHANGE_ALLOWED_PATHS = ("/api/v1/auth/change-password", "/api/v1/auth/me", "/api/v1/auth/logout")


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
    request: Request = None,  # injected by FastAPI; optional for direct callers
) -> UsvUser:
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
    if user is None or user.status != "active" or user.locked_at is not None:
        raise _unauthorized()
    # Sessions ended by a password reset or by disabling the person. iat has
    # one-second resolution, so compare whole seconds.
    revoked = user.sessions_revoked_before
    if revoked is not None and int(payload.get("iat", 0)) < int(revoked.timestamp()):
        raise _unauthorized()
    if user.must_change_password and (request is None or request.url.path not in _PASSWORD_CHANGE_ALLOWED_PATHS):
        raise HTTPException(status_code=403, detail={"error": {
            "code": "PASSWORD_CHANGE_REQUIRED", "message": "Set a new password before continuing"}})

    return user


def require_role(*allowed_roles: str):
    def dependency(current_user: UsvUser = Depends(get_current_user)) -> UsvUser:
        if current_user.role not in allowed_roles:
            raise _forbidden()
        return current_user

    return dependency
