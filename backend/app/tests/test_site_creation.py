import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _auth_header(client, username, password) -> dict:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _platform_admin_headers(client):
    return _auth_header(client, "platform.admin", "DevOnly!PlatformAdmin1")


def test_create_business_unit_then_site_end_to_end(client):
    headers = _platform_admin_headers(client)

    bu_response = client.post("/api/v1/business-units", json={"name": "Test BU"}, headers=headers)
    assert bu_response.status_code == 201
    business_unit_id = bu_response.json()["business_unit_id"]

    site_code = f"SITE-TEST-{uuid.uuid4().hex[:8]}"
    site_response = client.post(
        "/api/v1/site",
        json={
            "site_code": site_code,
            "name": "Second Plant (networked Tribot)",
            "business_unit_id": business_unit_id,
            "timezone": "UTC",
            "criticality": "high",
        },
        headers=headers,
    )
    assert site_response.status_code == 201
    body = site_response.json()
    assert body["site_code"] == site_code
    assert body["business_unit_id"] == business_unit_id
    assert body["status"] == "active"

    # Newly created site is visible via the regular list/detail endpoints.
    list_response = client.get("/api/v1/site", headers=headers)
    assert any(site["site_code"] == site_code for site in list_response.json())


def test_create_site_rejects_duplicate_site_code(client):
    headers = _platform_admin_headers(client)
    bu_response = client.post("/api/v1/business-units", json={"name": "Dup Test BU"}, headers=headers)
    business_unit_id = bu_response.json()["business_unit_id"]

    site_code = f"SITE-DUP-{uuid.uuid4().hex[:8]}"
    payload = {"site_code": site_code, "name": "First", "business_unit_id": business_unit_id}
    first = client.post("/api/v1/site", json=payload, headers=headers)
    assert first.status_code == 201

    second = client.post("/api/v1/site", json=payload, headers=headers)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "SITE_CODE_EXISTS"


def test_create_site_requires_admin_role(client):
    headers = _auth_header(client, "viewer.user", "DevOnly!Viewer1")
    response = client.post(
        "/api/v1/site",
        json={"site_code": "SITE-FORBIDDEN", "name": "x", "business_unit_id": str(uuid.uuid4())},
        headers=headers,
    )
    assert response.status_code == 403


def test_create_site_requires_authentication(client):
    response = client.post(
        "/api/v1/site",
        json={"site_code": "SITE-NOAUTH", "name": "x", "business_unit_id": str(uuid.uuid4())},
    )
    assert response.status_code == 401
