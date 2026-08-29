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
def test_list_integrations_returns_seeded_data_for_any_role(client, username, password):
    headers = _auth_header(client, username, password)
    response = client.get("/api/v1/integrations", headers=headers)

    assert response.status_code == 200
    body = response.json()
    names = {integration["name"] for integration in body}
    assert {"Tribot", "Claroty", "Nozomi", "Wazuh Manager", "Wazuh Indexer"}.issubset(names)


def test_list_integrations_includes_is_fixed_engine_field(client):
    headers = _auth_header(client, "viewer.user", "DevOnly!Viewer1")
    response = client.get("/api/v1/integrations", headers=headers)

    body = {integration["name"]: integration["is_fixed_engine"] for integration in response.json()}
    assert body["Tribot"] is False
    assert body["Claroty"] is False
    assert body["Nozomi"] is False
    assert body["Wazuh Manager"] is True
    assert body["Wazuh Indexer"] is True


def test_get_integration_detail_returns_correct_record(client):
    headers = _auth_header(client, "viewer.user", "DevOnly!Viewer1")
    list_response = client.get("/api/v1/integrations", headers=headers)
    integration_id = list_response.json()[0]["integration_id"]

    response = client.get(f"/api/v1/integrations/{integration_id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["integration_id"] == integration_id


def test_get_integration_detail_returns_404_for_nonexistent_uuid(client):
    headers = _auth_header(client, "viewer.user", "DevOnly!Viewer1")
    response = client.get(f"/api/v1/integrations/{uuid.uuid4()}", headers=headers)

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "INTEGRATION_NOT_FOUND", "message": "Integration not found"}
    }


def test_list_integrations_returns_401_with_no_token(client):
    response = client.get("/api/v1/integrations")
    assert response.status_code == 401


def test_get_integration_detail_returns_401_with_no_token(client):
    response = client.get(f"/api/v1/integrations/{uuid.uuid4()}")
    assert response.status_code == 401
