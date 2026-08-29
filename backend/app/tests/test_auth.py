import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.core.security import JWT_ALGORITHM
from app.main import app

SEEDED_USERS = [
    ("platform.admin", "DevOnly!PlatformAdmin1", "usv_platform_admin"),
    ("site.admin", "DevOnly!SiteAdmin1", "usv_site_admin"),
    ("l2.analyst", "DevOnly!L2Analyst1", "usv_l2_analyst"),
    ("l1.operator", "DevOnly!L1Operator1", "usv_l1_operator"),
    ("auditor.user", "DevOnly!Auditor1", "usv_auditor"),
    ("viewer.user", "DevOnly!Viewer1", "usv_viewer"),
]


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _latest_audit_row(event_type: str):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT event_type, actor_user_id, result, detail FROM audit_log "
                "WHERE event_type = :event_type ORDER BY created_at DESC LIMIT 1"
            ),
            {"event_type": event_type},
        ).mappings().first()


@pytest.mark.parametrize(
    "username,password,role", SEEDED_USERS, ids=[u for u, _, _ in SEEDED_USERS]
)
def test_login_succeeds_for_each_seeded_user(client, username, password, role):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})

    assert response.status_code == 200
    body = response.json()
    assert body["token"]
    assert body["user"]["username"] == username
    assert body["user"]["role"] == role

    me_response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me_response.status_code == 200
    assert me_response.json()["username"] == username


def test_login_rejects_wrong_password_with_generic_error_and_audit_row(client):
    response = client.post(
        "/api/v1/auth/login", json={"username": "platform.admin", "password": "definitely-wrong"}
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "UNAUTHORIZED", "message": "Invalid username or password"}
    }

    row = _latest_audit_row("login_failure")
    assert row is not None
    assert row["result"] == "failure"
    assert row["actor_user_id"] is not None
    assert row["detail"] == {"username": "platform.admin"}


def test_login_rejects_unknown_username_with_generic_error_and_audit_row(client):
    unknown_username = f"nobody-{uuid.uuid4().hex[:8]}"
    response = client.post(
        "/api/v1/auth/login", json={"username": unknown_username, "password": "whatever"}
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "UNAUTHORIZED", "message": "Invalid username or password"}
    }

    row = _latest_audit_row("login_failure")
    assert row is not None
    assert row["actor_user_id"] is None
    assert row["detail"] == {"username": unknown_username}


def test_me_returns_profile_without_password_hash(client):
    login_response = client.post(
        "/api/v1/auth/login", json={"username": "viewer.user", "password": "DevOnly!Viewer1"}
    )
    token = login_response.json()["token"]

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "viewer.user"
    assert body["role"] == "usv_viewer"
    assert "password_hash" not in body


def test_me_returns_401_with_no_token(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_me_returns_401_with_invalid_token(client):
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_me_returns_401_with_expired_token(client):
    now = datetime.now(timezone.utc)
    expired_payload = {
        "user_id": str(uuid.uuid4()),
        "role": "usv_viewer",
        "site_id": None,
        "iat": now - timedelta(minutes=60),
        "exp": now - timedelta(minutes=30),
    }
    expired_token = jwt.encode(expired_payload, settings.auth_secret_key, algorithm=JWT_ALGORITHM)

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert response.status_code == 401


def test_logout_succeeds_with_valid_token(client):
    login_response = client.post(
        "/api/v1/auth/login", json={"username": "l1.operator", "password": "DevOnly!L1Operator1"}
    )
    token = login_response.json()["token"]

    response = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
