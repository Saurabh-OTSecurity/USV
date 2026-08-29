from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


class AuditLogRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, entry: AuditLog) -> AuditLog:
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry
