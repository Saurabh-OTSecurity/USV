"""V012 organization roles: customer admin and BU admin

Revision ID: v012
Revises: v011
Create Date: 2026-10-18

USV O&M Manual section 11 adds two organization levels between platform and
site: usv_customer_admin and usv_bu_admin. Widens the usv_user role check.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "v012"
down_revision: Union[str, None] = "v011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_ROLES = ("usv_platform_admin", "usv_site_admin", "usv_l2_analyst", "usv_l1_operator", "usv_auditor", "usv_viewer")
NEW_ROLES = ("usv_platform_admin", "usv_customer_admin", "usv_bu_admin", "usv_site_admin", "usv_l2_analyst",
             "usv_l1_operator", "usv_auditor", "usv_viewer")


def upgrade() -> None:
    op.drop_constraint("ck_usv_user_role", "usv_user", type_="check")
    op.create_check_constraint("ck_usv_user_role", "usv_user", f"role IN {NEW_ROLES}")


def downgrade() -> None:
    op.drop_constraint("ck_usv_user_role", "usv_user", type_="check")
    op.create_check_constraint("ck_usv_user_role", "usv_user", f"role IN {OLD_ROLES}")
