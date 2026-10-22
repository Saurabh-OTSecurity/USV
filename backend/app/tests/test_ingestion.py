import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.alert import Alert
from app.models.correlation_group import CorrelationGroup
from app.models.fleet_asset import FleetAsset
from app.services.ingestion_worker import process_pending_events


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _platform_admin_headers(client):
    response = client.post("/api/v1/auth/login", json={"username": "platform.admin", "password": "DevOnly!PlatformAdmin1"})
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _create_site(client, headers) -> str:
    bu = client.post("/api/v1/business-units", json={"name": f"BU-{uuid.uuid4().hex[:6]}"}, headers=headers)
    site = client.post(
        "/api/v1/site",
        json={
            "site_code": f"SITE-ING-{uuid.uuid4().hex[:8]}",
            "name": "Networked Tribot Site",
            "business_unit_id": bu.json()["business_unit_id"],
        },
        headers=headers,
    )
    return site.json()["site_id"]


def _issue_ingestion_token(client, headers, site_id: str) -> str:
    response = client.post(f"/api/v1/sites/{site_id}/ingestion-tokens", headers=headers)
    assert response.status_code == 201
    return response.json()["token"]


def _envelope(event_type: str, object_type: str, object_id: str, payload: dict) -> dict:
    return {
        "eventId": f"TRB-EVT-{uuid.uuid4().hex}",
        "eventType": event_type,
        "objectType": object_type,
        "objectId": object_id,
        "occurredAt": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }


def test_second_site_can_push_asset_and_alert_end_to_end(client):
    """The actual scenario: a second Tribot instance, on another site, pushes
    its data to ECC using a per-site ingestion credential, and that data
    ends up queryable in ECC's own storage -- not fetched live from Tribot."""
    admin_headers = _platform_admin_headers(client)
    site_id = _create_site(client, admin_headers)
    token = _issue_ingestion_token(client, admin_headers, site_id)
    ingest_headers = {"Authorization": f"Bearer {token}"}

    asset_envelope = _envelope(
        "ASSET_UPDATED", "asset", "tribot-asset-001",
        {"asset_id": "tribot-asset-001", "name": "PLC-17", "device_type": "plc", "risk_level": "high"},
    )
    response = client.post("/api/v1/ingest/tribot", json=asset_envelope, headers=ingest_headers)
    assert response.status_code == 202
    assert response.json() == {"status": "accepted", "eventId": asset_envelope["eventId"]}

    # Retried delivery of the exact same event is a no-op, not reprocessed.
    duplicate_response = client.post("/api/v1/ingest/tribot", json=asset_envelope, headers=ingest_headers)
    assert duplicate_response.json()["status"] == "duplicate"

    alert_envelope = _envelope(
        "ALERT_CREATED", "alert", "tribot-alert-001",
        {"alert_id": "tribot-alert-001", "severity": "critical", "status": "open", "cve_id": "CVE-2024-9999"},
    )
    client.post("/api/v1/ingest/tribot", json=alert_envelope, headers=ingest_headers)

    db = SessionLocal()
    try:
        counts = process_pending_events(db)
        assert counts["processed"] == 2
        assert counts["failed"] == 0

        asset = db.query(FleetAsset).filter_by(site_id=uuid.UUID(site_id), source_asset_id="tribot-asset-001").one()
        assert asset.name == "PLC-17"
        assert asset.risk_level == "high"

        alert = db.query(Alert).filter_by(site_id=uuid.UUID(site_id), source_alert_id="tribot-alert-001").one()
        assert alert.severity == "critical"
        assert alert.cve_id == "CVE-2024-9999"

        # keyed by CVE plus asset type (manual decision); this alert names no asset
        group = db.query(CorrelationGroup).filter_by(correlation_key="cve:CVE-2024-9999|type:unknown").one()
        assert str(alert.alert_id) in group.member_ids
    finally:
        db.close()


def test_ingest_rejects_unknown_or_revoked_credential(client):
    response = client.post(
        "/api/v1/ingest/tribot",
        json=_envelope("ASSET_UPDATED", "asset", "x", {"asset_id": "x"}),
        headers={"Authorization": f"Bearer {uuid.uuid4()}.not-a-real-secret"},
    )
    assert response.status_code == 401

    admin_headers = _platform_admin_headers(client)
    site_id = _create_site(client, admin_headers)
    issue_response = client.post(f"/api/v1/sites/{site_id}/ingestion-tokens", headers=admin_headers)
    token_id = issue_response.json()["token_id"]
    plaintext = issue_response.json()["token"]

    revoke_response = client.delete(f"/api/v1/sites/{site_id}/ingestion-tokens/{token_id}", headers=admin_headers)
    assert revoke_response.status_code == 200

    response = client.post(
        "/api/v1/ingest/tribot",
        json=_envelope("ASSET_UPDATED", "asset", "x", {"asset_id": "x"}),
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert response.status_code == 401


def test_ingest_does_not_trust_site_id_from_payload(client):
    """FR-2.2: site/tenant scoping comes only from the credential. A forged
    siteId in the envelope body must not let one site's data land under a
    different site."""
    admin_headers = _platform_admin_headers(client)
    real_site_id = _create_site(client, admin_headers)
    other_site_id = _create_site(client, admin_headers)
    token = _issue_ingestion_token(client, admin_headers, real_site_id)

    spoof_asset_id = f"spoof-{uuid.uuid4().hex[:8]}"
    envelope = _envelope("ASSET_UPDATED", "asset", spoof_asset_id, {"asset_id": spoof_asset_id})
    envelope["siteId"] = other_site_id  # attacker-controlled body field
    client.post("/api/v1/ingest/tribot", json=envelope, headers={"Authorization": f"Bearer {token}"})

    db = SessionLocal()
    try:
        process_pending_events(db)
        asset = db.query(FleetAsset).filter_by(source_asset_id=spoof_asset_id).one()
        assert str(asset.site_id) == real_site_id
        assert str(asset.site_id) != other_site_id
    finally:
        db.close()
