"""V008 indexes for many-site ingestion

Revision ID: v008
Revises: v007
Create Date: 2026-10-13

Sized for hundreds of sites pushing into one USV:
- ingested_event pending queue: the worker polls "pending, oldest first"
  continuously; a partial index keeps that lookup small no matter how many
  processed rows the table holds.
- ingested_event.received_at: the retention purge deletes by age.
- fleet_asset.last_seen_at / alert.occurred_at: the paginated fleet views sort
  by these across every site (comprehensive view), so LIMIT/OFFSET pages need
  an index instead of a full sort of 100k+ rows.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "v008"
down_revision: Union[str, None] = "v007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_ingested_event_pending_received_at", "ingested_event", ["received_at"],
        postgresql_where=sa.text("process_status = 'pending'"),
    )
    op.create_index("ix_ingested_event_received_at", "ingested_event", ["received_at"])
    op.create_index("ix_fleet_asset_last_seen_at", "fleet_asset", ["last_seen_at"])
    op.create_index("ix_alert_occurred_at", "alert", ["occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_alert_occurred_at", table_name="alert")
    op.drop_index("ix_fleet_asset_last_seen_at", table_name="fleet_asset")
    op.drop_index("ix_ingested_event_received_at", table_name="ingested_event")
    op.drop_index("ix_ingested_event_pending_received_at", table_name="ingested_event")
