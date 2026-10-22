import uuid

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

VALID_ROLES = (
    "usv_platform_admin",
    "usv_customer_admin",
    "usv_bu_admin",
    "usv_site_admin",
    "usv_l2_analyst",
    "usv_l1_operator",
    "usv_auditor",
    "usv_viewer",
)


class UsvUser(Base):
    __tablename__ = "usv_user"
    __table_args__ = (
        CheckConstraint(f"role IN {VALID_ROLES}", name="ck_usv_user_role"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Legacy single-site scope -- kept for backward compatibility (existing
    # data, existing tests) but no longer the authoritative claim shape.
    # Prefer the usv_user_site rows (app/models/usv_user_site.py) for a
    # user scoped to specific sites (FRD Section 3's site_ids[] shape).
    site_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("site.site_id"))
    # A BU-scoped admin (Section 3.5) sees every site under this BU without
    # needing a usv_user_site row per site. Nullable: platform admins and
    # single-site users leave this unset.
    business_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_unit.business_unit_id")
    )
    username: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", server_default="active")
    last_login_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    email: Mapped[str | None] = mapped_column(String(255))
    # Password governance (USV O&M Manual section 10)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    locked_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    password_history: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    # Tokens issued before this moment are refused: the person left, or their
    # password was reset. Also sent to each Tribot (single sign-on sessions).
    sessions_revoked_before: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
