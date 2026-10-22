"""Identity governance (USV O&M Manual sections 10-11): lockout, one-time
shares, forced password change, approved resets with escalation, disabling
a person, break-glass with two approvals, single sign-on into Tribot."""
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.core import secrets_store
from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
from app.models.identity import BreakGlassAccount, PasswordResetRequest
from app.models.monitoring import UsvAlert, UsvNotification
from app.services import identity_flows
from app.services.monitoring.rules import run_monitoring

GOOD = "Correct-Horse-Battery-9"


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "monitor_loop_enabled", False)
    monkeypatch.setattr(settings, "secrets_dir", str(tmp_path))      # test keys, never the real ones
    secrets_store.reset_for_tests()
    with TestClient(app) as c:
        yield c
    secrets_store.reset_for_tests()


def _login(client, username, password, ok=True):
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    if ok:
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["user"]
    return r


def _admin(client):
    return _login(client, "platform.admin", "DevOnly!PlatformAdmin1")[0]


def _site(client, admin, **kw):
    bu = client.post("/api/v1/business-units", json={"name": f"BU-{uuid.uuid4().hex[:6]}"}, headers=admin).json()
    site = client.post("/api/v1/site", headers=admin, json={"site_code": f"ID-{uuid.uuid4().hex[:8]}", "name": "Id Site",
                                                           "business_unit_id": bu["business_unit_id"], **kw}).json()
    return site["site_id"], bu["business_unit_id"]


def _user(client, admin, role, password=GOOD, **kw):
    name = f"{role.split('_')[-1]}-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/v1/users", headers=admin, json={"username": name, "password": password, "role": role, **kw})
    assert r.status_code == 200, r.text
    return name, r.json()["user_id"]


def test_lockout_after_five_failures_and_admin_unlock(client):
    admin = _admin(client)
    site, _ = _site(client, admin)
    name, uid = _user(client, admin, "usv_viewer", site_id=site)
    for _ in range(5):
        assert _login(client, name, "wrong-password", ok=False).status_code == 401
    assert _login(client, name, GOOD, ok=False).status_code == 401         # locked even with the right password

    db = SessionLocal()
    try:
        run_monitoring(db)
        assert any(a.detail.get("username") == name for a in db.execute(
            select(UsvAlert).where(UsvAlert.rule_id == "SE-01", UsvAlert.status != "closed")).scalars())
    finally:
        db.close()

    assert client.post(f"/api/v1/users/{uid}/unlock", headers=admin).json()["locked"] is False
    _login(client, name, GOOD)


def test_one_time_share_forced_change_and_policy(client):
    admin = _admin(client)
    site, _ = _site(client, admin)
    name, uid = _user(client, admin, "usv_l1_operator", site_id=site)
    share = client.post(f"/api/v1/users/{uid}/initial-password-share", headers=admin).json()
    assert "secret" not in share and share["share_path"].startswith("/share/")

    opened = client.post(f"/api/v1/secure-shares/{share['share_token']}/open").json()
    assert opened["username"] == name
    assert client.post(f"/api/v1/secure-shares/{share['share_token']}/open").status_code == 410   # once only
    temp = opened["secret"]

    headers, user = _login(client, name, temp)
    assert user["must_change_password"] is True
    blocked = client.get("/api/v1/fleet/assets", headers=headers)
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"

    short = client.post("/api/v1/auth/change-password", headers=headers,
                        json={"current_password": temp, "new_password": "short"})
    assert short.status_code == 422
    reuse = client.post("/api/v1/auth/change-password", headers=headers,
                        json={"current_password": temp, "new_password": temp})
    assert reuse.status_code == 422
    assert client.post("/api/v1/auth/change-password", headers=headers,
                       json={"current_password": temp, "new_password": GOOD + "x"}).status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401     # old session ended
    _login(client, name, GOOD + "x")


