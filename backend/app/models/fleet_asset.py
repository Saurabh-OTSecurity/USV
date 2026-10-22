import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FleetAsset(Base):
    """The stored, queryable mirror of assets Tribot has reported via
    `usv_push`/the ingestion receiver -- what FR-3.1's compiled/fleet-wide
    view is built from. Unlike the legacy live pull-proxy
    (app/services/tribot_client.py), this table is what makes cross-site
    aggregation and the site-wise/BU-compiled/tenant-compiled view split
    (T-3) possible without fan-out-calling every site's Tribot on every
    dashboard load."""

    __tablename__ = "fleet_asset"
    __table_args__ = (UniqueConstraint("site_id", "source_asset_id", name="uq_fleet_asset_site_source"),)

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("site.site_id"), nullable=False)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False, default="tribot", server_default="tribot")
    source_asset_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    device_type: Mapped[str | None] = mapped_column(String(64))
    risk_level: Mapped[str | None] = mapped_column(String(32))
    industrial_zone: Mapped[str | None] = mapped_column(String(128))
    purdue_level: Mapped[int | None] = mapped_column(Integer)
    raw: Mapped[dict | None] = mapped_column(JSONB)
    # "active" / "silent" as the site's Tribot reports it (manual section 6), or
    # "missing_from_tribot" when a complete full resync no longer listed it.
    lifecycle_state: Mapped[str] = mapped_column(String(32), nullable=False, default="active", server_default="active")
    silent_since: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
