import uuid

from sqlalchemy import DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BusinessUnit(Base):
    """Sits between Tenant and Site (ECC_USV_PLATFORM_SPEC.md Section 3.5).
    Not tenancy -- a scoping/RBAC layer inside one tenant, for a large
    enterprise customer's internal divisions (e.g. Chemicals vs. Packaging),
    each owning some subset of sites. A Site belongs to exactly one BU
    (Decision, Section 3.5) in both deployment modes -- modeled here even in
    MULTI_TENANT_POOL so the schema is identical across both modes."""

    __tablename__ = "business_unit"

    business_unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", server_default="active")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