def test_approved_reset_with_reference_and_neutral_answer(client):
    admin = _admin(client)
    site, _ = _site(client, admin)
    sa_name, _ = _user(client, admin, "usv_site_admin", site_id=site)
    name, _ = _user(client, admin, "usv_viewer", site_id=site)
    site_admin, _ = _login(client, sa_name, GOOD)

    unknown = client.post("/api/v1/password-resets", json={"username": "nobody-" + uuid.uuid4().hex[:6]}).json()
    known = client.post("/api/v1/password-resets", json={"username": name}).json()
    assert unknown["message"] == known["message"] and unknown["reference"] and known["reference"]

    pending = client.get("/api/v1/password-resets/pending", headers=site_admin).json()
    (req,) = [p for p in pending if p["username"] == name]
    outsider, _ = _login(client, _user(client, admin, "usv_site_admin", site_id=_site(client, admin)[0])[0], GOOD)
    assert client.post(f"/api/v1/password-resets/{req['request_id']}/approve", headers=outsider).status_code == 403

    early = client.post("/api/v1/password-resets/complete", json={"reference": known["reference"], "new_password": GOOD + "!"})
    assert early.status_code == 409                                               # not approved yet
    assert client.post(f"/api/v1/password-resets/{req['request_id']}/approve", headers=site_admin).json()["status"] == "approved"
    done = client.post("/api/v1/password-resets/complete", json={"reference": known["reference"], "new_password": GOOD + "!"})
    assert done.status_code == 200
    again = client.post("/api/v1/password-resets/complete", json={"reference": known["reference"], "new_password": GOOD + "?"})
    assert again.status_code == 409
    _login(client, name, GOOD + "!")


def test_platform_admin_reset_needs_two_other_platform_admins(client):
    admin = _admin(client)
    target, _ = _user(client, admin, "usv_platform_admin")
    second, _ = _user(client, admin, "usv_platform_admin")
    ref = client.post("/api/v1/password-resets", json={"username": target}).json()["reference"]
    req_id = next(p["request_id"] for p in client.get("/api/v1/password-resets/pending", headers=admin).json()
                  if p["username"] == target)
    assert client.post(f"/api/v1/password-resets/{req_id}/approve", headers=admin).json()["status"] == "pending"
    second_headers, _ = _login(client, second, GOOD)
    assert client.post(f"/api/v1/password-resets/{req_id}/approve", headers=second_headers).json()["status"] == "approved"
    assert client.post("/api/v1/password-resets/status", json={"reference": ref}).json()["status"] == "approved"


def test_stale_reset_escalates_to_backup_and_raises_se02(client):
    admin = _admin(client)
    site, bu = _site(client, admin)
    _user(client, admin, "usv_site_admin", site_id=site)
    backup, backup_id = _user(client, admin, "usv_bu_admin", business_unit_id=bu)
    name, _ = _user(client, admin, "usv_viewer", site_id=site)
    client.post("/api/v1/password-resets", json={"username": name})
    db = SessionLocal()
    try:
        from app.models.usv_user import UsvUser
        uid = db.execute(select(UsvUser.user_id).where(UsvUser.username == name)).scalar_one()
        req = db.execute(select(PasswordResetRequest).where(PasswordResetRequest.user_id == uid)).scalar_one()
        db.execute(update(PasswordResetRequest).where(PasswordResetRequest.request_id == req.request_id)
                   .values(created_at=datetime.now(timezone.utc) - timedelta(hours=5)))
        db.commit()
        identity_flows.escalate_stale_resets(db)
        db.commit()
        assert db.execute(select(UsvAlert).where(UsvAlert.dedupe_key == f"SE-02|{req.request_id}")).scalar_one()
        assert db.execute(select(UsvNotification).where(UsvNotification.user_id == uuid.UUID(backup_id),
                                                        UsvNotification.level == "approver_backup")).first()
    finally:
        db.close()
    backup_headers, _ = _login(client, backup, GOOD)
    assert any(p["username"] == name and p["escalated"] for p in
               client.get("/api/v1/password-resets/pending", headers=backup_headers).json())


def test_disabling_a_person_ends_their_sessions(client):
    admin = _admin(client)
    site, _ = _site(client, admin)
    name, uid = _user(client, admin, "usv_l2_analyst", site_id=site)
    headers, _ = _login(client, name, GOOD)
    assert client.post(f"/api/v1/users/{uid}/disable", headers=admin).json()["status"] == "disabled"
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert _login(client, name, GOOD, ok=False).status_code == 401


