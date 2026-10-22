import uuid

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FleetAssetTombstone(Base):
    """A decommissioned asset id for one site (USV O&M Manual, section 6).
    An asset event that happened at or before decommissioned_at is ignored,
    so a late or repeated event can't bring the asset back. restored_at is
    set when Tribot restores it. The device returning on the network gets a
    new id in Tribot, so it is never blocked by this."""

    __tablename__ = "fleet_asset_tombstone"
    __table_args__ = (UniqueConstraint("site_id", "source_asset_id", name="uq_fleet_asset_tombstone_site_source"),)

    tombstone_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("site.site_id"), nullable=False)
    source_asset_id: Mapped[str] = mapped_column(String(128), nullable=False)
    asset_name: Mapped[str | None] = mapped_column(String(255))
    reason: Mapped[str | None] = mapped_column(String(500))
    decommissioned_by: Mapped[str | None] = mapped_column(String(128))
    decommissioned_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    origin: Mapped[str] = mapped_column(String(32), nullable=False, default="tribot", server_default="tribot")
    restored_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FleetTopologyLink(Base):
    """A link (who talks to whom) pushed by a site's Tribot, for the combined
    topology view (manual section 4). Endpoints are Tribot asset ids
    (fleet_asset.source_asset_id) within the same site."""

    __tablename__ = "fleet_topology_link"
    __table_args__ = (UniqueConstraint("site_id", "source_link_id", name="uq_fleet_topology_link_site_source"),)

    link_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("site.site_id"), nullable=False)
    source_link_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_asset_id: Mapped[str] = mapped_column(String(128), nullable=False)
    target_asset_id: Mapped[str] = mapped_column(String(128), nullable=False)
    protocol: Mapped[str | None] = mapped_column(String(64))
    ports: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    raw: Mapped[dict | None] = mapped_column(JSONB)
    first_seen: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SiteHealth(Base):
    """The latest health a site's Tribot sent with its heartbeat (manual
    section 7): capture running, last packet, disk, version, push queue...
    clock_skew_seconds = USV receive time minus the Tribot's own clock."""

    __tablename__ = "site_health"

    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("site.site_id"), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    health: Mapped[dict] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    clock_skew_seconds: Mapped[float | None] = mapped_column(Float)


class FleetObject(Base):
    """A raw detail record a site's Tribot pushed -- vulnerability, software,
    patch, ir_case or site_config -- kept as-is so USV can serve the same
    responses as Tribot's own API for that site (alembic v014)."""

    __tablename__ = "fleet_object"
    __table_args__ = (UniqueConstraint("site_id", "object_type", "source_id", name="uq_fleet_object_site_type_source"),)

    object_pk: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("site.site_id"), nullable=False)
    object_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    asset_source_id: Mapped[str | None] = mapped_column(String(128))
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
