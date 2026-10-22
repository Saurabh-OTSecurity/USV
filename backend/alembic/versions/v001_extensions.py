"""V001 extensions

Revision ID: v001
Revises:
Create Date: 2026-08-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Best-effort: some minimal/portable PostgreSQL builds (e.g. the
    # `pgserver` package used by scripts/dev_postgres.py for local dev, which
    # only bundles plpgsql/pgvector) don't ship the pgcrypto contrib module at
    # all, so even `CREATE EXTENSION IF NOT EXISTS` raises
    # FeatureNotSupported rather than silently no-op'ing. This doesn't block
    # the app: since PostgreSQL 13, gen_random_uuid() -- the only pgcrypto
    # function this schema uses -- is a core built-in, not dependent on the
    # extension (see backend/README.md's Troubleshooting section). A savepoint
    # keeps this best-effort attempt from aborting the whole migration
    # transaction on a standard install where pgcrypto legitimately can't be
    # created for some other reason.
    conn = op.get_bind()
    savepoint = conn.begin_nested()
    try:
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        savepoint.commit()
    except Exception:
        savepoint.rollback()


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
