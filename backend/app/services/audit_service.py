import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.repositories.audit_log_repository import AuditLogRepository


class AuditService:
    def __init__(self, db: Session):
        self.repository = AuditLogRepository(db)

    def record(
        self,
        *,
        event_type: str,
        result: str,
        actor_user_id: uuid.UUID | None = None,
        target_type: str | None = None,
        target_id: uuid.UUID | None = None,
        source_ip: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            occurred_at=datetime.now(timezone.utc),
            event_type=event_type,
            actor_user_id=actor_user_id,
            target_type=target_type,
            target_id=target_id,
            result=result,
            source_ip=source_ip,
            detail=detail,
        )
        return self.repository.create(entry)
