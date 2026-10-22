"""V014 fleet_object: per-site detail records for the Tribot-style site views

Revision ID: v014
Revises: v013
Create Date: 2026-10-19

So USV can show each pushed site exactly like the Tribot pages (assets,
topology, alerts, vulnerabilities, case board), it keeps the raw records a
site's Tribot pushes for: vulnerabilities, installed software and patches,
IR cases, and the site config (Purdue labels and zone roster). One generic
table, keyed by site + type + Tribot's own id; asset_source_id ties a record
to its asset so a decommission can remove them together.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "v014"
down_revision: Union[str, None] = "v013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fleet_object",
        sa.Column("object_pk", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("site.site_id"), nullable=False),
        sa.Column("object_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(128), nullable=False),
        sa.Column("asset_source_id", sa.String(128)),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("site_id", "object_type", "source_id", name="uq_fleet_object_site_type_source"),
    )
    op.create_index("ix_fleet_object_site_type", "fleet_object", ["site_id", "object_type"])
    op.create_index("ix_fleet_object_site_asset", "fleet_object", ["site_id", "asset_source_id"])


def downgrade() -> None:
    op.drop_index("ix_fleet_object_site_asset", table_name="fleet_object")
    op.drop_index("ix_fleet_object_site_type", table_name="fleet_object")
    op.drop_table("fleet_object")
