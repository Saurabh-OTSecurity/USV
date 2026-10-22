import uuid

from sqlalchemy import DateTime, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TenantRegistry(Base):
    """MULTI_TENANT_POOL only (ECC_USV_PLATFORM_SPEC.md Section 3.5/6.3):
    maps a tenant_id to the logical Postgres database that tenant's data
    lives in, inside the one shared cluster. Lives in the platform database
    (settings.platform_database_url). In SINGLE_TENANT mode this table is
    unused -- the app runs against the one configured database directly and
    app.core.tenancy's routing dependency is a no-op."""

    __tablename__ = "tenant_registry"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    # Duplicated (not authoritative) copies of the tenant's own name/code, so
    # login routing (which tenant does this username belong to?) and admin
    # listings work from the platform database alone, without first knowing
    # which tenant database to open. The authoritative Tenant row lives
    # inside that tenant's own database once you're routed there.
    tenant_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    database_name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="provisioning", server_default="provisioning")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
