import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.ingestion_token import IngestionToken


class IngestionTokenRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, token: IngestionToken) -> IngestionToken:
        self.db.add(token)
        self.db.commit()
        self.db.refresh(token)
        return token

    def get_by_id(self, token_id: uuid.UUID) -> IngestionToken | None:
        return self.db.get(IngestionToken, token_id)

    def list_for_site(self, site_id: uuid.UUID) -> list[IngestionToken]:
        return self.db.query(IngestionToken).filter_by(site_id=site_id).order_by(IngestionToken.created_at).all()

    # last_used_at is for "is this site still pushing?" visibility, so minute
    # resolution is enough -- avoids one UPDATE per ingest request per site.
    LAST_USED_RESOLUTION_SECONDS = 60

    def mark_used(self, token: IngestionToken) -> None:
        now = datetime.now(timezone.utc)
        if token.last_used_at is not None and (now - token.last_used_at).total_seconds() < self.LAST_USED_RESOLUTION_SECONDS:
            return
        token.last_used_at = now
        self.db.add(token)
        self.db.commit()

    def revoke(self, token: IngestionToken) -> IngestionToken:
        token.status = "revoked"
        token.revoked_at = datetime.now(timezone.utc)
        self.db.add(token)
        self.db.commit()
        self.db.refresh(token)
        return token
