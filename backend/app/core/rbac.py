import uuid

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import decode_access_token
from app.models.usv_user import UsvUser

USV_PLATFORM_ADMIN = "usv_platform_admin"
USV_SITE_ADMIN = "usv_site_admin"
USV_L2_ANALYST = "usv_l2_analyst"
USV_L1_OPERATOR = "usv_l1_operator"
USV_AUDITOR = "usv_auditor"
USV_VIEWER = "usv_viewer"

ALL_ROLES = (
    USV_PLATFORM_ADMIN,
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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
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
    if user is None or user.status != "active":
        raise _unauthorized()

    return user


def require_role(*allowed_roles: str):
    def dependency(current_user: UsvUser = Depends(get_current_user)) -> UsvUser:
        if current_user.role not in allowed_roles:
            raise _forbidden()
        return current_user

    return dependency
