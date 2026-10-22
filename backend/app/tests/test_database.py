import uuid

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.core.database import engine
from app.db.seed import seed

EXPECTED_COLUMNS = {
    "site": {
        "site_id", "business_unit_id", "site_code", "name", "description", "timezone",
        "criticality", "status", "created_at", "updated_at",
    },
    "usv": {
        "usv_id", "site_id", "usv_code", "hostname", "installation_id",
        "version", "status", "last_heartbeat", "created_at", "updated_at",
    },
    "integration": {
        "integration_id", "site_id", "integration_type", "name", "provider",
        "version", "status", "is_fixed_engine", "last_success_at",
        "last_error_at", "created_at", "updated_at",
    },
    "sync_state": {
        "sync_id", "integration_id", "entity_type", "watermark",
        "last_started_at", "last_completed_at", "records_received",
        "records_created", "records_updated", "records_failed", "status",
        "last_error", "created_at", "updated_at",
    },
    "usv_user": {
        "user_id", "site_id", "business_unit_id", "username", "password_hash", "role",
        "display_name", "status", "last_login_at", "created_at", "updated_at",
    },
    "audit_log": {
        "event_id", "occurred_at", "event_type", "actor_user_id",
        "target_type", "target_id", "result", "source_ip", "detail",
        "created_at",
    },
}


def test_database_connection_succeeds():
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1


@pytest.mark.parametrize("table_name,expected_columns", EXPECTED_COLUMNS.items())
def test_table_has_expected_columns(table_name, expected_columns):
    inspector = inspect(engine)
    actual_columns = {col["name"] for col in inspector.get_columns(table_name)}
    assert expected_columns.issubset(actual_columns)


def test_seed_data_loads_without_error():
    seed()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM site")).scalar() >= 1
        assert conn.execute(text("SELECT count(*) FROM usv")).scalar() >= 1
        assert conn.execute(text("SELECT count(*) FROM integration")).scalar() >= 7
        assert conn.execute(text("SELECT count(*) FROM usv_user")).scalar() >= 6


def test_usv_site_id_unique_constraint_is_enforced():
    site_code = f"TEST-SITE-{uuid.uuid4().hex[:8]}"
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            business_unit_id = conn.execute(text("SELECT business_unit_id FROM business_unit LIMIT 1")).scalar()
            site_id = conn.execute(
                text(
                    "INSERT INTO site (site_code, name, business_unit_id) VALUES (:code, :name, :bu_id) "
                    "RETURNING site_id"
                ),
                {"code": site_code, "name": "Unique Constraint Test Site", "bu_id": business_unit_id},
            ).scalar()

            conn.execute(
                text(
                    "INSERT INTO usv (site_id, usv_code) VALUES (:site_id, :usv_code)"
                ),
                {"site_id": site_id, "usv_code": f"TEST-USV-A-{uuid.uuid4().hex[:8]}"},
            )

            with pytest.raises(IntegrityError):
                conn.execute(
                    text(
                        "INSERT INTO usv (site_id, usv_code) VALUES (:site_id, :usv_code)"
                    ),
                    {"site_id": site_id, "usv_code": f"TEST-USV-B-{uuid.uuid4().hex[:8]}"},
                )
        finally:
            trans.rollback()


def test_usv_user_role_check_constraint_rejects_invalid_role():
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            with pytest.raises(IntegrityError):
                conn.execute(
                    text(
                        "INSERT INTO usv_user (username, password_hash, role) "
                        "VALUES (:username, 'x', 'not_a_real_role')"
                    ),
                    {"username": f"bad-role-{uuid.uuid4().hex[:8]}"},
                )
        finally:
            trans.rollback()
