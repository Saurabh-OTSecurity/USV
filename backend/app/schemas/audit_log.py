import uuid
from typing import Any

from pydantic import BaseModel


class AuditLogCreate(BaseModel):
    event_type: str
    actor_user_id: uuid.UUID | None = None
    target_type: str | None = None
    target_id: uuid.UUID | None = None
    result: str
    source_ip: str | None = None
    detail: dict[str, Any] | None = None
