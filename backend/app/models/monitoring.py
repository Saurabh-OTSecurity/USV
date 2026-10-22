"""USV monitoring (USV O&M Manual section 7). See alembic v010 for the schema
rationale; app/services/monitoring/ for the rules that use these tables."""
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UsvAlert(Base):
    """An alert USV raises itself -- things only USV can see (a Tribot that
    is down can't report that it's down). One not-closed row per dedupe_key:
    raising the same condition again updates it; it closes by itself on
    recovery. event_only rows are history entries (e.g. site added) created
    already closed."""

    __tablename__ = "usv_alert"

    usv_alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    site_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("site.site_id"))
    rule_id: Mapped[str] = mapped_column(String(16), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", server_default="open")
    event_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    opened_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    acknowledged_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("usv_user.user_id"))
    closed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    escalation_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    escalated_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))


class SiteState(Base):
    __tablename__ = "site_state"

    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("site.site_id"), primary_key=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    state_since: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    last_contact_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    first_data_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PlannedDowntime(Base):
    """A window during which a site's silent/disconnected alerts stay quiet."""

    __tablename__ = "planned_downtime"

    downtime_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("site.site_id"), nullable=False)
    starts_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("usv_user.user_id"))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MonitoringSetting(Base):
    """site_id NULL = this customer's defaults; a row per site overrides any
    of its fields (a NULL field falls back to the customer default, then to
    the platform default in app.core.config)."""

    __tablename__ = "monitoring_setting"

    setting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    site_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("site.site_id"), unique=True)
    check_in_minutes: Mapped[int | None] = mapped_column(Integer)
    silent_after_intervals: Mapped[int | None] = mapped_column(Integer)
    disconnected_after_intervals: Mapped[int | None] = mapped_column(Integer)
    first_data_hours: Mapped[int | None] = mapped_column(Integer)
    escalation_minutes: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class IngestionAuthFailure(Base):
    """A refused ingest request, for the rejected-connections rule (SU-08)."""

    __tablename__ = "ingestion_auth_failure"

    failure_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    occurred_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    token_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    site_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("site.site_id"))
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ip: Mapped[str | None] = mapped_column(String(64))


class UsvNotification(Base):
    """In-app notification (no email for now, per the user's decision)."""

    __tablename__ = "usv_notification"

    notification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("usv_user.user_id"), nullable=False)
    usv_alert_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("usv_alert.usv_alert_id"))
    level: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    read_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
