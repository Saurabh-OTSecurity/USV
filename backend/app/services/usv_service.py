import uuid

from sqlalchemy.orm import Session

from app.models.usv import Usv
from app.repositories.usv_repository import UsvRepository


class UsvService:
    def __init__(self, db: Session):
        self.repository = UsvRepository(db)

    def list_usvs(self) -> list[Usv]:
        return self.repository.list_all()

    def get_usv(self, usv_id: uuid.UUID) -> Usv | None:
        return self.repository.get_by_id(usv_id)
