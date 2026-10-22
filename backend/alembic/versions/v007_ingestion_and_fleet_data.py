"""V007 ingestion receiver + fleet data model

Revision ID: v007
Revises: v006
Create Date: 2026-09-27

Adds Task T-2 (ECC_USV_PLATFORM_SPEC.md Section 6.1/7): the ingestion
receiver's own tables (`ingestion_token`, `ingested_event`) and the fleet
storage tables the receiver normalizes into (`fleet_asset`, `alert`,
`finding`, `remediation`, `incident`, `correlation_group`).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "v007"
down_revision: Union[str, None] = "v006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingestion_token",
        sa.Column("token_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("site.site_id"), nullable=False),
        sa.Column("secret_hash", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "ingested_event",
        sa.Column("event_id", sa.String(128), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("site.site_id"), nullable=False),
        sa.Column("token_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ingestion_token.token_id")),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("object_type", sa.String(32), nullable=False),
        sa.Column("object_id", sa.String(128)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("process_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
    )
    op.create_index("ix_ingested_event_process_status", "ingested_event", ["process_status"])
    op.create_index("ix_ingested_event_site_id", "ingested_event", ["site_id"])

    op.create_table(
        "fleet_asset",
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("site.site_id"), nullable=False),
        sa.Column("source_system", sa.String(32), nullable=False, server_default="tribot"),
        sa.Column("source_asset_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(255)),
        sa.Column("device_type", sa.String(64)),
        sa.Column("risk_level", sa.String(32)),
        sa.Column("industrial_zone", sa.String(128)),
        sa.Column("purdue_level", sa.Integer()),
        sa.Column("raw", postgresql.JSONB()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("site_id", "source_asset_id", name="uq_fleet_asset_site_source"),
    )
    op.create_index("ix_fleet_asset_tenant_id", "fleet_asset", ["tenant_id"])

    op.create_table(
        "alert",
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("site.site_id"), nullable=False),
        sa.Column("source_alert_id", sa.String(128), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fleet_asset.asset_id")),
        sa.Column("severity", sa.String(32)),
        sa.Column("status", sa.String(32)),
        sa.Column("category", sa.String(64)),
        sa.Column("cve_id", sa.String(32)),
        sa.Column("title", sa.String(255)),
        sa.Column("description", sa.Text()),
        sa.Column("raw", postgresql.JSONB()),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("site_id", "source_alert_id", name="uq_alert_site_source"),
    )
    op.create_index("ix_alert_tenant_id", "alert", ["tenant_id"])
    op.create_index("ix_alert_cve_id", "alert", ["cve_id"])

    op.create_table(
        "finding",
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("site.site_id"), nullable=False),
        sa.Column("source_finding_id", sa.String(128), nullable=False),
        sa.Column("source_system", sa.String(32), nullable=False, server_default="tribot"),
        sa.Column("finding_type", sa.String(64)),
        sa.Column("category", sa.String(64)),
        sa.Column("severity", sa.String(32)),
        sa.Column("status", sa.String(32)),
        sa.Column("title", sa.String(255)),
        sa.Column("description", sa.Text()),
        sa.Column("source_alert_ids", postgresql.JSONB()),
        sa.Column("asset_ids", postgresql.JSONB()),
        sa.Column("owner", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("site_id", "source_finding_id", name="uq_finding_site_source"),
    )
    op.create_index("ix_finding_tenant_id", "finding", ["tenant_id"])

    op.create_table(
        "remediation",
        sa.Column("remediation_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("site.site_id"), nullable=False),
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("finding.finding_id")),
        sa.Column("source_remediation_id", sa.String(128), nullable=False),
        sa.Column("type", sa.String(64)),
        sa.Column("title", sa.String(255)),
        sa.Column("description", sa.Text()),
        sa.Column("owner", sa.String(128)),
        sa.Column("status", sa.String(32)),
        sa.Column("planned_date", sa.Date()),
        sa.Column("current_plan_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("implementation_date", sa.Date()),
        sa.Column("validation_date", sa.Date()),
        sa.Column("closure_date", sa.Date()),
        sa.Column("plan_history", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("site_id", "source_remediation_id", name="uq_remediation_site_source"),
    )
    op.create_index("ix_remediation_tenant_id", "remediation", ["tenant_id"])

    op.create_table(
        "incident",
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("site.site_id"), nullable=False),
        sa.Column("source_incident_id", sa.String(128), nullable=False),
        sa.Column("incident_source", sa.String(32)),
        sa.Column("ecc_incident_id", sa.String(128)),
        sa.Column("tribot_incident_id", sa.String(128)),
        sa.Column("title", sa.String(255)),
        sa.Column("description", sa.Text()),
        sa.Column("category", sa.String(64)),
        sa.Column("type", sa.String(64)),
        sa.Column("severity", sa.String(32)),
        sa.Column("priority", sa.String(32)),
        sa.Column("status", sa.String(32)),
        sa.Column("created_by", sa.String(128)),
        sa.Column("owner", sa.String(128)),
        sa.Column("alert_ids", postgresql.JSONB()),
        sa.Column("finding_ids", postgresql.JSONB()),
        sa.Column("asset_ids", postgresql.JSONB()),
        sa.Column("impact", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("site_id", "source_incident_id", name="uq_incident_site_source"),
    )
    op.create_index("ix_incident_tenant_id", "incident", ["tenant_id"])

    op.create_table(
        "correlation_group",
        sa.Column("correlation_group_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("correlation_key", sa.String(128), nullable=False),
        sa.Column("title", sa.String(255)),
        sa.Column("member_type", sa.String(16), nullable=False),
        sa.Column("member_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "correlation_key", name="uq_correlation_group_tenant_key"),
    )


def downgrade() -> None:
    op.drop_table("correlation_group")
    op.drop_table("incident")
    op.drop_table("remediation")
    op.drop_table("finding")
    op.drop_table("alert")
    op.drop_table("fleet_asset")
    op.drop_table("ingested_event")
    op.drop_table("ingestion_token")
