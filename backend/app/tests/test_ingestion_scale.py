"""Many-site ingestion: batch receiver, verified-token cache, batched worker
transactions, staging retention, and fleet paging."""
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.core.database import SessionLocal
from app.main import app
from app.models.alert import Alert
from app.models.fleet_asset import FleetAsset
from app.models.ingested_event import IngestedEvent
from app.services import ingestion_token_service
from app.services.ingestion_worker import process_pending_events, purge_processed_events


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _admin_headers(client):
    response = client.post("/api/v1/auth/login", json={"username": "platform.admin", "password": "DevOnly!PlatformAdmin1"})
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _site_with_token(client) -> tuple[str, str, dict]:
    headers = _admin_headers(client)
    bu = client.post("/api/v1/business-units", json={"name": f"BU-{uuid.uuid4().hex[:6]}"}, headers=headers).json()
    site = client.post(
        "/api/v1/site",
        json={"site_code": f"SITE-SC-{uuid.uuid4().hex[:8]}", "name": "Scale Site", "business_unit_id": bu["business_unit_id"]},
        headers=headers,
    ).json()
    issued = client.post(f"/api/v1/sites/{site['site_id']}/ingestion-tokens", headers=headers).json()
    return site["site_id"], issued["token"], headers


def _envelope(object_type: str, object_id: str, payload: dict) -> dict:
    return {
        "eventId": f"TRB-{uuid.uuid4().hex}",
        "eventType": f"{object_type.upper()}_SNAPSHOT",
        "objectType": object_type,
        "objectId": object_id,
        "occurredAt": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }


def _drain(site_id: str) -> None:
    """Process everything pending (other tests' leftovers included)."""
    db = SessionLocal()
    try:
        while process_pending_events(db)["processed"]:
            pass
    finally:
        db.close()


