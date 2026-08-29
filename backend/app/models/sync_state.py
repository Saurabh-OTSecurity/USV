import uuid

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SyncState(Base):
    __tablename__ = "sync_state"
    __table_args__ = (UniqueConstraint("integration_id", "entity_type", name="uq_sync_state_integration_entity"),)

    sync_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    integration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("integration.integration_id"), nullable=False
    )
    entity_type: Mapped[str | None] = mapped_column(String(64))
    watermark: Mapped[str | None] = mapped_column(Text)
    last_started_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    last_completed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    records_received: Mapped[int | None] = mapped_column(BigInteger)
    records_created: Mapped[int | None] = mapped_column(BigInteger)
    records_updated: Mapped[int | None] = mapped_column(BigInteger)
    records_failed: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str | None] = mapped_column(String(32))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
