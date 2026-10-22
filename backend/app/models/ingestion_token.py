import uuid

from sqlalchemy import DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class IngestionToken(Base):
    """A revocable, per-site credential (FR-1.4) a Tribot instance
    authenticates its `usv_push` deliveries with. Only `secret_hash` is
    stored -- the plaintext secret is shown to the caller exactly once, at
    issuance (app/services/ingestion_token_service.py), the same one-way
    philosophy app.core.security already uses for user passwords.

    The wire format returned to the caller is "<token_id>.<secret>" (matches
    the shape Tribot's own external-API credentials already use, per
    TRIBOT_EXTERNAL_DATA_API_ARCHITECTURE_v1.0.md) so the receiver can find
    the row by token_id before hashing/comparing the secret -- no need to
    hash-and-scan every active token on every ingested event."""

    __tablename__ = "ingestion_token"

    token_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("site.site_id"), nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", server_default="active")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
