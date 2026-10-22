import uuid

from sqlalchemy.orm import Session

from app.models.business_unit import BusinessUnit


class BusinessUnitRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> list[BusinessUnit]:
        return self.db.query(BusinessUnit).order_by(BusinessUnit.name).all()

    def get_by_id(self, business_unit_id: uuid.UUID) -> BusinessUnit | None:
        return self.db.get(BusinessUnit, business_unit_id)

    def create(self, business_unit: BusinessUnit) -> BusinessUnit:
        self.db.add(business_unit)
        self.db.commit()
        self.db.refresh(business_unit)
        return business_unit
