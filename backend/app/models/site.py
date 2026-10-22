import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Site(Base):
    __tablename__ = "site"

    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # A site belongs to exactly one Business Unit, in both deployment modes
    # (ECC_USV_PLATFORM_SPEC.md Section 3.5, decided -- no many-to-many).
    # v006 adds this column nullable, backfills a default tenant+BU for
    # existing rows, then ALTERs it to NOT NULL -- so by the time any code
    # runs against a migrated database this is always populated.
    business_unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_unit.business_unit_id"), nullable=False
    )
    site_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str | None] = mapped_column(String(64))
    criticality: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str | None] = mapped_column(String(32))
    # Where people open this site's Tribot, for single sign-on from USV.
    tribot_url: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
