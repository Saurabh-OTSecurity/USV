"""V001 extensions

Revision ID: v001
Revises:
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op

revision: str = "v001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
