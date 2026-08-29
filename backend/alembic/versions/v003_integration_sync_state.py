"""V003 integration + sync_state

Revision ID: v003
Revises: v002
Create Date: 2026-08-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "v003"
down_revision: Union[str, None] = "v002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "integration",
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("site.site_id")),
        sa.Column("integration_type", sa.String(64)),
        sa.Column("name", sa.String(255)),
        sa.Column("provider", sa.String(128)),
        sa.Column("version", sa.String(128)),
        sa.Column("status", sa.String(32)),
        sa.Column("is_fixed_engine", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "sync_state",
        sa.Column("sync_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("integration.integration_id"), nullable=False),
        sa.Column("entity_type", sa.String(64)),
        sa.Column("watermark", sa.Text()),
        sa.Column("last_started_at", sa.DateTime(timezone=True)),
        sa.Column("last_completed_at", sa.DateTime(timezone=True)),
        sa.Column("records_received", sa.BigInteger()),
        sa.Column("records_created", sa.BigInteger()),
        sa.Column("records_updated", sa.BigInteger()),
        sa.Column("records_failed", sa.BigInteger()),
        sa.Column("status", sa.String(32)),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("integration_id", "entity_type", name="uq_sync_state_integration_entity"),
    )


def downgrade() -> None:
    op.drop_table("sync_state")
    op.drop_table("integration")
