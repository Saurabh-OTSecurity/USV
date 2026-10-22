import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Zone(Base):
    """Sub-division of a Site (FR-1.3): IT/OT/DMZ/Engineering, Purdue-level
    aligned. `purdue_level` mirrors the vocabulary Tribot's own topology API
    reports (TRIBOT_EXTERNAL_DATA_API_ARCHITECTURE_v1.0.md Section 4.4's
    zoneId/purdue_level) so labels don't drift between what Tribot reports
    per-asset and what ECC shows per-zone."""

    __tablename__ = "zone"

    zone_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("site.site_id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    zone_type: Mapped[str | None] = mapped_column(String(32))  # it | ot | dmz | engineering
    purdue_level: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
