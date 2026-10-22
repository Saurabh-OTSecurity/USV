import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Finding(Base):
    """Mirrors TRIBOT_ECC_INTEGRATION_SPEC.md Section 5.3's Finding shape
    once Tribot's app/ir T-2 ships it (this repo's schema conforms to that
    one, per the build-sequencing decision -- field names here are expected
    to need a follow-up migration once Tribot's shapes are finalized)."""

    __tablename__ = "finding"
    __table_args__ = (UniqueConstraint("site_id", "source_finding_id", name="uq_finding_site_source"),)

    finding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("site.site_id"), nullable=False)
    source_finding_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False, default="tribot", server_default="tribot")
    finding_type: Mapped[str | None] = mapped_column(String(64))
    category: Mapped[str | None] = mapped_column(String(64))
    severity: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str | None] = mapped_column(String(32))
    title: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    source_alert_ids: Mapped[list | None] = mapped_column(JSONB)
    asset_ids: Mapped[list | None] = mapped_column(JSONB)
    owner: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
