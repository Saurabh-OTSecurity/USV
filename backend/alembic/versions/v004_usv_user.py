"""V004 usv_user

Revision ID: v004
Revises: v003
Create Date: 2026-08-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "v004"
down_revision: Union[str, None] = "v003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VALID_ROLES = (
    "usv_platform_admin",
    "usv_site_admin",
    "usv_l2_analyst",
    "usv_l1_operator",
    "usv_auditor",
    "usv_viewer",
)


def upgrade() -> None:
    op.create_table(
        "usv_user",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("site.site_id")),
        sa.Column("username", sa.String(128), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(255)),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("username", name="uq_usv_user_username"),
        sa.CheckConstraint(f"role IN {VALID_ROLES}", name="ck_usv_user_role"),
    )


def downgrade() -> None:
    op.drop_table("usv_user")
