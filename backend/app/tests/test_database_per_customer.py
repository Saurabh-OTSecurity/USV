"""Database per customer (MULTI_TENANT_POOL), end to end: provision two
customers, each sets up a site and token, Tribot pushes are routed by token
to the right customer database, the background worker serves every database,
and neither customer can see the other's data. The customer databases are
dropped afterwards."""
import uuid

import psycopg2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core import tenancy
from app.core.config import settings
from app.core.tenant_engines import reset_caches_for_tests
from app.main import _ingest_tick, app
from app.models.fleet_asset import FleetAsset
from app.models.tenant_registry import TenantRegistry


@pytest.fixture()
def pool_client(monkeypatch):
    monkeypatch.setattr(settings, "deployment_mode", tenancy.MULTI_TENANT_POOL)
    monkeypatch.setattr(settings, "monitor_loop_enabled", False)
    reset_caches_for_tests()
    tenancy._token_route_cache.clear()
    created: list[str] = []
    with TestClient(app) as c:
        c.created_customers = created
        yield c
    reset_caches_for_tests()
    # drop the customer databases this test created
    with tenancy.platform_session() as db:
        entries = db.query(TenantRegistry).filter(TenantRegistry.tenant_code.in_(created)).all()
        names = [e.database_name for e in entries]
        for e in entries:
            db.delete(e)
        db.commit()
    conn = psycopg2.connect(host=settings.database_host, port=settings.database_port, user=settings.database_user,
                            password=settings.database_password, dbname="postgres")
    conn.autocommit = True
    with conn.cursor() as cur:
        for name in names:
            cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    conn.close()


def _login(client, username, password, tenant_code=None):
    body = {"username": username, "password": password, **({"tenant_code": tenant_code} if tenant_code else {})}
    r = client.post("/api/v1/auth/login", json=body)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _new_customer(client, platform):
    code = f"T{uuid.uuid4().hex[:6].upper()}"
    r = client.post("/api/v1/platform/customers", headers=platform,
                    json={"tenant_code": code, "name": f"Customer {code}", "admin_username": "cust.admin"})
    assert r.status_code == 201, r.text
    client.created_customers.append(code)
    body = r.json()
    return code, _login(client, "cust.admin", body["admin_one_time_password"], tenant_code=code)


def _onboard_and_push(client, customer_admin, asset_id):
    bu = client.post("/api/v1/business-units", json={"name": "Power"}, headers=customer_admin).json()["business_unit_id"]
    site = client.post("/api/v1/site", json={"site_code": "PWR-01", "name": "Power Site 1", "business_unit_id": bu},
                       headers=customer_admin).json()["site_id"]
    token = client.post(f"/api/v1/sites/{site}/ingestion-tokens", headers=customer_admin).json()["token"]
    r = client.post("/api/v1/ingest/tribot/batch", headers={"Authorization": f"Bearer {token}"}, json={"events": [{
        "eventId": f"TRB-{uuid.uuid4().hex}", "eventType": "ASSET_SNAPSHOT", "objectType": "asset",
        "objectId": asset_id, "occurredAt": "2026-10-18T10:00:00Z", "payload": {"assetId": asset_id}}]})
    assert r.status_code == 202 and r.json()["accepted"] == 1, r.text
    return site


def test_each_customer_gets_its_own_database_and_sees_only_its_data(pool_client):
    client = pool_client
    platform = _login(client, "platform.admin", "DevOnly!PlatformAdmin1")
    code_a, admin_a = _new_customer(client, platform)
    code_b, admin_b = _new_customer(client, platform)

    # same site code in both customers is fine: separate databases
    site_a = _onboard_and_push(client, admin_a, "ASSET-OF-A")
    site_b = _onboard_and_push(client, admin_b, "ASSET-OF-B")

    _ingest_tick(purge=False)                                   # the worker serves every database

    assets_a = client.get("/api/v1/fleet/assets", headers=admin_a).json()
    assets_b = client.get("/api/v1/fleet/assets", headers=admin_b).json()
    assert [a["source_asset_id"] for a in assets_a] == ["ASSET-OF-A"]
    assert [a["source_asset_id"] for a in assets_b] == ["ASSET-OF-B"]
    assert client.get(f"/api/v1/site/{site_b}", headers=admin_a).status_code == 404

    # nothing leaked into the platform database
    with tenancy.platform_session() as db:
        assert db.execute(select(FleetAsset).where(
            FleetAsset.source_asset_id.in_(["ASSET-OF-A", "ASSET-OF-B"]))).first() is None

    customers = {c["tenant_code"] for c in client.get("/api/v1/platform/customers", headers=platform).json()}
    assert {code_a, code_b} <= customers


def test_only_platform_level_admins_manage_customers(pool_client):
    client = pool_client
    platform = _login(client, "platform.admin", "DevOnly!PlatformAdmin1")
    _, admin_a = _new_customer(client, platform)
    assert client.get("/api/v1/platform/customers", headers=admin_a).status_code == 403
    dup = client.post("/api/v1/platform/customers", headers=platform,
                      json={"tenant_code": client.created_customers[0], "name": "again", "admin_username": "x.admin"})
    assert dup.status_code == 409


def test_unknown_ingestion_token_is_refused_in_pool_mode(pool_client):
    r = pool_client.post("/api/v1/ingest/tribot/batch", json={"events": []},
                         headers={"Authorization": f"Bearer {uuid.uuid4()}.nope"})
    assert r.status_code == 401
