"""MULTI_TENANT_POOL tenant provisioning (ECC_USV_PLATFORM_SPEC.md Section
3.5/6.3, T-1): create one new logical database in the same Postgres
cluster, migrate it, seed its default Tenant/Business Unit rows, and
register it so app.core.tenancy's connection router can find it.

Deliberately NOT invoked automatically anywhere in this pass -- there is no
"create tenant" HTTP endpoint yet (that's real further work: who is allowed
to call this, rate limiting, billing hook-up). This module makes the
mechanism itself real and independently testable; wiring it behind an admin
endpoint is a follow-up once the product decides who can trigger it.

Idempotent/resumable by design (T-1's explicit requirement): each step
checks what's already done before repeating it, so a failure partway
through (database created, migrations not yet run) is safely retried by
calling provision_tenant again with the same tenant_code.
"""
import os
import uuid

import sqlalchemy
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.core.config import settings
from app.core.tenancy import platform_session
from app.core.tenant_engines import get_sessionmaker_for_database
from app.models.business_unit import BusinessUnit
from app.models.tenant import Tenant
from app.models.tenant_registry import TenantRegistry

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class TenantCodeAlreadyExistsError(Exception):
    pass


def _database_name_for(tenant_id: uuid.UUID) -> str:
    return f"usv_tenant_{tenant_id.hex}"


def _create_database_if_missing(database_name: str) -> None:
    admin_engine = sqlalchemy.create_engine(settings.admin_database_url, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": database_name}
            ).scalar()
            if not exists:
                # Database names can't be parameterized -- database_name is
                # always our own generated "usv_tenant_<hex>" value, never
                # user-supplied input, so this is safe.
                conn.execute(text(f'CREATE DATABASE "{database_name}"'))
    finally:
        admin_engine.dispose()


def _run_migrations(database_name: str) -> None:
    cfg = Config(os.path.join(_BACKEND_ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_BACKEND_ROOT, "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url_for(database_name))
    command.upgrade(cfg, "head")


def _seed_tenant_row(database_name: str, tenant_id: uuid.UUID, name: str) -> None:
    factory = get_sessionmaker_for_database(database_name)
    session = factory()
    try:
        existing = session.get(Tenant, tenant_id)
        if existing is None:
            session.add(Tenant(tenant_id=tenant_id, name=name, status="active"))
            session.flush()
        if session.query(BusinessUnit).filter_by(tenant_id=tenant_id).first() is None:
            session.add(BusinessUnit(tenant_id=tenant_id, name="Default Business Unit", status="active"))
        session.commit()
    finally:
        session.close()


def provision_tenant(tenant_code: str, name: str) -> TenantRegistry:
    with platform_session() as db:
        entry = db.query(TenantRegistry).filter_by(tenant_code=tenant_code).one_or_none()
        if entry is not None and entry.status == "ready":
            return entry
        if entry is None:
            tenant_id = uuid.uuid4()
            entry = TenantRegistry(
                tenant_id=tenant_id,
                tenant_code=tenant_code,
                name=name,
                database_name=_database_name_for(tenant_id),
                status="provisioning",
            )
            db.add(entry)
            db.commit()
            db.refresh(entry)

        _create_database_if_missing(entry.database_name)
        _run_migrations(entry.database_name)
        _seed_tenant_row(entry.database_name, entry.tenant_id, entry.name)

        entry.status = "ready"
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry
