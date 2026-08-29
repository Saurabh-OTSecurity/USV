import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import engine
from app.main import app

NON_ADMIN_LOGINS = [
    ("site.admin", "DevOnly!SiteAdmin1"),
    ("l2.analyst", "DevOnly!L2Analyst1"),
    ("l1.operator", "DevOnly!L1Operator1"),
    ("auditor.user", "DevOnly!Auditor1"),
    ("viewer.user", "DevOnly!Viewer1"),
]


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _auth_header(client, username, password) -> dict:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _admin_header(client) -> dict:
    return _auth_header(client, "platform.admin", "DevOnly!PlatformAdmin1")


def _latest_rbac_denied_row():
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT event_type, actor_user_id, result FROM audit_log "
                "WHERE event_type = 'rbac_denied' ORDER BY created_at DESC LIMIT 1"
            )
        ).mappings().first()


def test_platform_admin_can_list_users(client):
    headers = _admin_header(client)
    response = client.get("/api/v1/users", headers=headers)

    assert response.status_code == 200
    usernames = {user["username"] for user in response.json()}
    assert "platform.admin" in usernames


def test_platform_admin_can_create_user(client):
    headers = _admin_header(client)
    new_username = f"created-{uuid.uuid4().hex[:8]}"

    response = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": new_username,
            "password": "SomeDevPassword1!",
            "role": "usv_viewer",
            "display_name": "Created User",
            "site_id": None,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == new_username
    assert body["role"] == "usv_viewer"
    assert "password_hash" not in body

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT password_hash FROM usv_user WHERE username = :username"),
            {"username": new_username},
        ).mappings().first()
    assert row is not None
    assert row["password_hash"] != "SomeDevPassword1!"
    assert row["password_hash"].startswith("$2b$")


@pytest.mark.parametrize(
    "username,password", NON_ADMIN_LOGINS, ids=[u for u, _ in NON_ADMIN_LOGINS]
)
def test_non_admin_roles_receive_403_on_list_users_with_audit_row(client, username, password):
    headers = _auth_header(client, username, password)
    response = client.get("/api/v1/users", headers=headers)

    assert response.status_code == 403
    assert response.json() == {
        "error": {"code": "FORBIDDEN", "message": "Insufficient role for this action"}
    }

    row = _latest_rbac_denied_row()
    assert row is not None
    assert row["result"] == "denied"


@pytest.mark.parametrize(
    "username,password", NON_ADMIN_LOGINS, ids=[u for u, _ in NON_ADMIN_LOGINS]
)
def test_non_admin_roles_receive_403_on_create_user_with_audit_row(client, username, password):
    headers = _auth_header(client, username, password)
    response = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": f"shouldnotexist-{uuid.uuid4().hex[:8]}",
            "password": "SomeDevPassword1!",
            "role": "usv_viewer",
        },
    )

    assert response.status_code == 403
    assert response.json() == {
        "error": {"code": "FORBIDDEN", "message": "Insufficient role for this action"}
    }

    row = _latest_rbac_denied_row()
    assert row is not None
    assert row["result"] == "denied"


def test_create_user_with_invalid_role_is_rejected_with_validation_error(client):
    headers = _admin_header(client)

    response = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": f"badrole-{uuid.uuid4().hex[:8]}",
            "password": "SomeDevPassword1!",
            "role": "not_a_real_role",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_user_with_duplicate_username_is_rejected_cleanly(client):
    headers = _admin_header(client)
    duplicate_username = f"dupe-{uuid.uuid4().hex[:8]}"

    first = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": duplicate_username,
            "password": "SomeDevPassword1!",
            "role": "usv_viewer",
        },
    )
    assert first.status_code == 200

    second = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": duplicate_username,
            "password": "AnotherDevPassword1!",
            "role": "usv_viewer",
        },
    )

    assert second.status_code == 409
    body = second.json()
    assert body["error"]["code"] == "USERNAME_ALREADY_EXISTS"
    assert "password" not in body["error"]["message"].lower()
    assert "insert into" not in body["error"]["message"].lower()

    # The failed insert must not have left the session unusable for
    # subsequent requests (IntegrityError requires a rollback before the
    # session can be reused).
    followup = client.get("/api/v1/users", headers=headers)
    assert followup.status_code == 200
