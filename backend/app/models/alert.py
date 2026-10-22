import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Alert(Base):
    """Stored mirror of Tribot-reported alerts (FR-4.x). `cve_id` is pulled
    out of `raw` at ingestion time purely so correlation
    (app/services/correlation_service.py, FR-3.6) can group alerts sharing a
    CVE without re-parsing JSONB on every run."""

    __tablename__ = "alert"
    __table_args__ = (UniqueConstraint("site_id", "source_alert_id", name="uq_alert_site_source"),)

    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("site.site_id"), nullable=False)
    source_alert_id: Mapped[str] = mapped_column(String(128), nullable=False)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("fleet_asset.asset_id"))
    severity: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str | None] = mapped_column(String(32))
    category: Mapped[str | None] = mapped_column(String(64))
    cve_id: Mapped[str | None] = mapped_column(String(32))
    title: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    raw: Mapped[dict | None] = mapped_column(JSONB)
    occurred_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    # Set when USV closes the alert itself, e.g. its asset was decommissioned.
    closed_reason: Mapped[str | None] = mapped_column(String(255))
    closed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
