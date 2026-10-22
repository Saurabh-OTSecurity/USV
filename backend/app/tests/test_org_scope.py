"""Organization levels and data scoping (USV O&M Manual sections 2 and 11):
BU admins, site-scoped users, customer admins, role changes (SE-04)."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
from app.models.monitoring import UsvAlert
from app.services.ingestion_worker import process_pending_events


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(settings, "monitor_loop_enabled", False)
    with TestClient(app) as c:
        yield c


def _login(client, username, password):
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _admin(client):
    return _login(client, "platform.admin", "DevOnly!PlatformAdmin1")


def _bu(client, headers):
    return client.post("/api/v1/business-units", json={"name": f"BU-{uuid.uuid4().hex[:6]}"},
                       headers=headers).json()["business_unit_id"]


def _site(client, headers, bu_id):
    r = client.post("/api/v1/site", json={"site_code": f"ORG-{uuid.uuid4().hex[:8]}", "name": "Org Site",
                                          "business_unit_id": bu_id}, headers=headers)
    return r


def _user(client, headers, role, **kw):
    name = f"{role.split('_')[-1]}-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/v1/users", headers=headers, json={"username": name, "password": "Passw0rd!Passw0rd",
                                                            "role": role, **kw})
    return r, name


def _push_asset(client, admin, site_id):
    token = client.post(f"/api/v1/sites/{site_id}/ingestion-tokens", headers=admin).json()["token"]
    client.post("/api/v1/ingest/tribot/batch", headers={"Authorization": f"Bearer {token}"}, json={"events": [{
        "eventId": f"TRB-{uuid.uuid4().hex}", "eventType": "ASSET_SNAPSHOT", "objectType": "asset",
        "objectId": "X1", "occurredAt": "2026-10-18T10:00:00Z", "payload": {"assetId": "X1"}}]})
    db = SessionLocal()
    try:
        while process_pending_events(db)["processed"]:
            pass
    finally:
        db.close()


def test_bu_admin_sees_and_manages_only_their_business_unit(client):
    admin = _admin(client)
    bu_a, bu_b = _bu(client, admin), _bu(client, admin)
    a1 = _site(client, admin, bu_a).json()["site_id"]
    b1 = _site(client, admin, bu_b).json()["site_id"]
    _push_asset(client, admin, a1)
    _push_asset(client, admin, b1)

    r, name = _user(client, admin, "usv_bu_admin", business_unit_id=bu_a)
    assert r.status_code == 200
    bu_admin = _login(client, name, "Passw0rd!Passw0rd")

    sites = {s["site_id"] for s in client.get("/api/v1/site", headers=bu_admin).json()}
    assert a1 in sites and b1 not in sites
    assets = {a["site_id"] for a in client.get("/api/v1/fleet/assets", headers=bu_admin).json()}
    assert assets == {a1}
    # even when explicitly asking for the other BU's site, nothing comes back
    assert client.get("/api/v1/fleet/assets", params={"siteId": b1}, headers=bu_admin).json() == []
    assert client.get(f"/api/v1/site/{b1}", headers=bu_admin).status_code == 404
    assert {b["business_unit_id"] for b in client.get("/api/v1/business-units", headers=bu_admin).json()} == {bu_a}

    # manage: own BU yes, other BU no
    assert _site(client, bu_admin, bu_a).status_code == 201
    assert _site(client, bu_admin, bu_b).status_code == 403
    assert client.post(f"/api/v1/sites/{a1}/ingestion-tokens", headers=bu_admin).status_code == 201
    assert client.post(f"/api/v1/sites/{b1}/ingestion-tokens", headers=bu_admin).status_code == 404
    assert client.post("/api/v1/business-units", json={"name": "nope"}, headers=bu_admin).status_code == 403


def test_site_scoped_viewer_sees_only_their_site_and_no_platform_alerts(client):
    admin = _admin(client)
    bu = _bu(client, admin)
    s1 = _site(client, admin, bu).json()["site_id"]
    s2 = _site(client, admin, bu).json()["site_id"]
    _push_asset(client, admin, s1)
    _push_asset(client, admin, s2)
    r, name = _user(client, admin, "usv_viewer", site_id=s1)
    viewer = _login(client, name, "Passw0rd!Passw0rd")

    assert {a["site_id"] for a in client.get("/api/v1/fleet/assets", headers=viewer).json()} == {s1}
    alerts = client.get("/api/v1/monitoring/alerts", headers=viewer).json()
    assert alerts and all(a["site_id"] == s1 for a in alerts)
    summary = client.get("/api/v1/monitoring/health-summary", headers=viewer).json()
    assert [s["site_id"] for s in summary["sites"]] == [s1] and "database" not in summary


def test_customer_admin_manages_people_but_cannot_grant_platform_admin(client):
    admin = _admin(client)
    r, name = _user(client, admin, "usv_customer_admin")
    customer_admin = _login(client, name, "Passw0rd!Passw0rd")

    ok, _ = _user(client, customer_admin, "usv_site_admin")
    assert ok.status_code == 200
    denied, _ = _user(client, customer_admin, "usv_platform_admin")
    assert denied.status_code == 403
    assert client.get("/api/v1/users", headers=customer_admin).status_code == 200


def test_role_change_raises_se04_and_audit(client):
    admin = _admin(client)
    bu = _bu(client, admin)
    site = _site(client, admin, bu).json()["site_id"]
    r, name = _user(client, admin, "usv_viewer")
    user_id = r.json()["user_id"]

    changed = client.put(f"/api/v1/users/{user_id}/role", headers=admin,
                         json={"role": "usv_site_admin", "site_id": site})
    assert changed.status_code == 200 and changed.json()["role"] == "usv_site_admin"
    db = SessionLocal()
    try:
        event = db.execute(select(UsvAlert).where(UsvAlert.rule_id == "SE-04")
                           .order_by(UsvAlert.opened_at.desc())).scalars().first()
        assert event.detail["username"] == name and event.detail["after"]["role"] == "usv_site_admin"
    finally:
        db.close()
    bad = client.put(f"/api/v1/users/{user_id}/role", headers=admin, json={"role": "usv_nobody"})
    assert bad.status_code == 422
