"""Identity governance (USV O&M Manual sections 10-11). See alembic v013."""
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PasswordPolicy(Base):
    """One row: this customer's password policy (defaults from the manual's
    section 10 starting values)."""

    __tablename__ = "password_policy"

    policy_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    min_length: Mapped[int] = mapped_column(Integer, nullable=False, default=14, server_default="14")
    history_count: Mapped[int] = mapped_column(Integer, nullable=False, default=5, server_default="5")
    max_failed_logins: Mapped[int] = mapped_column(Integer, nullable=False, default=5, server_default="5")
    expiry_days: Mapped[int | None] = mapped_column(Integer)
    share_link_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24, server_default="24")
    reset_link_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30, server_default="30")
    reset_approval_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=4, server_default="4")
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Approver(Base):
    """A named approver (or backup) for one organization level: platform,
    customer, a business unit (scope_id) or a site (scope_id)."""

    __tablename__ = "approver"
    __table_args__ = (UniqueConstraint("level", "scope_id", "user_id", name="uq_approver_level_scope_user"),)

    approver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    level: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("usv_user.user_id"), nullable=False)
    is_backup: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PasswordResetRequest(Base):
    __tablename__ = "password_reset_request"

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("usv_user.user_id"), nullable=False)
    # Hash of the reference the requester was given; only they can complete the reset.
    reference_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", server_default="pending")
    required_approvals: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    approvals: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    source_ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    escalated_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("usv_user.user_id"))
    completed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))


class SecureShare(Base):
    """A one-time secret behind a capability link: opens once, expires, then
    the secret is destroyed. Only the hash of the link token is stored."""

    __tablename__ = "secure_share"

    share_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("usv_user.user_id"))
    secret_encrypted: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("usv_user.user_id"))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    opened_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class BreakGlassAccount(Base):
    """The one local emergency account on a site's Tribot, for when USV is
    unreachable. USV generates and rotates its password; Tribot receives only
    its own-format hash through the directory poll."""

    __tablename__ = "break_glass_account"

    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("site.site_id"), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, default="breakglass", server_default="breakglass")
    password_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    tribot_password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    rotated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    rotate_due_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))


class BreakGlassRequest(Base):
    __tablename__ = "break_glass_request"

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("site.site_id"), nullable=False)
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("usv_user.user_id"), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", server_default="pending")
    approvals: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    opened_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
