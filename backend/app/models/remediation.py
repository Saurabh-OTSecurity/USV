import uuid

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Remediation(Base):
    """Mirrors TRIBOT_ECC_INTEGRATION_SPEC.md Section 5.3's Remediation
    shape. `plan_history` is append-only (FRD Section 10/29: "complete
    replan history retained") -- app/services/fleet_service.py's ingestion
    path must only ever append to this array, never overwrite it; there is
    no application code path that replaces an existing entry."""

    __tablename__ = "remediation"
    __table_args__ = (UniqueConstraint("site_id", "source_remediation_id", name="uq_remediation_site_source"),)

    remediation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("site.site_id"), nullable=False)
    finding_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("finding.finding_id"))
    source_remediation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str | None] = mapped_column(String(32))
    planned_date: Mapped[object | None] = mapped_column(Date)
    current_plan_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    implementation_date: Mapped[object | None] = mapped_column(Date)
    validation_date: Mapped[object | None] = mapped_column(Date)
    closure_date: Mapped[object | None] = mapped_column(Date)
    # Append-only array of {plan_version, planned_date, planned_by, planned_on, reason, remarks}
    plan_history: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
