"""V010 USV monitoring: USV-generated alerts, site state, planned downtime

Revision ID: v010
Revises: v009
Create Date: 2026-10-18

USV O&M Manual section 7 (backlog 18, 21, 22): alerts only USV can raise
(site added/silent/disconnected, token problems, ingestion backlog,
database/certificate/backup health, security), one open alert per site per
condition with auto-close, planned-downtime windows, per-site limits, and
in-app notification with escalation.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "v010"
down_revision: Union[str, None] = "v009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "usv_alert",
        sa.Column("usv_alert_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("site_id", UUID, sa.ForeignKey("site.site_id")),
        sa.Column("rule_id", sa.String(16), nullable=False),           # SU-05, PL-01, SE-01 ...
        sa.Column("dedupe_key", sa.String(255), nullable=False),        # rule + subject
        sa.Column("category", sa.String(32), nullable=False),           # Site / Platform / Security
        sa.Column("severity", sa.String(16), nullable=False),           # Info / Warning / Critical
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),  # open/acknowledged/closed
        sa.Column("event_only", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_by", UUID, sa.ForeignKey("usv_user.user_id")),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("escalation_level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("escalated_at", sa.DateTime(timezone=True)),
    )
    # At most one not-closed alert per condition: raising again updates it.
    op.create_index("uq_usv_alert_open_dedupe", "usv_alert", ["dedupe_key"], unique=True,
                    postgresql_where=sa.text("status <> 'closed'"))
    op.create_index("ix_usv_alert_status_opened", "usv_alert", ["status", "opened_at"])
    op.create_index("ix_usv_alert_site", "usv_alert", ["site_id"])

    op.create_table(
        "site_state",
        sa.Column("site_id", UUID, sa.ForeignKey("site.site_id"), primary_key=True),
        sa.Column("state", sa.String(32), nullable=False),              # waiting_first_data/healthy/silent/disconnected
        sa.Column("state_since", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_contact_at", sa.DateTime(timezone=True)),
        sa.Column("first_data_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "planned_downtime",
        sa.Column("downtime_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("site_id", UUID, sa.ForeignKey("site.site_id"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("created_by", UUID, sa.ForeignKey("usv_user.user_id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("ends_at > starts_at", name="ck_planned_downtime_window"),
    )
    op.create_index("ix_planned_downtime_site_window", "planned_downtime", ["site_id", "starts_at", "ends_at"])

    # One row with site_id NULL = this customer's default; rows with a site_id override it.
    op.create_table(
        "monitoring_setting",
        sa.Column("setting_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("site_id", UUID, sa.ForeignKey("site.site_id"), unique=True),
        sa.Column("check_in_minutes", sa.Integer()),
        sa.Column("silent_after_intervals", sa.Integer()),
        sa.Column("disconnected_after_intervals", sa.Integer()),
        sa.Column("first_data_hours", sa.Integer()),
        sa.Column("escalation_minutes", sa.Integer()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("uq_monitoring_setting_default", "monitoring_setting", [sa.text("(site_id IS NULL)")],
                    unique=True, postgresql_where=sa.text("site_id IS NULL"))

    op.create_table(
        "ingestion_auth_failure",
        sa.Column("failure_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("token_id", UUID),
        sa.Column("site_id", UUID, sa.ForeignKey("site.site_id")),
        sa.Column("reason", sa.String(32), nullable=False),             # unknown_token / revoked / bad_secret / malformed
        sa.Column("source_ip", sa.String(64)),
    )
    op.create_index("ix_ingestion_auth_failure_site_time", "ingestion_auth_failure", ["site_id", "occurred_at"])

    op.create_table(
        "usv_notification",
        sa.Column("notification_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID, sa.ForeignKey("usv_user.user_id"), nullable=False),
        sa.Column("usv_alert_id", UUID, sa.ForeignKey("usv_alert.usv_alert_id")),
        sa.Column("level", sa.String(32), nullable=False),              # site_admin / bu_admin / customer_admin / platform_admin
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("read_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_usv_notification_user_unread", "usv_notification", ["user_id", "read_at"])


def downgrade() -> None:
    op.drop_table("usv_notification")
    op.drop_table("ingestion_auth_failure")
    op.drop_index("uq_monitoring_setting_default", table_name="monitoring_setting")
    op.drop_table("monitoring_setting")
    op.drop_table("planned_downtime")
    op.drop_table("site_state")
    op.drop_table("usv_alert")
