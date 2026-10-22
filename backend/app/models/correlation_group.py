import uuid

from sqlalchemy import DateTime, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CorrelationGroup(Base):
    """FR-3.6: alerts/incidents sharing a CVE/vendor-firmware/attack-pattern
    grouped across sites within a tenant. Built on-write at ingestion time
    (app/services/correlation_service.py) rather than as a scheduled job --
    simplest correct option for the current data volume; revisit if a
    tenant's alert rate makes on-write grouping too slow."""

    __tablename__ = "correlation_group"
    __table_args__ = (UniqueConstraint("tenant_id", "correlation_key", name="uq_correlation_group_tenant_key"),)

    correlation_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    correlation_key: Mapped[str] = mapped_column(String(128), nullable=False)  # e.g. "cve:CVE-2024-12345"
    title: Mapped[str | None] = mapped_column(String(255))
    member_type: Mapped[str] = mapped_column(String(16), nullable=False)  # "alert" | "incident"
    member_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
