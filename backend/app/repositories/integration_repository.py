import uuid

from sqlalchemy.orm import Session

from app.models.integration import Integration


class IntegrationRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> list[Integration]:
        return self.db.query(Integration).order_by(Integration.name).all()

    def get_by_id(self, integration_id: uuid.UUID) -> Integration | None:
        return self.db.get(Integration, integration_id)
