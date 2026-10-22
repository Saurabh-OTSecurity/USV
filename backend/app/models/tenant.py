import uuid

from sqlalchemy import DateTime, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Tenant(Base):
    """A customer. In SINGLE_TENANT deployments (ECC_USV_PLATFORM_SPEC.md
    Section 3.5) exactly one row ever exists here. In MULTI_TENANT_POOL
    deployments each tenant gets its own logical database (see
    app/models/tenant_registry.py) -- this row lives in the platform
    database and is the FR-1.1 "tenant" record: super-admin creates,
    suspends, deactivates."""

    __tablename__ = "tenant"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", server_default="active")
    initial_plan_ref: Mapped[str | None] = mapped_column(String(128))
    suspended_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    deactivated_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
