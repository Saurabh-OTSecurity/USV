import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

LOGIN_CREDENTIALS = [
    ("platform.admin", "DevOnly!PlatformAdmin1"),
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


@pytest.mark.parametrize(
    "username,password", LOGIN_CREDENTIALS, ids=[u for u, _ in LOGIN_CREDENTIALS]
)
def test_list_usvs_returns_seeded_data_for_any_role(client, username, password):
    headers = _auth_header(client, username, password)
    response = client.get("/api/v1/usv", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert any(usv["usv_code"] == "USV-001" for usv in body)


def test_get_usv_detail_returns_correct_record(client):
    headers = _auth_header(client, "viewer.user", "DevOnly!Viewer1")
    list_response = client.get("/api/v1/usv", headers=headers)
    usv_id = list_response.json()[0]["usv_id"]

    response = client.get(f"/api/v1/usv/{usv_id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["usv_id"] == usv_id


def test_get_usv_detail_returns_404_for_nonexistent_uuid(client):
    headers = _auth_header(client, "viewer.user", "DevOnly!Viewer1")
    response = client.get(f"/api/v1/usv/{uuid.uuid4()}", headers=headers)

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "USV_NOT_FOUND", "message": "USV not found"}
    }


def test_list_usvs_returns_401_with_no_token(client):
    response = client.get("/api/v1/usv")
    assert response.status_code == 401


def test_get_usv_detail_returns_401_with_no_token(client):
    response = client.get(f"/api/v1/usv/{uuid.uuid4()}")
    assert response.status_code == 401
