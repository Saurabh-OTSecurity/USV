import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Incident(Base):
    """FR-3.5/Section 4.3.1: built from day one even though Tribot won't
    populate it until its own Finding/Remediation/Incident work ships --
    the column shape must exist so ECC's compiled views don't need a
    breaking migration later. `ecc_incident_id`/`tribot_incident_id` are the
    cross-reference pair that must round-trip losslessly in both directions
    (wire contract Section 38/companion spec Section 5.3)."""

    __tablename__ = "incident"
    __table_args__ = (UniqueConstraint("site_id", "source_incident_id", name="uq_incident_site_source"),)

    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("site.site_id"), nullable=False)
    source_incident_id: Mapped[str] = mapped_column(String(128), nullable=False)
    incident_source: Mapped[str | None] = mapped_column(String(32))  # "tribot" | "ecc"
    ecc_incident_id: Mapped[str | None] = mapped_column(String(128))
    tribot_incident_id: Mapped[str | None] = mapped_column(String(128))
    title: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(64))
    type: Mapped[str | None] = mapped_column(String(64))
    severity: Mapped[str | None] = mapped_column(String(32))
    priority: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str | None] = mapped_column(String(32))
    created_by: Mapped[str | None] = mapped_column(String(128))
    owner: Mapped[str | None] = mapped_column(String(128))
    alert_ids: Mapped[list | None] = mapped_column(JSONB)
    finding_ids: Mapped[list | None] = mapped_column(JSONB)
    asset_ids: Mapped[list | None] = mapped_column(JSONB)
    impact: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