def test_break_glass_needs_customer_and_tribastion_approval(client):
    admin = _admin(client)
    site, bu = _site(client, admin)
    sa_name, _ = _user(client, admin, "usv_site_admin", site_id=site)
    bu_name, _ = _user(client, admin, "usv_bu_admin", business_unit_id=bu)
    site_admin, _ = _login(client, sa_name, GOOD)
    bu_admin, _ = _login(client, bu_name, GOOD)

    req = client.post(f"/api/v1/sites/{site}/break-glass/requests", headers=site_admin,
                      json={"reason": "USV unreachable during outage"}).json()
    rid = req["request_id"]
    assert client.post(f"/api/v1/break-glass/requests/{rid}/approve", headers=site_admin).status_code == 403  # requester
    assert client.post(f"/api/v1/break-glass/requests/{rid}/open", headers=site_admin).status_code == 409    # not yet
    assert client.post(f"/api/v1/break-glass/requests/{rid}/approve", headers=bu_admin).json()["status"] == "pending"
    assert client.post(f"/api/v1/break-glass/requests/{rid}/approve", headers=admin).json()["status"] == "approved"

    opened = client.post(f"/api/v1/break-glass/requests/{rid}/open", headers=site_admin).json()
    assert opened["username"] == "breakglass" and len(opened["password"]) >= 20
    db = SessionLocal()
    try:
        assert db.execute(select(UsvAlert).where(UsvAlert.rule_id == "SE-03", UsvAlert.site_id == uuid.UUID(site))).first()
        account = db.get(BreakGlassAccount, uuid.UUID(site))
        old_hash = account.tribot_password_hash
        identity_flows.rotate_due_break_glass(db, datetime.now(timezone.utc) + timedelta(hours=25))
        db.commit()
        db.refresh(account)
        assert account.tribot_password_hash != old_hash and account.rotate_due_at is None
    finally:
        db.close()


def test_sso_assertion_role_mapping_and_directory(client):
    admin = _admin(client)
    site, _ = _site(client, admin, tribot_url="http://127.0.0.1:8101")
    sa_name, _ = _user(client, admin, "usv_site_admin", site_id=site)
    eng_name, _ = _user(client, admin, "usv_l2_analyst", site_id=site)
    viewer_name, _ = _user(client, admin, "usv_viewer", site_id=site)

    key = client.get("/api/v1/sso/public-key").json()
    site_code = client.get(f"/api/v1/site/{site}", headers=admin).json()["site_code"]
    for name, role in ((sa_name, "Admin"), (eng_name, "Engineer")):
        headers, _ = _login(client, name, GOOD)
        r = client.post("/api/v1/sso/tribot/assertion", headers=headers, json={"site_id": site}).json()
        claims = jwt.decode(r["assertion"], key["public_key_pem"], algorithms=["EdDSA"], audience=f"tribot:{site_code}")
        assert (claims["sub"], claims["role"], claims["site_code"]) == (name, role, site_code)
        assert r["redirect_url"].startswith("http://127.0.0.1:8101/#/sso?assertion=")

    viewer, _ = _login(client, viewer_name, GOOD)
    refused = client.post("/api/v1/sso/tribot/assertion", headers=viewer, json={"site_id": site})
    assert refused.status_code == 403 and "read-only" in refused.json()["error"]["message"]

    token = client.post(f"/api/v1/sites/{site}/ingestion-tokens", headers=admin).json()["token"]
    d = client.get("/api/v1/sso/tribot/directory", headers={"Authorization": f"Bearer {token}"}).json()
    roles = {u["username"]: u["role"] for u in d["users"]}
    assert roles[sa_name] == "Admin" and roles[eng_name] == "Engineer" and viewer_name not in roles
    assert d["break_glass"]["password_hash"].count(":") == 1 and d["usv_public_key"]["kid"] == key["kid"]
    assert client.get("/api/v1/sso/tribot/directory", headers={"Authorization": "Bearer nope.nope"}).status_code == 401
