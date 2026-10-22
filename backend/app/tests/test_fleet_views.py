import time
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.main import app
from app.models.ingested_event import IngestedEvent
from app.services.ingestion_worker import process_pending_events


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _admin_headers(client):
    response = client.post("/api/v1/auth/login", json={"username": "platform.admin", "password": "DevOnly!PlatformAdmin1"})
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _create_bu(client, headers) -> str:
    return client.post("/api/v1/business-units", json={"name": f"BU-{uuid.uuid4().hex[:6]}"}, headers=headers).json()[
        "business_unit_id"
    ]


def _create_site(client, headers, business_unit_id: str) -> str:
    return client.post(
        "/api/v1/site",
        json={"site_code": f"SITE-{uuid.uuid4().hex[:8]}", "name": "Site", "business_unit_id": business_unit_id},
        headers=headers,
    ).json()["site_id"]


def _push_asset(client, site_id: str, asset_name: str) -> None:
    token = client.post(f"/api/v1/sites/{site_id}/ingestion-tokens", headers=_ADMIN_HEADERS_CACHE[0]).json()["token"]
    envelope = {
        "eventId": f"EVT-{uuid.uuid4().hex}",
        "eventType": "ASSET_UPDATED",
        "objectType": "asset",
        "objectId": asset_name,
        "occurredAt": datetime.now(timezone.utc).isoformat(),
        "payload": {"asset_id": asset_name, "name": asset_name},
    }
    response = client.post("/api/v1/ingest/tribot", json=envelope, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 202


_ADMIN_HEADERS_CACHE = [None]


def test_site_wise_bu_compiled_and_comprehensive_views(client):
    """The actual thing the user asked for: run Tribot at more than one
    site, and be able to see one site's data alone, one Business Unit's
    data compiled, and everything compiled across the whole deployment."""
    headers = _admin_headers(client)
    _ADMIN_HEADERS_CACHE[0] = headers

    bu_a = _create_bu(client, headers)
    bu_b = _create_bu(client, headers)
    site_a1 = _create_site(client, headers, bu_a)
    site_a2 = _create_site(client, headers, bu_a)
    site_b1 = _create_site(client, headers, bu_b)

    _push_asset(client, site_a1, f"asset-a1-{uuid.uuid4().hex[:6]}")
    _push_asset(client, site_a2, f"asset-a2-{uuid.uuid4().hex[:6]}")
    _push_asset(client, site_b1, f"asset-b1-{uuid.uuid4().hex[:6]}")

    # Drain rather than assert a count: the app's own background ingestion
    # worker (started by TestClient's lifespan) may claim some of these three
    # events first (FOR UPDATE SKIP LOCKED); what matters is the views below.
    db = SessionLocal()
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            process_pending_events(db)
            # a plain count also sees rows another worker holds locked
            if not db.execute(select(func.count()).where(IngestedEvent.process_status == "pending")).scalar():
                break
            time.sleep(0.1)
    finally:
        db.close()

    # Site-wise: exactly that site's one asset.
    site_wise = client.get("/api/v1/fleet/assets", params={"siteId": site_a1}, headers=headers).json()
    assert len(site_wise) == 1
    assert site_wise[0]["site_id"] == site_a1

    # BU-compiled: both of BU A's sites, none of BU B's.
    bu_compiled = client.get("/api/v1/fleet/assets", params={"businessUnitId": bu_a}, headers=headers).json()
    assert {a["site_id"] for a in bu_compiled} == {site_a1, site_a2}

    # Comprehensive (no filter): every site across the whole deployment.
    comprehensive = client.get("/api/v1/fleet/assets", headers=headers).json()
    seen_site_ids = {a["site_id"] for a in comprehensive}
    assert {site_a1, site_a2, site_b1}.issubset(seen_site_ids)


def test_business_unit_with_no_sites_returns_empty_not_everything(client):
    headers = _admin_headers(client)
    _ADMIN_HEADERS_CACHE[0] = headers
    empty_bu = _create_bu(client, headers)

    response = client.get("/api/v1/fleet/assets", params={"businessUnitId": empty_bu}, headers=headers)
    assert response.status_code == 200
    assert response.json() == []
