import uuid

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core.database import SessionLocal
from app.core.rbac import (
    ALL_ROLES,
    USV_PLATFORM_ADMIN,
    get_current_user,
    require_role,
)
from app.core.security import create_access_token
from app.models.usv_user import UsvUser


def _credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


class _FakeUser:
    def __init__(self, role: str):
        self.role = role


def test_require_role_allows_matching_role_through():
    dependency = require_role(USV_PLATFORM_ADMIN)
    user = _FakeUser(USV_PLATFORM_ADMIN)
    assert dependency(current_user=user) is user


@pytest.mark.parametrize("role", [r for r in ALL_ROLES if r != USV_PLATFORM_ADMIN])
def test_require_role_rejects_every_other_role_with_403(role):
    dependency = require_role(USV_PLATFORM_ADMIN)
    user = _FakeUser(role)

    with pytest.raises(HTTPException) as exc_info:
        dependency(current_user=user)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error"]["code"] == "FORBIDDEN"


def test_get_current_user_raises_401_with_no_token():
    db = SessionLocal()
    try:
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(credentials=None, db=db)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["error"]["code"] == "UNAUTHORIZED"
    finally:
        db.close()


def test_get_current_user_raises_401_with_malformed_token():
    db = SessionLocal()
    try:
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(credentials=_credentials("not-a-real-token"), db=db)
        assert exc_info.value.status_code == 401
    finally:
        db.close()


def test_get_current_user_raises_401_with_expired_token():
    import jwt
    from datetime import datetime, timedelta, timezone

    from app.core.config import settings
    from app.core.security import JWT_ALGORITHM

    now = datetime.now(timezone.utc)
    expired_payload = {
        "user_id": str(uuid.uuid4()),
        "role": "usv_viewer",
        "site_id": None,
        "iat": now - timedelta(minutes=60),
        "exp": now - timedelta(minutes=30),
    }
    expired_token = jwt.encode(expired_payload, settings.auth_secret_key, algorithm=JWT_ALGORITHM)

    db = SessionLocal()
    try:
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(credentials=_credentials(expired_token), db=db)
        assert exc_info.value.status_code == 401
    finally:
        db.close()


def test_get_current_user_raises_401_when_user_id_does_not_exist():
    token = create_access_token(user_id=str(uuid.uuid4()), role="usv_viewer", site_id=None)
    db = SessionLocal()
    try:
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(credentials=_credentials(token), db=db)
        assert exc_info.value.status_code == 401
    finally:
        db.close()


def test_get_current_user_raises_401_when_user_is_not_active():
    db = SessionLocal()
    try:
        inactive_user = UsvUser(
            username=f"inactive-{uuid.uuid4().hex[:8]}",
            password_hash="irrelevant-for-this-test",
            role="usv_viewer",
            status="disabled",
        )
        db.add(inactive_user)
        db.commit()
        db.refresh(inactive_user)

        token = create_access_token(user_id=str(inactive_user.user_id), role="usv_viewer", site_id=None)

        with pytest.raises(HTTPException) as exc_info:
            get_current_user(credentials=_credentials(token), db=db)
        assert exc_info.value.status_code == 401

        db.delete(inactive_user)
        db.commit()
    finally:
        db.close()
