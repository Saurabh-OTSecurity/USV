import uuid

from sqlalchemy.orm import Session

from app.models.usv import Usv


class UsvRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> list[Usv]:
        return self.db.query(Usv).order_by(Usv.usv_code).all()

    def get_by_id(self, usv_id: uuid.UUID) -> Usv | None:
        return self.db.get(Usv, usv_id)
