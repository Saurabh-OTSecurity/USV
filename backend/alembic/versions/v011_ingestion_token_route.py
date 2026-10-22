"""V011 ingestion token route (database per customer)

Revision ID: v011
Revises: v010
Create Date: 2026-10-18

MULTI_TENANT_POOL mode keeps each customer in its own database. A Tribot's
push carries only its ingestion token, so the platform database keeps a
token_id -> tenant_id route to reach the right customer database. Created
in every database (same schema everywhere); only the platform one is used.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "v011"
down_revision: Union[str, None] = "v010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingestion_token_route",
        sa.Column("token_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_ingestion_token_route_tenant", "ingestion_token_route", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_ingestion_token_route_tenant", table_name="ingestion_token_route")
    op.drop_table("ingestion_token_route")
