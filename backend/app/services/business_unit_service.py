import uuid

from sqlalchemy.orm import Session

from app.models.business_unit import BusinessUnit
from app.models.tenant import Tenant
from app.repositories.business_unit_repository import BusinessUnitRepository


class BusinessUnitService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = BusinessUnitRepository(db)

    def list_business_units(self) -> list[BusinessUnit]:
        return self.repository.list_all()

    def get_business_unit(self, business_unit_id: uuid.UUID) -> BusinessUnit | None:
        return self.repository.get_by_id(business_unit_id)

    def create_business_unit(self, name: str) -> BusinessUnit:
        # SINGLE_TENANT: this database has exactly one Tenant row (created by
        # v006's migration backfill) -- attach every new BU to it.
        tenant = self.db.query(Tenant).first()
        if tenant is None:
            tenant = Tenant(name="Default Tenant", status="active")
            self.db.add(tenant)
            self.db.flush()
        return self.repository.create(BusinessUnit(tenant_id=tenant.tenant_id, name=name, status="active"))
