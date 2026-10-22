import uuid

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UsvUserSite(Base):
    """Many-to-many: which sites a user may act on (FRD Section 3's
    `site_ids[]` claim shape), replacing the old single nullable
    `usv_user.site_id` column as the authoritative scoping mechanism. A
    platform-wide or BU-wide admin simply has no rows here and is scoped by
    `role`/`business_unit_id` instead -- this table is only consulted for a
    user scoped to specific sites (Analyst/Operator roles)."""

    __tablename__ = "usv_user_site"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usv_user.user_id"), primary_key=True
    )
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("site.site_id"), primary_key=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
