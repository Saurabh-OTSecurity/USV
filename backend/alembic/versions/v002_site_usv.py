"""V002 site + usv

Revision ID: v002
Revises: v001
Create Date: 2026-08-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "v002"
down_revision: Union[str, None] = "v001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "site",
        sa.Column("site_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("site_code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("timezone", sa.String(64)),
        sa.Column("criticality", sa.String(32)),
        sa.Column("status", sa.String(32)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("site_code", name="uq_site_site_code"),
    )

    op.create_table(
        "usv",
        sa.Column("usv_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("site.site_id"), nullable=False),
        sa.Column("usv_code", sa.String(64), nullable=False),
        sa.Column("hostname", sa.String(255)),
        sa.Column("installation_id", sa.String(255)),
        sa.Column("version", sa.String(64)),
        sa.Column("status", sa.String(32)),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("usv_code", name="uq_usv_usv_code"),
        sa.UniqueConstraint("site_id", name="uq_usv_site_id"),
    )


def downgrade() -> None:
    op.drop_table("usv")
    op.drop_table("site")
