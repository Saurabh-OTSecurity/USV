import uuid

from sqlalchemy import create_engine, inspect, text

from app.core.config import settings
from app.core.tenant_engines import get_sessionmaker_for_database, reset_caches_for_tests
from app.models.business_unit import BusinessUnit
from app.models.tenant import Tenant
from app.services.tenant_provisioning_service import provision_tenant


def test_provision_tenant_creates_a_real_isolated_database_and_is_resumable():
    """MULTI_TENANT_POOL scaffolding (ECC_USV_PLATFORM_SPEC.md Section
    3.5/6.3): provisioning a tenant must produce an actually-separate,
    actually-migrated Postgres database -- not a mock. This test creates a
    real one against the same Postgres cluster the rest of the suite uses."""
    tenant_code = f"test-tenant-{uuid.uuid4().hex[:8]}"

    entry = provision_tenant(tenant_code, "Acme Test Tenant")
    try:
        assert entry.status == "ready"
        assert entry.database_name.startswith("usv_tenant_")

        # The database is real, separate, and fully migrated (has every
        # table through v007) -- not shared with the default database.
        tenant_engine = create_engine(settings.database_url_for(entry.database_name))
        try:
            table_names = set(inspect(tenant_engine).get_table_names())
            assert {"tenant", "business_unit", "site", "fleet_asset", "ingested_event", "alembic_version"}.issubset(
                table_names
            )
        finally:
            tenant_engine.dispose()

        # Seeded exactly one Tenant + one Business Unit row, matching the
        # registry entry.
        factory = get_sessionmaker_for_database(entry.database_name)
        session = factory()
        try:
            tenant_row = session.get(Tenant, entry.tenant_id)
            assert tenant_row is not None
            assert tenant_row.name == "Acme Test Tenant"
            assert session.query(BusinessUnit).filter_by(tenant_id=entry.tenant_id).count() == 1
        finally:
            session.close()

        # Resumable/idempotent: calling again with the same tenant_code
        # returns the same, already-ready entry rather than erroring or
        # re-provisioning.
        second_call = provision_tenant(tenant_code, "Acme Test Tenant")
        assert second_call.tenant_id == entry.tenant_id
        assert second_call.database_name == entry.database_name
    finally:
        reset_caches_for_tests()
        admin_engine = create_engine(settings.admin_database_url, isolation_level="AUTOCOMMIT")
        try:
            with admin_engine.connect() as conn:
                conn.execute(text(f'DROP DATABASE IF EXISTS "{entry.database_name}" WITH (FORCE)'))
        finally:
            admin_engine.dispose()
        with create_engine(settings.platform_database_url).connect() as conn:
            conn.execute(text("DELETE FROM tenant_registry WHERE tenant_code = :code"), {"code": tenant_code})
            conn.commit()
