"""USV-generated alerts (USV O&M Manual section 7): site state machine,
planned downtime, rejected connections, clock skew, volume, platform and
security rules, escalation, limits API."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, select, update

from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
from app.models.ingested_event import IngestedEvent
from app.models.ingestion_token import IngestionToken
from app.models.monitoring import SiteState, UsvAlert, UsvNotification
from app.models.usv_user import UsvUser
from app.models.usv_user_site import UsvUserSite
from app.services.ingestion_worker import process_pending_events
from app.services.monitoring.rules import evaluate_volume, run_monitoring


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(settings, "monitor_loop_enabled", False)  # tests drive run_monitoring themselves
    monkeypatch.setattr(settings, "ingestion_worker_enabled", False)  # ...and process events themselves
    with TestClient(app) as c:
        yield c


def _login(client, username="platform.admin", password="DevOnly!PlatformAdmin1"):
    return {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'username': username, 'password': password}).json()['token']}"}


def _site(client, with_token=True):
    headers = _login(client)
    bu = client.post("/api/v1/business-units", json={"name": f"BU-{uuid.uuid4().hex[:6]}"}, headers=headers).json()
    site = client.post("/api/v1/site", json={"site_code": f"MON-{uuid.uuid4().hex[:8]}", "name": "Monitored",
                                             "business_unit_id": bu["business_unit_id"]}, headers=headers).json()
    token = None
    if with_token:
        token = client.post(f"/api/v1/sites/{site['site_id']}/ingestion-tokens", headers=headers).json()["token"]
    return uuid.UUID(site["site_id"]), token, headers


def _push(client, token, n=1, health=None):
    events = [{"eventId": f"TRB-{uuid.uuid4().hex}", "eventType": "ASSET_SNAPSHOT", "objectType": "asset",
               "objectId": f"A{i}", "occurredAt": datetime.now(timezone.utc).isoformat(), "payload": {"assetId": f"A{i}"}}
              for i in range(n)]
    body = {"events": events, **({"health": health} if health else {})}
    r = client.post("/api/v1/ingest/tribot/batch", json=body, headers={"Authorization": f"Bearer {token}"})
    db = SessionLocal()
    try:
        while process_pending_events(db)["processed"]:
            pass
    finally:
        db.close()
    return r


def _run(now=None):
    db = SessionLocal()
    try:
        run_monitoring(db, now or datetime.now(timezone.utc))
    finally:
        db.close()


def _alerts(site_id=None, rule_id=None, active=None):
    db = SessionLocal()
    try:
        q = select(UsvAlert)
        if site_id:
            q = q.where(UsvAlert.site_id == site_id)
        if rule_id:
            q = q.where(UsvAlert.rule_id == rule_id)
        if active is True:
            q = q.where(UsvAlert.status != "closed")
        return db.execute(q.order_by(UsvAlert.opened_at)).scalars().all()
    finally:
        db.close()


def _set_last_contact(site_id, when):
    db = SessionLocal()
    try:
        db.execute(update(IngestionToken).where(IngestionToken.site_id == site_id).values(last_used_at=when))
        db.commit()
    finally:
        db.close()


def _state(site_id):
    db = SessionLocal()
    try:
        return db.get(SiteState, site_id).state
    finally:
        db.close()


def test_site_added_token_issued_waiting_then_onboarded(client):
    site_id, token, _ = _site(client)
    assert [a.rule_id for a in _alerts(site_id)] == ["SU-01", "SU-02"]
    assert all(a.event_only and a.status == "closed" for a in _alerts(site_id))

    _run(datetime.now(timezone.utc) + timedelta(hours=25))           # no data after 24 h
    (waiting,) = _alerts(site_id, "SU-03", active=True)
    assert waiting.severity == "Warning"

    _push(client, token)
    _run()
    assert _alerts(site_id, "SU-03", active=True) == []
    assert len(_alerts(site_id, "SU-04")) == 1 and _state(site_id) == "healthy"


def test_silent_then_disconnected_then_reconnected(client):
    site_id, token, _ = _site(client)
    _push(client, token)
    now = datetime.now(timezone.utc)
    _run(now)

    _set_last_contact(site_id, now - timedelta(minutes=35))          # > 2 x 15 min
    _run(now)
    assert _state(site_id) == "silent" and _alerts(site_id, "SU-05", active=True)[0].severity == "Warning"

    _set_last_contact(site_id, now - timedelta(minutes=65))          # > 4 x 15 min
    _run(now)
    assert _state(site_id) == "disconnected"
    assert _alerts(site_id, "SU-05", active=True) == []
    assert _alerts(site_id, "SU-06", active=True)[0].severity == "Critical"

    _set_last_contact(site_id, now)
    _run(now + timedelta(minutes=1))
    assert _state(site_id) == "healthy" and _alerts(site_id, "SU-06", active=True) == []
    (back,) = _alerts(site_id, "SU-07")
    assert back.title.startswith("Site reconnected") and back.event_only


def test_planned_downtime_keeps_site_alerts_quiet(client):
    site_id, token, admin = _site(client)
    _push(client, token)
    now = datetime.now(timezone.utc)
    r = client.post(f"/api/v1/monitoring/sites/{site_id}/downtime", headers=admin, json={
        "starts_at": (now - timedelta(hours=1)).isoformat(), "ends_at": (now + timedelta(hours=2)).isoformat(),
        "reason": "substation maintenance"})
    assert r.status_code == 201
    _set_last_contact(site_id, now - timedelta(hours=3))
    _run(now)
    assert _alerts(site_id, "SU-05", active=True) == [] and _alerts(site_id, "SU-06", active=True) == []

    bad = client.post(f"/api/v1/monitoring/sites/{site_id}/downtime", headers=admin, json={
        "starts_at": now.isoformat(), "ends_at": (now - timedelta(hours=1)).isoformat(), "reason": "backwards"})
    assert bad.status_code == 422


def test_rejected_connections_and_revoked_token(client):
    site_id, token, admin = _site(client)
    token_id = token.split(".")[0]
    for _ in range(5):
        client.post("/api/v1/ingest/tribot/batch", json={"events": []},
                    headers={"Authorization": f"Bearer {token_id}.wrong-secret"})
    _run()
    (rejected,) = _alerts(site_id, "SU-08", active=True)
    assert rejected.severity == "Warning" and rejected.detail["last_10_min"]["bad_secret"] == 5

    client.delete(f"/api/v1/sites/{site_id}/ingestion-tokens/{token_id}", headers=admin)
    client.post("/api/v1/ingest/tribot/batch", json={"events": []}, headers={"Authorization": f"Bearer {token}"})
    _run()
    assert _alerts(site_id, "SU-08", active=True)[0].severity == "Critical"   # revoked token used

    ack = client.post(f"/api/v1/monitoring/alerts/{rejected.usv_alert_id}/acknowledge", headers=admin)
    assert ack.status_code == 200 and ack.json()["status"] == "closed"         # SU-08 closes on acknowledge


def test_clock_skew_alert(client):
    site_id, token, _ = _site(client)
    skewed = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()
    _push(client, token, health={"tribotTime": skewed})
    _run()
    assert _alerts(site_id, "SU-09", active=True)[0].detail["clock_skew_seconds"] < -1100


def test_volume_drop_against_the_sites_own_normal(client):
    site_id, token, _ = _site(client)
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        tenant = db.execute(select(IngestedEvent.tenant_id).limit(1)).scalar() or uuid.uuid4()
        rows = [{"event_id": f"VOL-{uuid.uuid4().hex}", "tenant_id": tenant, "site_id": site_id,
                 "event_type": "ASSET_SNAPSHOT", "object_type": "asset", "occurred_at": now,
                 "received_at": now - timedelta(hours=2 + h, minutes=m), "raw_payload": {},
                 "process_status": "processed"}
                for h in range(48) for m in range(0, 60, 2)]                    # 30/h for 2 days, none recently
        db.execute(insert(IngestedEvent), rows)
        db.commit()
        evaluate_volume(db, now)
        db.commit()
    finally:
        db.close()
    (vol,) = _alerts(site_id, "SU-10", active=True)
    assert vol.title.startswith("Event volume dropped") and vol.detail["last_hour"] == 0


def test_backlog_and_stalled_worker_then_recovery(client):
    site_id, token, _ = _site(client)
    client.post("/api/v1/ingest/tribot/batch", headers={"Authorization": f"Bearer {token}"}, json={"events": [
        {"eventId": f"TRB-{uuid.uuid4().hex}", "eventType": "X", "objectType": "asset", "objectId": "P",
         "occurredAt": datetime.now(timezone.utc).isoformat(), "payload": {"assetId": "P"}}]})
    later = datetime.now(timezone.utc) + timedelta(hours=1)          # nothing processed for an hour
    _run(later)
    assert _alerts(rule_id="PL-01", active=True)[0].severity == "Critical"
    assert _alerts(rule_id="PL-03", active=True)

    _push(client, token, n=0)                                         # drains the backlog
    _run(later)
    assert _alerts(rule_id="PL-01", active=True) == [] and _alerts(rule_id="PL-03", active=True) == []


def test_repeated_failed_logins(client):
    name = f"ghost-{uuid.uuid4().hex[:6]}"
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"username": name, "password": "nope"})
    _run()
    assert any(a.detail.get("username") == name for a in _alerts(rule_id="SE-01", active=True))


def test_alert_notifies_site_admin_then_escalates(client):
    site_id, token, admin = _site(client)
    db = SessionLocal()
    try:
        site_admin = db.execute(select(UsvUser).where(UsvUser.username == "site.admin")).scalar_one()
        db.add(UsvUserSite(user_id=site_admin.user_id, site_id=site_id))
        db.commit()
        site_admin_id = site_admin.user_id
    finally:
        db.close()
    _push(client, token)
    now = datetime.now(timezone.utc)
    _set_last_contact(site_id, now - timedelta(minutes=35))
    _run(now)
    (silent,) = _alerts(site_id, "SU-05", active=True)
    db = SessionLocal()
    try:
        first = db.execute(select(UsvNotification).where(UsvNotification.usv_alert_id == silent.usv_alert_id)).scalars().all()
        assert {n.user_id for n in first} == {site_admin_id} and first[0].level == "site_admin"
    finally:
        db.close()

    later = now + timedelta(minutes=31)                               # not acknowledged in time
    _set_last_contact(site_id, later - timedelta(minutes=35))         # still silent, not yet disconnected
    _run(later)
    db = SessionLocal()
    try:
        levels = {n.level for n in db.execute(select(UsvNotification).where(
            UsvNotification.usv_alert_id == silent.usv_alert_id)).scalars()}
        # escalated one level up: never to a BU admin of another BU (this
        # site's BU has none), so to a customer admin or, if none, platform admin
        assert "site_admin" in levels and "bu_admin" not in levels and len(levels) == 2
    finally:
        db.close()

    site_admin_headers = _login(client, "site.admin", "DevOnly!SiteAdmin1")
    mine = client.get("/api/v1/monitoring/notifications", params={"unreadOnly": True}, headers=site_admin_headers).json()
    assert any(n["usv_alert_id"] == str(silent.usv_alert_id) for n in mine)


def test_limits_api_respects_platform_bounds(client):
    site_id, _, admin = _site(client, with_token=False)
    bad = client.put(f"/api/v1/monitoring/sites/{site_id}/settings", headers=admin, json={"check_in_minutes": 1})
    assert bad.status_code == 422
    ok = client.put(f"/api/v1/monitoring/sites/{site_id}/settings", headers=admin,
                    json={"check_in_minutes": 30, "silent_after_intervals": 3, "disconnected_after_intervals": 6})
    assert ok.status_code == 200
    eff = ok.json()["effective"]
    assert (eff["check_in_minutes"], eff["silent_after_intervals"], eff["first_data_hours"]) == (30, 3, 24)


def test_health_summary_shape(client):
    r = client.get("/api/v1/monitoring/health-summary", headers=_login(client))
    body = r.json()
    assert r.status_code == 200
    assert set(body["site_counts"]) >= {"healthy", "silent", "disconnected", "waiting_first_data"}
    assert body["database"]["ok"] is True
    assert body["certificate"] == {"configured": False}


def test_escalation_reaches_only_the_sites_own_bu_admin(client):
    admin = _login(client)
    site_id, token, _ = _site(client)
    db = SessionLocal()
    try:
        from app.models.site import Site
        own_bu = db.get(Site, site_id).business_unit_id
    finally:
        db.close()
    other_bu = client.post("/api/v1/business-units", json={"name": f"BU-{uuid.uuid4().hex[:6]}"},
                           headers=admin).json()["business_unit_id"]
    names = {}
    for label, bu in (("own", str(own_bu)), ("other", other_bu)):
        name = f"bu-{label}-{uuid.uuid4().hex[:6]}"
        r = client.post("/api/v1/users", headers=admin, json={"username": name, "password": "Passw0rd!Passw0rd",
                                                             "role": "usv_bu_admin", "business_unit_id": bu})
        names[label] = r.json()["user_id"]

    _push(client, token)
    now = datetime.now(timezone.utc)
    _set_last_contact(site_id, now - timedelta(minutes=35))
    _run(now)                                                         # no site admin: goes straight to BU level
    (silent,) = _alerts(site_id, "SU-05", active=True)
    db = SessionLocal()
    try:
        notified = {str(n.user_id) for n in db.execute(select(UsvNotification).where(
            UsvNotification.usv_alert_id == silent.usv_alert_id, UsvNotification.level == "bu_admin")).scalars()}
    finally:
        db.close()
    assert notified == {names["own"]}
