"""V006 tenancy + business unit foundation

Revision ID: v006
Revises: v005
Create Date: 2026-09-27

Adds the multi-tenancy + Business Unit foundation from
ECC_USV_PLATFORM_SPEC.md Section 3.5 / Task T-1:
  - `tenant`, `business_unit`, `zone`, `tenant_registry` tables
  - `usv_user_site` (many-to-many, replaces usv_user.site_id as the
    authoritative site-scoping claim; usv_user.site_id is kept for
    backward compatibility)
  - `site.business_unit_id`, `usv_user.business_unit_id`

This install is SINGLE_TENANT (there is exactly one tenant), so this
migration also backfills: creates one default Tenant + Business Unit and
points every existing Site at it, then makes site.business_unit_id
NOT NULL. A fresh MULTI_TENANT_POOL tenant database gets the same schema
via the same migration, just with no rows to backfill.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "v006"
down_revision: Union[str, None] = "v005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("initial_plan_ref", sa.String(128)),
        sa.Column("suspended_at", sa.DateTime(timezone=True)),
        sa.Column("deactivated_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "business_unit",
        sa.Column("business_unit_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.tenant_id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "zone",
        sa.Column("zone_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("site.site_id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("zone_type", sa.String(32)),
        sa.Column("purdue_level", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "tenant_registry",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("database_name", sa.String(128), nullable=False, unique=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="provisioning"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "usv_user_site",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("usv_user.user_id"), primary_key=True),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("site.site_id"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.add_column("site", sa.Column("business_unit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("business_unit.business_unit_id"), nullable=True))
    op.add_column("usv_user", sa.Column("business_unit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("business_unit.business_unit_id"), nullable=True))

    # --- Backfill: this install is SINGLE_TENANT, so create exactly one
    # Tenant + Business Unit and point every existing Site at it. A brand
    # new database (no sites yet) just gets the default rows sitting ready.
    conn = op.get_bind()
    tenant_id = conn.execute(sa.text("SELECT gen_random_uuid()")).scalar()
    conn.execute(
        sa.text(
            "INSERT INTO tenant (tenant_id, name, status) VALUES (:tenant_id, :name, 'active')"
        ),
        {"tenant_id": tenant_id, "name": "Default Tenant"},
    )
    business_unit_id = conn.execute(sa.text("SELECT gen_random_uuid()")).scalar()
    conn.execute(
        sa.text(
            "INSERT INTO business_unit (business_unit_id, tenant_id, name, status) "
            "VALUES (:bu_id, :tenant_id, :name, 'active')"
        ),
        {"bu_id": business_unit_id, "tenant_id": tenant_id, "name": "Default Business Unit"},
    )
    conn.execute(
        sa.text("UPDATE site SET business_unit_id = :bu_id WHERE business_unit_id IS NULL"),
        {"bu_id": business_unit_id},
    )

    op.alter_column("site", "business_unit_id", nullable=False)


def downgrade() -> None:
    op.alter_column("site", "business_unit_id", nullable=True)
    op.drop_column("usv_user", "business_unit_id")
    op.drop_column("site", "business_unit_id")
    op.drop_table("usv_user_site")
    op.drop_table("tenant_registry")
    op.drop_table("zone")
    op.drop_table("business_unit")
    op.drop_table("tenant")
