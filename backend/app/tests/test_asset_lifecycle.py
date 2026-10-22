"""USV side of the O&M Manual's asset lifecycle (section 6), pushed topology
links (section 4) and heartbeat health (section 7)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import SessionLocal
from app.main import app
from app.models.alert import Alert
from app.models.audit_log import AuditLog
from app.models.fleet_asset import FleetAsset
from app.models.fleet_lifecycle import FleetAssetTombstone, FleetTopologyLink, SiteHealth
from app.models.ingested_event import IngestedEvent
from app.services.ingestion_worker import process_pending_events


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _login(client, username="platform.admin", password="DevOnly!PlatformAdmin1"):
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _site(client):
    headers = _login(client)
    bu = client.post("/api/v1/business-units", json={"name": f"BU-{uuid.uuid4().hex[:6]}"}, headers=headers).json()
    site = client.post("/api/v1/site", json={"site_code": f"LC-{uuid.uuid4().hex[:8]}", "name": "Lifecycle Site",
                                             "business_unit_id": bu["business_unit_id"]}, headers=headers).json()
    token = client.post(f"/api/v1/sites/{site['site_id']}/ingestion-tokens", headers=headers).json()["token"]
    return site["site_id"], {"Authorization": f"Bearer {token}"}, headers


def _env(object_type, object_id, payload, event_type=None, occurred_at=None):
    return {"eventId": f"TRB-{uuid.uuid4().hex}", "eventType": event_type or f"{object_type.upper()}_SNAPSHOT",
            "objectType": object_type, "objectId": object_id,
            "occurredAt": (occurred_at or datetime.now(timezone.utc)).isoformat(), "payload": payload}


def _push(client, auth, *events, health=None):
    body = {"events": list(events)}
    if health is not None:
        body["health"] = health
    r = client.post("/api/v1/ingest/tribot/batch", json=body, headers=auth)
    assert r.status_code == 202, r.text
    db = SessionLocal()
    try:
        while process_pending_events(db)["processed"] or process_pending_events(db)["skipped"]:
            pass
    finally:
        db.close()
    return r.json()


def _status(event):
    db = SessionLocal()
    try:
        return db.get(IngestedEvent, event["eventId"]).process_status
    finally:
        db.close()


def _assets(site_id):
    db = SessionLocal()
    try:
        return {a.source_asset_id: a for a in db.execute(
            select(FleetAsset).where(FleetAsset.site_id == uuid.UUID(site_id))).scalars()}
    finally:
        db.close()


def test_decommission_removes_asset_links_closes_alerts_and_audits(client):
    site_id, auth, _ = _site(client)
    _push(client, auth,
          _env("asset", "A1", {"assetId": "A1", "name": "PLC-1"}),
          _env("asset", "A2", {"assetId": "A2", "name": "PLC-2"}),
          _env("topology_link", "L1", {"linkId": "L1", "sourceNodeId": "A1", "targetNodeId": "A2", "protocol": "S7"}),
          _env("alert", "AL1", {"alertId": "AL1", "assetId": "A1", "status": "Open", "severity": "High"}))
    db = SessionLocal()
    alert = db.execute(select(Alert).where(Alert.source_alert_id == "AL1", Alert.site_id == uuid.UUID(site_id))).scalar_one()
    assert alert.asset_id is not None                                  # linked to its fleet asset
    db.close()

    decom = _env("asset", "A1", {"assetId": "A1", "reason": "replaced", "decommissionedBy": "site.admin",
                                  "decommissionedAt": datetime.now(timezone.utc).isoformat()},
                 event_type="ASSET_DECOMMISSIONED")
    _push(client, auth, decom)

    assert set(_assets(site_id)) == {"A2"}
    db = SessionLocal()
    try:
        assert db.execute(select(FleetTopologyLink).where(FleetTopologyLink.site_id == uuid.UUID(site_id))).first() is None
        alert = db.execute(select(Alert).where(Alert.source_alert_id == "AL1", Alert.site_id == uuid.UUID(site_id))).scalar_one()
        assert alert.status == "Closed" and alert.closed_reason == "asset decommissioned: replaced"
        assert alert.asset_id is None                                   # kept for history
        tomb = db.execute(select(FleetAssetTombstone).where(FleetAssetTombstone.site_id == uuid.UUID(site_id))).scalar_one()
        assert (tomb.source_asset_id, tomb.decommissioned_by, tomb.origin) == ("A1", "site.admin", "tribot")
        audit = db.execute(select(AuditLog).where(AuditLog.event_type == "fleet_asset_decommissioned")
                           .order_by(AuditLog.occurred_at.desc())).scalars().first()
        assert audit.detail["source_asset_id"] == "A1" and audit.detail["alerts_closed"] == 1
    finally:
        db.close()


def test_tombstone_ignores_older_events_and_restore_lifts_it(client):
    site_id, auth, _ = _site(client)
    now = datetime.now(timezone.utc)
    _push(client, auth, _env("asset", "B1", {"assetId": "B1"}, occurred_at=now - timedelta(hours=2)))
    _push(client, auth, _env("asset", "B1", {"assetId": "B1", "reason": "site closed"},
                             event_type="ASSET_DECOMMISSIONED", occurred_at=now - timedelta(hours=1)))

    late = _env("asset", "B1", {"assetId": "B1", "name": "stale"}, occurred_at=now - timedelta(hours=1, minutes=30))
    _push(client, auth, late)
    assert _status(late) == "skipped" and "B1" not in _assets(site_id)

    _push(client, auth, _env("asset", "B1", {"assetId": "B1", "restoredBy": "site.admin",
                                              "asset": {"assetId": "B1", "name": "restored"}},
                             event_type="ASSET_RESTORED", occurred_at=now))
    assert _assets(site_id)["B1"].name == "restored"                   # back at once, from the event itself
    _push(client, auth, _env("asset", "B1", {"assetId": "B1", "name": "back"}, occurred_at=now - timedelta(hours=3)))
    assert _assets(site_id)["B1"].name == "back"                       # restored: tombstone no longer applies


def test_inventory_flags_missing_assets_and_relisting_clears_them(client):
    site_id, auth, _ = _site(client)
    _push(client, auth, _env("asset", "C1", {"assetId": "C1"}), _env("asset", "C2", {"assetId": "C2"}))
    _push(client, auth, _env("site_inventory", None, {"assetIds": ["C1"], "count": 1}, event_type="INVENTORY_COMPLETE"))
    assets = _assets(site_id)
    assert assets["C2"].lifecycle_state == "missing_from_tribot" and assets["C1"].lifecycle_state == "active"

    _push(client, auth, _env("site_inventory", None, {"assetIds": ["C1", "C2"]}, event_type="INVENTORY_COMPLETE"))
    assert _assets(site_id)["C2"].lifecycle_state == "active"


def test_admin_confirms_or_dismisses_a_missing_asset(client):
    site_id, auth, admin = _site(client)
    _push(client, auth, _env("asset", "D1", {"assetId": "D1"}), _env("asset", "D2", {"assetId": "D2"}))
    _push(client, auth, _env("site_inventory", None, {"assetIds": []}, event_type="INVENTORY_COMPLETE"))
    assets = _assets(site_id)

    missing = client.get("/api/v1/fleet/assets", params={"siteId": site_id, "lifecycleState": "missing_from_tribot"},
                         headers=admin)
    assert missing.headers["X-Total-Count"] == "2"

    # not allowed for a role without admin rights
    viewer = _login(client, "viewer.user", "DevOnly!Viewer1")
    denied = client.post(f"/api/v1/fleet/assets/{assets['D1'].asset_id}/confirm-decommission",
                         json={"reason": "removed"}, headers=viewer)
    assert denied.status_code == 403

    r = client.post(f"/api/v1/fleet/assets/{assets['D1'].asset_id}/confirm-decommission",
                    json={"reason": "removed during outage"}, headers=admin)
    assert r.status_code == 200 and r.json()["origin"] == "usv_admin"
    r = client.post(f"/api/v1/fleet/assets/{assets['D2'].asset_id}/dismiss-missing", headers=admin)
    assert r.status_code == 200 and r.json()["lifecycle_state"] == "active"
    assert set(_assets(site_id)) == {"D2"}

    # confirming an asset that isn't missing is refused
    again = client.post(f"/api/v1/fleet/assets/{assets['D2'].asset_id}/confirm-decommission",
                        json={"reason": "nope"}, headers=admin)
    assert again.status_code == 409


def test_silent_state_from_tribot_is_stored(client):
    site_id, auth, _ = _site(client)
    _push(client, auth, _env("asset", "E1", {"assetId": "E1", "lifecycleState": "silent",
                                              "silentSince": "2026-10-18T10:00:00Z"}))
    asset = _assets(site_id)["E1"]
    assert asset.lifecycle_state == "silent" and asset.silent_since.hour == 10


def test_heartbeat_health_is_stored_with_clock_skew(client):
    site_id, auth, admin = _site(client)
    tribot_time = (datetime.now(timezone.utc) - timedelta(minutes=12)).isoformat().replace("+00:00", "Z")
    _push(client, auth, health={"tribotTime": tribot_time, "captureRunning": True, "diskFreePercent": 42.0})
    db = SessionLocal()
    try:
        row = db.get(SiteHealth, uuid.UUID(site_id))
        assert row.health["captureRunning"] is True
        assert 11 * 60 < row.clock_skew_seconds < 13 * 60
    finally:
        db.close()
    listed = client.get("/api/v1/fleet/site-health", params={"siteId": site_id}, headers=admin).json()
    assert listed[0]["health"]["diskFreePercent"] == 42.0


def test_topology_links_are_listed_per_site(client):
    site_id, auth, admin = _site(client)
    _push(client, auth, _env("topology_link", "L9", {"linkId": "L9", "sourceNodeId": "X", "targetNodeId": "Y",
                                                      "protocol": "Modbus", "ports": [502]}))
    r = client.get("/api/v1/fleet/topology-links", params={"siteId": site_id}, headers=admin)
    assert r.headers["X-Total-Count"] == "1"
    assert r.json()[0]["protocol"] == "Modbus" and r.json()[0]["ports"] == [502]


def test_related_across_sites_groups_by_cve_and_asset_type(client):
    cve = f"CVE-2026-{uuid.uuid4().int % 90000 + 10000}"
    site_a, auth_a, admin = _site(client)
    site_b, auth_b, _ = _site(client)
    for auth, plc in ((auth_a, "PA"), (auth_b, "PB")):
        _push(client, auth,
              _env("asset", plc, {"assetId": plc, "deviceType": "PLC"}),
              _env("asset", "WS", {"assetId": "WS", "deviceType": "Workstation"}),
              _env("alert", f"{plc}-1", {"alertId": f"{plc}-1", "assetId": plc, "cveId": cve, "status": "Open"}),
              _env("alert", f"{plc}-2", {"alertId": f"{plc}-2", "assetId": "WS", "cveId": cve, "status": "Open"}))
    groups = [g for g in client.get("/api/v1/fleet/correlation-groups", params={"acrossSitesOnly": True},
                                    headers=admin).json() if cve in g["correlation_key"]]
    by_key = {g["correlation_key"]: g for g in groups}
    assert set(by_key) == {f"cve:{cve}|type:plc", f"cve:{cve}|type:workstation"}
    assert set(by_key[f"cve:{cve}|type:plc"]["site_ids"]) == {site_a, site_b}
    assert by_key[f"cve:{cve}|type:plc"]["title"] == f"{cve} on PLC assets"


def test_site_summary_counts(client):
    site_id, auth, admin = _site(client)
    _push(client, auth,
          _env("asset", "S1", {"assetId": "S1"}),
          _env("asset", "S2", {"assetId": "S2", "lifecycleState": "silent"}),
          _env("alert", "AL-H", {"alertId": "AL-H", "severity": "High", "status": "Open"}),
          _env("alert", "AL-L", {"alertId": "AL-L", "severity": "Low", "status": "Open"}),
          _env("alert", "AL-X", {"alertId": "AL-X", "severity": "High", "status": "Closed"}))
    (row,) = client.get("/api/v1/fleet/site-summary", params={"siteIds": site_id}, headers=admin).json()
    assert (row["assets"], row["silent_assets"]) == (2, 1)
    assert row["open_alerts"] == {"high": 1, "low": 1}
