import uuid

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class IngestionTokenRoute(Base):
    """Platform database, MULTI_TENANT_POOL mode: which customer database
    holds an ingestion token. A Tribot's push carries only the token, so this
    is how it reaches the right customer's database (app.core.tenancy.
    session_for_ingestion_token). Holds no secret -- the token's hash stays
    in the customer database."""

    __tablename__ = "ingestion_token_route"

    token_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
