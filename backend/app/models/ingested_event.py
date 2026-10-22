from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class IngestedEvent(Base):
    """Receive-side staging table for the wire contract's event envelope
    (TRIBOT_ECC_INTEGRATION_SPEC.md Section 5.2 /
    ECC_USV_PLATFORM_SPEC.md Section 8): every pushed event is written here
    FIRST, synchronously and fast, before the ingestion HTTP handler
    returns -- this is what makes the receiver safe to accept a burst of
    events without blocking on normalization (T-2's "async receive
    architecture" requirement) and is also the idempotency table: `event_id`
    is the wire contract's eventId and is the primary key, so a retried
    delivery of the same event is a harmless duplicate-key no-op, never a
    reprocessed event (FRD Section 35).

    app/services/ingestion_worker.py polls `process_status='pending'` rows,
    normalizes each into the appropriate fleet_* table based on
    object_type, and marks it processed -- the receiving-side mirror of the
    durable outbox TRIBOT_ECC_INTEGRATION_SPEC.md's T-3 builds on the
    sending side.
    """

    __tablename__ = "ingested_event"

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    tenant_id: Mapped[object] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[object] = mapped_column(UUID(as_uuid=True), ForeignKey("site.site_id"), nullable=False)
    token_id: Mapped[object | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_token.token_id"))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_type: Mapped[str] = mapped_column(String(32), nullable=False)
    object_id: Mapped[str | None] = mapped_column(String(128))
    occurred_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)  # FR-2.4: raw_event preserved verbatim
    received_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    process_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", server_default="pending")
    processed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
