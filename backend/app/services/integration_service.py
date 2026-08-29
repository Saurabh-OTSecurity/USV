import uuid

from sqlalchemy.orm import Session

from app.models.integration import Integration
from app.repositories.integration_repository import IntegrationRepository


class IntegrationService:
    def __init__(self, db: Session):
        self.repository = IntegrationRepository(db)

    def list_integrations(self) -> list[Integration]:
        return self.repository.list_all()

    def get_integration(self, integration_id: uuid.UUID) -> Integration | None:
        return self.repository.get_by_id(integration_id)
