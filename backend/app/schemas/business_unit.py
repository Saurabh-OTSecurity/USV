import uuid

from pydantic import BaseModel, ConfigDict


class BusinessUnitCreate(BaseModel):
    name: str


class BusinessUnitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    business_unit_id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    status: str
