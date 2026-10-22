"""Apply database migrations everywhere: the configured (platform) database,
then -- in MULTI_TENANT_POOL mode -- every customer database listed in the
tenant registry. This is the "apply database migrations" step of an upgrade
(USV O&M Manual section 8) once customers have their own databases.

    .venv\\Scripts\\python -m app.db.migrate_all

Continues past a customer database that fails and reports it, so one broken
customer doesn't block the others; exits non-zero if any failed.
"""
import os
import sys

from alembic import command
from alembic.config import Config

from app.core.config import settings
from app.core.tenancy import MULTI_TENANT_POOL, platform_session
from app.models.tenant_registry import TenantRegistry

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def upgrade(url: str) -> None:
    cfg = Config(os.path.join(_BACKEND_ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_BACKEND_ROOT, "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")


def main() -> int:
    print(f"platform database ({settings.database_name})")
    upgrade(settings.database_url)
    if settings.deployment_mode != MULTI_TENANT_POOL:
        return 0
    with platform_session() as db:
        tenants = db.query(TenantRegistry).order_by(TenantRegistry.tenant_code).all()
    failed = []
    for tenant in tenants:
        print(f"customer {tenant.tenant_code} ({tenant.database_name})")
        try:
            upgrade(settings.database_url_for(tenant.database_name))
        except Exception as exc:  # noqa: BLE001 -- report and continue with the next customer
            print(f"  FAILED: {exc}")
            failed.append(tenant.tenant_code)
    print(f"{len(tenants) - len(failed)}/{len(tenants)} customer databases at head")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
