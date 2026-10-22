"""V013 identity governance: password policy, approvers, resets, secure
shares, break-glass, single sign-on to Tribot

Revision ID: v013
Revises: v012
Create Date: 2026-10-18

USV O&M Manual sections 10-11 (backlog 10-15): USV is the single authority
for who may log in where. Adds the password policy and lockout state, named
approvers per organization level (with backups), forgot-password requests
that an approver must approve, one-time secure shares, one break-glass
account per site (opened only with two approvals), and the site's Tribot
address for single sign-on.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "v013"
down_revision: Union[str, None] = "v012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column("usv_user", sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("usv_user", sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("usv_user", sa.Column("locked_at", sa.DateTime(timezone=True)))
    op.add_column("usv_user", sa.Column("password_changed_at", sa.DateTime(timezone=True)))
    op.add_column("usv_user", sa.Column("password_history", postgresql.JSONB(), nullable=False, server_default="[]"))
    # Tokens issued before this moment are refused (person left, password reset).
    op.add_column("usv_user", sa.Column("sessions_revoked_before", sa.DateTime(timezone=True)))
    op.add_column("usv_user", sa.Column("email", sa.String(255)))

    op.add_column("site", sa.Column("tribot_url", sa.String(512)))

    op.create_table(
        "password_policy",
        sa.Column("policy_id", sa.Integer(), primary_key=True),
        sa.Column("min_length", sa.Integer(), nullable=False, server_default="14"),
        sa.Column("history_count", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("max_failed_logins", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("expiry_days", sa.Integer()),
        sa.Column("share_link_hours", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("reset_link_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("reset_approval_hours", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "approver",
        sa.Column("approver_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("level", sa.String(32), nullable=False),            # platform / customer / business_unit / site
        sa.Column("scope_id", UUID),                                    # BU or site id; NULL for platform/customer
        sa.Column("user_id", UUID, sa.ForeignKey("usv_user.user_id"), nullable=False),
        sa.Column("is_backup", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("level", "scope_id", "user_id", name="uq_approver_level_scope_user"),
    )

    op.create_table(
        "password_reset_request",
        sa.Column("request_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID, sa.ForeignKey("usv_user.user_id"), nullable=False),
        sa.Column("reference_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),  # pending/approved/rejected/completed/expired
        sa.Column("required_approvals", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("approvals", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("source_ip", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("escalated_at", sa.DateTime(timezone=True)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decided_by", UUID, sa.ForeignKey("usv_user.user_id")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_password_reset_request_status", "password_reset_request", ["status", "created_at"])

    op.create_table(
        "secure_share",
        sa.Column("share_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("purpose", sa.String(32), nullable=False),            # initial_password / reset_password ...
        sa.Column("target_user_id", UUID, sa.ForeignKey("usv_user.user_id")),
        sa.Column("secret_encrypted", sa.Text()),                       # destroyed once opened or expired
        sa.Column("created_by", UUID, sa.ForeignKey("usv_user.user_id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True)),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "break_glass_account",
        sa.Column("site_id", UUID, sa.ForeignKey("site.site_id"), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, server_default="breakglass"),
        sa.Column("password_encrypted", sa.Text(), nullable=False),
        sa.Column("tribot_password_hash", sa.String(255), nullable=False),  # Tribot's own hash format
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotate_due_at", sa.DateTime(timezone=True)),             # set after it was opened
    )

    op.create_table(
        "break_glass_request",
        sa.Column("request_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("site_id", UUID, sa.ForeignKey("site.site_id"), nullable=False),
        sa.Column("requested_by", UUID, sa.ForeignKey("usv_user.user_id"), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),  # pending/approved/opened/rejected/expired
        sa.Column("approvals", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("opened_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("break_glass_request")
    op.drop_table("break_glass_account")
    op.drop_table("secure_share")
    op.drop_index("ix_password_reset_request_status", table_name="password_reset_request")
    op.drop_table("password_reset_request")
    op.drop_table("approver")
    op.drop_table("password_policy")
    op.drop_column("site", "tribot_url")
    for col in ("email", "sessions_revoked_before", "password_history", "password_changed_at", "locked_at",
                "failed_login_count", "must_change_password"):
        op.drop_column("usv_user", col)
