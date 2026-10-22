"""V009 asset lifecycle, pushed topology links, site health

Revision ID: v009
Revises: v008
Create Date: 2026-10-18

USV O&M Manual sections 4, 6 and 7:
- fleet_asset.lifecycle_state ("active" / "silent" as Tribot reports it, or
  "missing_from_tribot" from the full-resync safety net) and silent_since.
- alert.closed_reason / closed_at: open alerts of a decommissioned asset are
  closed with a reason and kept for history.
- fleet_asset_tombstone: a decommissioned asset id per site, so a late or
  repeated older event can't bring it back.
- fleet_topology_link: links pushed by Tribot, for the combined topology view.
- site_health: the latest health a site's Tribot sent with its heartbeat.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "v009"
down_revision: Union[str, None] = "v008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("fleet_asset", sa.Column("lifecycle_state", sa.String(32), nullable=False, server_default="active"))
    op.add_column("fleet_asset", sa.Column("silent_since", sa.DateTime(timezone=True)))
    op.create_index("ix_fleet_asset_site_lifecycle", "fleet_asset", ["site_id", "lifecycle_state"])

    op.add_column("alert", sa.Column("closed_reason", sa.String(255)))
    op.add_column("alert", sa.Column("closed_at", sa.DateTime(timezone=True)))
    op.create_index("ix_alert_asset_id", "alert", ["asset_id"])

    op.create_table(
        "fleet_asset_tombstone",
        sa.Column("tombstone_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("site.site_id"), nullable=False),
        sa.Column("source_asset_id", sa.String(128), nullable=False),
        sa.Column("asset_name", sa.String(255)),
        sa.Column("reason", sa.String(500)),
        sa.Column("decommissioned_by", sa.String(128)),
        sa.Column("decommissioned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("origin", sa.String(32), nullable=False, server_default="tribot"),  # tribot / usv_admin
        sa.Column("restored_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("site_id", "source_asset_id", name="uq_fleet_asset_tombstone_site_source"),
    )

    op.create_table(
        "fleet_topology_link",
        sa.Column("link_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("site.site_id"), nullable=False),
        sa.Column("source_link_id", sa.String(128), nullable=False),
        sa.Column("source_asset_id", sa.String(128), nullable=False),
        sa.Column("target_asset_id", sa.String(128), nullable=False),
        sa.Column("protocol", sa.String(64)),
        sa.Column("ports", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("raw", postgresql.JSONB()),
        sa.Column("first_seen", sa.DateTime(timezone=True)),
        sa.Column("last_seen", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("site_id", "source_link_id", name="uq_fleet_topology_link_site_source"),
    )
    op.create_index("ix_fleet_topology_link_site_source_asset", "fleet_topology_link", ["site_id", "source_asset_id"])
    op.create_index("ix_fleet_topology_link_site_target_asset", "fleet_topology_link", ["site_id", "target_asset_id"])

    op.create_table(
        "site_health",
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("site.site_id"), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("health", postgresql.JSONB(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("clock_skew_seconds", sa.Float()),
    )


def downgrade() -> None:
    op.drop_table("site_health")
    op.drop_index("ix_fleet_topology_link_site_target_asset", table_name="fleet_topology_link")
    op.drop_index("ix_fleet_topology_link_site_source_asset", table_name="fleet_topology_link")
    op.drop_table("fleet_topology_link")
    op.drop_table("fleet_asset_tombstone")
    op.drop_index("ix_alert_asset_id", table_name="alert")
    op.drop_column("alert", "closed_at")
    op.drop_column("alert", "closed_reason")
    op.drop_index("ix_fleet_asset_site_lifecycle", table_name="fleet_asset")
    op.drop_column("fleet_asset", "silent_since")
    op.drop_column("fleet_asset", "lifecycle_state")