def test_batch_ingest_accepts_dedupes_and_rejects_per_event(client):
    site_id, token, _ = _site_with_token(client)
    good = _envelope("asset", "A-1", {"assetId": "A-1", "name": "PLC-1"})
    malformed = {"eventId": "TRB-bad", "objectType": "asset"}  # missing required fields
    body = {"events": [good, good, malformed, _envelope("alert", "AL-1", {"alertId": "AL-1", "severity": "High"})]}

    response = client.post("/api/v1/ingest/tribot/batch", json=body, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 202
    data = response.json()
    assert (data["accepted"], data["duplicate"], data["rejected"]) == (3, 0, 1)
    assert [r["status"] for r in data["results"]] == ["accepted", "accepted", "rejected", "accepted"]
    assert data["results"][2]["eventId"] == "TRB-bad"

    # Re-sending the same batch is idempotent
    again = client.post("/api/v1/ingest/tribot/batch", json={"events": [good]}, headers={"Authorization": f"Bearer {token}"})
    assert again.json()["duplicate"] == 1

    _drain(site_id)
    db = SessionLocal()
    try:
        names = db.execute(select(FleetAsset.name).where(FleetAsset.site_id == uuid.UUID(site_id))).scalars().all()
        assert names == ["PLC-1"]
    finally:
        db.close()


def test_batch_ingest_requires_valid_token_and_caps_size(client):
    _, token, _ = _site_with_token(client)
    bad = client.post("/api/v1/ingest/tribot/batch", json={"events": []},
                      headers={"Authorization": f"Bearer {token.split('.')[0]}.wrong"})
    assert bad.status_code == 401

    too_many = {"events": [_envelope("asset", f"A-{i}", {"assetId": f"A-{i}"}) for i in range(501)]}
    response = client.post("/api/v1/ingest/tribot/batch", json=too_many, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 413


def test_verified_token_cache_skips_bcrypt_but_not_revocation(client, monkeypatch):
    site_id, token, headers = _site_with_token(client)
    auth = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/v1/ingest/tribot/batch", json={"events": []}, headers=auth).status_code == 202

    calls = []
    real_verify = ingestion_token_service.verify_ingestion_secret
    monkeypatch.setattr(ingestion_token_service, "verify_ingestion_secret",
                        lambda *a: calls.append(1) or real_verify(*a))
    start = time.monotonic()
    for _ in range(5):
        assert client.post("/api/v1/ingest/tribot/batch", json={"events": []}, headers=auth).status_code == 202
    assert calls == []  # served from the cache
    assert time.monotonic() - start < 1.0

    # A wrong secret for the same token_id is still checked (and refused)
    wrong = {"Authorization": f"Bearer {token.split('.')[0]}.not-the-secret"}
    assert client.post("/api/v1/ingest/tribot/batch", json={"events": []}, headers=wrong).status_code == 401

    # Revocation takes effect immediately despite the cached verification
    token_id = token.split(".")[0]
    assert client.delete(f"/api/v1/sites/{site_id}/ingestion-tokens/{token_id}", headers=headers).status_code == 200
    assert client.post("/api/v1/ingest/tribot/batch", json={"events": []}, headers=auth).status_code == 401


def test_worker_isolates_a_failing_event_inside_a_batch(client):
    site_id, token, _ = _site_with_token(client)
    events = [
        _envelope("asset", "OK-1", {"assetId": "OK-1", "name": "first"}),
        _envelope("asset", None, {"name": "no id anywhere"}),  # normalizer raises
        _envelope("asset", "OK-2", {"assetId": "OK-2", "name": "second"}),
    ]
    client.post("/api/v1/ingest/tribot/batch", json={"events": events}, headers={"Authorization": f"Bearer {token}"})
    _drain(site_id)

    db = SessionLocal()
    try:
        statuses = dict(db.execute(
            select(IngestedEvent.event_id, IngestedEvent.process_status)
            .where(IngestedEvent.event_id.in_([e["eventId"] for e in events]))
        ).all())
        assert [statuses[e["eventId"]] for e in events] == ["processed", "failed", "processed"]
        names = set(db.execute(select(FleetAsset.name).where(FleetAsset.site_id == uuid.UUID(site_id))).scalars())
        assert names == {"first", "second"}
    finally:
        db.close()


def test_database_error_falls_back_to_isolating_the_bad_event(client):
    """A value only the database rejects (longer than the column) fails the
    fast path at flush time; the batch is re-run event by event so only that
    event fails."""
    site_id, token, _ = _site_with_token(client)
    events = [
        _envelope("asset", "DB-1", {"assetId": "DB-1", "name": "fine"}),
        _envelope("asset", "DB-2", {"assetId": "DB-2", "device_type": "x" * 100}),  # column is String(64)
        _envelope("asset", "DB-3", {"assetId": "DB-3", "name": "also fine"}),
    ]
    client.post("/api/v1/ingest/tribot/batch", json={"events": events}, headers={"Authorization": f"Bearer {token}"})
    _drain(site_id)

    db = SessionLocal()
    try:
        statuses = dict(db.execute(
            select(IngestedEvent.event_id, IngestedEvent.process_status)
            .where(IngestedEvent.event_id.in_([e["eventId"] for e in events]))
        ).all())
        assert [statuses[e["eventId"]] for e in events] == ["processed", "failed", "processed"]
        names = set(db.execute(select(FleetAsset.name).where(FleetAsset.site_id == uuid.UUID(site_id))).scalars())
        assert names == {"fine", "also fine"}
    finally:
        db.close()


def test_repeated_object_in_one_batch_updates_a_single_row(client):
    """The prefetch cache must hand the second event the row the first one
    created, not insert a duplicate."""
    site_id, token, _ = _site_with_token(client)
    events = [_envelope("asset", "REP-1", {"assetId": "REP-1", "name": f"v{i}"}) for i in range(3)]
    client.post("/api/v1/ingest/tribot/batch", json={"events": events}, headers={"Authorization": f"Bearer {token}"})
    _drain(site_id)

    db = SessionLocal()
    try:
        names = db.execute(select(FleetAsset.name).where(FleetAsset.site_id == uuid.UUID(site_id))).scalars().all()
        assert names == ["v2"]
    finally:
        db.close()


def test_purge_removes_old_processed_events_but_keeps_failed(client):
    site_id, token, _ = _site_with_token(client)
    ok = _envelope("asset", "P-1", {"assetId": "P-1"})
    bad = _envelope("asset", None, {})
    client.post("/api/v1/ingest/tribot/batch", json={"events": [ok, bad]}, headers={"Authorization": f"Bearer {token}"})
    _drain(site_id)

    db = SessionLocal()
    try:
        db.execute(update(IngestedEvent).where(IngestedEvent.event_id.in_([ok["eventId"], bad["eventId"]]))
                   .values(received_at=datetime.now(timezone.utc) - timedelta(days=30)))
        db.commit()
        purge_processed_events(db, older_than_days=7)
        remaining = set(db.execute(select(IngestedEvent.event_id).where(
            IngestedEvent.event_id.in_([ok["eventId"], bad["eventId"]]))).scalars())
        assert remaining == {bad["eventId"]}
    finally:
        db.close()


def test_fleet_lists_are_paged_with_total_count(client):
    site_id, token, headers = _site_with_token(client)
    events = [_envelope("alert", f"PG-{i}", {"alertId": f"PG-{i}", "severity": "Low"}) for i in range(7)]
    client.post("/api/v1/ingest/tribot/batch", json={"events": events}, headers={"Authorization": f"Bearer {token}"})
    _drain(site_id)

    first = client.get("/api/v1/fleet/alerts", params={"siteId": site_id, "limit": 3}, headers=headers)
    second = client.get("/api/v1/fleet/alerts", params={"siteId": site_id, "limit": 3, "offset": 3}, headers=headers)
    rest = client.get("/api/v1/fleet/alerts", params={"siteId": site_id, "limit": 3, "offset": 6}, headers=headers)
    assert first.headers["X-Total-Count"] == "7"
    ids = [a["alert_id"] for page in (first, second, rest) for a in page.json()]
    assert len(ids) == 7 and len(set(ids)) == 7

    assert client.get("/api/v1/fleet/alerts", params={"limit": 5001}, headers=headers).status_code == 422
